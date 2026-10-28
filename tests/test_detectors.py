"""The report lines the skills turn into proposals: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"
sys.path[:0] = [str(SKILLS / "quality-gates" / "scripts"), str(SKILLS / "context-audit" / "scripts")]

import digest  # noqa: E402
import friction  # noqa: E402
import gates  # noqa: E402


def bash(id_, command, cwd):
    return {"type": "assistant", "cwd": cwd, "message": {"id": f"m{id_}", "content": [
        {"type": "tool_use", "id": f"t{id_}", "name": "Bash", "input": {"command": command}}]}}


def result(id_, text, cwd, error=True):
    return {"type": "user", "cwd": cwd, "message": {"content": [
        {"type": "tool_result", "tool_use_id": f"t{id_}", "is_error": error, "content": text}]}}


class Sandbox(unittest.TestCase):
    """A home directory with one repository and its transcripts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / "repo"
        self.root.mkdir()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self):
        os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def transcript(self, records):
        d = self.home / ".claude" / "projects" / str(self.root).replace("/", "-").replace(".", "-")
        d.mkdir(parents=True, exist_ok=True)
        f = d / "s.jsonl"
        f.write_text("\n".join(json.dumps(r) for r in records))
        return f


class Failures(Sandbox):
    def test_counts_rules_type_errors_and_format_from_failed_checks_in_this_repository(self):
        here, there = str(self.root), str(self.home / "other")
        biome = "src/a.ts:1:1 lint/complexity/useOptionalChain FIXABLE\nsrc/b.ts:2:1 lint/complexity/useOptionalChain\n" \
                "src/c.ts Formatter would have printed the following content:"
        self.transcript([
            bash(1, "npx biome check src", here), result(1, biome, here),
            bash(2, "npx tsc --noEmit", here), result(2, "Exit code 2\nsrc/a.ts(3,5): error TS2345: no", here, error=False),
            # Printing an old log is not a check, and work in another repository is not this one's.
            bash(3, "cat lint.log", here), result(3, "lint/style/useConst", here),
            bash(4, "npx biome check", there), result(4, "lint/style/useConst", there),
            # A check that passed taught nothing.
            bash(5, "npx biome check", here), result(5, "lint/style/noVar", here, error=False),
        ])
        lint, types, codes, fmt = friction.failures(self.root, lambda cmd, cwd: cwd != here)
        self.assertEqual(dict(lint), {("biome", "complexity/useOptionalChain"): 2})
        self.assertEqual(dict(types), {"typescript": 1})
        self.assertEqual(dict(codes), {("typescript", "TS2345"): 1})
        self.assertEqual(dict(fmt), {"biome": 1})


class LongFiles(Sandbox):
    def test_counts_tracked_source_over_the_limit_and_leaves_generated_code_out(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "big.ts").write_text("x\n\n" * 601)
        (self.root / "src" / "short.ts").write_text("x\n" * 10)
        (self.root / "src" / "types.d.ts").write_text("x\n" * 900)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        self.assertEqual(friction.long_files(self.root), {
            "TypeScript / JavaScript": {"files": 2, "over": [{"file": "src/big.ts", "lines": 601}]}})

    def test_finds_a_file_length_rule_in_the_lint_config(self):
        (self.root / "biome.json").write_text('{"style": {"noExcessiveLinesPerFile": "error"}}')
        (self.root / ".swiftlint.yml").write_text("file_length:\n  error: 600\n")
        self.assertEqual(friction.length_rules(self.root),
                         ["biome.json (noExcessiveLinesPerFile)", ".swiftlint.yml (file_length)"])

    def test_a_blocking_ci_step_that_checks_file_length_is_the_rule(self):
        (self.root / ".gitlab-ci.yml").write_text(
            "test:\n  script:\n    # check-file-size.sh comes later\n    - go test ./...\n"
            "go:\n  script:\n    - go run ./tools/filecheck .\n"
            "size:\n  allow_failure: true\n  script:\n    - ./scripts/check-file-size.sh\n")
        jobs = gates.ci_jobs(self.root)
        self.assertEqual(friction.friction(self.root, self.root, lambda *_: False, [], jobs)["lengthRules"],
                         ["./tools/filecheck in blocking CI job go"])
        self.assertEqual([j["name"] for j in jobs if "budget" in j["kinds"]], ["go", "size"])


class GoBuild(Sandbox):
    def test_go_vet_over_the_module_is_the_build_rung_and_says_so(self):
        (self.root / ".gitlab-ci.yml").write_text(
            "test:\n  script:\n    - go vet ./...\n    - go test ./... -race\n"
            "lint:\n  script:\n    - go vet ./internal/...\n"
            "build:\n  script:\n    - go vet ./...\n    - go build ./...\n")
        jobs = {j["name"]: j for j in gates.ci_jobs(self.root)}
        self.assertIn("build", jobs["test"]["kinds"])
        self.assertEqual(jobs["test"]["compiles"], "go vet ./...")
        self.assertNotIn("build", jobs["lint"]["kinds"])
        self.assertEqual(jobs["build"]["compiles"], "")


