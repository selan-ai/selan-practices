---
name: install
description: Use when adding a quality component to a repository - code review on merge requests, or dead code detection - in whatever language the repository uses.
disable-model-invocation: true
argument-hint: "code-review | dead-code"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/bootstrap.py *) Read Grep Glob Edit Write
---

# Install a component

Requested: **$ARGUMENTS**

The repository as it is:

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/bootstrap.py "${CLAUDE_PROJECT_DIR}"`

## Components

| Component | Recipe | What it adds |
| --- | --- | --- |
| `code-review` | [components/code-review/README.md](components/code-review/README.md) | An agent that reviews every merge request and writes a severity table with a fix per finding. The practice is https://selan.ai/docs/agents/code-review |
| `dead-code` | [components/dead-code.md](components/dead-code.md) | knip, deadcode, vulture or clippy, whichever the stack needs, locally and in CI |

If nothing was requested, or the name is not in the table, list the table with what the
report above says is installed or missing, and ask which one. If it is already installed,
say so and stop.

## How

1. Read the component's recipe, then the repository's `CLAUDE.md` and CI file. Follow the
   repository's own conventions (runner tags, images, package manager) over the recipe's
   defaults.
2. Say in three lines what you will add and where, then add it. Copy the recipe's files as
   they are; the reasons for each line are in the recipe or the page it links.
3. Run the recipe's Verify step and show the result.
4. Show the diff. Never commit. End with the two commands that ship it: the branch and commit,
   and opening the merge request.

A component that needs a secret (code review's token) never gets the value: name the CI
variable to create, where, and with which flags (masked, protected).
