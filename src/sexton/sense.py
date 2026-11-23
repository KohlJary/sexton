"""Sensors: measure the machine the same way every time.

v0 is tier 0 only (vitals): how the machine is, never what anyone is doing.
No command lines, no window titles, no file names outside system paths.
Every reader takes its root paths as arguments so tests can point it at
fixtures instead of the real /proc and /sys.
"""
import datetime as dt
import os
import re
import shutil
import subprocess
from pathlib import Path

TIER = 0
REAL_FS = {"ext4", "ext3", "ext2", "btrfs", "xfs", "f2fs", "zfs", "ntfs", "ntfs3", "exfat", "vfat"}
SKIP_PREFIX = ("/proc", "/sys", "/dev", "/run", "/snap", "/var/lib/snapd", "/boot/efi")


def disks(mounts="/proc/mounts"):
    out, seen = [], set()
    for line in Path(mounts).read_text().splitlines():
        dev, mnt, fs, *_ = line.split()
        mnt = mnt.replace("\\040", " ")
        if fs not in REAL_FS or mnt.startswith(SKIP_PREFIX) or dev in seen:
            continue
        seen.add(dev)
        try:
            u = shutil.disk_usage(mnt)
        except OSError:
            continue
        out.append({"mount": mnt, "total_gb": round(u.total / 1e9, 1), "free_gb": round(u.free / 1e9, 1),
                    "used_pct": round(100 * (u.total - u.free) / u.total, 1) if u.total else 0.0})
    return out


def memory(meminfo="/proc/meminfo"):
    kv = {}
    for line in Path(meminfo).read_text().splitlines():
        k, v = line.split(":", 1)
        kv[k] = int(v.split()[0])  # kB
    tot, av = kv.get("MemTotal", 0), kv.get("MemAvailable", 0)
    st, sf = kv.get("SwapTotal", 0), kv.get("SwapFree", 0)
    return {"total_gb": round(tot / 1e6, 1), "available_pct": round(100 * av / tot, 1) if tot else 0.0,
            "swap_used_pct": round(100 * (st - sf) / st, 1) if st else 0.0}


def load():
    l1, l5, l15 = os.getloadavg()
    return {"load1": round(l1, 2), "load15": round(l15, 2), "cpus": os.cpu_count()}


def uptime(path="/proc/uptime"):
    return {"days": round(float(Path(path).read_text().split()[0]) / 86400, 1)}


def temps(hwmon="/sys/class/hwmon"):
    out = {}
    for d in sorted(Path(hwmon).glob("hwmon*")):
        try:
            name = (d / "name").read_text().strip()
        except OSError:
            continue
        vals = []
        for t in d.glob("temp*_input"):
            try:
                vals.append(int(t.read_text()) / 1000)
            except (OSError, ValueError):
                pass
        if vals:
            out[name] = max(out.get(name, 0), round(max(vals), 1))
    return out


def battery(ps="/sys/class/power_supply"):
    for b in sorted(Path(ps).glob("BAT*")):
        try:
            return {"pct": int((b / "capacity").read_text()), "status": (b / "status").read_text().strip()}
        except (OSError, ValueError):
            continue
    return None


def failed_units(run=subprocess.run):
    out = {}
    for scope, flag in (("system", []), ("user", ["--user"])):
        try:
            r = run(["systemctl", *flag, "--failed", "--plain", "--no-legend"], capture_output=True, text=True, timeout=10)
            out[scope] = [l.split()[0] for l in r.stdout.splitlines() if l.strip()]
        except (OSError, subprocess.TimeoutExpired):
            out[scope] = None
    return out


_TS = re.compile(r"^\[([^\]]+)\] \[(\w+(?:-\w+)?)\] (.*)$")


def _when(s):
    """pacman.log timestamps: '2026-09-24T20:02:03-0400' (new) or '2019-01-01 12:00' (old). Naive local time."""
    for parse in (dt.datetime.fromisoformat, lambda x: dt.datetime.strptime(x, "%Y-%m-%d %H:%M")):
        try:
            w = parse(s)
        except ValueError:
            continue
        return w.astimezone().replace(tzinfo=None) if w.tzinfo else w
    return None


def upgrades(log="/var/log/pacman.log"):
    """Last *completed* full upgrade (-Syu that reached 'transaction completed'), and last package change.

    A -Syu that aborts (dependency errors, a no at the prompt) doesn't count:
    that's exactly how a machine goes a year without one and nobody notices.
    """
    p = Path(log)
    if not p.exists():
        return None
    full = last_change = None
    in_full = False
    for line in p.read_text(errors="replace").splitlines():
        m = _TS.match(line)
        if not m:
            continue
        ts, src, msg = m.groups()
        if src == "PACMAN" and msg.startswith("Running"):
            in_full = False
        if msg == "starting full system upgrade":
            in_full = True
        elif msg == "transaction completed" and in_full:
            full = ts
        elif src == "ALPM" and msg.startswith(("upgraded ", "installed ", "removed ")):
            last_change = ts
    now = dt.datetime.now()

    def days(ts):
        w = _when(ts) if ts else None
        return round((now - w).total_seconds() / 86400, 1) if w else None
    return {"last_full_upgrade": full, "days_since_full_upgrade": days(full),
            "last_package_change": last_change}


