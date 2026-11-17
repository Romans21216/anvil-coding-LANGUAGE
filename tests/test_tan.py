"""tan: one spelling, identical results on both backends (8.12).

`sin` and `cos` are libm calls on the C backend and wrapped Taylor series in the
freestanding wasm runtime; the tests for those already pin their printed values.
`tan` is new, so this compares the two backends on the same program, byte for
byte, and checks the identities a caller relies on.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"
NEEDS_WASM = all(shutil.which(tool) for tool in ("clang", "node", "wasm-ld"))

PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say tan(0)",
        "  say tan(0.25)",
        "  say tan(0.5)",
        "  say tan(1)",
        "  say tan(-0.75)",
        "  say tan(2)",
        "  say tan(3)",
        "  say tan(10)",
        "  say tan(1000)",
        # The identity the implementation is built on: tan is sin/cos.
        "  say tan(1) - sin(1) / cos(1)",
        # A known value, so a wrong-but-consistent pair cannot pass.
        "  say round(tan(1) * 1000000)",
        # Near three poles: scaling by the known distance from the pole should
        # give +/-1. This catches a small cosine approximation residual taking
        # over the denominator.
        "  say round(tan(1.5707963167948966) * 0.00000001 * 1000000000000)",
        "  say round(tan(1.5707963367948966) * 0.00000001 * 1000000000000)",
        "  say round(tan(7.853981623974483) * 0.00000001 * 1000000000000)",
        # The nearest binary64 value to pi/2 is not the mathematical pole; it
        # must produce the same finite, large result as the C backend.
        "  say tan(1.5707963267948966)",
        "end",
        "",
    )
)


def build(root: pathlib.Path, backend: str | None) -> subprocess.CompletedProcess:
    source = root / "tan.ANVL"
    source.write_text(PROGRAM, encoding="utf-8")
    command = [sys.executable, str(COMPILER), str(source)]
    if backend:
        out = root / "tan.wasm"
        command += ["--backend", backend]
    else:
        out = root / "tan.exe"
    command += ["-o", str(out)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    result.output_path = out  # type: ignore[attr-defined]
    return result


def lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").strip().splitlines()


class TanParityTests(unittest.TestCase):
    def test_tan_is_identical_on_c_and_wasm(self) -> None:
        if not NEEDS_WASM:
            raise unittest.SkipTest("clang, wasm-ld and node are required")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_build = build(root, None)
            if c_build.returncode != 0:
                if "No C compiler found" in c_build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(c_build.stderr)
            c_run = subprocess.run(
                [str(c_build.output_path)],  # type: ignore[attr-defined]
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            wasm_build = build(root, "wasm")
            self.assertEqual(wasm_build.returncode, 0, wasm_build.stderr)
            wasm_run = subprocess.run(
                ["node", str(HOST), str(wasm_build.output_path)],  # type: ignore[attr-defined]
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(c_run.returncode, 0, c_run.stderr)
        self.assertEqual(wasm_run.returncode, 0, wasm_run.stderr)
        c_lines = lines(c_run.stdout)
        self.assertEqual(len(c_lines), 15, c_lines)
        self.assertEqual(c_lines, lines(wasm_run.stdout))
        # Straight angles and the identity, independent of the parity check.
        self.assertEqual(c_lines[0], "0")
        self.assertEqual(c_lines[9], "0")  # tan(1) == sin(1)/cos(1)
        self.assertEqual(c_lines[10], "1557408")  # tan(1) * 1e6
        # 80-digit mpmath references evaluated at the exact binary64 inputs,
        # then rounded after scaling tan(x) by 1e-8 and 1e12.
        self.assertEqual(
            c_lines[11:14], ["999999999954", "-1000000012201", "999999975461"]
        )
        self.assertTrue(float(c_lines[14]) > 1.0e15, c_lines[14])

    def test_tan_is_refused_by_the_native_backend(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result = build(root, "native")
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("tan", combined)
        self.assertIn("not available", combined)


if __name__ == "__main__":
    unittest.main()
