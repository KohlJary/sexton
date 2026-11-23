"""tells: a deterministic record of your machine, for you and for any agent you let read it.

  tells               the brief: what the record says needs attention
  tells now [--json]  every tier-0 vital, measured now
  tells record [--net]  measure and store a sample (the timer runs this); --net also counts pending updates
  tells trend METRIC [DAYS]   a metric over time, with its slope
  tells metrics       what's stored
  tells access        who has read the record, when, and what
  tells mcp           run the MCP server (stdio)

Tier 0 only in v0: how the machine is, never what you're doing.
"""
import json
import sys

from . import sense, store


def brief(v=None):
    v = v or sense.vitals()
    p = store.latest("pending_updates")
    notes = sense.tells(v, pending=int(p[1]) if p else None)
    host = (v.get("distro") or {}).get("name") or "this machine"
    if not notes:
        return f"{host}: nothing in the record needs you."
    return f"{host}, per the record:\n" + "\n".join(f"- {n}" for n in notes)


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    cmd, rest = (a[0], a[1:]) if a else ("brief", [])
    if cmd in ("-h", "--help", "help"):
        print((__doc__ or "").strip())
    elif cmd == "brief":
        print(brief())
    elif cmd == "now":
        v = sense.vitals()
        print(json.dumps(v, indent=2) if "--json" in rest else brief(v) + "\n\n" + json.dumps(v, indent=2))
    elif cmd == "record":
        v = sense.vitals(net="--net" in rest)
        store.record(v)
        print(f"recorded {len(store.flatten(v))} metrics at {v['at']}")
    elif cmd == "trend" and rest:
        print(json.dumps(store.trend(rest[0], int(rest[1]) if len(rest) > 1 else 30), indent=2))
    elif cmd == "metrics":
        print("\n".join(store.metrics()) or "nothing recorded yet: run `tells record`")
    elif cmd == "access":
        p = store.state_dir() / "access.log"
        print(p.read_text() if p.exists() else "No agent has read the record yet.")
    elif cmd == "mcp":
        from .mcp_server import serve
        serve()
    else:
        print((__doc__ or "").strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
