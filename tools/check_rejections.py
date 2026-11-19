"""Drive real Bazel through the locks and module files the ruleset must refuse.

The parser and the component fetch refuse with `fail()`, which only a Bazel
run can observe. Each case writes a lock into a throwaway module and the Maven
files it pins into a directory a local HTTP server serves as the module's
repository, builds its layout, and checks the run failed with that refusal's
message. A first case that must succeed, a module file placing its variant in
another directory, shows the harness itself works, so a refusal cannot pass by
failing for another reason.

Served over HTTP, a pinned file can also answer 404 before it is served, as a
repository does in a moment of inconsistency, or never be served at all.

    python3 tools/check_rejections.py [--bazel bazel]
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
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
    # Each served path that answers 404 this many times before it is served.
    missing_first: dict[str, int] = field(default_factory=dict[str, int])


class _Repository(http.server.SimpleHTTPRequestHandler):
    """Serves a directory, answering 404 for a path while it has misses left.
    Each path's misses so far are kept in `answered`."""

    def __init__(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
        server: socketserver.BaseServer,
        *,
        directory: str,
        misses: dict[str, int],
        answered: dict[str, int],
    ) -> None:
        self._misses = misses
        self._answered = answered
        super().__init__(request, client_address, server, directory=directory)

    def do_GET(self) -> None:
        path = self.path.lstrip("/")
        if self._answered.get(path, 0) < self._misses.get(path, 0):
            self._answered[path] = self._answered.get(path, 0) + 1
            self.send_error(404)
            return
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass


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
    name: str,
    refusal: str,
    url: str,
    jar_at: str,
    jar: bytes = b"jar",
    missing_first: dict[str, int] | None = None,
    **extra: str,
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
    return Case(
        name, refusal, served, pinned, missing_first=missing_first or {}, **extra
    )


def _unserved(case: Case, path: str) -> Case:
    del case.served[path]
    return case


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
        _case(
            "a pinned file that answers 404 before it is served",
            "",
            placed,
            elsewhere,
            # Bytes no other case pins, so no earlier case's fetch serves them.
            jar=b"jar served after two misses",
            missing_first={elsewhere: 2},
        ),
        _unserved(
            _case(
                "a pinned file no repository serves",
                f"/{elsewhere}] to ",
                placed,
                elsewhere,
                jar=b"jar never served",
            ),
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


def _write_module(workspace: Path, checkout: Path, repository: str) -> None:
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
    repositories = [{json.dumps(repository)}],
)
use_repo(gradle_maven, "case_maven")
""")


def _run(
    case: Case,
    bazel: list[str],
    workspace: Path,
    served: Path,
    repository_cache: Path,
    misses: dict[str, int],
    answered: dict[str, int],
) -> bool:
    shutil.rmtree(served, ignore_errors=True)
    misses.clear()
    misses.update(case.missing_first)
    answered.clear()
    for path, data in case.served.items():
        (served / path).parent.mkdir(parents=True, exist_ok=True)
        (served / path).write_bytes(data)
    (workspace / "lock.xml").write_text(_lock(case))
    built = subprocess.run(
        [
            *bazel,
            "build",
            "@case_maven//:files",
            "--lockfile_mode=off",
            f"--repository_cache={repository_cache}",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    output = built.stdout + built.stderr
    # A fetch served from a cache would pass the 404 cases without a miss.
    if answered != misses:
        print(output, file=sys.stderr)
        print(
            f"check_rejections: FAIL: {case.name} was answered 404 {answered},"
            f" not {misses}",
            file=sys.stderr,
        )
        return False
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
        # The run's own, so no case's pinned file is served from an earlier
        # run's fetch without asking the repository.
        repository_cache = Path(scratch) / "repository-cache"
        workspace.mkdir()
        served.mkdir()
        misses: dict[str, int] = {}
        answered: dict[str, int] = {}
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            functools.partial(
                _Repository, misses=misses, answered=answered, directory=str(served)
            ),
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _write_module(
            workspace, checkout, f"http://127.0.0.1:{server.server_address[1]}"
        )
        bazel = [args.bazel, "--ignore_all_rc_files", f"--output_base={output_base}"]
        try:
            results = [
                _run(case, bazel, workspace, served, repository_cache, misses, answered)
                for case in _cases()
            ]
        finally:
            server.shutdown()
            server.server_close()
            subprocess.run([*bazel, "shutdown"], cwd=workspace, check=False)
            # Bazel leaves its output base read-only.
            subprocess.run(["chmod", "-R", "u+w", str(output_base)], check=False)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
