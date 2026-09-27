#!/usr/bin/env python3
"""Which quality gates a repository has, where each one runs, and whether its sessions pass through them.

Usage: python3 gates.py <repo-root> [--json]
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HOME = Path.home() / ".claude"
# The ladder, cheapest first: a change should clear each rung before it reaches the next.
KINDS = [
    ("format", r"prettier|biome format|gofmt|goimports|ruff format|\bblack\b|--write"),
    ("lint", r"biome (check|lint|ci)|eslint|go vet|golangci|ruff( check)?\b|\blint\b"),
    ("typecheck", r"\btsc\b|typecheck|mypy|pyright|go vet|go build"),
    ("build", r"\bbuild\b"),
    ("unit", r"\bjest\b|vitest|go test|pytest|\btest(:quiet|:coverage)?\b|check\.sh|test\.sh"),
    ("integration", r"integration"),
    ("e2e", r"playwright|\be2e\b"),
    ("budget", r"comment-budget|file-size|size-limit|complexity"),
    ("secrets", r"gitleaks|trufflehog|detect-secrets|secret-scan|scan-secrets"),
    ("review", r"agent-run code-review|claude -p .*review|^review$"),
]
RESERVED = {"workflow", "default", "stages", "variables", "include", "image", "services",
            "before_script", "after_script", "cache", "spec"}
CHECK = re.compile("|".join(p for k, p in KINDS if k in ("lint", "typecheck", "unit", "format")))
COMMIT = re.compile(r"(^|[;&|]\s*)git( -C \S+)? commit\b")
FAILED = re.compile(r"(?:pipeline FAILED|Pipeline failed)[^\n]*?(?:jobs:|:)\s*([\w ,:.-]+)", re.I)


def main_checkout(path):
    """A worktree's sessions belong to its repository, so the audit always reads the main checkout."""
    try:
        common = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return Path(common).parent.resolve()
    except (OSError, subprocess.SubprocessError):
        return path


def kinds_of(text):
    return [k for k, p in KINDS if re.search(p, text, re.I)]


def package_scripts(root):
    try:
        return json.loads((root / "package.json").read_text()).get("scripts") or {}
    except (OSError, ValueError):
        return {}


def expand(text, scripts):
    """`pnpm run build` means whatever package.json says build is: `tsc && tsup` is a typecheck too."""
    return re.sub(r"\b(?:npm|pnpm|yarn)(?: -s)?(?: run)? ([\w:-]+)",
                  lambda m: f"{m.group(0)} {scripts.get(m.group(1), '')}", text)


def ci_jobs(root):
    """GitLab and GitHub jobs, parsed by indentation: enough to name a job, its script and whether it blocks."""
    jobs, scripts = [], package_scripts(root)
    gl = root / ".gitlab-ci.yml"
    if gl.is_file():
        name, body = None, []
        for line in gl.read_text(errors="replace").splitlines() + ["END:"]:
            m = re.match(r"^([A-Za-z][\w-]*):\s*$", line)
            if m or line == "END:":
                if name and name not in RESERVED:
                    text = "\n".join(body)
                    # Everything but the job's plumbing, so a multi-line `- |` script block is read too.
                    script = expand("\n".join(l for l in body if not re.match(
                        r"^\s+(rules|- if:|if:|when:|image:|tags:|stage:|needs:|cache:|artifacts:|variables:|services:|- name:|name:|entrypoint:|#)", l)), scripts)
                    jobs.append({
                        "ci": "gitlab", "name": name,
                        "blocking": not re.search(r"allow_failure:\s*true", text),
                        "manual": bool(re.search(r"when:\s*manual", text)),
                        # A review or secrets job's prompt mentions tests and builds; its name says what it gates.
                        "kinds": [k for k in kinds_of(name) if k in ("review", "secrets")]
                                 or sorted(set(kinds_of(name) + kinds_of(script))),
                    })
                name, body = (m.group(1) if m else None), []
            elif name:
                body.append(line)
    for wf in (root / ".github" / "workflows").glob("*.y*ml"):
        text = wf.read_text(errors="replace")
        for job, body in re.findall(r"^  ([\w-]+):\n((?:    .*\n|\n)*)", text, re.M):
            jobs.append({"ci": "github", "name": job, "blocking": "continue-on-error: true" not in body,
                         "manual": False, "kinds": sorted(set(kinds_of(job) + kinds_of(body)))})
    return [j for j in jobs if not j["manual"]]


