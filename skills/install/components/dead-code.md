# dead-code

Finds code nothing reaches: unused files, exports, functions, dependencies. Dead code costs a
session twice: it is read while looking for the live path, and it is kept in step with changes
nobody needed.

## Tool per stack

| Stack | Tool | Local command | Fails on findings |
| --- | --- | --- | --- |
| TypeScript / JavaScript | knip | `npx knip --no-progress` | yes |
| Go | deadcode (golang.org/x/tools) | `go run golang.org/x/tools/cmd/deadcode@latest -test ./...` | no: wrap with `test -z "$(…)"` |
| Python | vulture | `pipx run vulture . --min-confidence 80` | yes (exit 3) |
| Rust | the compiler | `cargo clippy -- -D dead_code -D unused` | yes |
| Swift | Periphery | `periphery scan --strict` (first run: `periphery scan --setup` writes `.periphery.yml`) | yes, with `--strict` |
| Kotlin | detekt, `Unused*` rules | `./gradlew detekt` | yes, when those rules are active |
| Kotlin on Android | Android Lint `UnusedResources` | `./gradlew lint` | when set to error in `lint.xml` |
| Java | PMD, `Unused*` rules | `./gradlew pmdMain` or `mvn pmd:check` | yes |

A monorepo gets the tool for each stack it has.

Kotlin and Java tools find unused private members, parameters, imports and resources, not an
unused public class or method: nothing reliable does that on the JVM. Say so in the proposal
rather than implying the whole codebase was checked.

Swift: Periphery builds the project to index it, so it needs the scheme and targets in
`.periphery.yml`, and it runs on macOS only. On GitLab it needs a macOS runner; on GitHub,
`runs-on: macos-latest`. Code reached only through Objective-C or Interface Builder is a
false positive: `retain_objc_accessible: true` in the config.

Kotlin and Java: add the tool through the build (the `io.gitlab.arturbosch.detekt` plugin,
Gradle's `pmd` plugin or `maven-pmd-plugin`), enabling only the `Unused*` rules at first, so
the job is about dead code and not every style rule the tool knows.

## Steps

1. Run the local command once and count the findings. Do not delete anything yet.
2. Read each finding. Dynamic imports, reflection, framework entry points, generated code and
   test helpers are the usual false positives: declare them in the tool's config (`knip.json`
   entry/ignore, a vulture whitelist file, `//nolint` is not needed for deadcode) rather than
   deleting code that runs.
3. Propose deleting what is really dead only after `grep` finds no reference, and run the
   repository's tests after. Deleting is its own merge request, separate from installing.
4. Add the command to CI on merge requests:
   - zero findings after steps 2-3: blocking, in the existing test job;
   - findings left: its own job with `allow_failure: true` (GitHub: `continue-on-error: true`)
     until they are gone, then blocking. Say which.
5. Name the local command in `CLAUDE.md` in one line.

## Verify

The command exits 0 on the current tree after the config, and a deliberately unused export
or function added to a scratch copy is reported.
