"""Materialize declared component files into Gradle's offline Maven layout.

The marker locates the adjacent directory output through its relative `root`.
Component module metadata may place the same artifact in overlapping paths;
equal bytes are shared, while conflicting bytes fail acquisition.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
import traceback
from pathlib import Path


def assemble(entries: list[list[str]], repository: Path, marker: Path) -> None:
    repository.mkdir(parents=True, exist_ok=True)
    for source, relative in entries:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"Maven artifact leaves the repository: {relative}")
        destination = repository / path
        if destination.exists():
            if not filecmp.cmp(source, destination, shallow=False):
                raise ValueError(
                    f"Maven components supply conflicting bytes: {relative}"
                )
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    marker.write_text(json.dumps({"root": repository.name}) + "\n")
    print(f"Maven layout: assembled {len(entries)} declared files into {repository}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()
    try:
        assemble(json.loads(args.manifest.read_text()), args.repository, args.marker)
    except (OSError, ValueError, TypeError):
        print("Maven layout failed (reason=assemble_maven_layout).", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
