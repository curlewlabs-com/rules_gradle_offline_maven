"""Check the offline Maven layout the assembler writes from declared files."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from assemble_maven_layout import assemble


class MavenLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.repository = self.root / "repository"
        self.marker = self.root / "maven-repository.json"

    def source(self, name: str, contents: bytes) -> str:
        path = self.root / name
        path.write_bytes(contents)
        return str(path)

    def test_gradle_sees_binary_artifacts_and_metadata_at_their_maven_paths(
        self,
    ) -> None:
        entries = [
            [
                self.source("library.jar", b"PK\x00\xff"),
                "org/example/library/1/library-1.jar",
            ],
            [
                self.source("library.pom", b"<project/>"),
                "org/example/library/1/library-1.pom",
            ],
            # Module variants may place an artifact outside their own version.
            [
                self.source("variant.aar", b"variant"),
                "org/example/library/1-android/variant.aar",
            ],
        ]
        assemble(entries, self.repository, self.marker)
        # The marker's root is relative to the marker, which is how a
        # consumer finds the layout.
        repository = self.marker.parent / json.loads(self.marker.read_text())["root"]
        for source, relative in entries:
            self.assertEqual(
                (repository / relative).read_bytes(), Path(source).read_bytes()
            )
            self.assertFalse((repository / relative).is_symlink())
        self.assertEqual(json.loads(self.marker.read_text()), {"root": "repository"})

    def test_overlapping_components_share_equal_bytes(self) -> None:
        # A Gradle variant can name a file also pinned by its own component.
        relative = "com/example/library/1/library.jar"
        assemble(
            [
                [self.source("a.jar", b"same"), relative],
                [self.source("b.jar", b"same"), relative],
            ],
            self.repository,
            self.marker,
        )
        self.assertEqual((self.repository / relative).read_bytes(), b"same")

    def test_conflicting_components_fail_before_publishing_the_marker(self) -> None:
        relative = "com/example/library/1/library.jar"
        with self.assertRaisesRegex(ValueError, "conflicting bytes"):
            assemble(
                [
                    [self.source("a.jar", b"a"), relative],
                    [self.source("b.jar", b"b"), relative],
                ],
                self.repository,
                self.marker,
            )
        self.assertFalse(self.marker.exists())

    def test_a_component_cannot_write_outside_the_maven_layout(self) -> None:
        for relative in ("../outside.jar", "/outside.jar", ""):
            with (
                self.subTest(relative=relative),
                self.assertRaisesRegex(ValueError, "leaves the repository"),
            ):
                assemble(
                    [[self.source("artifact.jar", b"artifact"), relative]],
                    self.repository,
                    self.marker,
                )


if __name__ == "__main__":
    unittest.main()
