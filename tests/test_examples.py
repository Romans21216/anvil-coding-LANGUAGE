"""Every checked-in example must pass the compiler's own check on its backend."""

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
EXAMPLES = ROOT / "examples"


class ExampleCheckTests(unittest.TestCase):
    def test_every_example_passes_check_on_its_backend(self):
        examples = sorted(EXAMPLES.glob("*.ANVL"))
        self.assertTrue(examples, "no examples found")
        for path in examples:
            backend = "native" if path.name.startswith("native_") else "c"
            with self.subTest(example=path.name, backend=backend):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(COMPILER),
                        str(path),
                        "--backend",
                        backend,
                        "--check",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_example_is_canonically_formatted(self):
        for path in sorted(EXAMPLES.glob("*.ANVL")):
            with self.subTest(example=path.name):
                result = subprocess.run(
                    [sys.executable, str(COMPILER), str(path), "--format-check"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
