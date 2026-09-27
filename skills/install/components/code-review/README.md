# code-review

An agent that reviews every merge request and writes `review.md`: a severity table, one block
per finding, a concrete fix for each. The practice, and the reason behind every line of these
files, is https://selan.ai/docs/agents/code-review . Read it before changing a file here.

## Files

| File | Goes to |
| --- | --- |
| `code-review.md` | `.claude/agents/code-review.md` |
| `gitlab-review.yml` | merged into `.gitlab-ci.yml` (GitLab) |
| `review-to-codequality.mjs` | `scripts/review-to-codequality.mjs` (GitLab only) |
| `github-review.yml` | `.github/workflows/review.yml` (GitHub) |

## Steps

1. Copy `code-review.md`. Keep it short: Claude Code loads `CLAUDE.md` itself, so the house
   style is not repeated in the brief. Add one line naming what this repository treats as
   Critical, taken from its `CLAUDE.md`, if it has one.
2. Add the pipeline for the repository's CI host. On GitLab, add the `workflow:` block only if
   the file has none; if one exists, check it already creates merge request pipelines.
3. The job is advisory (`allow_failure: true` / `continue-on-error: true`) and stays that way:
   a model's opinion must not block a merge.
4. Credential. The job runs `selan agent-run`, which needs a Selan CLI token in `SELAN_TOKEN`,
   masked and protected. Without Selan, replace `selan agent-run code-review "<prompt>"` with
   `claude -p --agent code-review --dangerously-skip-permissions "<prompt>"` and set
   `ANTHROPIC_API_KEY` instead. Tell the user which variable to create and where; never ask
   for its value and never write it to a file.
5. If `.claude/rules/*.md` exist, add to the brief: "Before reviewing, Read every
   `.claude/rules/*.md` whose `paths:` match a file in the diff." Path rules load only on Read,
   and the reviewer reads the diff through `git diff`.

## Verify

Open the merge request that adds these files: its own pipeline runs the review on itself.
It passes when `review.md` exists with the counts table; on GitLab the findings appear in the
merge request's Reports tab.
