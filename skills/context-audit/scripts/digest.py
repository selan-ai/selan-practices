#!/usr/bin/env python3
"""Reads this repository's Claude Code transcripts and reports what the agent read and ran.

Usage: python3 digest.py <repo-root> [--cap 8000] [--json]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOKEN_CHARS = 4
GENERATED = re.compile(
    r"(^|/)(dist|build|coverage|node_modules|\.next)/"
    r"|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$|\.min\.(js|css)$|\.snap$"
)
LOADED = re.compile(r"^(CLAUDE\.md|CLAUDE\.local\.md|\.claude/rules/.*)$")
LEADING_CD = re.compile(r"^(cd\s+\S+\s*(&&|;)\s*)+")
# A command whose output is cut down after the fact: the filter is the rule the command lacks.
PIPED_FILTER = re.compile(r"^(?P<cmd>[^|]+?)\s*(2>&1\s*)?\|\s*(?P<filter>grep|tail|head|rg)\b(?P<args>[^|]*)")


def main_checkout(path):
    """A worktree's sessions belong to its repository, so the digest always reads the main checkout."""
    try:
        common = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return Path(common).parent.resolve()
    except (OSError, subprocess.SubprocessError):
        return path


def parse_args(argv):
    root = next((a for a in argv if not a.startswith("--") and not a.isdigit()), os.getcwd())
    cap = int(argv[argv.index("--cap") + 1]) if "--cap" in argv else 8000
    return main_checkout(Path(root).resolve()), cap, "--json" in argv


def transcript_files(root):
    projects = Path.home() / ".claude" / "projects"
    encoded = re.sub(r"[/.]", "-", str(root))
    for d in projects.iterdir():
        if d.is_dir() and d.name.startswith(encoded):
            yield from d.rglob("*.jsonl")


def repo_path(root, file):
    """A worktree of this repository counts as the repository, so its paths fold onto the root."""
    prefix = str(root) + os.sep
    if not file or not file.startswith(prefix):
        return None
    rel = file[len(prefix):]
    wt = re.match(r"^\.claude/worktrees/[^/]+/(.*)$", rel)
    return wt.group(1) if wt else rel


def kind_of(cmd):
    """What a command is for, judged by its first word after any leading cd."""
    w = (cmd.split() or [""])[0]
    if re.fullmatch(r"sed|cat|head|tail|less|awk|nl|wc", w):
        return "read a file"
    if re.fullmatch(r"grep|rg|find|ls|fd|tree", w):
        return "search"
    if re.fullmatch(r"python3?", w) or (w in ("node", "tsx") and "<<" in cmd):
        return "inline script"
    if w in ("git", "glab", "gh"):
        return "git / MR"
    if re.fullmatch(r"npm|npx|pnpm|jest|tsc|biome", w):
        return "build / test / lint"
    if re.fullmatch(r"gcloud|curl|psql", w):
        return "cloud / network"
    return "other"


def content_chars(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(c.get("text") or "") for c in content if isinstance(c, dict))
    return 0


HABITS = {
    "cd before the command": re.compile(r"^\s*cd\s"),
    "PATH exported inline": re.compile(r"export\s+PATH="),
    "sleep": re.compile(r"(^|[;&|]\s*)sleep\s"),
    "edit through a script (bypasses Edit hooks)": re.compile(r"python3?\s+-\s*<<.*\.(replace|write)\(", re.S),
}


