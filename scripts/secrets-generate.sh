#!/usr/bin/env bash
# Generate esphome/secrets.yaml from macOS Keychain.
# Run after cloning on a new machine (requires secrets-store.sh to have been run first).
set -euo pipefail

SERVICE="tublemetry-esphome"
OUT="$(dirname "$0")/../esphome/secrets.yaml"

fetch() {
  local account="$1"
  local value
  value=$(security find-generic-password -a "$account" -s "$SERVICE" -w 2>/dev/null) || {
    echo "Error: '$account' not found in Keychain (service: $SERVICE)."
    echo "Run scripts/secrets-store.sh first."
    exit 1
  }
  echo "$value"
}

echo "Reading credentials from Keychain (service: $SERVICE)..."

wifi_ssid=$(fetch wifi_ssid)
wifi_password=$(fetch wifi_password)
api_key=$(fetch api_key)
ota_password=$(fetch ota_password)

cat > "$OUT" <<EOF
wifi_ssid: "$wifi_ssid"
wifi_password: "$wifi_password"
api_key: "$api_key"
ota_password: "$ota_password"
EOF

echo "Written to $OUT"
