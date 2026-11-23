"""The trend store: local sqlite, numbers only, 90 days by default.

Nothing here leaves the machine. Every metric is a flat name and a number,
so a trend is just a query.
"""
import datetime as dt
import os
import sqlite3
from pathlib import Path

RETAIN_DAYS = 90


def state_dir():
    d = Path(os.environ.get("SEXTON_STATE") or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "sexton")
    d.mkdir(parents=True, exist_ok=True)
    return d


def connect(path=None):
    db = sqlite3.connect(path or state_dir() / "sexton.db")
    db.execute("create table if not exists samples (ts text, metric text, value real)")
    db.execute("create index if not exists samples_m on samples (metric, ts)")
    return db


def flatten(v):
    m = {}
    for d in v["disks"]:
        m[f"disk_used_pct:{d['mount']}"] = d["used_pct"]
        m[f"disk_free_gb:{d['mount']}"] = d["free_gb"]
    m["mem_available_pct"] = v["memory"]["available_pct"]
    m["swap_used_pct"] = v["memory"]["swap_used_pct"]
    m["load1"] = v["load"]["load1"]
    for k, t in (v.get("temps") or {}).items():
        m[f"temp_c:{k}"] = t
    if v.get("battery"):
        m["battery_pct"] = v["battery"]["pct"]
    u = v.get("upgrades") or {}
    if u.get("days_since_full_upgrade") is not None:
        m["days_since_full_upgrade"] = u["days_since_full_upgrade"]
    fu = v.get("failed_units") or {}
    m["failed_units"] = sum(len(x or []) for x in fu.values())
    if v.get("pending_updates") is not None:
        m["pending_updates"] = v["pending_updates"]
    return m


def record(v, db=None):
    db = db or connect()
    ts = v["at"]
    db.executemany("insert into samples values (?,?,?)", [(ts, k, float(x)) for k, x in flatten(v).items()])
    cutoff = (dt.datetime.fromisoformat(ts) - dt.timedelta(days=RETAIN_DAYS)).isoformat()
    db.execute("delete from samples where ts < ?", (cutoff,))
    db.commit()
    return db


def metrics(db=None):
    db = db or connect()
    return [r[0] for r in db.execute("select distinct metric from samples order by metric")]


def latest(metric, db=None):
    db = db or connect()
    r = db.execute("select ts, value from samples where metric=? order by ts desc limit 1", (metric,)).fetchone()
    return r


def trend(metric, days=30, db=None, now=None):
    """Samples over the window, plus a least-squares slope per day. For disk metrics,
    also when the disk fills at that rate. A projection, labelled as one."""
    db = db or connect()
    now = now or dt.datetime.now()
    since = (now - dt.timedelta(days=days)).isoformat()
    rows = db.execute("select ts, value from samples where metric=? and ts>=? order by ts", (metric, since)).fetchall()
    out = {"metric": metric, "days": days, "n": len(rows), "first": rows[0] if rows else None,
           "last": rows[-1] if rows else None, "slope_per_day": None, "projection": None}
    if len(rows) >= 2:
        t0 = dt.datetime.fromisoformat(rows[0][0])
        xs = [(dt.datetime.fromisoformat(t) - t0).total_seconds() / 86400 for t, _ in rows]
        ys = [y for _, y in rows]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            s = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
            out["slope_per_day"] = round(s, 4)
            if metric.startswith("disk_used_pct:") and s > 0:
                out["projection"] = f"full in about {round((100 - ys[-1]) / s)} days at this rate (projection, not a promise)"
    return out


def log_access(client, tool, args=""):
    """Every read through MCP leaves a line the owner can read: who, when, what."""
    with open(state_dir() / "access.log", "a") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{client}\t{tool}\t{args}\n")
