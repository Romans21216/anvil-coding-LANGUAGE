"""Part 8.10: build to a staging file and replace the last good output only on success."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402


class AtomicOutputTests(unittest.TestCase):
    def test_failed_toolchain_preserves_the_previous_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            generated = root / "prog.generated.c"
            generated.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            out = root / "prog.exe"
            out.write_bytes(b"the last good executable")

            # sys.executable is not a C compiler: it exits nonzero without ever
            # writing the requested output.
            with self.assertRaises(Exception):
                build_c(sys.executable, generated, out, True)

            self.assertEqual(out.read_bytes(), b"the last good executable")
            self.assertEqual(list(root.glob("*.partial.exe")), [])

    def test_successful_build_replaces_the_output_without_leaving_staging(self) -> None:
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            generated = root / "prog.c"
            generated.write_text(
                '#include <stdio.h>\nint main(void) { printf("ok\\n"); return 0; }\n',
                encoding="utf-8",
            )
            out = root / "prog.exe"
            build_c(compiler[1], generated, out, True)
            self.assertTrue(out.exists())
            self.assertEqual(list(root.glob("*.partial.exe")), [])


if __name__ == "__main__":
    unittest.main()
