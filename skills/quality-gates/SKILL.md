---
name: quality-gates
description: Use when it is unclear what "done" means in a repository - which checks exist, which ones block a merge, which the agent skips before committing - or when CI keeps catching what a local check would have, or a merge request can merge with nothing checked.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/gates.py *) Read Grep Glob
---

# Quality gates

The ladder this repository has, where each rung runs, and how its sessions pass through it:

!`python3 ${CLAUDE_SKILL_DIR}/scripts/gates.py "${CLAUDE_PROJECT_DIR}"`

A rung is a kind of check, cheapest first: format, lint, typecheck, build, unit, integration,
e2e, budget, secrets, review. It can run in four places, weakest to strongest: a local command
someone has to remember, a hook that runs on its own, a CI job that is advisory, a CI job that
blocks the merge.

## What you produce

Two turns. This first one reads the report plus `.gitlab-ci.yml` (or the workflows) and
`.claude/settings.json`, nothing else.

1. **The ladder as it is**, one table: rung, local command, hook, CI blocking, CI advisory.
   This table is the answer to "what does quality mean here"; keep it exact.
2. **The gaps, most consequential first.** Each one is four lines:
   - the gap, in one sentence;
   - the report line it comes from, quoted;
   - what it lets through, concretely;
   - the change and the file it touches.
3. **One question**: which numbers to apply.

In the second turn, after the user picks, make those changes, run the new or changed gate once
to prove it passes on the current tree, and show the diff. Never commit.

## Which finding leads to which proposal

| Report line | Proposal |
| --- | --- |
| A rung CI runs only on the default branch, none on merge requests | A blocking MR job for it: the merge is the gate, not the deploy. |
| lint, typecheck, build or unit with no blocking CI job | Add it to the blocking test job. |
| A rung with only a local command | A blocking CI job; a local command alone is a suggestion. |
| Commits with no check since the last edit, a fifth or more | A `PreToolUse` hook on `Bash(git commit*)` that runs the quiet check and blocks on failure. Name the quiet check; if there is none, propose it first. |
| CI failures the sessions saw, on a rung that has a local command | Name that command in `CLAUDE.md` as the step before every push. |
| `--no-verify` above 0 | Find what it skipped and why; a hook people bypass is a hook to fix, not a rule to repeat. |
| `secrets: nowhere` on a repository that handles credentials | A secret scan in CI. |
| review only advisory | Leave it: a model's opinion does not block. Say so. |
| `nowhere` for integration or e2e in a repository with no such tests | Nothing to add; say which rungs do not apply. |

A gate must be fast enough to run every time, or it will be skipped: propose the quiet form
that prints only failures, and put slow suites in CI rather than in a commit hook.
