"""Check the layout holds what the lock pins, where Gradle looks for it."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


class LayoutTest(unittest.TestCase):
    def test_the_android_variant_is_where_the_jre_module_serves_it(self) -> None:
        # Pinned under guava:33.5.0-jre, the jar is served from the -android
        # version's directory; Gradle resolving offline looks for it there.
        marker = Path(os.environ["MARKER"])
        root = marker.parent / json.loads(marker.read_text())["root"]
        guava = root / "com" / "google" / "guava" / "guava"
        self.assertTrue(
            (guava / "33.5.0-android" / "guava-33.5.0-android.jar").is_file()
        )
        self.assertTrue((guava / "33.5.0-jre" / "guava-33.5.0-jre.module").is_file())
        self.assertFalse((guava / "33.5.0-jre" / "guava-33.5.0-android.jar").exists())


if __name__ == "__main__":
    unittest.main()
