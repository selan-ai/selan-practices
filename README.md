# selan-practices

Find out what Claude Code spends in a repository, and cut it. A [Claude Code](https://claude.com/claude-code)
plugin that reads the repository's own session transcripts on your machine and proposes a
shorter `CLAUDE.md` and a setup that reads less, each change with the numbers behind it.

```
/plugin marketplace add selan-ai/selan-practices
/plugin install selan-practices@selan-practices
```

Then, inside the repository, start here:

```
/selan-practices:setup            what the repository has, and a plan in plain words
```

It works on a new repository with no history, from the files alone. It recommends what to
install, one component at a time:

```
/selan-practices:install code-review   an agent that reviews every merge request
/selan-practices:install dead-code     knip, deadcode, vulture or clippy, by stack
```

The code review component is the practice documented at
https://selan.ai/docs/agents/code-review : that page explains every line, the plugin ships
the files.

Once there are a few weeks of sessions, the audits show what to cut and what is missing:

```
/selan-practices:context-audit    what every request pays for, and how to cut it
/selan-practices:skill-audit      which skills are used, ignored, shadowed or missing
/selan-practices:quality-gates    what "done" means here, and where each check runs
```

## Quality gates

Draws the repository's quality ladder, cheapest rung first: format, lint, typecheck, build,
unit, integration, e2e, budget, secrets, review. For each rung it shows where the check runs:
a local command someone has to remember, a hook, an advisory CI job, or a CI job that blocks
the merge. From the transcripts it counts commits made with no check since the last edit and
the CI failures sessions ran into, then proposes the gaps worth closing: a rung that runs only
on the default branch, a rung with only a local command, a missing secret scan.

## Skill audit

Lists the skills and agents a session has (project, user, plugin), then checks the
transcripts for which ones ran, which failed, and which were worked around: sessions that
ran a skill's own commands without calling it. It also flags two skills with the same name,
where only one ever runs, and throwaway scripts written to `/tmp` in session after session,
which usually means a skill is missing.

## Context audit

`CLAUDE.md` is sent with every request, so its size times your request count is often the
largest single cost. The audit also counts work done in another repository from this one,
command output filtered after the fact (`tsc | grep -v node_modules`), large and generated
files read, and paths `CLAUDE.md` names that no longer exist.

It proposes; it does not write. Pick the items you want and it writes those, and never commits.

## Why not generate a CLAUDE.md

A generated context file made agents slightly worse and about 20% more expensive
([ETH Zurich](https://arxiv.org/pdf/2601.20404)). What helps is what the code cannot tell the
agent, and your transcripts are where that shows up.

## Privacy

Transcripts are read locally by `scripts/digest.py`, standard-library Python 3. Nothing is
sent anywhere.

## Requirements

Python 3 (`python3` on your `PATH`).

## License

MIT
