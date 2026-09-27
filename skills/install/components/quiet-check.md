# quiet-check

One command that runs the repository's fast checks and prints only what failed. Without it a
session runs each check by hand and filters the output after the fact (`tsc | grep -v
node_modules`, `jest | grep Tests:`), which costs calls and hides the failure it filtered.

## The script

`scripts/check.sh`, one step per check, each step silent on success:

```sh
#!/usr/bin/env bash
# The repository's fast checks; prints only failures. `scripts/check.sh <step>` runs one.
set -uo pipefail
status=0
only=" $* "
run() {
  local name=$1; shift
  [ "$only" = "  " ] || [[ "$only" == *" $name "* ]] || return 0
  local out
  if ! out=$("$@" 2>&1); then
    printf '%s FAILED\n%s\n' "$name" "$(printf '%s\n' "$out" | tail -60)"
    status=1
  fi
}
# One `run` line per check the repository has, cheapest first.
run lint npx biome check
run typecheck npx tsc --noEmit
run test npx jest --silent
exit $status
```

Replace the three `run` lines with the repository's own commands, in ladder order (format,
lint, typecheck, build, unit). Go: `gofmt -l` (fails when it prints), `go vet ./...`,
`go test ./...`. Python: `ruff check`, `mypy`, `pytest -q`. Keep a failing step's output
whole enough to act on: show the tail, not a filter that might drop the assertion.

## Steps

1. Take the commands from `package.json`, `Makefile`, `go.mod` or CI, never invent a tool the
   repository does not have.
2. Make each step exit non-zero on failure (gofmt does not: wrap it).
3. Name it in `CLAUDE.md` as the check to run before every commit and push, replacing any
   lines that list the individual commands.

## Verify

On a clean tree it prints nothing and exits 0. With one deliberate failure per step (a type
error, a failing assertion), it prints that step's failure and exits 1, with enough of the
output to see why.
