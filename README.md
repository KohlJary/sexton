# Sexton

**The sexton keeps the building and rings the bell when something needs you.**

Your AI agent has been guessing what `df` says. It has been guessing whether
the service it just "fixed" is actually running the fix. It has been
guessing, confidently and in full sentences, about a machine it could have just
*measured*. Sexton measures it. It does it the same way every time, keeps the
numbers on your machine, and hands any agent you allow a record to read instead
of a vibe to hallucinate from.

```
$ sexton
The sexton rang (Manjaro Linux):
- / is at 83.5%.
- /boot is 97.0% full (0.0 GB left).
- Last completed full upgrade was 386 days ago (2025-11-02).
- That's on Manjaro unstable, where partial upgrades break things fastest.
- Failed user units: offsite-backup.service.
- queue-dm.service is running code older than its checkout: started 2026-11-22T13:33:10,
  last commit 2026-11-23T11:40:53 on main. A fix isn't live until it restarts.
```

That's a real machine, lightly anonymized. Every line was sitting in a log or a
`statvfs` call that nobody, human or agent, was reading. The `/boot` one was
caught about ten minutes before a kernel upgrade would have tried to write a
new initramfs into eighteen megabytes and handed its owner a black screen.

## Why this exists

The industry has two answers for "agents that understand your computer":

1. **Give the agent root.** Then every email it reads, every web page, every
   forum reply is a prompt injection with root on your box. Excellent plan.
   No notes.
2. **Ship your machine's telemetry to someone's cloud,** so their model can
   tell you your disk is full, for a monthly fee, forever.

Sexton is the third option: **a deterministic record, local, read-only, with
consent built in.** The machine gets measured by code, not by vibes, and the
model reads the measurements. Same machine, same reading. It's haruspicy
where the entrails are `/proc` and the readings are reproducible, which is
more than any haruspex ever managed.

## What it reads (v0: tier 0, vitals)

How the machine *is*, never what you're *doing*:

- disk use per real mount
- memory and swap
- load and uptime
- temperatures (hwmon) and battery
- failed systemd units (system and user)
- **stale services**: anything running from a git checkout whose code is newer
  than the process. "Running code ≠ code on disk" is a vital, not a footnote.
  Restart counts too, because a crash loop looks perfectly healthy to `is-active`.
- **the last *completed* full upgrade** (Arch-family): a `-Syu` that died on a
  dependency error doesn't count. That's exactly how a machine goes a year
  without one while everyone assumes it's fine.
- pending updates (optional, needs the network)

The brief only speaks when something's ringing. A line that shows up every
session turns into wallpaper, and agents learn to skip wallpaper.

## Install

```sh
uv tool install git+https://github.com/KohlJary/sexton
sexton                 # the brief
sexton now --json      # every vital
```

The trend store (a sample every 15 minutes, kept 90 days, never leaves the machine):

```sh
cp systemd/sexton-record.* ~/.config/systemd/user/
systemctl --user enable --now sexton-record.timer
sexton trend "disk_used_pct:/" 30     # slope per day, and when it fills at this rate
```

### Claude Code

```
/plugin marketplace add KohlJary/sexton
/plugin install sexton@sexton
```

You get the MCP server (`brief`, `vitals`, `trend`, `metrics`), a `/sexton`
command, and a SessionStart hook that opens your session with the brief, but
only if something's ringing. Any other agent that speaks MCP can use
`sexton mcp` directly. Write your own plug; the server doesn't care whose it is.

## Consent, or: the part that makes this not spyware

"Any agent can see what's going on with your machine" is either a great tool
or a spyware SDK. The only difference is consent, so consent is the
architecture, not a settings page:

| Tier | What | Default |
|---|---|---|
| 0 Vitals | disk, memory, temps, battery, failed and stale units, upgrade state | **on**, read-only *(built)* |
| 1 System | packages, service list, logs (scrubbed) | ask once per agent *(idea)* |
| 2 Activity | processes and their command lines, window titles, recent files | opt-in per agent, expires, visible indicator while read *(idea)* |
| 3 Person | shell and browser history, clipboard, screenshots, messages | **not offered** to third-party agents *(idea)* |
| Hands | doing anything at all | none; one named, confirmed action at a time *(idea)* |

Rules that hold at every tier:

- **Every read is logged.** `sexton access` shows who read what, and when.
- **Enforcement lives in the service, never in a plugin.** A sloppy or hostile
  plug gets what it was granted and not a byte more.
- **Scrub at the sensor**, before any tier sees the data.
- **One-command revoke** per agent. **Nothing leaves the machine.**
- It never reads inside other programs' data (sizes and mtimes only), never
  reads messages or anything decrypted, never acts on its own, and never phones
  home. A new sensor names its tier when it's written, so "vitals" can't
  quietly grow into "everything."

The shape is four questions, answered per agent: what can it see, who's
looking, is there a record of it, and can the owner close it. If any answer
is "unclear," it's off.

## Status

**Built:** tier-0 sensors, the brief, the trend store, the MCP server, the
Claude Code plugin, the stale-service check. 0.0.1, in other words. It has
been run on exactly one machine, and that machine was on fire.

**Next:** the permission broker and per-agent tokens (tiers 1+), session ids in
the access log, last-success-per-backup-job, auth-failure and rate-limit
counts per service, GPU/VRAM holders, port owners, secret-file modes, and
repos registering their own checks.

## Why "Sexton"

In a church, the sexton is the caretaker: keeps the building, tends the
grounds, rings the bell. It doesn't watch the congregation. It looks after
the building and rings when something needs attention. That's tier 0.

---

Built by RoboKohl ⊖, a daemon in Kohl's house, for Kohl ☉ and anyone else
whose agent has been guessing. MIT. The joke is load-bearing.
