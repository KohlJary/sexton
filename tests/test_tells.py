import datetime as dt

from tells import sense, store

LOG = """\
[2025-10-23T12:00:00-0400] [PACMAN] Running 'pacman -Syu'
[2025-10-23T12:00:01-0400] [PACMAN] starting full system upgrade
[2025-10-23T12:05:00-0400] [ALPM] transaction started
[2025-10-23T12:07:34-0400] [ALPM] upgraded systemd (257.9-1 -> 257.10-1)
[2025-10-23T12:08:00-0400] [ALPM] transaction completed
[2026-09-24T20:02:06-0400] [PACMAN] Running 'pacman -Syu --ignore audit'
[2026-09-24T20:02:07-0400] [PACMAN] starting full system upgrade
[2026-10-12T21:48:17-0400] [PACMAN] Running 'pacman -S discord'
[2026-10-12T21:48:19-0400] [ALPM] transaction started
[2026-10-12T21:48:20-0400] [ALPM] upgraded discord (1:0.0.124-1 -> 1:1.0.159-1)
[2026-10-12T21:48:21-0400] [ALPM] transaction completed
"""


def test_an_aborted_syu_is_not_an_upgrade(tmp_path):
    # The real failure: -Syu that dies on dependencies, then one-off -S installs
    # that complete. Only the Oct 2025 run counts as a full upgrade.
    p = tmp_path / "pacman.log"
    p.write_text(LOG)
    u = sense.upgrades(p)
    assert u["last_full_upgrade"].startswith("2025-10-23")
    assert u["last_package_change"].startswith("2026-10-12")
    assert u["days_since_full_upgrade"] > 300


def test_tells_names_the_weekend():
    v = {"disks": [{"mount": "/", "used_pct": 83.0, "free_gb": 597.0, "total_gb": 3500.0}],
         "memory": {"available_pct": 40.0, "swap_used_pct": 0.0},
         "upgrades": {"last_full_upgrade": "2025-10-23T12:08:00-0400", "days_since_full_upgrade": 396.0},
         "distro": {"name": "Manjaro Linux", "branch": "unstable"},
         "failed_units": {"system": [], "user": ["robokohl-queue-dm.service"]}, "temps": {"k10temp": 70.0}}
    t = sense.tells(v)
    assert any("/ is at 83.0%" in x for x in t)
    assert any("396 days ago (2025-10-23)" in x for x in t)
    assert any("Manjaro unstable" in x for x in t)
    assert any("robokohl-queue-dm.service" in x for x in t)


def test_quiet_machine_says_nothing():
    v = {"disks": [{"mount": "/", "used_pct": 40.0, "free_gb": 900.0, "total_gb": 1500.0}],
         "memory": {"available_pct": 60.0, "swap_used_pct": 0.0},
         "upgrades": {"last_full_upgrade": "x", "days_since_full_upgrade": 3.0},
         "distro": {}, "failed_units": {"system": [], "user": []}, "temps": {}}
    assert sense.tells(v) == []


def test_mounts_skip_pseudo_and_duplicates(tmp_path):
    m = tmp_path / "mounts"
    m.write_text("/dev/a / ext4 rw 0 0\nproc /proc proc rw 0 0\n/dev/a /home ext4 rw 0 0\n"
                 "/dev/loop0 /var/lib/snapd/snap/x squashfs ro 0 0\n")
    assert [d["mount"] for d in sense.disks(m)] == ["/"]


def test_trend_slope_and_projection(tmp_path):
    db = store.connect(tmp_path / "t.db")
    t0 = dt.datetime(2026, 11, 1)
    for i in range(10):
        db.execute("insert into samples values (?,?,?)", ((t0 + dt.timedelta(days=i)).isoformat(), "disk_used_pct:/", 80 + i))
    tr = store.trend("disk_used_pct:/", 30, db=db, now=t0 + dt.timedelta(days=10))
    assert tr["slope_per_day"] == 1.0
    assert "full in about 11 days" in tr["projection"]


def test_record_flattens_and_keeps_90_days(tmp_path, monkeypatch):
    monkeypatch.setenv("TELLS_STATE", str(tmp_path))
    db = store.connect(tmp_path / "t.db")
    old = {"at": "2026-01-01T00:00:00", "disks": [{"mount": "/", "used_pct": 50.0, "free_gb": 1.0}],
           "memory": {"available_pct": 50.0, "swap_used_pct": 0.0}, "load": {"load1": 1.0}}
    store.record(old, db)
    new = dict(old, at="2026-11-23T00:00:00")
    store.record(new, db)
    assert db.execute("select count(*) from samples where ts like '2026-01%'").fetchone()[0] == 0
    assert "disk_used_pct:/" in store.metrics(db)


def test_stale_service_is_a_vital():
    import subprocess

    def fake(cmd, **kw):
        out = ""
        if "list-units" in cmd:
            out = "queue-dm.service loaded active running x\n" if "--user" in cmd else ""
        elif "show" in cmd:
            out = "WorkingDirectory=/home/k/robokohl\nExecMainStartTimestamp=@1000\nNRestarts=0\n"
        elif "%ct" in " ".join(cmd):
            out = "2000\n"
        elif "--abbrev-ref" in cmd:
            out = "main\n"
        return subprocess.CompletedProcess(cmd, 0, out, "")
    s = sense.services(run=fake)
    assert s and s[0]["stale"] and s[0]["branch"] == "main"
    v = {"disks": [], "memory": {"available_pct": 50.0}, "services": s}
    assert any("A fix isn't live until it restarts" in t for t in sense.tells(v))
