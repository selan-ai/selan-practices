# file-length

Fails the lint run on a source file over 600 lines. A long file is read in pieces, session
after session, and an agent adds to it rather than splitting it. The rule is an error or it is
absent: an agent treats a warning as noise, so this component never sets one.

The files already over the limit are listed as exceptions, so the build stays green on the day
the rule lands. The list only shrinks: a file comes off it in the merge request that splits it.

## Rule per stack

Use the repository's own linter when it has a file-length rule, so the agent sees the failure in
the lint run it already does. Where its linters have none, use alint, one static binary.

| Stack | Rule | Exceptions |
| --- | --- | --- |
| TypeScript / JavaScript, Biome 2.3.12+ | `style.noExcessiveLinesPerFile` | an `overrides` entry with `includes`, the rule `"off"` |
| TypeScript / JavaScript, ESLint or oxlint | `max-lines` | a `files` block with the rule `"off"` |
| Go, golangci-lint v2 | revive `file-length-limit` | `linters.exclusions.rules`, `path` and `text: file-length-limit` |
| Python | Pylint `too-many-lines` (C0302), `max-module-lines` | `# pylint: disable=too-many-lines` at the top of the file |
| Java | Checkstyle `FileLength`, a child of `Checker` | a `suppressions.xml` `<suppress checks="FileLength" files="…"/>` |
| Swift | SwiftLint `file_length` | `// swiftlint:disable file_length` at the top of the file |
| PHP | PHP_CodeSniffer, `SlevomatCodingStandard.Files.FileLength` (default 250) | `<exclude-pattern>` inside the rule |
| Scala | Scalastyle `FileLengthChecker` | a `// scalastyle:off` block |
| Ruff only, Rust, Kotlin, Ruby, C / C++, Dart, others | none in their linters: alint `file_max_lines` | `paths` excludes |

Ruff, Clippy, detekt, ktlint and RuboCop have no file-length rule (RuboCop's `ClassLength` and
`ModuleLength` measure something else); say so rather than enabling one of those.

Generated files are never counted: `*.d.ts`, `*_pb.*`, `*.pb.go`, `*.gen.*`, `*.g.dart`,
`*.freezed.dart`, `*.Designer.cs`, `*.min.js`, `dist/`, `build/`, `vendor/`.

```jsonc
// biome.json
"linter": { "rules": { "style": { "noExcessiveLinesPerFile": {
  "level": "error", "options": { "maxLines": 600, "skipBlankLines": true } } } } },
"overrides": [{ "includes": ["src/app.ts"],
  "linter": { "rules": { "style": { "noExcessiveLinesPerFile": "off" } } } }]
```

```js
// eslint.config.js
{ rules: { "max-lines": ["error", { max: 600, skipBlankLines: true, skipComments: true }] } },
{ files: ["src/app.ts"], rules: { "max-lines": "off" } },
```

```yaml
# .golangci.yml
version: "2"
linters:
  enable: [revive]
  settings:
    revive:
      rules:
        - name: file-length-limit
          severity: error
          arguments: [{ max: 600, skip-comments: true, skip-blank-lines: true }]
  exclusions:
    rules:
      - path: internal/cli/cli.go
        text: file-length-limit
```

```toml
# pyproject.toml
[tool.pylint.format]
max-module-lines = 600
```

```xml
<!-- checkstyle.xml, directly under <module name="Checker"> -->
<module name="FileLength">
  <property name="max" value="600"/>
  <property name="severity" value="error"/>
</module>
```

```yaml
# .swiftlint.yml: both levels at 600, so a long file is an error and never a warning
file_length:
  warning: 600
  error: 600
  ignore_comment_only_lines: true
```

```xml
<!-- phpcs.xml -->
<rule ref="SlevomatCodingStandard.Files.FileLength">
  <properties><property name="maxLinesLength" value="600"/></properties>
  <exclude-pattern>src/Legacy/BigService.php</exclude-pattern>
</rule>
```

```yaml
# .alint.yml (alint counts every line, blank ones too)
version: 1
rules:
  - id: max-file-lines
    kind: file_max_lines
    paths:
      include: ["**/*.rs", "**/*.kt", "**/*.rb"]
      exclude: ["src/legacy/big.rs"]
    max_lines: 600
    level: error
```

## Steps

1. List the files over 600 lines with the repository's own count: `git ls-files` for the stack's
   extensions, generated files left out. The quality-gates report names the largest.
2. Add the rule at `error`, merged into the existing config. Keep any longer limit the
   repository already set for tests; do not lower it in the same change.
3. Add every file over the limit as an exception, one entry per file, so the list can shrink.
4. With a revive `rules:` list, run golangci-lint before and after: if findings other than
   `file-length-limit` disappear, the repository relied on revive's default rules, and those
   rules go into the list too.
5. Where the lint already runs in CI, nothing else changes. Where it does not, add it to the
   blocking test job.
6. One line in the instructions file (`AGENTS.md`, or `CLAUDE.md` where the repository has
   one): split a file before it reaches 600 lines; the exception list only shrinks.

## Verify

The lint passes on the current tree. A scratch copy of a short file padded past 600 lines
fails it with the file-length rule's name, and passes again once the copy is deleted.
