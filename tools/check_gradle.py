"""Build the example consumer's Gradle project offline against its Bazel layout.

Bazel fetches what the example's lock pins and assembles the layout; Gradle
then compiles the project with --offline, the example's init script and a
fresh Gradle user home, so nothing reaches it except the layout. A dependency
the lock does not pin must then fail to resolve.

    python3 tools/check_gradle.py [--gradle gradle] [--bazel bazel]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# On Maven Central and absent from the example's lock.
_UNPINNED = "org.slf4j:slf4j-api:2.0.17"


def _layout(bazel: str, consumer: Path) -> Path:
    marker_label = "@consumer_maven//:maven-repository.json"
    subprocess.run(
        [bazel, "build", "@consumer_maven//:files"],
        cwd=consumer,
        check=True,
        stdout=sys.stderr,
    )
    execution_root = Path(
        subprocess.check_output(
            [bazel, "info", "execution_root"], cwd=consumer, text=True
        ).strip()
    )
    marker = (
        execution_root
        / subprocess.check_output(
            [bazel, "cquery", marker_label, "--output=files"], cwd=consumer, text=True
        ).strip()
    )
    root = json.loads(marker.read_text())["root"]
    if not isinstance(root, str):
        raise TypeError(f"the layout marker names no directory: {marker}")
    return marker.parent / root


def _gradle(
    gradle: str, consumer: Path, layout: Path, home: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            gradle,
            "--offline",
            "--no-daemon",
            "--stacktrace",
            f"--gradle-user-home={home}",
            f"--init-script={consumer / 'offline.init.gradle'}",
            f"-Doffline.maven.repository={layout}",
            "--project-dir",
            str(consumer),
            "--dependency-verification=strict",
            "compileJava",
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gradle", default="gradle")
    parser.add_argument("--bazel", default="bazel")
    args = parser.parse_args()
    consumer = Path(__file__).resolve().parents[1] / "examples" / "consumer"
    layout = _layout(args.bazel, consumer)
    print(f"check_gradle: layout at {layout}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as scratch:
        built = _gradle(args.gradle, consumer, layout, Path(scratch) / "pinned")
        if built.returncode != 0:
            print(built.stdout, built.stderr, sep="\n", file=sys.stderr)
            print("check_gradle: the pinned build failed offline", file=sys.stderr)
            return 1
        print("check_gradle: the pinned build compiled offline", file=sys.stderr)

        # A fresh home, so the first build's resolution cache cannot answer.
        unpinned = _gradle(
            args.gradle,
            consumer,
            layout,
            Path(scratch) / "unpinned",
            f"-PextraDependency={_UNPINNED}",
        )
        output = unpinned.stdout + unpinned.stderr
        if (
            unpinned.returncode == 0
            or "Could not find org.slf4j:slf4j-api" not in output
        ):
            print(output, file=sys.stderr)
            print(
                f"check_gradle: {_UNPINNED} is not in the lock and did not fail to"
                " resolve",
                file=sys.stderr,
            )
            return 1
        print(
            f"check_gradle: {_UNPINNED} failed to resolve, as expected", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
