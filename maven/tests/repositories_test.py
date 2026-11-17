"""Check the lock's parsing and component repositories on the rules' own output."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any


def _cases() -> dict[str, Any]:
    with open(os.environ["CASES"]) as source:
        cases: dict[str, Any] = json.load(source)
    return cases


class ComponentRepositoryTests(unittest.TestCase):
    def test_replacing_a_dependency_preserves_the_other_acquisitions(self) -> None:
        # The point of a repository per component: an unrelated lock edit
        # must not change the attributes, and so the cache identity, of the
        # components it left alone.
        cases = _cases()
        before, after = cases["before"], cases["after"]
        for name, attributes in before.items():
            if attributes["module"] in ("a", "b"):
                self.assertEqual(after[name], attributes)
            else:
                self.assertNotIn(name, after)
        self.assertEqual({value["module"] for value in after.values()}, {"a", "b", "d"})

    def test_version_and_checksum_changes_invalidate_the_changed_component(
        self,
    ) -> None:
        cases = _cases()
        before = cases["before"]
        for variant in ("upgraded", "repinned"):
            with self.subTest(variant=variant):
                current = cases[variant]
                for name, attributes in before.items():
                    if attributes["module"] == "b":
                        self.assertNotEqual(current.get(name), attributes)
                    else:
                        self.assertEqual(current[name], attributes)

    def test_an_outside_component_is_fetched_but_not_laid_out(self) -> None:
        # Laid out, a component only a test runtime reads rides every Gradle
        # action's inputs; left out of the outside set, that runtime has no
        # jar to load.
        cases = _cases()
        self.assertEqual(len(cases["outside"]), 1)
        self.assertIn("runtime", cases["outside"][0])
        self.assertEqual(len(cases["layout"]), 2)
        self.assertNotIn(cases["outside"][0], cases["layout"])

    def test_coordinate_separators_cannot_merge_distinct_components(self) -> None:
        components = _cases()["separators"]
        self.assertEqual(
            {(value["module"], value["version"]) for value in components.values()},
            {("a_b", "c"), ("a", "b_c"), ("a_1b", "c")},
        )

    def test_a_group_hint_only_reorders_the_repositories(self) -> None:
        # The digest decides what is accepted, so a hint may change which
        # repository is asked first, never which are asked.
        sources = _cases()["sources"]
        self.assertEqual(
            sources["hinted"], ["https://google.example", "https://central.example"]
        )
        self.assertEqual(
            sources["default"], ["https://central.example", "https://google.example"]
        )


class VerificationMetadataTests(unittest.TestCase):
    def test_each_component_keeps_its_artifacts_and_digests(self) -> None:
        self.assertEqual(
            _cases()["parsed"],
            [
                {
                    "group": "com.google.guava",
                    "name": "guava",
                    "version": "33.8.0-jre",
                    "artifacts": {
                        "guava-33.8.0-android.jar": "1" * 64,
                        "guava-33.8.0-jre.module": "2" * 64,
                    },
                },
                {
                    "group": "org.example",
                    "name": "plain",
                    "version": "1",
                    "artifacts": {"plain-1.pom": "3" * 64},
                },
            ],
        )

    def test_a_variant_file_is_placed_where_its_module_serves_it(self) -> None:
        # Gradle reads the Android variant from the sibling version's
        # directory; fetched beside the jre module instead, it would not
        # resolve offline.
        self.assertEqual(
            _cases()["locations"],
            {
                "guava-33.8.0-jre.jar": "guava-33.8.0-jre.jar",
                "guava-33.8.0-android.jar": "../33.8.0-android/guava-33.8.0-android.jar",
            },
        )


if __name__ == "__main__":
    unittest.main()
