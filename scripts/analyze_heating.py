"""
Heating rate analysis: queries HA recorder DB directly from raw state history.

Derives heating events from setpoint changes — no helpers required.
For each event where setpoint > water temp (heating needed), records:
  - start time, start water temp, target setpoint, outdoor temp at start
  - time to reach setpoint (within tolerance), heating rate (deg/min)

Usage:
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db --csv out.csv
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db --plot

The HA recorder DB is typically at:
    /config/home-assistant_v2.db  (on HA OS, accessible via Samba share or SSH)
    ~/config/home-assistant_v2.db (on HA Container)

To copy from HA OS:
    scp homeassistant@homeassistant.local:/config/home-assistant_v2.db ./ha.db
"""

import argparse
import sqlite3
from datetime import datetime, timezone

import pandas as pd

ENTITIES = {
    "water_temp":    "sensor.tublemetry_hot_tub_temperature",
    "setpoint":      "number.tublemetry_hot_tub_setpoint",
    "outdoor_temp":  "sensor.outdoor_temperature",
    "heater":        "binary_sensor.tublemetry_hot_tub_heater",
}

# Tolerance: how close water temp needs to get to setpoint to count as "reached"
REACHED_TOLERANCE_F = 1.0

# Ignore heating events shorter than this (probably setpoint noise)
MIN_DURATION_MIN = 2.0

# Ignore heating events longer than this (probably interrupted / tub used mid-heat)
MAX_DURATION_MIN = 240.0


def load_entity_history(db_path: str, entity_id: str) -> pd.Series:
    """Load full state history for one entity as a time-indexed Series."""
    con = sqlite3.connect(db_path)
    query = """
        SELECT s.state, s.last_updated_ts
        FROM states s
        JOIN states_meta sm ON s.metadata_id = sm.metadata_id
        WHERE sm.entity_id = ?
          AND s.state NOT IN ('unknown', 'unavailable', '')
        ORDER BY s.last_updated_ts
    """
    df = pd.read_sql_query(query, con, params=(entity_id,))
    con.close()

    df["ts"] = pd.to_datetime(df["last_updated_ts"], unit="s", utc=True)
    df["value"] = pd.to_numeric(df["state"], errors="coerce")
    df = df.dropna(subset=["value"]).set_index("ts")["value"]
    return df


def resample_to_common(series_dict: dict, freq="1min") -> pd.DataFrame:
    """
    Resample all series to a common 1-minute grid using forward-fill.
    Returns a DataFrame with one column per entity key.
    """
    frames = {}
    for key, s in series_dict.items():
        frames[key] = s.resample(freq).last().ffill()
    df = pd.DataFrame(frames).dropna()
    return df


