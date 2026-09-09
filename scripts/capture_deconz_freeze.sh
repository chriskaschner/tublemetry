#!/usr/bin/env bash
# Capture what deCONZ is BLOCKED ON during a freeze.
#
# RUN THIS ON THE HA HOST, not on your laptop -- the deCONZ add-on's ports are
# not exposed to the LAN, so this has to happen inside the container.
#
#   1. Settings > Apps > "Install app" (blue button, BOTTOM RIGHT) > search
#      "Advanced SSH & Web Terminal" > install.
#      NOTE on the UI, confirmed on HA 2026.8.3: "Add-ons" is renamed "Apps"
#      (puzzle-piece icon, "Run extra applications next to Home Assistant"), and
#      the "Add-on Store" is now the "Install app" button. The Apps screen itself
#      lists only what is ALREADY installed, which is why the store looks missing.
#      Pick Advanced SSH specifically -- it ships the docker CLI and tmux, which
#      the plain "Terminal & SSH" add-on may not.
#   2. In its Configuration tab, turn Protection mode OFF. Required for docker
#      access; without it the container is invisible and this script exits with
#      a message saying so.
#   3. Open the Terminal, then run it under tmux so closing the browser tab does
#      not kill a run that may be waiting an hour for a freeze:
#
#        tmux new -s deconz
#        bash capture_deconz_freeze.sh
#
#      Detach with Ctrl-B then D. Reattach later with: tmux attach -t deconz
#
# WHY: as of 2026-09-09 the deCONZ add-on hangs 20-110 min at a time, ~8x/day.
# sensor.deconz_cpu_percent proved it goes QUIET while hung (0.35% frozen vs
# 1.38% healthy, no overlap), which rules out the two published lookalikes -- the
# main-thread spin in phoscon forum 6754 and the FD exhaustion in rest-plugin
# #8603, both of which burn CPU. So deCONZ is BLOCKED on something with a long
# timeout. This script finds out what.
#
# It waits for a freeze, then captures the four things that discriminate between
# the remaining candidates. Freezes average ~8/day, so expect to wait 1-3 hours.
#
# Output: /tmp/deconz-freeze-<timestamp>.txt -- attach it to a bug report.

set -uo pipefail

CONTAINER="addon_core_deconz"
POLL=30
OUT="/tmp/deconz-freeze-$(date +%Y%m%d-%H%M%S).txt"

# In-container exec. deCONZ's image ships curl and lsof; /proc works regardless
# of whether procps is installed, so everything below falls back to /proc.
dex() { docker exec "$CONTAINER" sh -c "$1" 2>&1; }

log() { echo "$*" | tee -a "$OUT"; }

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: container $CONTAINER not found."
  echo "Is Protection mode still ON for the SSH add-on? It must be OFF."
  echo "Containers present:"
  docker ps --format '  {{.Names}}' 2>/dev/null || echo "  (docker unavailable)"
  exit 1
fi

echo "watching $CONTAINER for a freeze; polling every ${POLL}s"
echo "writing to $OUT"
echo "freezes run ~8/day, so this may sit here for a while. Ctrl-C to stop."
echo

# A freeze means the REST API stops answering. That is the same signal HA loses,
# and unlike CPU it needs no HA access from here. 5s timeout: a healthy deCONZ
# answers in milliseconds, so this cannot false-positive on mere slowness.
is_frozen() {
  local code
  code=$(dex "curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:40850/api/config")
  [ "$code" != "200" ]
}

while true; do
  if is_frozen; then
    # Confirm rather than react to a single blip.
    sleep 10
    if ! is_frozen; then
      echo "$(date +%H:%M:%S)  transient, not a freeze"
      sleep "$POLL"; continue
    fi

    log "================================================================"
    log "FREEZE CONFIRMED at $(date -Iseconds)"
    log "================================================================"

    PID=$(dex "pidof deCONZ" | tr -d '\r\n ')
    log ""
    log "deCONZ pid: ${PID:-NOT FOUND}"

    if [ -z "$PID" ]; then
      log "process is GONE -- this is a crash, not a hang. Different problem."
      break
    fi

    # --- T2: file descriptors -------------------------------------------------
    # rest-plugin #8603: a leak to the 1024 limit breaks the REST API. It also
    # breaks the SERIAL layer, because deCONZ selects on fd_set
    # (src/zm_master_com_serial_unix.cpp:411) which silently fails past
    # FD_SETSIZE. Climbing toward 1024 => that family. Flat at 20-40 => refuted.
    log ""
    log "--- T2  file descriptors (leak check; 1024 is the limit) ---"
    log "open fds : $(dex "ls /proc/$PID/fd 2>/dev/null | wc -l")"
    log "fd limit : $(dex "grep 'Max open files' /proc/$PID/limits 2>/dev/null")"
    log ""
    log "fd types (a leak shows as a pile of 'socket'):"
    dex "ls -l /proc/$PID/fd 2>/dev/null | awk '{print \$NF}' | sed 's/\[.*\]//' | sort | uniq -c | sort -rn | head -12" | tee -a "$OUT"

    # --- T3: accept backlog ---------------------------------------------------
    # Recv-Q on a LISTEN socket = completed connections nobody has accept()ed.
    # Non-zero proves the accept loop specifically is not running, which upgrades
    # the "802 accepts drained in 77 bursts of ~3ms" inference to a measurement.
    log ""
    log "--- T3  listen-socket backlog (Recv-Q > 0 = accept loop stalled) ---"
    dex "ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null || cat /proc/net/tcp" | tee -a "$OUT"
    log ""
    log "CLOSE_WAIT count (high = sockets never being closed):"
    dex "ss -tan 2>/dev/null | grep -c CLOSE_WAIT || echo 'ss unavailable'" | tee -a "$OUT"

    # --- T4: what is each thread doing ---------------------------------------
    # THE MOST IMPORTANT SECTION. State R = spinning (already refuted by CPU).
    # State S/D with a wchan naming a syscall tells us exactly what it is blocked
    # on -- futex = lock contention, a socket wait = network, D = uninterruptible
    # disk I/O. This is the question the whole investigation is down to.
    log ""
    log "--- T4  per-thread state and wait channel  <-- THE ANSWER LIVES HERE ---"
    log "state: R=running S=sleeping D=uninterruptible-IO  |  wchan = what it waits on"
    dex "for t in /proc/$PID/task/*; do
           tid=\$(basename \$t)
           st=\$(awk '{print \$3}' \$t/stat 2>/dev/null)
           nm=\$(cat \$t/comm 2>/dev/null)
           wc=\$(cat \$t/wchan 2>/dev/null)
           echo \"  tid=\$tid state=\$st name=\$nm wchan=\${wc:-none}\"
         done" | tee -a "$OUT"

    log ""
    log "--- process totals ---"
    dex "grep -E 'Threads|VmRSS|voluntary_ctxt' /proc/$PID/status" | tee -a "$OUT"

    # Context switches over 5s separate "blocked" from "quietly looping".
    V1=$(dex "grep voluntary_ctxt_switches /proc/$PID/status | awk '{print \$2}'" | tr -d '\r\n ')
    sleep 5
    V2=$(dex "grep voluntary_ctxt_switches /proc/$PID/status | awk '{print \$2}'" | tr -d '\r\n ')
    log ""
    log "voluntary context switches over 5s: $V1 -> $V2"
    log "  unchanged => genuinely parked on one blocking call"
    log "  climbing  => looping on something that keeps returning"

    log ""
    log "================================================================"
    log "captured to $OUT"
    log "================================================================"
    break
  fi
  echo "$(date +%H:%M:%S)  healthy"
  sleep "$POLL"
done
