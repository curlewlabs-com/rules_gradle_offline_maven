# Offline Maven repositories for Gradle, from Gradle's own lock

Let [Bazel](https://bazel.build) fetch every file a Gradle build's
`verification-metadata.xml` pins, and hand the build those files as one
declared input: an offline Maven repository that Gradle resolves against with
`--offline`.

This is for a Gradle build that stays a Gradle build, such as an Android or
Flutter app, run by Bazel as an action. Gradle keeps its own dependency
declarations, its resolution, its variant selection and its verification of
what it reads. Bazel owns the fetch and the action's inputs:

- **The lock is Gradle's.** `gradle --write-verification-metadata sha256`
  writes the file this reads, so there is no second dependency list to keep in
  step.
- **Every file is fetched by its SHA-256** through Bazel's downloader, so it
  lands in the repository cache and any remote or shared cache like other
  Bazel-fetched files.
- **One repository per Maven component.** Each component's repository holds
  only its own coordinates, digests and source repositories, so editing one
  dependency leaves every other component's cached fetch valid, in a fresh
  output base too.
- **A real Maven layout.** POMs, Gradle `.module` files and variant artifacts
  are placed where Gradle looks for them, including artifacts a module serves
  from a location other than its own directory, such as Guava's Android
  variant, served from the sibling `-android` version.

[rules_jvm_external](https://github.com/bazel-contrib/rules_jvm_external)
resolves and pins Maven dependencies for Bazel's own Java rules; this module
does neither. It reads a lock Gradle already wrote and lays its files out for
Gradle. Whether any of it belongs upstream is open in
[rules_jvm_external#1640](https://github.com/bazel-contrib/rules_jvm_external/issues/1640).

This module is at major version zero: a release promises no compatibility with
the one before it. It is not published in the Bazel Central Registry.

## Use

Add the module from a release; each
[release](https://github.com/curlewlabs-com/rules_gradle_offline_maven/releases)
carries the `bazel_dep` and `archive_override` to copy. Then declare the lock:

```starlark
gradle_maven = use_extension(
    "@curlewlabs_rules_gradle_offline_maven//maven:extensions.bzl",
    "gradle_maven",
)
gradle_maven.lock(
    name = "app_maven",
    lock = "//app:gradle/verification-metadata.xml",
    # Every repository the Gradle build declares.
    repositories = [
        "https://dl.google.com/dl/android/maven2",
        "https://repo.maven.apache.org/maven2",
    ],
    # Optional: a group tries this repository first.
    group_repositories = {
        "androidx.": "https://dl.google.com/dl/android/maven2",
        "com.android": "https://dl.google.com/dl/android/maven2",
    },
    # Optional: fetched, but kept out of the layout.
    outside_layout = ["org.robolectric:android-all-instrumented"],
)
use_repo(gradle_maven, "app_maven")
```

| Target                               | What it is                                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `@app_maven//:files`                 | The layout, a directory, and its marker. Declare it as an input of the action that runs Gradle.                 |
| `@app_maven//:maven-repository.json` | The marker alone: `{"root": "repository"}`, the layout directory's name relative to the marker's own directory. |
| `@app_maven//:outside_layout_jars`   | The jars of the `outside_layout` components.                                                                    |

Every file a component serves is fetched from the first repository that has
it, and accepted only if its digest matches the lock. `group_repositories` only
changes which repository is asked first: Bazel logs a warning for each
repository that answers 404 before one serves the file, which is most of a cold
fetch's log when every Android artifact asks Maven Central first.

A repository can answer 404 for a moment for a file it serves; Maven Central
has done so for a published pom. Every file fetched here is one the lock pins,
so when no repository serves it, the fetch logs that and asks again a few times,
for about 15 seconds in all, before it fails.

`outside_layout` is for a component the lock pins that no Gradle resolution
reads, such as the Android framework jars Robolectric loads at test time. In
the layout, it would be an input of every Gradle action; outside it, only the
targets that read it declare it.

### The Gradle side

Starting with v0.2.0, run Gradle with `--offline` and the module's init script,
`@curlewlabs_rules_gradle_offline_maven//gradle:offline.init.gradle`
([source](gradle/offline.init.gradle)). It replaces every repository the build
declares with the layout, including repositories a plugin adds while projects
are configured. With a v0.1.x release, use `examples/consumer/offline.init.gradle`
from that release instead. The script takes the layout's path as a system
property:

```sh
gradle --offline \
  --init-script "$INIT_SCRIPT" \
  -Doffline.maven.repository="$LAYOUT" \
  assembleDebug
```

where `$INIT_SCRIPT` is the script's path and `$LAYOUT` is the marker's
directory joined with its `root`. An action that runs Gradle declares the
script as an input beside `@app_maven//:files` and passes its execution path
to Gradle. A `genrule` can obtain the path with `$(execpath)` applied to the
script's label. Gradle still verifies what it reads against its own
`verification-metadata.xml`, and a dependency the lock does not pin fails to
resolve.

### Keeping the lock current

The lock is Gradle's file, so it is refreshed the way Gradle refreshes it: run
the build once online with `--write-verification-metadata sha256`, and commit
the result. The parser reads only what that command writes, with
`verify-metadata` on and `verify-signatures` off, and fails on anything else:
a signature, another checksum or a trusted-artifact rule changes which files
Gradle reads, so it is an error here rather than something to skip.

## Example

[`examples/consumer`](examples/consumer) is a Java library on Guava's Android
variant, with its own lock. CI fetches its layout cold from Maven Central,
checks where the Android jar landed, and then
[`tools/check_gradle.py`](tools/check_gradle.py) compiles the project with
Gradle offline against it, under the module's init script, and checks that a
dependency the lock does not pin fails to resolve.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues as described in
[SECURITY.md](SECURITY.md).

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- MIT license ([LICENSE-MIT](LICENSE-MIT))

at your option. Releases published under the MIT license alone may also be used
under either license.

### Contribution

By submitting a contribution for inclusion in this project, you agree that it
is dual licensed as above, without any additional terms or conditions.