def session(root, path):
    requests, reads, bash, edits, pending = [], [], [], [], {}
    usage = {"input": 0, "cacheWrite": 0, "cacheRead": 0, "output": 0}
    habits = dict.fromkeys(HABITS, 0)
    elsewhere = {}
    images = 0
    parent = str(root.parent) + os.sep
    in_repo = False
    prefix = str(root) + os.sep
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cwd = r.get("cwd") or ""
            if cwd == str(root) or cwd.startswith(prefix):
                in_repo = True
            msg = r.get("message") or {}
            if r.get("type") == "assistant":
                mid = msg.get("id")
                if mid and (not requests or requests[-1] != mid):
                    requests.append(mid)
                    u = msg.get("usage") or {}
                    usage["input"] += u.get("input_tokens") or 0
                    usage["cacheWrite"] += u.get("cache_creation_input_tokens") or 0
                    usage["cacheRead"] += u.get("cache_read_input_tokens") or 0
                    usage["output"] += u.get("output_tokens") or 0
                for c in msg.get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    inp = c.get("input") or {}
                    target = inp.get("command") or inp.get("file_path") or inp.get("path") or ""
                    # A call into a sibling repository is that repository's habit, not this one's.
                    foreign = bool(cwd) and not (cwd == str(root) or cwd.startswith(prefix))
                    for m in re.finditer(re.escape(parent) + r"([^/\s'\"]+)", str(target)):
                        if m.group(1) != root.name:
                            elsewhere[m.group(1)] = elsewhere.get(m.group(1), 0) + 1
                            foreign = True
                            break
                    pending[c.get("id")] = {**c, "foreign": foreign}
                    if foreign:
                        continue
                    if c.get("name") == "Read" and re.search(r"\.(png|jpe?g|gif|webp)$", str(inp.get("file_path") or ""), re.I):
                        images += 1
                    if c.get("name") == "Bash":
                        for name, rx in HABITS.items():
                            habits[name] += bool(rx.search(str(inp.get("command") or "")))
                    if c.get("name") in ("Edit", "Write", "MultiEdit"):
                        edits.append({"file": repo_path(root, (c.get("input") or {}).get("file_path")), "at": len(requests)})
            if r.get("type") == "user" and isinstance(msg.get("content"), list):
                for c in msg["content"]:
                    if not isinstance(c, dict) or c.get("type") != "tool_result":
                        continue
                    use = pending.get(c.get("tool_use_id")) or {}
                    inp = use.get("input") or {}
                    tokens = round(content_chars(c.get("content")) / TOKEN_CHARS)
                    result = r.get("toolUseResult")
                    f_ = result.get("file") if isinstance(result, dict) else None
                    if use.get("name") == "Read" and isinstance(f_, dict) and f_.get("numLines") is not None:
                        reads.append({
                            "file": repo_path(root, f_.get("filePath")), "lines": f_["numLines"],
                            "total": f_.get("totalLines") or 0, "start": f_.get("startLine") or 1,
                            "full": not inp.get("offset") and not inp.get("limit"),
                            "tokens": tokens, "at": len(requests),
                        })
                    if use.get("name") == "Bash":
                        full = LEADING_CD.sub("", str(inp.get("command") or "").strip())
                        segments = (m for m in (PIPED_FILTER.match(seg.strip()) for seg in re.split(r"\n|&&|;", full)) if m)
                        piped = None if use.get("foreign") else next(segments, None)
                        bash.append({
                            "piped": {
                                "cmd": " ".join(LEADING_CD.sub("", piped["cmd"].strip()).split()[:2]),
                                "filter": f"{piped['filter']}{piped['args'].rstrip()}"[:60],
                            } if piped else None,
                            "cmd": " ".join(full.split()[:2]), "kind": kind_of(full),
                            "tokens": tokens, "error": bool(c.get("is_error")), "at": len(requests),
                        })
    if not in_repo:
        return None
    # Tokens a result keeps costing: it is re-sent, as cache read, on every later request.
    for x in reads + bash:
        x["carried"] = x["tokens"] * max(0, len(requests) - x["at"])
    return {"requests": len(requests), "reads": reads, "bash": bash, "edits": edits,
            "usage": usage, "habits": habits, "elsewhere": elsewhere, "images": images}


def edit_hooks(root):
    """Hooks on Edit or Write in the committed settings: a scripted edit skips exactly these."""
    found = []
    for name in ("settings.json", "settings.local.json"):
        f = root / ".claude" / name
        try:
            hooks = json.loads(f.read_text()).get("hooks") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for event, entries in hooks.items():
            for e in entries if isinstance(entries, list) else []:
                if re.search(r"Edit|Write", str(e.get("matcher") or "")):
                    found.append(f"{event} {e.get('matcher')}")
    return found


def standing_context(root):
    """Files Claude Code loads into every request: they cost their size times the request count."""
    files = [root / "CLAUDE.md", root / ".claude" / "CLAUDE.md", root / "CLAUDE.local.md", root / "AGENTS.md"]
    rules = root / ".claude" / "rules"
    if rules.is_dir():
        files += [f for f in rules.rglob("*.md") if not f.read_text(errors="replace").lstrip().startswith("---\npaths:")]
    out = []
    for f in files:
        if f.is_file():
            text = f.read_text(errors="replace")
            out.append({"file": str(f.relative_to(root)), "lines": text.count("\n"), "tokens": round(len(text) / TOKEN_CHARS)})
    return out