def distro(os_release="/etc/os-release", mirrorlist="/etc/pacman.d/mirrorlist"):
    name = None
    for line in Path(os_release).read_text().splitlines() if Path(os_release).exists() else []:
        if line.startswith("NAME="):
            name = line.split("=", 1)[1].strip('"')
    branch = None
    if Path(mirrorlist).exists():
        m = re.search(r"/manjaro/(stable|testing|unstable)/", Path(mirrorlist).read_text())
        branch = m.group(1) if m else None
    return {"name": name, "branch": branch}


def pending_updates(run=subprocess.run):
    """Needs the network (checkupdates syncs a private copy of the db). None if unavailable."""
    if not shutil.which("checkupdates"):
        return None
    try:
        r = run(["checkupdates"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 2):  # 2 = no updates
        return None
    return len([l for l in r.stdout.splitlines() if l.strip()])


def _git(wd, *args, run=subprocess.run):
    try:
        r = run(["git", "-C", wd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def services(run=subprocess.run):
    """Running services whose code lives in a git checkout: is the process older than its code?

    Daedalus's #1 (2026-11-23): "Running code ≠ code on disk" should be a vital.
    Reads only git metadata of the checkout (commit time, branch), never its files'
    contents, and never a data directory.
    """
    out = []
    for scope, flag in (("user", ["--user"]), ("system", [])):
        try:
            r = run(["systemctl", *flag, "list-units", "--type=service", "--state=active", "--plain", "--no-legend"],
                    capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for unit in (l.split()[0] for l in r.stdout.splitlines() if l.strip()):
            try:
                s = run(["systemctl", *flag, "show", unit, "--timestamp=unix",
                         "-p", "WorkingDirectory,ExecMainStartTimestamp,NRestarts"],
                        capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.TimeoutExpired):
                continue
            p = dict(l.split("=", 1) for l in s.splitlines() if "=" in l)
            wd, started = p.get("WorkingDirectory", ""), p.get("ExecMainStartTimestamp", "")
            if not wd.startswith("/") or not started.startswith("@"):
                continue
            ct = _git(wd, "log", "-1", "--format=%ct", run=run)
            if not ct:
                continue
            start, commit = int(started[1:]), int(ct)
            out.append({"unit": unit, "scope": scope, "dir": wd,
                        "branch": _git(wd, "rev-parse", "--abbrev-ref", "HEAD", run=run),
                        "started": dt.datetime.fromtimestamp(start).isoformat(timespec="seconds"),
                        "code_committed": dt.datetime.fromtimestamp(commit).isoformat(timespec="seconds"),
                        "stale": commit > start, "restarts": int(p.get("NRestarts", "0") or 0)})
    return out


SENSOR = "sexton 0.0.1"
SCHEMA = 1


def vitals(net=False):
    v = {"tier": TIER, "sensor": SENSOR, "schema": SCHEMA, "at": dt.datetime.now().isoformat(timespec="seconds"),
         "services": services(),
         "disks": disks(), "memory": memory(), "load": load(), "uptime": uptime(),
         "temps": temps(), "battery": battery(), "failed_units": failed_units(),
         "upgrades": upgrades(), "distro": distro()}
    if net:
        v["pending_updates"] = pending_updates()
    return v


# --- bells: what the sexton rings for ------------------------------------------

def bells(v, pending=None):
    """Plain-language notices from a vitals record. Deterministic rules, no model."""
    out = []
    for d in v["disks"]:
        if d["used_pct"] >= 90:
            out.append(f"{d['mount']} is {d['used_pct']}% full ({d['free_gb']} GB left).")
        elif d["used_pct"] >= 80:
            out.append(f"{d['mount']} is at {d['used_pct']}%.")
    u = v.get("upgrades") or {}
    days = u.get("days_since_full_upgrade")
    if days is None and u:
        out.append("No completed full system upgrade in the pacman log at all.")
    elif days is not None and days > 30:
        out.append(f"Last completed full upgrade was {days:.0f} days ago ({u['last_full_upgrade'][:10]}).")
        if (v.get("distro") or {}).get("branch") == "unstable":
            out.append("That's on Manjaro unstable, where partial upgrades break things fastest.")
    for scope, units in (v.get("failed_units") or {}).items():
        if units:
            out.append(f"Failed {scope} units: {', '.join(units)}.")
    for s in v.get("services") or []:
        if s["stale"]:
            out.append(f"{s['unit']} is running code older than its checkout: started {s['started']}, "
                       f"last commit {s['code_committed']} on {s['branch']}. A fix isn't live until it restarts.")
        if s["restarts"] >= 3:
            out.append(f"{s['unit']} has restarted {s['restarts']} times: possibly a crash loop.")
    if v["memory"]["available_pct"] < 10:
        out.append(f"Only {v['memory']['available_pct']}% of memory available.")
    hot = {k: t for k, t in (v.get("temps") or {}).items() if t >= 85}
    if hot:
        out.append("Running hot: " + ", ".join(f"{k} {t}°C" for k, t in hot.items()) + ".")
    p = pending if pending is not None else v.get("pending_updates")
    if p and p >= 200:
        out.append(f"{p} updates pending.")
    return out
