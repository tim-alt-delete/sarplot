import subprocess
import json
import pandas as pd

def get_cpu_stats():

    # 1) Run sadf to get JSON for the desired time window (aggregate CPU only)
    cmd = ["sadf", "-j", "/var/log/sa/sa04", "--", "-s", "08:00:00", "-e", "10:30:00", "-u"]
    raw = subprocess.check_output(cmd, text=True)

    # 2) Load JSON
    data = json.loads(raw)

    # 3) Extract the 'statistics' array for the first host
    host = data["sysstat"]["hosts"][0]
    stats = host.get("statistics", [])

    # remove empty {}
    # [{..},{..},{}]
    stats_filtered = [d for d in stats if d] 

    # 4) Normalize JSON -> flat table
    #    This flattens 'cpu-load' entries and keeps timestamp fields alongside
    df = pd.json_normalize(
        stats_filtered,
        record_path=["cpu-load"],
        meta=[["timestamp", "date"],
            ["timestamp", "time"],
            ["timestamp", "utc"],
            ["timestamp", "interval"]],
        errors="ignore"
    )

    # 5) Filter to aggregate CPU ("all") and build a proper timestamp
    df = df[df["cpu"] == "all"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp.date"] + " " + df["timestamp.time"])
    df.rename(columns={
        "user": "%user",
        "nice": "%nice",
        "system": "%system",
        "iowait": "%iowait",
        "steal": "%steal",
        "idle": "%idle",
        "timestamp.interval": "interval_seconds",
        "timestamp.utc": "utc_flag",
        "cpu": "CPU"
    }, inplace=True)

    # (Optional) order columns and add %busy
    cols = ["timestamp", "CPU", "%user", "%nice", "%system", "%iowait", "%steal", "%idle",
            "interval_seconds", "utc_flag"]
    df = df[cols]
    df["%busy"] = 100 - df["%idle"]

    return df