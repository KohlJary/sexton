"""MCP server: any agent that speaks MCP can read the record.

v0 serves tier 0 (vitals) only, so there's nothing to grant yet: every
tool here is harmless machine health. Every call is still logged with the
client's name, so `tells access` always shows who's been reading. Tiers 1+
arrive with the permission broker, in this process, not in any plugin.
"""
from mcp.server.fastmcp import Context, FastMCP

from . import cli, sense, store

mcp = FastMCP("tells", instructions=(
    "A deterministic record of this machine (tier 0: vitals only). Read it before "
    "guessing about disk, memory, temperatures, failed services or upgrade state. "
    "What it reports is measured; anything you infer from it, say is yours."))


def _who(ctx):
    try:
        ci = ctx.session.client_params.clientInfo
        return f"{ci.name}/{ci.version}"
    except Exception:
        return "unknown-client"


@mcp.tool()
def brief(ctx: Context) -> str:
    """What the machine's record says needs attention right now, in plain language."""
    store.log_access(_who(ctx), "brief")
    return cli.brief()


@mcp.tool()
def vitals(ctx: Context) -> dict:
    """Every tier-0 vital, measured now: disks, memory, load, uptime, temps, battery, failed units, upgrade state, distro."""
    store.log_access(_who(ctx), "vitals")
    return sense.vitals()


@mcp.tool()
def trend(metric: str, ctx: Context, days: int = 30) -> dict:
    """A stored metric over the last N days with its slope per day (see `metrics` for names)."""
    store.log_access(_who(ctx), "trend", f"{metric} {days}")
    return store.trend(metric, days)


@mcp.tool()
def metrics(ctx: Context) -> list[str]:
    """Names of every metric in the local trend store."""
    store.log_access(_who(ctx), "metrics")
    return store.metrics()


def serve():
    mcp.run()
