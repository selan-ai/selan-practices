# selan-practices

Find out what Claude Code spends in a repository, and cut it. A [Claude Code](https://claude.com/claude-code)
plugin that reads the repository's own session transcripts on your machine and proposes a
shorter `CLAUDE.md` and a setup that reads less, each change with the numbers behind it.

```
/plugin marketplace add selan-ai/selan-practices
/plugin install selan-practices@selan-practices
```

Then, inside the repository:

```
/selan-practices:context-audit
```

## What it looks at

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