def stale_paths(root):
    """Paths CLAUDE.md names in backticks that no longer exist: each one sends the agent looking."""
    f = root / "CLAUDE.md"
    if not f.is_file():
        return []
    named = set(re.findall(r"`((?:\.{0,2}/)?[\w.-]+/[\w./-]*[\w-])`", f.read_text(errors="replace")))
    # Only paths into this repository: a first segment that exists here, so URLs and imports drop out.
    top = {e.name for e in root.iterdir()}
    inside = (p.lstrip("./") for p in named if "*" not in p)
    return sorted(p for p in inside if p.split("/")[0] in top and not (root / p).exists())


def digest(root, cap):
    sessions = [s for s in (session(root, p) for p in transcript_files(root)) if s]
    reads = [r for s in sessions for r in s["reads"] if r["file"]]

    per_file = {}
    for r in reads:
        e = per_file.setdefault(r["file"], {"file": r["file"], "reads": 0, "lines": 0, "tokens": 0, "carried": 0, "total": 0})
        e["reads"] += 1
        e["lines"] += r["lines"]
        e["tokens"] += r["tokens"]
        e["carried"] += r["carried"]
        e["total"] = max(e["total"], r["total"])
        e["exists"] = (root / r["file"]).exists()

    # Re-read: same file, same start, in one session, with no edit to it in between.
    rereads = reread_tokens = paged = 0
    for s in sessions:
        seen = {}
        own = [x for x in s["reads"] if x["file"]]
        for r in own:
            key = (r["file"], r["start"])
            prev = seen.get(key)
            if prev is not None and not any(e["file"] == r["file"] and prev <= e["at"] <= r["at"] for e in s["edits"]):
                rereads += 1
                reread_tokens += r["tokens"]
            seen[key] = r["at"]
            if not r["full"] and r["start"] > 1 and any(o["file"] == r["file"] and o["at"] < r["at"] and o["start"] < r["start"] for o in own):
                paged += 1

    over = [r for r in reads if r["tokens"] > cap]
    bash = [b for s in sessions for b in s["bash"]]
    kinds, cmds = {}, {}
    for b in bash:
        k = kinds.setdefault(b["kind"], {"kind": b["kind"], "runs": 0, "tokens": 0, "carried": 0})
        k["runs"] += 1
        k["tokens"] += b["tokens"]
        k["carried"] += b["carried"]
        c = cmds.setdefault(b["cmd"], {"cmd": b["cmd"], "runs": 0, "tokens": 0, "errors": 0})
        c["runs"] += 1
        c["tokens"] += b["tokens"]
        c["errors"] += b["error"]

    requests = sum(s["requests"] for s in sessions)
    usage = {u: sum(s["usage"][u] for s in sessions) for u in ("input", "cacheWrite", "cacheRead", "output")}
    habits = {h: sum(s["habits"][h] for s in sessions) for h in HABITS}
    elsewhere = {}
    for s in sessions:
        for repo, n in s["elsewhere"].items():
            elsewhere[repo] = elsewhere.get(repo, 0) + n
    standing = standing_context(root)
    filters = {}
    for b in bash:
        if b["piped"]:
            key = (b["piped"]["cmd"], b["piped"]["filter"])
            filters[key] = filters.get(key, 0) + 1
    return {
        "root": str(root),
        "usage": usage,
        "toolCalls": sum(len(s["bash"]) + len(s["reads"]) for s in sessions),
        "elsewhere": dict(sorted(elsewhere.items(), key=lambda x: -x[1])[:8]),
        "habits": habits,
        "imagesRead": sum(s["images"] for s in sessions),
        "stalePaths": stale_paths(root),
        "editHooks": edit_hooks(root),
        "standing": {"files": standing, "tokens": sum(f["tokens"] for f in standing),
                     "carried": sum(f["tokens"] for f in standing) * requests},
        "pipedFilters": [{"cmd": c, "filter": f, "runs": n} for (c, f), n in sorted(filters.items(), key=lambda x: -x[1])[:10]],
        "sessions": len(sessions),
        "requests": requests,
        "reads": {
            "count": len(reads),
            "tokens": sum(r["tokens"] for r in reads),
            "carried": sum(r["carried"] for r in reads),
            "overCap": {
                "cap": cap, "count": len(over), "tokens": sum(r["tokens"] for r in over),
                "trimmed": sum(r["tokens"] - cap for r in over),
                "carriedTrimmed": sum(r["carried"] * (r["tokens"] - cap) / r["tokens"] for r in over),
            },
            "loaded": [{"file": r["file"], "tokens": r["tokens"]} for r in reads if LOADED.match(r["file"])],
            "generated": [{"file": r["file"], "tokens": r["tokens"]} for r in reads if GENERATED.search(r["file"])],
            "rereads": {"count": rereads, "tokens": reread_tokens},
            "paged": paged,
            "topFiles": sorted(per_file.values(), key=lambda e: -e["carried"])[:15],
        },
        "bash": {
            "count": len(bash),
            "tokens": sum(b["tokens"] for b in bash),
            "carried": sum(b["carried"] for b in bash),
            "kinds": sorted(kinds.values(), key=lambda k: -k["runs"]),
            "top": sorted(cmds.values(), key=lambda c: -c["tokens"])[:10],
        },
    }


