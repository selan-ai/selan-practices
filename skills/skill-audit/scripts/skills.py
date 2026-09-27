#!/usr/bin/env python3
"""Which skills and agents this repository's sessions have, use, trip over, or work around.

Usage: python3 skills.py <repo-root> [--json]
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home() / ".claude"
# Commands too common to say anything about which skill a session needed.
GENERIC = re.compile(r"^(cd|ls|cat|echo|sed|grep|rg|head|tail|find|git (status|diff|log|add|show)|npm (test|install)|npx tsc)\b")
CLI = re.compile(r"^(git|glab|gh|gcloud|npm|npx|pnpm|node|python3?|go|curl|psql|docker|make|claude|selan|\./|scripts/|bash|sh)\b")


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


def frontmatter(path):
    text = path.read_text(errors="replace")
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            if v:
                fm[k.strip()] = v.strip().strip("'\"")
    return fm, text


def signatures(text, script_names):
    """The commands a skill exists to run: seeing them without the skill means it was worked around."""
    found = set()
    for cmd in re.findall(r"`([^`\n]{4,120})`", text) + re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.S):
        for line in cmd.splitlines():
            words = line.strip().lstrip("$ ").split()
            # Three literal words, so `npm run` or `curl` alone never counts as this skill's.
            if len(words) >= 3 and CLI.match(words[0]) and not GENERIC.match(" ".join(words)) \
                    and not re.match(r"^[-<$\"'{(]", words[2]):
                found.add(" ".join(words[:3]))
    return found | set(script_names)


def installed(root):
    """Skills and agents by bare name, from the project, the user and every installed plugin."""
    items = []

    def add(kind, scope, path, name=None, plugin=None):
        fm, text = frontmatter(path)
        bare = fm.get("name") or name or path.stem
        scripts = [p.name for p in path.parent.rglob("*") if p.suffix in (".sh", ".py", ".mjs", ".js")] if kind == "skill" and path.name == "SKILL.md" else []
        items.append({
            "kind": kind, "scope": scope, "name": bare, "plugin": plugin,
            "id": f"{plugin}:{bare}" if plugin else bare, "path": str(path),
            "description": fm.get("description", ""),
            "manual": fm.get("disable-model-invocation") == "true",
            "signatures": sorted(signatures(text, scripts)) if kind == "skill" else [],
        })

    for scope, base in (("project", root / ".claude"), ("user", HOME)):
        for f in (base / "skills").glob("*/SKILL.md"):
            add("skill", scope, f, name=f.parent.name)
        for f in (base / "commands").glob("*.md"):
            add("skill", scope, f)
        for f in (base / "agents").glob("*.md"):
            add("agent", scope, f)
    try:
        plugins = json.loads((HOME / "plugins" / "installed_plugins.json").read_text()).get("plugins") or {}
    except (OSError, ValueError):
        plugins = {}
    for key, installs in plugins.items():
        plugin = key.split("@")[0]
        for inst in installs if isinstance(installs, list) else []:
            base = Path(inst.get("installPath") or "")
            for f in (base / "skills").glob("*/SKILL.md"):
                add("skill", "plugin", f, name=f.parent.name, plugin=plugin)
            for f in (base / "agents").glob("*.md"):
                add("agent", "plugin", f, plugin=plugin)
    return items


def sessions(root):
    encoded = re.sub(r"[/.]", "-", str(root))
    for d in (HOME / "projects").iterdir():
        if d.is_dir() and d.name.startswith(encoded):
            yield from d.rglob("*.jsonl")


def bare(name):
    """`.claude/worktrees/x:qa-prod` and `qa-prod` are one skill seen from two directories."""
    return (name or "").rsplit(":", 1)[-1] if (name or "").startswith((".", "/")) else (name or "")


def usage(root, items):
    prefix = str(root) + os.sep
    invoked, errors, adhoc = Counter(), defaultdict(Counter), defaultdict(set)
    bypass_calls, bypass_sessions = Counter(), Counter()
    n = 0
    for f in sessions(root):
        in_repo, used, cmds, pend = False, set(), [], {}
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cwd = r.get("cwd") or ""
            in_repo = in_repo or cwd == str(root) or cwd.startswith(prefix)
            c = (r.get("message") or {}).get("content")
            if r.get("type") == "user" and isinstance(c, str):
                for s in re.findall(r"<command-name>/?([^<]+)</command-name>", c):
                    used.add(bare(s))
            for b in c if isinstance(c, list) else []:
                if not isinstance(b, dict):
                    continue
                inp = b.get("input") or {}
                if b.get("type") == "tool_use":
                    pend[b.get("id")] = b
                    if b.get("name") == "Skill":
                        used.add(bare(inp.get("skill") or inp.get("command")))
                    elif b.get("name") in ("Agent", "Task"):
                        used.add(inp.get("subagent_type") or "general-purpose")
                    elif b.get("name") == "Bash":
                        cmds.append(str(inp.get("command") or ""))
                        m = re.search(r"cat\s*>\s*(/tmp/[\w.-]+\.(?:sh|py|mjs|js))", cmds[-1])
                        if m:
                            adhoc[Path(m.group(1)).name].add(f.stem)
                    elif b.get("name") == "Write" and re.match(r"^/(private/)?tmp/.*\.(sh|py|mjs|js)$", str(inp.get("file_path") or "")):
                        adhoc[Path(inp["file_path"]).name].add(f.stem)
                if b.get("type") == "tool_result" and b.get("is_error") and b.get("tool_use_id") in pend:
                    u = pend[b["tool_use_id"]]
                    if u.get("name") in ("Skill", "Agent", "Task"):
                        ui = u.get("input") or {}
                        who = bare(ui.get("skill") or ui.get("subagent_type") or ui.get("command"))
                        t = b.get("content") if isinstance(b.get("content"), str) else json.dumps(b.get("content"))
                        why = ("not found" if re.search(r"not found|Unknown skill|does not exist", t, re.I)
                               else "re-invoked itself" if "already executing" in t else "failed")
                        errors[("skill" if u.get("name") == "Skill" else "agent", who)][why] += 1
        if not in_repo:
            continue
        n += 1
        for name in used:
            invoked[name] += 1
        for it in items:
            if it["kind"] != "skill" or it["name"] in used or it["id"] in used:
                continue
            matched = {sig for cmd in cmds for sig in it["signatures"] if sig in cmd}
            scripted = any(s.endswith((".sh", ".py", ".mjs", ".js")) for s in matched)
            if len(matched) >= 2 or scripted:
                hits = sum(1 for cmd in cmds for sig in matched if sig in cmd)
                bypass_calls[it["id"]] += hits
                bypass_sessions[it["id"]] += 1
    return n, invoked, errors, bypass_calls, bypass_sessions, adhoc


def references(root, items):
    """Where the repository names a skill or agent outside sessions: CI, docs, other skills."""
    files = [root / ".gitlab-ci.yml", root / "CLAUDE.md", *root.glob(".github/workflows/*.y*ml"),
             *(f for f in root.glob(".claude/**/*.md") if "worktrees" not in f.parts)]
    texts = {f: f.read_text(errors="replace") for f in files if f.is_file()}
    found = {}
    for it in items:
        # An invocation, not the word: `/name`, `agent-run name`, `subagent_type: name` or `name` in backticks.
        rx = re.compile(r"(?:(?<![\w/.-])/|agent-run\s+|subagent_type[\"':=\s]+|`)" + re.escape(it["name"]) + r"(?![\w-])")
        found[it["id"]] = sorted(str(f.relative_to(root)) for f, t in texts.items() if str(f) != it["path"] and rx.search(t))
    return found


def audit(root):
    items = installed(root)
    refs = references(root, items)
    n, invoked, errors, bcalls, bsess, adhoc = usage(root, items)
    by_name = defaultdict(list)
    for it in items:
        if not it["plugin"]:
            by_name[(it["kind"], it["name"])].append(it["scope"])
    names = {it["name"] for it in items} | {it["id"] for it in items}
    rows = []
    for it in items:
        if it["scope"] == "plugin" and not invoked[it["id"]] and not bsess[it["id"]]:
            continue
        rows.append({
            "id": it["id"], "kind": it["kind"], "scope": it["scope"],
            "sessionsUsed": invoked[it["id"]] or invoked[it["name"]],
            "sessionsWorkedAround": bsess[it["id"]], "callsWorkedAround": bcalls[it["id"]],
            "errors": dict(errors.get((it["kind"], it["name"]), {})), "signatures": it["signatures"][:4],
            "manual": it["manual"], "path": it["path"].replace(str(Path.home()), "~"),
            "referencedBy": refs[it["id"]][:4],
        })
    plugin_names = defaultdict(list)
    for it in items:
        if it["plugin"]:
            plugin_names[(it["kind"], it["name"])].append(it["plugin"])
    return {
        "root": str(root), "sessions": n,
        "collisions": [{"kind": k, "name": nm, "scopes": sc} for (k, nm), sc in by_name.items() if len(sc) > 1],
        "duplicates": [{"kind": k, "name": nm, "plugins": plugin_names[(k, nm)]}
                       for (k, nm) in by_name if plugin_names.get((k, nm))],
        "missing": [{"kind": k, "name": nm, "errors": dict(e)} for (k, nm), e in errors.items() if "not found" in e or nm not in names],
        "brokenBuiltins": [{"kind": k, "name": nm, "errors": dict(e)} for (k, nm), e in errors.items()
                           if "not found" not in e and not any(it["kind"] == k and it["name"] == nm for it in items)],
        "items": sorted(rows, key=lambda r: (-r["sessionsWorkedAround"], -r["sessionsUsed"])),
        "adhocScripts": sorted(({"file": k, "sessions": len(v)} for k, v in adhoc.items() if len(v) > 1), key=lambda x: -x["sessions"])[:15],
        "pluginSkillsInstalled": sum(1 for it in items if it["scope"] == "plugin" and it["kind"] == "skill"),
    }


def print_report(rep):
    print(f"{rep['root']}\n{rep['sessions']} sessions\n")
    if rep["collisions"]:
        print("Same name in more than one place (one shadows the other):")
        for c in rep["collisions"]:
            print(f"  {c['kind']} {c['name']}: {', '.join(c['scopes'])}")
        print()
    if rep["duplicates"]:
        print("Also shipped by a plugin (listed twice in every session):")
        for d in rep["duplicates"]:
            print(f"  {d['kind']} {d['name']}: {', '.join(d['plugins'])}")
        print()
    if rep["missing"]:
        print("Called but not there:")
        for m in rep["missing"]:
            print(f"  {m['kind']} {m['name']}: {m['errors']}")
        print()
    if rep["brokenBuiltins"]:
        print("Built-in skills or agents that failed when called:")
        for m in rep["brokenBuiltins"]:
            print(f"  {m['kind']} {m['name']}: {m['errors']}")
        print()
    print("Skills and agents (sessions used / sessions that ran its commands without it):")
    for r in rep["items"]:
        err = f"  errors {r['errors']}" if r["errors"] else ""
        sig = f"  [{'; '.join(r['signatures'])}]" if r["sessionsWorkedAround"] else ""
        ref = f"  named in {', '.join(r['referencedBy'])}" if not r["sessionsUsed"] and r["referencedBy"] else ""
        print(f"  {r['sessionsUsed']:>4} used  {r['sessionsWorkedAround']:>4} around ({r['callsWorkedAround']} calls)  {r['kind']:<5} {r['id']}  {r['path']}{err}{sig}{ref}")
    print(f"\nPlugin skills installed but unused here: {rep['pluginSkillsInstalled'] - sum(1 for r in rep['items'] if r['scope'] == 'plugin')}")
    if rep["adhocScripts"]:
        print("\nScripts written to /tmp in more than one session (a skill that does not exist yet):")
        for a in rep["adhocScripts"]:
            print(f"  {a['sessions']:>3} sessions  {a['file']}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    root = main_checkout(Path(next((a for a in argv if not a.startswith("--")), os.getcwd())).resolve())
    rep = audit(root)
    print(json.dumps(rep, indent=2) if "--json" in argv else "", end="") if "--json" in argv else print_report(rep)
