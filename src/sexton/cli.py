"""sexton: a deterministic record of your machine, for you and for any agent you let read it.

  sexton               the brief: what the record says needs attention
  sexton now [--json]  every tier-0 vital, measured now
  sexton record [--net]  measure and store a sample (the timer runs this); --net also counts pending updates
  sexton trend METRIC [DAYS]   a metric over time, with its slope
  sexton metrics       what's stored
  sexton access        who has read the record, when, and what
  sexton mcp           run the MCP server (stdio)
  sexton hook          Claude Code SessionStart hook: the brief, only if something's ringing

Tier 0 only in v0: how the machine is, never what you're doing.
"""
import json
import sys

from . import sense, store


def brief(v=None):
    v = v or sense.vitals()
    p = store.latest("pending_updates")
    notes = sense.bells(v, pending=int(p[1]) if p else None)
    host = (v.get("distro") or {}).get("name") or "this machine"
    if not notes:
        return f"The sexton has nothing to ring for on {host}."
    return f"The sexton rang ({host}):\n" + "\n".join(f"- {n}" for n in notes)


def hook(stdin=sys.stdin):
    """SessionStart hook: inject the brief only when something's ringing.
    A line that shows up every session becomes wallpaper; agents learn to skip it."""
    try:
        json.load(stdin)
    except ValueError:
        pass
    v = sense.vitals()
    p = store.latest("pending_updates")
    if not sense.bells(v, pending=int(p[1]) if p else None):
        return 0
    store.log_access("claude-code-hook", "brief")
    json.dump({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": brief(v)}}, sys.stdout)
    return 0


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
        print("\n".join(store.metrics()) or "nothing recorded yet: run `sexton record`")
    elif cmd == "access":
        p = store.state_dir() / "access.log"
        print(p.read_text() if p.exists() else "No agent has read the record yet.")
    elif cmd == "hook":
        return hook()
    elif cmd == "mcp":
        from .mcp_server import serve
        serve()
    else:
        print((__doc__ or "").strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
