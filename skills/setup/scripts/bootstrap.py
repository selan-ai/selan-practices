#!/usr/bin/env python3
"""What a repository already has for Claude Code, read from its files alone, so setup works before any session exists.

Usage: python3 bootstrap.py <repo-root>
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home() / ".claude"
LOCKS = {"pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn", "bun.lockb": "bun", "bun.lock": "bun", "package-lock.json": "npm"}
# The package.json scripts a session needs to know about; everything else it can discover when asked.
WANTED = ("test", "lint", "typecheck", "check", "build", "format", "dev", "verify")


def main_checkout(path):
    try:
        common = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return Path(common).parent.resolve()
    except (OSError, subprocess.SubprocessError):
        return path


def stack(root):
    found = []
    if (root / "package.json").is_file():
        pm = next((v for k, v in LOCKS.items() if (root / k).exists()), "npm")
        node = (root / ".nvmrc").read_text().strip() if (root / ".nvmrc").is_file() else None
        found.append(f"node ({pm}{', node ' + node if node else ''})")
    if (root / "go.mod").is_file():
        m = re.search(r"^go (\S+)", (root / "go.mod").read_text(errors="replace"), re.M)
        found.append(f"go{' ' + m.group(1) if m else ''}")
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        found.append("python")
    if (root / "Cargo.toml").is_file():
        found.append("rust")
    return found


def commands(root):
    out = []
    pkg = root / "package.json"
    if pkg.is_file():
        pm = next((v for k, v in LOCKS.items() if (root / k).exists()), "npm")
        try:
            scripts = json.loads(pkg.read_text()).get("scripts") or {}
        except ValueError:
            scripts = {}
        for name, body in scripts.items():
            if name.split(":")[0] in WANTED:
                out.append(f"{pm} run {name}  ->  {body[:90]}")
    mk = root / "Makefile"
    if mk.is_file():
        out += [f"make {t}" for t in re.findall(r"^([\w-]+):", mk.read_text(errors="replace"), re.M)
                if t.split("-")[0] in WANTED]
    out += [f"scripts/{f.name}" for f in sorted((root / "scripts").glob("*.sh"))
            if re.search(r"check|test|lint|verify", f.name)]
    if (root / "go.mod").is_file() and not any("go " in c for c in out):
        out.append("go test ./...  (Go default)")
    return out


def claude_setup(root):
    md = root / "CLAUDE.md"
    settings = root / ".claude" / "settings.json"
    hooks = []
    try:
        hooks = sorted((json.loads(settings.read_text()).get("hooks") or {}).keys())
    except (OSError, ValueError, AttributeError):
        pass
    return {
        "claudeMd": md.read_text(errors="replace").count("\n") if md.is_file() else None,
        "agentsMd": (root / "AGENTS.md").is_file(),
        "rules": len(list((root / ".claude" / "rules").glob("**/*.md"))),
        "skills": sorted(p.parent.name for p in (root / ".claude" / "skills").glob("*/SKILL.md")),
        "agents": sorted(p.stem for p in (root / ".claude" / "agents").glob("*.md")),
        "hooks": hooks,
    }


def ci(root):
    if (root / ".gitlab-ci.yml").is_file():
        return "gitlab"
    if list((root / ".github" / "workflows").glob("*.y*ml")):
        return "github"
    return None


def components(root):
    """Which of /selan-practices:install's components are already in place."""
    def text(*paths):
        return "\n".join(p.read_text(errors="replace") for p in paths if p.is_file())
    ci_text = text(root / ".gitlab-ci.yml", *(root / ".github" / "workflows").glob("*.y*ml"))
    pkg = text(root / "package.json")
    return {
        "code-review": (root / ".claude" / "agents" / "code-review.md").is_file() and bool(re.search(r"code-review|review\.md", ci_text)),
        "dead-code": bool(re.search(r"\bknip\b|cmd/deadcode|\bvulture\b|dead_code", ci_text + pkg)),
    }


def sessions(root):
    encoded = re.sub(r"[/.]", "-", str(root))
    base = HOME / "projects"
    if not base.is_dir():
        return 0
    return sum(len(list(d.glob("*.jsonl"))) for d in base.iterdir() if d.is_dir() and d.name.startswith(encoded))


def behind(path):
    """Commits the checkout lacks from its upstream, as of the last fetch: the report reads files on disk."""
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-list", "--count", "HEAD..@{u}"],
                             capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip()) if out.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0


def main(files):
    root = main_checkout(files)
    c = claude_setup(files)
    n = sessions(root)
    print(f"{files}")
    lag = behind(files)
    if lag:
        print(f"WARNING: this checkout is {lag} commits behind its upstream. Pull first: this report reads the files on disk.")
    print(f"Stack: {', '.join(stack(files)) or 'not recognised'}")
    print(f"Sessions on this machine: {n}{'  (the audits need a few weeks of sessions; setup uses the files alone)' if n < 5 else ''}")
    print(f"CI: {ci(files) or 'none'}")
    print(f"CLAUDE.md: {str(c['claudeMd']) + ' lines' if c['claudeMd'] is not None else 'none'}"
          f"{'; AGENTS.md present' if c['agentsMd'] else ''}")
    print(f".claude/: {c['rules']} rules, skills {c['skills'] or 'none'}, agents {c['agents'] or 'none'}, hooks {c['hooks'] or 'none'}")
    print("Checks a session can run:")
    for cmd in commands(files) or ["none found"]:
        print(f"  {cmd}")
    comp = components(files)
    print(f"Components installed: {', '.join(k for k, v in comp.items() if v) or 'none'}")
    print(f"Components missing: {', '.join(k for k, v in comp.items() if not v) or 'none'}")


if __name__ == "__main__":
    if sys.version_info < (3, 8):
        sys.exit("selan-practices needs Python 3.8 or newer.")
    main(Path(next((a for a in sys.argv[1:] if not a.startswith("--")), os.getcwd())).resolve())