def extract_heating_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find heating events: moments where setpoint increases above water temp.
    For each event, record start conditions and time to reach setpoint.
    """
    events = []

    # Detect setpoint changes
    setpoint_changes = df["setpoint"].diff().fillna(0)
    change_idx = df.index[setpoint_changes > 0]

    for start_time in change_idx:
        row = df.loc[start_time]
        target = row["setpoint"]
        start_temp = row["water_temp"]

        # Only care about heating (setpoint raised above current temp)
        if target <= start_temp + REACHED_TOLERANCE_F:
            continue

        outdoor = row.get("outdoor_temp", float("nan"))

        # Find when water temp reaches target
        future = df.loc[start_time:]
        reached = future[future["water_temp"] >= target - REACHED_TOLERANCE_F]

        if reached.empty:
            # Never reached — still heating or interrupted
            duration_min = None
            deg_per_min = None
        else:
            end_time = reached.index[0]
            duration_min = (end_time - start_time).total_seconds() / 60.0
            delta = target - start_temp
            deg_per_min = delta / duration_min if duration_min > 0 else None

            # Filter implausible durations
            if duration_min < MIN_DURATION_MIN or duration_min > MAX_DURATION_MIN:
                duration_min = None
                deg_per_min = None

        events.append({
            "start_time":   start_time.astimezone(),
            "start_temp":   round(start_temp, 1),
            "target_temp":  round(target, 1),
            "delta_deg":    round(target - start_temp, 1),
            "outdoor_temp": round(outdoor, 1) if pd.notna(outdoor) else None,
            "duration_min": round(duration_min, 1) if duration_min is not None else None,
            "deg_per_min":  round(deg_per_min, 4) if deg_per_min is not None else None,
        })

    return pd.DataFrame(events)


def print_summary(df: pd.DataFrame) -> None:
    print(f"\n{'='*70}")
    print(f"Heating events found: {len(df)}  |  completed: {df['duration_min'].notna().sum()}")
    print(f"{'='*70}")

    complete = df.dropna(subset=["duration_min"])
    if complete.empty:
        print("No completed heating events yet.")
        print("Either not enough data has been collected, or setpoint was never")
        print("raised while the tub was below temperature.")
        return

    print(complete[[
        "start_time", "start_temp", "target_temp", "delta_deg",
        "outdoor_temp", "duration_min", "deg_per_min"
    ]].to_string(index=False, float_format="{:.1f}".format))

    print(f"\nAverage heating rate:  {complete['deg_per_min'].mean():.4f} deg/min")
    print(f"                       {60 / complete['deg_per_min'].mean():.1f} min/deg")

    if complete["outdoor_temp"].notna().sum() >= 3:
        corr = complete[["outdoor_temp", "duration_min"]].dropna().corr().iloc[0, 1]
        print(f"Outdoor temp correlation with duration: {corr:.3f}")
        print("  (negative = colder outside → longer heat-up, as expected)")

    # Rough preheat estimator
    print(f"\n{'─'*70}")
    print("Preheat time estimates (at average rate):")
    avg_rate = complete["deg_per_min"].mean()
    for delta in [2, 4, 6, 8, 10]:
        mins = delta / avg_rate
        print(f"  {delta}°F raise → ~{mins:.0f} min ({mins/60:.1f}h)")


def plot_results(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    complete = df.dropna(subset=["duration_min", "outdoor_temp"])
    if complete.empty:
        print("No completed events to plot.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    sc1 = axes[0].scatter(
        complete["outdoor_temp"], complete["duration_min"],
        c=complete["delta_deg"], cmap="YlOrRd", s=80, edgecolors="k", linewidths=0.5
    )
    axes[0].set_xlabel("Outdoor Temp (°F)")
    axes[0].set_ylabel("Heat-up Time (min)")
    axes[0].set_title("Heat-up Time vs Outdoor Temp\n(color = delta °F)")
    plt.colorbar(sc1, ax=axes[0], label="Delta °F")

    sc2 = axes[1].scatter(
        complete["delta_deg"], complete["duration_min"],
        c=complete["outdoor_temp"], cmap="coolwarm", s=80, edgecolors="k", linewidths=0.5
    )
    axes[1].set_xlabel("Delta Degrees (°F)")
    axes[1].set_ylabel("Heat-up Time (min)")
    axes[1].set_title("Heat-up Time vs Delta Degrees\n(color = outdoor °F)")
    plt.colorbar(sc2, ax=axes[1], label="Outdoor °F")

    plt.tight_layout()
    plt.savefig("heating_analysis.png", dpi=150)
    print("Plot saved to heating_analysis.png")
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze hot tub heating rate from HA recorder DB"
    )
    parser.add_argument("--db", required=True, help="Path to home-assistant_v2.db")
    parser.add_argument("--csv", help="Export events to CSV")
    parser.add_argument("--plot", action="store_true", help="Generate scatter plots")
    args = parser.parse_args()

    print("Loading entity history...")
    series = {}
    for key, entity_id in ENTITIES.items():
        s = load_entity_history(args.db, entity_id)
        print(f"  {key}: {len(s)} data points ({entity_id})")
        if s.empty:
            print(f"  WARNING: no data for {entity_id} — check entity ID")
        series[key] = s

    print("Resampling to 1-minute grid...")
    df = resample_to_common(series)
    print(f"  {len(df)} minutes of data ({df.index.min()} → {df.index.max()})")

    print("Extracting heating events...")
    events = extract_heating_events(df)

    print_summary(events)

    if args.csv:
        events.to_csv(args.csv, index=False)
        print(f"\nExported to {args.csv}")

    if args.plot:
        plot_results(events)


if __name__ == "__main__":
    main()
