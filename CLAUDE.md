# selan-practices

A Claude Code plugin. What it does is in `README.md`; this file is what the code will not tell you.

## Commands

```sh
python3 skills/context-audit/scripts/digest.py <repo>     # the context report, as the skill sees it
python3 skills/skill-audit/scripts/skills.py <repo>       # the skill report
claude plugin validate .claude-plugin/plugin.json          # manifests and every SKILL.md
cd <repo> && claude -p "/selan-practices:<skill>" --plugin-dir <this checkout> --model sonnet --output-format json
```

The last one is the real test: it runs the skill as a user would, including the `!` injection.
`num_turns` and `total_cost_usd` in its JSON are what a change to a `SKILL.md` is judged on.

## Rules

- **Scripts are standard-library Python 3.** Node is not on `PATH` for everyone (nvm loads only
  in an interactive shell), and a dependency is one more thing to install before a skill works.
- **A script lives beside the skill that runs it** and is executed, never read: `SKILL.md`
  injects its output with `` !`python3 ${CLAUDE_SKILL_DIR}/scripts/…` `` and grants exactly
  that command in `allowed-tools`.
- **A skill proposes in the first turn and writes in the second.** Writing a full diff up
  front took 92 turns and $4.28 on a large repository.
- **Every proposal is a report line.** A finding the script cannot show is not added to a
  `SKILL.md` table; add the detector to the script first.
- **Resolve a worktree to its main checkout** (`git rev-parse --git-common-dir`), or the
  report sees only that worktree's sessions.
- **A call into a sibling repository is that repository's habit.** Count it under "elsewhere",
  never under this one's habits, or a Go repository gets a Node fix.

## Releasing

Bump `version` in both `.claude-plugin/plugin.json` and `marketplace.json`, then
`gh release create vX.Y.Z`. `docs/` is gitignored on purpose: specs stay local.
