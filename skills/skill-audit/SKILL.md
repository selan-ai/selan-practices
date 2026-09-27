---
name: skill-audit
description: Use when a repository's skills or agents seem unused, ignored, duplicated, shadowed or failing, when the agent keeps redoing work by hand or writing throwaway scripts, or when deciding what should become a skill.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/skills.py *) Read Grep Glob
---

# Skill audit

The skills and agents this repository's sessions had, used, tripped over and worked around,
from its transcripts on this machine:

!`python3 ${CLAUDE_SKILL_DIR}/scripts/skills.py "${CLAUDE_PROJECT_DIR}"`

If the report says 0 sessions, say so and stop.

## What you produce

Two turns. This first one reads nothing beyond the report above.

1. **The state**, three lines at most: how many skills are used, worked around, broken.
2. **Proposals, most sessions affected first.** Each one is four lines:
   - the change, in one sentence;
   - the report line it comes from, quoted;
   - the sessions or calls it affects;
   - the file it touches.
3. **One question**: which numbers to apply.

In the second turn, after the user picks, read what those items need, write them, and show
the diff. Never commit, and never delete a user-level or plugin skill yourself: say what to
remove and let the user do it.

## Which finding leads to which proposal

| Report line | Proposal |
| --- | --- |
| Same name in more than one place | Only one runs. Rename or merge the other, keeping whichever holds the scripts the sessions needed. |
| Also shipped by a plugin | Remove the user-level copy; the plugin's is the maintained one. |
| Called but not there | Create it, or remove whatever names it: grep `CLAUDE.md`, `.claude/`, and the other skills for the name. |
| Built-in failed, `re-invoked itself` | The skill runs forked and was called again from inside itself. Say so; the fix is in how it is invoked, not in this repository. |
| `around` above `used`, 5 sessions or more | The description does not match how people ask. Rewrite it with the words of the requests that should have triggered it, or add the step the sessions kept doing by hand. |
| `used` 0 and `around` 0, project skill or agent | Unused over the period: propose removing it. |
| `used` 0 and `around` 0, user or plugin skill | Say it is unused here, nothing more: it may serve every other repository. |
| Scripts written to /tmp in 3 sessions or more | A missing skill. In the second turn, read two of those scripts from the transcripts and propose one skill with one bundled script that covers them. |

A skill with a bundled script beats one with prose: propose the script whenever the sessions
ran the same commands in the same order.
