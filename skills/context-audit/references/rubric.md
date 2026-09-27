# Rubric: what goes where

## Contents
- Where each kind of rule lives
- Keep in CLAUDE.md
- Move out of CLAUDE.md
- Delete
- Settings: caps, deny, hooks
- Sources

## Where each kind of rule lives

| Content | Home | Loaded |
| --- | --- | --- |
| Commands, conventions, traps every session needs | `CLAUDE.md` | every request |
| A rule for one directory or file type | `.claude/rules/<topic>.md` with `paths:` | when a matching file is read |
| A multi-step procedure (deploy, migrate, release) | a skill | when invoked or relevant |
| Something that must never happen | `permissions.deny` or a `PreToolUse` hook | enforced, costs nothing |
| Formatting and style | the linter or formatter config | never |
| Personal preferences | `CLAUDE.local.md`, `~/.claude/CLAUDE.md` | that person only |

A line in `CLAUDE.md` is paid for on every request of every session. Everything else is paid
for only when used, so the default answer for a new rule is "not in `CLAUDE.md`".

## Keep in CLAUDE.md

1. **Commands that are not the stack's default**, in a code fence, copy-pasteable: setup,
   test, lint, typecheck, deploy. The quiet form first: one that prints only failures.
2. **Rules given more than once**, each with a one-line reason. A rule with its reason
   generalises; a bare rule is dropped under pressure.
3. **Traps already hit**: a failure that is silent, and the command or check that shows it.
4. **Where something non-obvious lives**: generated files and their source, the one file
   that owns a concept. One line each, not a map.

Test for every line: could you tell from the agent's output whether it followed it?

## Move out of CLAUDE.md

- A section longer than ~15 lines that one kind of task needs: a skill.
- A section about one directory: `.claude/rules/` with `paths:`.
- A "never do X" that a tool can check: `permissions.deny`, a hook, or a lint rule.
- Background and history ("why we moved off X in 2025"): `docs/`, linked in one line.

## Delete

- Anything inferable from the code: directory tours, dependency lists, framework basics.
  Architecture overviews did not help agents find files, and cost 20% more.
- Personality and generic advice: "you are a senior engineer", "write clean code".
- Paths that no longer exist, and hand-maintained counts (tests, lines, files).
- One of two rules that contradict each other; the model otherwise picks arbitrarily.
- A rule the transcripts show was never needed.

## Settings: caps, deny, hooks

All in the committed `.claude/settings.json`, reviewed in a merge request like code.

- **Read cap**: `env.CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`. Past the cap, Read returns the
  first page and tells the agent the file's length and to Grep or page. Propose it only when
  the digest shows reads over the cap; if the agent reads through Bash, a cap changes nothing.
- **Deny generated files**: `permissions.deny: ["Read(./dist/**)", …]`. Applies to Read, to
  Grep and Glob on that path, and to `cat`/`head`/`sed` naming it. Only for paths the digest
  shows being read, or that are generated and large.
- **Hooks**: only where a cheaper form failed: a file paged through repeatedly, or an
  already-loaded file read again.
- **Quiet scripts** are not settings but belong here: when the digest shows
  `<cmd> | grep …` or `<cmd> | tail -1` recurring, the filter is the script's job.

## Sources

- Anthropic, memory and CLAUDE.md: https://code.claude.com/docs/en/memory
- Anthropic, tool output limits: https://code.claude.com/docs/en/tools-reference
- ETH Zurich, AGENTbench (generated context files cost more and help less): https://arxiv.org/pdf/2601.20404
- Instruction adherence factorial study (size and layout alone had no effect): https://arxiv.org/abs/2605.10039
- Spotify, context engineering for coding agents: https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2
