"""Drive real Bazel through the locks and module files the ruleset must refuse.

The parser and the component fetch refuse with `fail()`, which only a Bazel
run can observe. Each case writes a lock and the Maven files it pins into a
throwaway module served from a `file://` repository, builds its layout, and
checks the run failed with that refusal's message. A first case that must
succeed, a module file placing its variant in another directory, shows the
harness itself works, so a refusal cannot pass by failing for another reason.

    python3 tools/check_rejections.py [--bazel bazel]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_DIRECTORY = "org/example/lib/1"


@dataclass
class Case:
    name: str
    # The refusal's message; empty for the case that must succeed.
    refusal: str
    # Each served file's path under the repository, and its bytes.
    served: dict[str, bytes]
    # Each artifact the lock pins under org.example:lib:1, and its digest.
    pinned: dict[str, str] = field(default_factory=dict[str, str])
    configuration: str = (
        "<verify-metadata>true</verify-metadata>"
        "<verify-signatures>false</verify-signatures>"
    )
    extra_artifact: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _module(url: str) -> bytes:
    return json.dumps(
        {
            "formatVersion": "1.1",
            "variants": [
                {"name": "runtime", "files": [{"name": "lib-1.jar", "url": url}]}
            ],
        }
    ).encode()


def _case(
    name: str, refusal: str, url: str, jar_at: str, jar: bytes = b"jar", **extra: str
) -> Case:
    pom = b"<project/>"
    module = _module(url)
    served = {
        f"{_DIRECTORY}/lib-1.pom": pom,
        f"{_DIRECTORY}/lib-1.module": module,
        jar_at: jar,
    }
    pinned = {
        "lib-1.pom": _sha256(pom),
        "lib-1.module": _sha256(module),
        "lib-1.jar": _sha256(jar),
    }
    return Case(name, refusal, served, pinned, **extra)


def _cases() -> list[Case]:
    elsewhere = "org/example/lib/1-other/lib-1-other.jar"
    placed = "../1-other/lib-1-other.jar"
    return [
        _case("a variant served from another directory", "", placed, elsewhere),
        _case(
            "signature verification on",
            "must verify metadata and not signatures",
            placed,
            elsewhere,
            configuration=(
                "<verify-metadata>true</verify-metadata>"
                "<verify-signatures>true</verify-signatures>"
            ),
        ),
        _case(
            "an alternative checksum",
            "<sha512>",
            placed,
            elsewhere,
            extra_artifact=(
                '<artifact name="lib-1-sources.jar"><sha512 value="'
                + "0" * 128
                + '"/></artifact>'
            ),
        ),
        _case(
            "a trusted-artifact rule",
            "has <trusted-artifacts>, which this fetch does not read",
            placed,
            elsewhere,
            configuration=(
                "<verify-metadata>true</verify-metadata>"
                "<verify-signatures>false</verify-signatures>"
                '<trusted-artifacts><trust group="org.example"/></trusted-artifacts>'
            ),
        ),
        _case(
            "an absolute module URL",
            "serves lib-1.jar from outside the repository",
            "/etc/lib-1.jar",
            elsewhere,
        ),
        _case(
            "a module URL with a scheme",
            "serves lib-1.jar from outside the repository",
            "https://example.invalid/lib-1.jar",
            elsewhere,
        ),
        _case(
            "a module URL escaping the layout",
            "leaves the repository",
            "../../../../../lib-1.jar",
            elsewhere,
        ),
        # The variant is placed at the pom's own path, with the jar's digest.
        _case(
            "a variant at the pom's path with another digest",
            f"pins {_DIRECTORY}/lib-1.pom with two digests",
            "lib-1.pom",
            elsewhere,
        ),
    ]


def _lock(case: Case) -> str:
    artifacts = "".join(
        f'<artifact name="{name}"><sha256 value="{digest}"/></artifact>'
        for name, digest in case.pinned.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<verification-metadata>"
        f"<configuration>{case.configuration}</configuration>"
        '<components><component group="org.example" name="lib" version="1">'
        f"{artifacts}{case.extra_artifact}"
        "</component></components></verification-metadata>\n"
    )


def _write_module(workspace: Path, checkout: Path, served: Path) -> None:
    (workspace / ".bazelversion").write_text((checkout / ".bazelversion").read_text())
    (workspace / "BUILD.bazel").write_text('exports_files(["lock.xml"])\n')
    (workspace / "MODULE.bazel").write_text(f"""module(name = "rejections")

bazel_dep(name = "curlewlabs_rules_gradle_offline_maven", version = "0.0.0")
local_path_override(
    module_name = "curlewlabs_rules_gradle_offline_maven",
    path = {json.dumps(str(checkout))},
)

gradle_maven = use_extension("@curlewlabs_rules_gradle_offline_maven//maven:extensions.bzl", "gradle_maven")
gradle_maven.lock(
    name = "case_maven",
    lock = "//:lock.xml",
    repositories = [{json.dumps(served.as_uri())}],
)
use_repo(gradle_maven, "case_maven")
""")


def _run(case: Case, bazel: list[str], workspace: Path, served: Path) -> bool:
    shutil.rmtree(served, ignore_errors=True)
    for path, data in case.served.items():
        (served / path).parent.mkdir(parents=True, exist_ok=True)
        (served / path).write_bytes(data)
    (workspace / "lock.xml").write_text(_lock(case))
    built = subprocess.run(
        [*bazel, "build", "@case_maven//:files", "--lockfile_mode=off"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    output = built.stdout + built.stderr
    if not case.refusal:
        layout = workspace / "bazel-bin" / "external"
        placed = list(layout.glob("*case_maven/repository/org/example/lib/1-other"))
        if (
            built.returncode == 0
            and placed
            and (placed[0] / "lib-1-other.jar").is_file()
        ):
            print(f"check_rejections: ok: {case.name} built", file=sys.stderr)
            return True
        print(output, file=sys.stderr)
        print(f"check_rejections: FAIL: {case.name} did not build", file=sys.stderr)
        return False
    if built.returncode != 0 and case.refusal in output:
        print(f"check_rejections: ok: {case.name} refused", file=sys.stderr)
        return True
    print(output, file=sys.stderr)
    print(
        f"check_rejections: FAIL: {case.name} was not refused with {case.refusal!r}",
        file=sys.stderr,
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bazel", default="bazel")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as scratch:
        workspace = Path(scratch) / "workspace"
        served = Path(scratch) / "served"
        output_base = Path(scratch) / "output-base"
        workspace.mkdir()
        _write_module(workspace, checkout, served)
        bazel = [args.bazel, "--ignore_all_rc_files", f"--output_base={output_base}"]
        try:
            results = [_run(case, bazel, workspace, served) for case in _cases()]
        finally:
            subprocess.run([*bazel, "shutdown"], cwd=workspace, check=False)
            # Bazel leaves its output base read-only.
            subprocess.run(["chmod", "-R", "u+w", str(output_base)], check=False)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