class CiComments(Sandbox):
    def test_a_comment_above_the_next_job_is_not_the_previous_jobs_script(self):
        (self.root / ".gitlab-ci.yml").write_text(
            "deploy:\n  variables:\n    KEY: abc # gitleaks:allow\n  script:\n    - ./deploy.sh\n"
            "\n# gitleaks over the merge request's commits; e2e runs nightly\n"
            "secrets:\n  script:\n    - gitleaks git\n")
        jobs = {j["name"]: j for j in gates.ci_jobs(self.root)}
        self.assertEqual(jobs["deploy"]["kinds"], [])
        self.assertEqual(jobs["secrets"]["kinds"], ["secrets"])

    def test_golangci_complexity_linters_are_the_budget_and_says_so(self):
        (self.root / ".golangci.yml").write_text(
            "linters:\n  enable:\n    - gocognit # cognitive complexity 20\n    - funlen\n    - lll\n"
            "  settings:\n    gocyclo:\n      min-complexity: 10\n")
        (self.root / ".gitlab-ci.yml").write_text("lint:\n  script:\n    - golangci-lint run ./...\n")
        lint = gates.ci_jobs(self.root)[0]
        self.assertIn("budget", lint["kinds"])
        self.assertEqual(lint["golangciBudget"], "gocognit funlen")


class SubdirectoryScripts(Sandbox):
    def test_npm_after_cd_or_with_prefix_reads_that_directorys_package_json(self):
        (self.root / "package.json").write_text('{"scripts": {"test": "jest"}}')
        (self.root / "fake").mkdir()
        (self.root / "fake" / "package.json").write_text('{"scripts": {"test": "tsc && node --test test/"}}')
        (self.root / ".gitlab-ci.yml").write_text(
            "test:\n  script:\n    - cd fake\n    - npm ci\n    - npm test\n"
            "prefix:\n  script:\n    - npm --prefix fake test\n"
            "back:\n  script:\n    - cd fake && cd ..\n    - npm test\n")
        jobs = {j["name"]: j for j in gates.ci_jobs(self.root)}
        self.assertIn("typecheck", jobs["test"]["kinds"])
        self.assertEqual(jobs["test"]["followed"], ["`npm test` in fake/ is its package.json's `tsc && node --test test/`"])
        self.assertIn("typecheck", jobs["prefix"]["kinds"])
        self.assertNotIn("typecheck", jobs["back"]["kinds"])
        self.assertEqual(jobs["back"]["followed"], [])


class ShellSetup(unittest.TestCase):
    def test_splits_the_setup_in_front_of_a_command_and_writes_home_one_way(self):
        home = digest.HOME_DIR
        cmd = f'cd src && export PATH="{home}/.nvm/versions/node/v26.8.2/bin:$PATH" && unset GIT_DIR; npm test'
        self.assertEqual(digest.shell_setup(cmd), ["export PATH=$HOME/.nvm/versions/node/v26.8.2/bin:$PATH", "unset GIT_DIR"])
        self.assertEqual(digest.shell_setup("export PATH=~/bin:$PATH && make"), ["export PATH=$HOME/bin:$PATH"])
        self.assertEqual(digest.shell_setup("npm test && export X=1"), [])


class Refusals(Sandbox):
    def test_counts_blocked_sleep_and_worktree_refusals(self):
        here = str(self.root)
        f = self.transcript([
            bash(1, "sleep 60", here),
            result(1, "<tool_use_error>Blocked: sleep 60 followed by: cat x. To wait for a condition, use Monitor", here),
            bash(2, "cd /elsewhere && ls", here),
            result(2, "This agent is isolated in the worktree at /tmp/wt and cannot cd outside it", here),
            bash(3, "npm test", here), result(3, "<tool_use_error>Blocked: fmt.Errorf( by a hook", here),
        ])
        s = digest.session(self.root, f)
        self.assertEqual(s["blocked"], {"sleep": 1})
        self.assertEqual(s["worktreeRefused"], 1)


class InstructionFiles(Sandbox):
    def test_agents_md_counts_only_where_there_is_no_claude_md(self):
        (self.root / "AGENTS.md").write_text("a\n")
        self.assertEqual(digest.instruction_files(self.root), [self.root / "AGENTS.md"])
        (self.root / "CLAUDE.md").write_text("c\n")
        self.assertEqual(digest.instruction_files(self.root), [self.root / "CLAUDE.md"])


if __name__ == "__main__":
    unittest.main()
