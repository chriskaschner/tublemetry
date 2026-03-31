"""
Heating rate analysis: queries HA recorder DB to correlate
heat-up time with outdoor temp and delta degrees.

Usage:
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db --plot
    uv run scripts/analyze_heating.py --db /path/to/home-assistant_v2.db --csv out.csv

The HA recorder DB is typically at:
    /config/home-assistant_v2.db  (on HA OS, accessible via Samba share or SSH)
"""

import argparse
import sqlite3
from datetime import datetime, timezone

import pandas as pd


HELPERS = {
    "timestamp":    "input_number.hot_tub_last_command_timestamp",
    "start_temp":   "input_number.hot_tub_last_command_start_temp",
    "target_temp":  "input_number.hot_tub_last_command_target_temp",
    "outdoor_temp": "input_number.hot_tub_last_command_outdoor_temp",
    "duration":     "input_number.hot_tub_last_heating_duration",
}


def load_helper_history(db_path: str) -> pd.DataFrame:
    """
    Pull state change history for all helpers and pivot into one row per event.
    Each 'event' is identified by the timestamp helper changing.
    """
    con = sqlite3.connect(db_path)

    entity_list = ", ".join(f"'{v}'" for v in HELPERS.values())
    query = f"""
        SELECT
            s.entity_id,
            s.state,
            s.last_updated_ts
        FROM states s
        JOIN states_meta sm ON s.metadata_id = sm.metadata_id
        WHERE sm.entity_id IN ({entity_list})
          AND s.state NOT IN ('unknown', 'unavailable', '')
        ORDER BY s.last_updated_ts
    """
    df = pd.read_sql_query(query, con)
    con.close()

    df["last_updated_ts"] = pd.to_datetime(df["last_updated_ts"], unit="s", utc=True)
    df["state"] = pd.to_numeric(df["state"], errors="coerce")
    df = df.dropna(subset=["state"])

    # Reverse-map entity_id to field name
    reverse = {v: k for k, v in HELPERS.items()}
    df["field"] = df["entity_id"].map(reverse)

    # Pivot: group by rounded timestamp windows
    # Each event fires all 4 helpers within a few seconds of each other.
    # Use the command timestamp value itself as the event key.
    ts_changes = df[df["field"] == "timestamp"].copy()
    ts_changes = ts_changes.rename(columns={"state": "command_ts", "last_updated_ts": "recorded_at"})
    ts_changes = ts_changes[["command_ts", "recorded_at"]].reset_index(drop=True)

    rows = []
    for _, ev in ts_changes.iterrows():
        cmd_ts = ev["command_ts"]
        rec_at = ev["recorded_at"]
        window_start = rec_at - pd.Timedelta(seconds=10)
        window_end   = rec_at + pd.Timedelta(seconds=10)

        # Find values for the other helpers recorded in the same ~20s window
        nearby = df[
            (df["last_updated_ts"] >= window_start) &
            (df["last_updated_ts"] <= window_end)
        ]

        def get(field):
            rows_ = nearby[nearby["field"] == field]["state"]
            return rows_.iloc[0] if not rows_.empty else None

        # Duration recorded separately (fires when heating completes)
        # Find the next duration change after this command
        future_duration = df[
            (df["field"] == "duration") &
            (df["last_updated_ts"] > rec_at)
        ]
        duration = future_duration["state"].iloc[0] if not future_duration.empty else None

        rows.append({
            "command_time": datetime.fromtimestamp(cmd_ts, tz=timezone.utc).astimezone(),
            "start_temp":   get("start_temp"),
            "target_temp":  get("target_temp"),
            "outdoor_temp": get("outdoor_temp"),
            "duration_min": duration,
        })

    events = pd.DataFrame(rows)
    events["delta_deg"] = events["target_temp"] - events["start_temp"]
    events["deg_per_min"] = events["delta_deg"] / events["duration_min"]
    return events


def print_summary(df: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"Heating events: {len(df)}  |  with duration: {df['duration_min'].notna().sum()}")
    print(f"{'='*60}")
    complete = df.dropna(subset=["duration_min"])
    if complete.empty:
        print("No completed heating events yet.")
        return
    print(complete[[
        "command_time", "start_temp", "target_temp", "delta_deg",
        "outdoor_temp", "duration_min", "deg_per_min"
    ]].to_string(index=False, float_format="{:.1f}".format))
    print(f"\nAverage heating rate: {complete['deg_per_min'].mean():.3f} deg/min")
    print(f"Correlation (outdoor temp vs duration): "
          f"{complete[['outdoor_temp','duration_min']].corr().iloc[0,1]:.3f}")


def plot_results(df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    complete = df.dropna(subset=["duration_min", "outdoor_temp"])
    if complete.empty:
        print("No completed events to plot.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].scatter(complete["outdoor_temp"], complete["duration_min"],
                    c=complete["delta_deg"], cmap="YlOrRd", s=80, edgecolors="k", linewidths=0.5)
    axes[0].set_xlabel("Outdoor Temp (°F)")
    axes[0].set_ylabel("Heat-up Time (min)")
    axes[0].set_title("Heat-up Time vs Outdoor Temp\n(color = delta degrees)")
    plt.colorbar(axes[0].collections[0], ax=axes[0], label="Delta °F")

    axes[1].scatter(complete["delta_deg"], complete["duration_min"],
                    c=complete["outdoor_temp"], cmap="coolwarm", s=80, edgecolors="k", linewidths=0.5)
    axes[1].set_xlabel("Delta Degrees (°F)")
    axes[1].set_ylabel("Heat-up Time (min)")
    axes[1].set_title("Heat-up Time vs Delta Degrees\n(color = outdoor temp)")
    plt.colorbar(axes[1].collections[0], ax=axes[1], label="Outdoor °F")

    plt.tight_layout()
    plt.savefig("heating_analysis.png", dpi=150)
    print("Plot saved to heating_analysis.png")
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Analyze hot tub heating rate data from HA recorder")
    parser.add_argument("--db", required=True, help="Path to home-assistant_v2.db")
    parser.add_argument("--csv", help="Export events to CSV file")
    parser.add_argument("--plot", action="store_true", help="Generate scatter plots")
    args = parser.parse_args()

    df = load_helper_history(args.db)
    print_summary(df)

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\nExported to {args.csv}")

    if args.plot:
        plot_results(df)


if __name__ == "__main__":
    main()
