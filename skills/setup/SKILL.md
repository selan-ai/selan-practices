---
name: setup
description: Use when a developer wants their repository set up well for Claude Code and does not know where to start, or on a new repository with no CLAUDE.md, no checks and no history of sessions.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/*) Read Grep Glob Edit Write
---

# Set up this repository for Claude Code

What the repository has, from its files:

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/bootstrap.py "${CLAUDE_PROJECT_DIR}"`

Its quality ladder:

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/quality-gates/scripts/gates.py "${CLAUDE_PROJECT_DIR}"`

What its sessions spent, if there are any:

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/context-audit/scripts/digest.py "${CLAUDE_PROJECT_DIR}"`

If the first block says `python3: command not found`, stop and tell the user to install
Python 3 (macOS: `xcode-select --install`; Windows: python.org, then reopen the terminal).

## The reader

Assume the developer has never configured Claude Code. Every item says, in one plain
sentence, what the thing is and why it helps them, before any file name. The glossary at
https://selan.ai/docs/practices#glossary is where to send them for more.

## What you produce

Two turns. This one reads nothing beyond the reports above and the repository's `CLAUDE.md`.

1. **Your repository today**, five lines at most: stack, the checks it has, whether a red
   pipeline blocks a merge, `CLAUDE.md`, how many sessions there are to learn from.
2. **The plan**, five items at most, in this order, skipping what is already in place:
   1. `CLAUDE.md`: none yet, write one under 60 lines from the files (commands that differ
      from the stack's defaults, nothing a reader of the code can see). Over 200 lines, cut
      it (details: `/selan-practices:context-audit`).
   2. Merge enforcement, when the report says OFF: the project setting to turn on.
   3. Any rung CI checks only after merge: move it onto merge requests.
   4. `code-review`, when the repository has none.
   5. `dead-code`, as a suggestion.
   Each item: the plain sentence, the report line it comes from, the files it touches, and
   the `/selan-practices:install <component>` that does it when there is one.
3. **One question**: which numbers to apply, or "all".

In the second turn, apply the picked items: for a component, follow its recipe under
`${CLAUDE_PLUGIN_ROOT}/skills/install/components/`; for `CLAUDE.md`, the rubric in
`${CLAUDE_PLUGIN_ROOT}/skills/context-audit/references/rubric.md`. Run each item's
verification, show the diff, never commit, and end with the commands that ship it.

With fewer than five sessions, close with one line: run `/selan-practices:setup` again in
two weeks, when the sessions can show what to cut and what is missing.
