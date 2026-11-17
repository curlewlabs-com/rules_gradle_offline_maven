# Security policy

Report suspected vulnerabilities privately using
[GitHub private vulnerability reporting](https://github.com/curlewlabs-com/rules_gradle_offline_maven/security/advisories/new).
Include the affected source revision or release, the Bazel and Gradle
versions, the reproduction steps, and the observed impact.

Curlew Labs maintains this repository; Jeffrey Wall
([jeffwall-curlewlabs](https://github.com/jeffwall-curlewlabs)) is the release
and security contact through GitHub. Reports are reviewed on a best-effort
basis without a guaranteed response time. Fixes target the latest published
release; older release lines have no promised backport window.

## Trust boundary

A file enters the layout only if its SHA-256 matches the lock, whichever
repository served it. A pinned file's location, from the lock or from a module
file's variants, must stay inside the layout, and two components that would
place different bytes at one path fail the build.

The lock is trusted: it decides which bytes are accepted. Review a change to it
as you would a dependency change, since Gradle's
`--write-verification-metadata` records whatever the repositories served when
it ran. The parser rejects signature verification rather than skipping it, so
this module adds no signature check of its own.
