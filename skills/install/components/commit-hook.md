# commit-hook

A Claude Code hook that runs the fast checks before a session's `git commit` and blocks the
commit when they fail. It only concerns commits made by Claude Code; a developer's own
`git commit` is untouched.

Install it when the quality-gates report shows a fifth or more of commits made with no check
since the last edit. Needs `quiet-check` first.

## The hook script

`.claude/hooks/check-before-commit.sh`:

```sh
#!/bin/sh
# Blocks a Claude Code `git commit` when the fast checks fail; every other command passes at once.
cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0
case "$cmd" in
  *"git commit"*|*"git -C "*" commit"*) ;;
  *) exit 0 ;;
esac
out=$("$CLAUDE_PROJECT_DIR/scripts/check.sh" lint typecheck 2>&1) && exit 0
printf 'Fix these before committing:\n%s\n' "$out" >&2
exit 2
```

Exit 2 is what makes Claude Code block the call and show stderr to the model.

## Settings

Merge into `.claude/settings.json`, keeping any hooks already there:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR/.claude/hooks/check-before-commit.sh\"", "timeout": 120 }] }
    ]
  }
}
```

## Rules

- Fast steps only: lint and typecheck, never the whole test suite. A hook that takes a minute
  gets bypassed; slow suites belong in CI.
- Every other command must pass in milliseconds: the script exits before running anything.

## Verify

Time it: any non-commit command under 50 ms, a commit on a clean tree in a few seconds. A
commit with a type error is blocked with the error shown.
