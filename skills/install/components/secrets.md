# secrets

gitleaks over each merge request's own commits, blocking. Scanning only the merge request
means a secret already in history cannot block every branch; history is a separate clean-up.

## GitLab

```yaml
# Only the merge request's own commits, so history cannot block every branch.
secrets:
  stage: test
  image:
    name: ghcr.io/gitleaks/gitleaks:v8.28.0
    entrypoint: [""]
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  variables:
    GIT_DEPTH: 0
  script:
    - git config --global --add safe.directory "$CI_PROJECT_DIR"
    - gitleaks git --no-banner --redact --log-opts="$CI_MERGE_REQUEST_DIFF_BASE_SHA..HEAD" .
```

Reuse the runner tags the other jobs use. The image has arm64 builds.

## GitHub

```yaml
name: secrets
on: pull_request
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: |
          docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/gitleaks/gitleaks:v8.28.0 \
            git --no-banner --redact --log-opts="${{ github.event.pull_request.base.sha }}..HEAD" .
```

## Allowlist

Scan the whole tree once. Every hit is either a real secret (stop and tell the user: rotate
it, then remove it) or a fake fixture. Fakes go in `.gitleaks.toml`, by path first, by one
narrow regex only when a fake is spread across many files:

```toml
[extend]
useDefault = true

[[allowlists]]
description = "Test fixtures shaped like real credentials, known to be fake"
paths = ['''^src/.*\.test\.ts$''']
```

Never allowlist a rule, and never a path that holds real configuration.

## Verify

The merge request's own pipeline runs the job and passes. Then prove it catches something:
a realistic token (for example `glpat-` followed by 20 characters) in a non-fixture file of a
scratch branch makes it fail.
