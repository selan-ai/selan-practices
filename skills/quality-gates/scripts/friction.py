"""What sessions ran into at the cheap rungs, and the files too long to read whole.

Each count is a failure something earlier would have shown: a language server right after the
edit, a formatting hook, one line of the instructions file. Imported by gates.py.
"""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

LIMIT = 600
# A failed run of a checker: anything else that fails may be printing an old log.
CHECKER = re.compile(r"\b(biome|eslint|oxlint|lint|golangci-lint|ruff|clippy|rubocop|prettier|gofmt|rustfmt|check|verify)\b")
# `cat lint.log` names a checker and runs none.
READER = re.compile(r"^(?:cd\s+\S+\s*(?:&&|;)\s*)*(?:cat|head|tail|less|sed|awk|grep|rg|nl|wc|ls|echo|printf)\b")
LINT_RULES = [
    ("biome", re.compile(r"\blint/(\w+/\w+)")),
    ("eslint", re.compile(r"^\s+\d+:\d+\s+error\s+.+?\s{2,}(@?[\w-]+(?:/[\w-]+)*)\s*$", re.M)),
    ("golangci-lint", re.compile(r"^\S+\.go:\d+:\d+: .+ \((\w+)\)$", re.M)),
    ("ruff", re.compile(r"^\S+\.py:\d+:\d+: ([A-Z]{1,3}\d{3,4})\b", re.M)),
    ("clippy", re.compile(r"clippy::(\w+)")),
    ("rubocop", re.compile(r": [CW]: (\w+/\w+):")),
]
TYPE_ERRORS = [
    ("typescript", re.compile(r"error (TS\d{4,5})")),
    ("rust", re.compile(r"error\[(E\d{4})\]")),
    ("csharp", re.compile(r"error (CS\d{4})")),
    # A Go compiler line; a golangci-lint line ends in `(linter)` and is a lint rule instead.
    ("go", re.compile(r"^\S+\.go:\d+:\d+: (?!.*\(\w+\)$)", re.M)),
    ("python", re.compile(r"\.py:\d+:\d+ - error|: error: .*\[([\w-]+)\]$", re.M)),
    ("java", re.compile(r"\.java:\d+: error:")),
    ("kotlin", re.compile(r"^e: \S+\.kt", re.M)),
    ("swift", re.compile(r"\.swift:\d+:\d+: error:")),
    ("cpp", re.compile(r"\.(?:c|cc|cpp|cxx|h|hpp):\d+:\d+: error:")),
]
# The claude-plugins-official plugin that shows a language's errors right after each edit.
LSP = {"typescript": "typescript-lsp", "go": "gopls-lsp", "python": "pyright-lsp", "rust": "rust-analyzer-lsp",
       "java": "jdtls-lsp", "kotlin": "kotlin-lsp", "csharp": "csharp-lsp", "swift": "swift-lsp", "cpp": "clangd-lsp"}
FORMAT_FAILED = [
    ("biome", re.compile(r"Formatter would have printed|File content differs from formatting output")),
    ("prettier", re.compile(r"Code style issues found")),
    ("ruff", re.compile(r"would reformat")),
    ("rustfmt", re.compile(r"^Diff in \S+ at line", re.M)),
]
LANGUAGES = {
    **dict.fromkeys((".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"), "TypeScript / JavaScript"),
    ".go": "Go", ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".swift": "Swift",
    ".cs": "C#", ".php": "PHP", ".scala": "Scala", ".rs": "Rust", ".rb": "Ruby", ".dart": "Dart",
    **dict.fromkeys((".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"), "C / C++"),
}
GENERATED = re.compile(
    r"(^|/)(node_modules|vendor|third_party|dist|build|generated|testdata)/"
    r"|\.d\.ts$|_pb2?\.\w+$|\.pb\.go$|\.gen\.\w+$|\.g\.(dart|cs)$|\.freezed\.dart$|\.Designer\.cs$|\.min\.js$"
)
# A file-length rule in any linter this plugin's file-length component knows.
LENGTH_RULE = re.compile(r"noExcessiveLinesPerFile|[\"']max-lines[\"']|file-length-limit|max-module-lines"
                         r"|\bFileLength\b|file_length|file_max_lines|FileLengthChecker")
LINT_CONFIGS = ("biome.json", "biome.jsonc", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
                "eslint.config.ts", ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".oxlintrc.json",
                ".golangci.yml", ".golangci.yaml", ".golangci.toml", "pyproject.toml", ".pylintrc", "setup.cfg",
                ".swiftlint.yml", "checkstyle.xml", "config/checkstyle/checkstyle.xml", "phpcs.xml",
                "phpcs.xml.dist", "scalastyle-config.xml", ".alint.yml")


