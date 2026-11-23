---
description: Ask the sexton how the machine is: what's ringing, and why
argument-hint: [a metric to trend, or nothing for the brief]
---
Call the sexton's `brief` tool. If `$ARGUMENTS` names a metric, call `trend`
with it (use `metrics` to find the exact name).

Report what's ringing in plain words, most urgent first, and for each one
the one command that would fix it. What the record says is measured; what
you infer from it is yours, so say which is which. Anything that changes the
system (deleting, restarting, upgrading) is the user's to run: hand them the
command, don't run it yourself. If something needs sudo, give it as a
terminal command, never as a `!` command, because sudo can't ask for a
password there.

If nothing's ringing, say so in one line and stop.