def local_gates(root):
    """What runs without anyone asking: Claude Code hooks and git hooks."""
    hooks = []
    for f in (root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"):
        try:
            data = json.loads(f.read_text()).get("hooks") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for event, entries in data.items():
            for e in entries if isinstance(entries, list) else []:
                cmds = " ".join(h.get("command", "") for h in e.get("hooks") or [])
                hooks.append({"where": f"claude {event}", "kinds": kinds_of(cmds), "command": cmds[:100]})
    try:
        hooks_path = subprocess.run(["git", "-C", str(root), "config", "core.hooksPath"],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        hooks_path = ""
    # A committed hooks directory named by core.hooksPath, then the untracked .git/hooks of this clone.
    for d in [root / hooks_path] if hooks_path else [] + [root / ".git" / "hooks"]:
        for f in d.glob("*") if d.is_dir() else []:
            if f.is_file() and not f.name.endswith(".sample"):
                hooks.append({"where": f"git {f.name}", "kinds": kinds_of(f.read_text(errors="replace")), "command": f.name})
    for d in (root / ".husky",):
        for f in d.glob("*") if d.is_dir() else []:
            if f.is_file() and not f.name.startswith("_"):
                hooks.append({"where": f"husky {f.name}", "kinds": kinds_of(f.read_text(errors="replace")), "command": f.name})
    for name in ("lefthook.yml", ".pre-commit-config.yaml"):
        f = root / name
        if f.is_file():
            hooks.append({"where": name, "kinds": kinds_of(f.read_text(errors="replace")), "command": name})
    return hooks


def commands(root):
    """The checks a developer can run: package.json scripts, Makefile targets, scripts/*.sh."""
    found = {}
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            for k, v in (json.loads(pkg.read_text()).get("scripts") or {}).items():
                kinds = sorted(set(kinds_of(k) + kinds_of(v)))
                if kinds:
                    found[f"npm run {k}"] = kinds
        except ValueError:
            pass
    mk = root / "Makefile"
    if mk.is_file():
        for t in re.findall(r"^([\w-]+):", mk.read_text(errors="replace"), re.M):
            if kinds_of(t):
                found[f"make {t}"] = kinds_of(t)
    for f in (root / "scripts").glob("*.sh"):
        if kinds_of(f.name):
            found[f"scripts/{f.name}"] = kinds_of(f.name)
    return found


def sessions(root):
    encoded = re.sub(r"[/.]", "-", str(root))
    for d in (HOME / "projects").iterdir():
        if d.is_dir() and d.name.startswith(encoded):
            yield from d.glob("*.jsonl")


def compliance(root):
    """Commits made with no check since the last edit, --no-verify, CI failures seen, hooks that fired."""
    prefix, parent = str(root) + os.sep, str(root.parent) + os.sep
    n = commits = unchecked = noverify = 0
    ci_failed, hook_blocks, checks_run = Counter(), Counter(), Counter()
    for f in sessions(root):
        in_repo, last_edit, last_check, i = False, -1, -1, 0
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cwd = r.get("cwd") or ""
            in_repo = in_repo or cwd == str(root) or cwd.startswith(prefix)
            c = (r.get("message") or {}).get("content")
            for b in c if isinstance(c, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    i += 1
                    inp = b.get("input") or {}
                    cmd = str(inp.get("command") or "")
                    if re.search(re.escape(parent) + r"(?!" + re.escape(root.name) + r"[/\s'\"])", cmd):
                        continue
                    if b.get("name") in ("Edit", "Write", "MultiEdit") or re.search(r"python3?\s+-\s*<<.*\.(replace|write)\(", cmd, re.S):
                        last_edit = i
                    if b.get("name") == "Bash":
                        if CHECK.search(cmd):
                            last_check = i
                            for k in kinds_of(cmd):
                                checks_run[k] += 1
                        if COMMIT.search(cmd):
                            commits += 1
                            unchecked += last_edit > last_check
                            noverify += "--no-verify" in cmd
                if b.get("type") == "tool_result":
                    t = b.get("content") if isinstance(b.get("content"), str) else json.dumps(b.get("content"))
                    for m in FAILED.finditer(t or ""):
                        for job in re.split(r"[,\s]+", m.group(1).strip()):
                            if job and not job.isdigit() and len(job) > 2:
                                ci_failed[job] += 1
                    if b.get("is_error") and re.search(r"\bhook\b", t or "", re.I):
                        hook_blocks[(t or "").strip().splitlines()[0][:90]] += 1
        n += in_repo
    return {"sessions": n, "commits": commits, "commitsWithoutCheck": unchecked, "noVerify": noverify,
            "checksRun": dict(checks_run), "ciFailedJobs": dict(ci_failed.most_common(8)),
            "hookBlocks": dict(hook_blocks.most_common(5))}


def merge_enforced(root):
    """Whether a red pipeline stops the merge at all: without this, every blocking job is a suggestion."""
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"gitlab\.com[:/](.+?)(?:\.git)?$", url)
    if m:
        try:
            out = subprocess.run(["glab", "api", "projects/" + m.group(1).replace("/", "%2F")],
                                 capture_output=True, text=True, timeout=20).stdout
            return {"host": "gitlab", "pipelineMustSucceed": json.loads(out).get("only_allow_merge_if_pipeline_succeeds")}
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if m:
        try:
            r = subprocess.run(["gh", "api", f"repos/{m.group(1)}/branches/main/protection"],
                               capture_output=True, text=True, timeout=20)
            return {"host": "github", "pipelineMustSucceed": r.returncode == 0 and "required_status_checks" in r.stdout}
        except (OSError, subprocess.SubprocessError):
            return None
    return None


def audit(root, files):
    jobs, hooks, cmds = ci_jobs(files), local_gates(files), commands(files)
    ladder = []
    for kind, _ in KINDS:
        ladder.append({
            "kind": kind,
            "local": [c for c, ks in cmds.items() if kind in ks][:3],
            "hook": [h["where"] for h in hooks if kind in h["kinds"]],
            "ciBlocking": [j["name"] for j in jobs if kind in j["kinds"] and j["blocking"]],
            "ciAdvisory": [j["name"] for j in jobs if kind in j["kinds"] and not j["blocking"]],
        })
    return {"root": str(root), "ladder": ladder, "ciJobs": jobs, "hooks": hooks,
            "mergeEnforced": merge_enforced(files), **compliance(root)}


def print_report(rep):
    print(f"{rep['root']}\n{rep['sessions']} sessions\n")
    print("The ladder (where each rung runs):")
    print(f"  {'rung':<12} {'local command':<34} {'hook':<26} {'CI blocks':<22} CI advisory")
    for r in rep["ladder"]:
        cell = lambda xs, w: (", ".join(xs) or "-")[:w]
        print(f"  {r['kind']:<12} {cell(r['local'], 34):<34} {cell(r['hook'], 26):<26} {cell(r['ciBlocking'], 22):<22} {cell(r['ciAdvisory'], 30)}")
    missing = [r["kind"] for r in rep["ladder"] if not (r["local"] or r["hook"] or r["ciBlocking"] or r["ciAdvisory"])]
    if missing:
        print(f"  nowhere: {', '.join(missing)}")
    me = rep["mergeEnforced"]
    if me is None:
        print("Merge enforcement: unknown (no gitlab/github remote, or no glab/gh login)")
    elif me["pipelineMustSucceed"]:
        print(f"Merge enforcement: a red pipeline blocks the merge ({me['host']})")
    else:
        print(f"Merge enforcement: OFF - a red pipeline does not stop the merge ({me['host']}), so 'CI blocks' blocks nothing")
    print(f"\nCommits: {rep['commits']}, of which {rep['commitsWithoutCheck']} with no lint/typecheck/test run since the last edit; --no-verify: {rep['noVerify']}")
    print(f"Checks run by sessions: {', '.join(f'{k} {v}' for k, v in rep['checksRun'].items()) or 'none'}")
    if rep["ciFailedJobs"]:
        print(f"CI failures the sessions saw, by job: {', '.join(f'{k} {v}' for k, v in rep['ciFailedJobs'].items())}")
    if rep["hookBlocks"]:
        print("Hooks that stopped a tool call:")
        for t, v in rep["hookBlocks"].items():
            print(f"  {v:>4}x  {t}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    # Sessions are keyed by the main checkout; files are read where the skill runs, which is current.
    files = Path(next((a for a in argv if not a.startswith("--")), os.getcwd())).resolve()
    rep = audit(main_checkout(files), files)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