def transcripts(root):
    """This repository's sessions, their subagents' included: an agent in a worktree runs the checks too."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return
    encoded = re.sub(r"[/.]", "-", str(root))
    for d in base.iterdir():
        if d.is_dir() and d.name.startswith(encoded):
            yield from d.rglob("*.jsonl")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text") or "" for c in content if isinstance(c, dict))
    return ""


def failures(root, foreign):
    """Lint rules, type errors and format checks in the output of commands that failed in this repository."""
    lint, types, codes, fmt = Counter(), Counter(), Counter(), Counter()
    for f in transcripts(root):
        pending = {}
        for line in open(f, encoding="utf-8", errors="replace"):
            if '"tool_' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cwd = r.get("cwd") or ""
            c = (r.get("message") or {}).get("content")
            for b in c if isinstance(c, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = str((b.get("input") or {}).get("command") or "")
                    if not foreign(cmd, cwd):
                        pending[b.get("id")] = cmd
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    cmd, out = pending.pop(b["tool_use_id"]), text_of(b.get("content"))
                    if not (b.get("is_error") or out.startswith("Exit code")):
                        continue
                    for lang, rx in TYPE_ERRORS:
                        for m in rx.finditer(out):
                            types[lang] += 1
                            if m.lastindex and m.group(1):
                                codes[(lang, m.group(1))] += 1
                    if not CHECKER.search(cmd) or READER.match(cmd.strip()):
                        continue
                    for tool, rx in LINT_RULES:
                        for m in rx.finditer(out):
                            lint[(tool, m.group(1))] += 1
                    for tool, rx in FORMAT_FAILED:
                        fmt[tool] += bool(rx.search(out))
                    if re.search(r"\bgofmt -l\b", cmd) and re.search(r"\.go\s*$", out, re.M):
                        fmt["gofmt"] += 1
    return lint, types, codes, +fmt


def instructions_text(root):
    """Every instructions file and rule, to tell a rule the agent was already told about."""
    files = [root / n for n in ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md", ".claude/AGENTS.md", "CLAUDE.local.md")]
    files += sorted((root / ".claude" / "rules").glob("**/*.md"))
    return "\n".join(f.read_text(errors="replace") for f in files if f.is_file())


def enabled_plugins(root):
    on = set()
    for f in (Path.home() / ".claude" / "settings.json", root / ".claude" / "settings.json",
              root / ".claude" / "settings.local.json"):
        try:
            plugins = json.loads(f.read_text()).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        on |= {k.split("@")[0] for k, v in plugins.items() if v}
    return on


def long_files(root):
    """Tracked source files over the limit in non-blank lines, by language, generated code left out."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    langs = {}
    for rel in filter(None, out.decode(errors="replace").split("\0")):
        lang = LANGUAGES.get(Path(rel).suffix)
        f = root / rel
        if not lang or GENERATED.search(rel) or not f.is_file() or f.stat().st_size > 2_000_000:
            continue
        lines = sum(1 for line in f.read_bytes().splitlines() if line.strip())
        e = langs.setdefault(lang, {"files": 0, "over": []})
        e["files"] += 1
        if lines > LIMIT:
            e["over"].append({"file": rel, "lines": lines})
    for e in langs.values():
        e["over"].sort(key=lambda x: -x["lines"])
    return {k: v for k, v in langs.items() if v["over"]}


def length_rules(root):
    found = []
    for name in LINT_CONFIGS:
        try:
            m = LENGTH_RULE.search((root / name).read_text(errors="replace"))
        except OSError:
            continue
        if m:
            found.append(f"{name} ({m.group(0).strip(chr(34) + chr(39))})")
    return found


def friction(root, files, foreign, hooks):
    lint, types, codes, fmt = failures(root, foreign)
    told, plugins = instructions_text(files), enabled_plugins(files)
    return {
        "lintRules": [{"tool": t, "rule": r, "failures": n, "named": r.split("/")[-1] in told}
                      for (t, r), n in lint.most_common(12)],
        "typeErrors": [{"language": lang, "errors": n, "plugin": LSP.get(lang), "pluginEnabled": LSP.get(lang) in plugins,
                        "codes": [{"code": c, "errors": k} for (l, c), k in codes.most_common() if l == lang][:3]}
                       for lang, n in types.most_common()],
        "formatFailures": dict(fmt),
        "formatHooks": [h["where"] for h in hooks if h["where"] == "claude PostToolUse" and "format" in h["kinds"]],
        "longFiles": long_files(files),
        "lengthRules": length_rules(files),
    }


def print_friction(rep):
    print("\nWhat the sessions ran into (a language server, a hook or one line of the instructions shows these first):")
    rules = rep["lintRules"]
    named = [r["rule"].split("/")[-1] for r in rules if r["named"]]
    broken = ", ".join("%s %d" % (r["rule"], r["failures"]) for r in rules if not r["named"])
    print(f"  lint rules that failed a check: {broken or 'none'}"
          f"{'; already in the instructions: ' + ', '.join(named) if named else ''}")
    for t in rep["typeErrors"]:
        top = ", ".join(f"{c['code']} {c['errors']}" for c in t["codes"])
        plugin = f"; {t['plugin']} plugin {'enabled' if t['pluginEnabled'] else 'not enabled'}" if t["plugin"] else ""
        print(f"  type errors in failed commands: {t['language']} {t['errors']}{f' ({top})' if top else ''}{plugin}")
    fmt = rep["formatFailures"]
    print(f"  format checks that failed: {', '.join(f'{k} {v}' for k, v in fmt.items()) or 'none'}"
          f"; hook formatting each edit: {', '.join(rep['formatHooks']) or 'none'}")
    for lang, e in rep["longFiles"].items():
        top = ", ".join(f"{x['file']} {x['lines']}" for x in e["over"][:3])
        print(f"Files over {LIMIT} non-blank lines: {lang} {len(e['over'])} of {e['files']} ({top})")
    if rep["longFiles"]:
        print(f"  file-length rule: {', '.join(rep['lengthRules']) or 'none'}")
