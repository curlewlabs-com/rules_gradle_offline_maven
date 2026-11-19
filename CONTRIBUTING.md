# Contributing

Use the Bazel release in `.bazelversion`, Git, Python 3.11 or later (on 3.10
mypy needs a package `requirements-dev.txt` does not pin), and for the Gradle
check a JDK and the Gradle release CI pins. Keep changes on a branch and open a
pull request with the behavior change and its verification.

## Maintainership and review

Curlew Labs maintains this project. Jeffrey Wall
([jeffwall-curlewlabs](https://github.com/jeffwall-curlewlabs)) reviews changes
and approves the releases that
[need approval](docs/releases.md#which-releases-need-approval). Use issues for
reproducible defects and proposals; use
[private vulnerability reporting](SECURITY.md) for security concerns.

Changes land through pull requests with passing CI and maintainer review;
[dependency updates](#dependency-updates) merge on passing CI alone. Fixed
version tags and published release artifacts are never replaced.

## Local checks

```sh
python3 -m pip install -r requirements-dev.txt
mypy
bazel test //...
python3 tools/check_rejections.py
(cd examples/consumer && bazel test //...)
python3 tools/check_gradle.py --gradle /path/to/gradle
```

`tools/check_rejections.py` runs Bazel against locks and module files the
fetch must refuse, and against a pinned file that answers 404 before it is
served, all from a local HTTP server. The consumer and the Gradle check fetch
the example's lock from Maven Central.

## Dependency updates

[Renovate](https://docs.renovatebot.com/) proposes each new minor and patch
release of Bazel, the Bazel modules, the workflow actions, and the JDK and
Gradle the Gradle check runs, once it has aged, and merges the pull request
when CI passes. A new Bazel major is moved by hand. The `# renovate:` comment
above a pin tells Renovate what the literal below is.

The example's Guava version is its lock's, not a pin to move: changing it
means regenerating `examples/consumer/gradle/verification-metadata.xml` with
`gradle --write-verification-metadata sha256 compileJava`.

## Releases

Follow [releases](docs/releases.md).

## License

By submitting a contribution for inclusion in this project, you agree that it
is licensed under the MIT and Apache-2.0 licenses, as the README's License
section describes, without any additional terms or conditions.
