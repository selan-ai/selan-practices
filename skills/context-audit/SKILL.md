---
name: context-audit
description: Use when Claude Code sessions in a repository cost too many tokens or tool calls, when CLAUDE.md is missing, long or stale, or when asked to tune a repository's Claude Code setup (.claude/settings.json, rules, read limits).
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/digest.py *) Read Grep Glob
---

# Context audit

What this repository's own sessions spent, from its transcripts on this machine:

!`python3 ${CLAUDE_SKILL_DIR}/scripts/digest.py "${CLAUDE_PROJECT_DIR}"`

If the report above is empty or says 0 sessions, say so and stop: there is no evidence to
act on, and a CLAUDE.md written without it costs more than it saves.

## What you produce

Two turns. This first one is cheap: the digest above plus a look at `CLAUDE.md` and
`.claude/settings.json`, nothing else read.

1. **Where it goes**, three lines at most: the biggest cost and the second, in tokens.
2. **Proposals, largest saving first.** Each one is four lines:
   - the change, in one sentence;
   - the digest line it comes from, quoted;
   - the saving, as tokens or calls over the period the digest covers;
   - the file it touches.
3. **One question**: which numbers to apply.

In the second turn, after the user picks, read what those items need, write them, and show
the diff. Never commit.

Anything the digest shows once is not a proposal. Anything it does not show at all is not
one either, however good an idea it is. A new script is proposed only to replace a command
and its filter; searching, reading and editing already have tools.

## Which finding leads to which proposal

| Digest line | Proposal |
| --- | --- |
| Loaded into every request | Cut `CLAUDE.md` to under 200 lines by [the rubric](references/rubric.md). State each section's tokens × requests, and move or delete the costly ones that one kind of task needs. |
| Calls naming a sibling repository | One line at the top of `CLAUDE.md`: work in another repository starts a session there, where its own `CLAUDE.md` loads. Lead with this when it is a fifth of calls or more. |
| Output cut down after the fact | A script that prints only what the filter kept, named in `CLAUDE.md`, replacing the command. |
| Paths in CLAUDE.md that do not exist | Fix or delete each line. |
| Images read, over 50 | Measure in code, read a clipped screenshot only to show someone. |
| Edit through a script, over 50, and Edit/Write hooks listed | Edit with Edit/Write, which those hooks see. With no hooks listed, nothing is skipped: no proposal. |
| PATH exported inline, over 50 | A `SessionStart` hook that writes PATH to `$CLAUDE_ENV_FILE`, for the runtime this repository itself uses. |
| Over a cap, 20 reads or more | `env.CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` in `.claude/settings.json`. Under 20, say the cap would change nothing here. |
| Already-loaded files read | Say so; one line in `CLAUDE.md` is enough. |
| Generated files read | `permissions.deny` `Read(./path/**)` for those paths. |

When the agent reads through Bash (`read a file` far above `Reads`), a Read cap or Read hook
changes nothing: say so rather than proposing one.

## What a new or cut CLAUDE.md contains

Commands that differ from the stack's default, quiet form first; rules the transcripts show
were needed more than once, each with its reason; traps already hit. Nothing a reader of the
code can see: no directory map, no dependency list, no architecture summary. Check each line
against [the rubric](references/rubric.md) before proposing it.

With no `CLAUDE.md` yet, the proposal is under 60 lines.
