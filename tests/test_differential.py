"""Seeded C/native differential: identical programs must agree exactly.

Part 8 §8.15 asks for seeded C/native differentials. `tools/differential.py`
generates programs from the features both backends claim to support and compares
exit code and stdout; this test runs a small seeded batch so a divergence lands
in CI instead of in a player's build.
"""

import importlib.util
import pathlib
import random
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "anvil_differential", ROOT / "tools" / "differential.py"
)
DIFFERENTIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIFFERENTIAL)


class DifferentialTests(unittest.TestCase):
    def test_seeded_programs_agree_on_both_backends(self):
        mismatches = DIFFERENTIAL.compare(6, seed=1)
        report = "\n\n".join(
            f"{row['verdict']}\n{row['source']}" for row in mismatches
        )
        self.assertEqual(mismatches, [], report)

    def test_the_generator_stays_inside_the_shared_subset(self):
        # A differential only means something if both backends claim the
        # feature; text, assets, audio and assertions are documented C-only.
        source = DIFFERENTIAL.generate(random.Random(5))
        for banned in (
            "display",
            "print",
            "image_load",
            "sound_",
            "expect",
            "net ",
            "scene",
        ):
            self.assertNotIn(banned, source)
        self.assertIn("fn(main)", source)
        self.assertIn("output", source)


if __name__ == "__main__":
    unittest.main()