def k(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(round(n))


def print_report(rep):
    R, B = rep["reads"], rep["bash"]
    print(f"{rep['root']}\n{rep['sessions']} sessions, {k(rep['requests'])} requests\n")
    U = rep["usage"]
    print(f"Tokens: {k(U['cacheRead'])} cache read, {k(U['cacheWrite'])} cache write, {k(U['input'])} input, {k(U['output'])} output")
    if rep["elsewhere"]:
        print("Calls naming a sibling repository (work that belongs in a session there):")
        for repo, n in rep["elsewhere"].items():
            print(f"  {n:>6}  {repo}")
    print("Habits in Bash commands:")
    for h, n in rep["habits"].items():
        print(f"  {n:>6}  {h}")
    print(f"Images read: {rep['imagesRead']}")
    print(f"Edit/Write hooks in .claude/settings: {', '.join(rep['editHooks']) or 'none'}")
    if rep["stalePaths"]:
        print(f"Paths in CLAUDE.md that do not exist: {', '.join(rep['stalePaths'][:12])}")
    print()
    S = rep["standing"]
    print(f"Loaded into every request: {k(S['tokens'])} tokens x {k(rep['requests'])} requests = {k(S['carried'])}")
    for f in S["files"]:
        print(f"  {f['lines']:>5} lines  {k(f['tokens']):>5} tokens  {f['file']}")
    print()
    print(f"Reads: {R['count']}, {k(R['tokens'])} tokens read, {k(R['carried'])} tokens carried as context afterwards")
    o = R["overCap"]
    print(f"Over a {k(o['cap'])} cap: {o['count']} reads, {k(o['trimmed'])} tokens above it, {k(o['carriedTrimmed'])} carried")
    print(f"Already-loaded files read: {len(R['loaded'])} ({k(sum(r['tokens'] for r in R['loaded']))} tokens)")
    print(f"Generated files read: {len(R['generated'])} ({k(sum(r['tokens'] for r in R['generated']))} tokens)")
    print(f"Unchanged re-reads: {R['rereads']['count']} ({k(R['rereads']['tokens'])} tokens); paged reads: {R['paged']}\n")
    print("Files by tokens carried:")
    for f in R["topFiles"]:
        gone = "" if f["exists"] else "  (gone)"
        print(f"  {k(f['carried']):>6}  {f['reads']:>3}x  {f['total']:>5} lines  {f['file']}{gone}")
    print(f"\nBash: {B['count']} calls, {k(B['tokens'])} tokens of output, {k(B['carried'])} carried")
    for x in B["kinds"]:
        print(f"  {x['runs']:>6} calls  {k(x['tokens']):>6} out  {k(x['carried']):>7} carried  {x['kind']}")
    print("Output cut down after the fact (command | filter):")
    for x in rep["pipedFilters"]:
        print(f"  {x['runs']:>5}x  {x['cmd']}  | {x['filter']}")
    print("Top commands by output:")
    for c in B["top"]:
        failed = f"{c['errors']} failed  " if c["errors"] else ""
        print(f"  {k(c['tokens']):>6}  {c['runs']:>4}x  {failed}{c['cmd']}")


if __name__ == "__main__":
    root, cap, as_json = parse_args(sys.argv[1:])
    rep = digest(root, cap)
    if as_json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
