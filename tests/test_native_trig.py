"""Native-backend trig builtins must match the C backend's libm results."""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tests.test_native_x64 import NativeRunMixin  # noqa: E402


class NativeTrigTests(NativeRunMixin, unittest.TestCase):
    def _value(self, expression: str) -> float:
        # `output` is Anvil's return statement: a top-level call prints the
        # value, so every case compiles a program with exactly one `output`.
        source = f"fn(main)\n  output {expression}\nend\ncall fn(main)\n"
        return float(self._run_source(source).strip())

    def test_quadrant_angles_match_libm(self) -> None:
        cases = [
            ("sin(0)", math.sin(0.0)),
            ("cos(0)", math.cos(0.0)),
            ("sin(1.5707963267948966)", math.sin(math.pi / 2)),
            ("cos(1.5707963267948966)", math.cos(math.pi / 2)),
            ("sin(3.141592653589793)", math.sin(math.pi)),
            ("cos(3.141592653589793)", math.cos(math.pi)),
            ("sin(-1.5707963267948966)", math.sin(-math.pi / 2)),
        ]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                self.assertAlmostEqual(self._value(expression), expected, delta=1e-6)

    def test_large_arguments_are_range_reduced(self) -> None:
        cases = [
            ("sin(6.283185307179586)", math.sin(2 * math.pi)),
            ("cos(6.283185307179586)", math.cos(2 * math.pi)),
            ("sin(123456.789)", math.sin(123456.789)),
            ("cos(987654.321)", math.cos(987654.321)),
            ("sin(-12345.6789)", math.sin(-12345.6789)),
            ("cos(-100000)", math.cos(-100000)),
        ]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                self.assertAlmostEqual(self._value(expression), expected, delta=1e-6)

    def test_trig_inside_user_functions(self) -> None:
        source = (
            "fn(wave, t)\n"
            "  output sin(var(t) * 6.283185307179586) * 100\n"
            "end\n"
            "fn(main)\n"
            "  output call fn(wave, 0.25)\n"
            "end\n"
            "call fn(main)\n"
        )
        self.assertAlmostEqual(float(self._run_source(source).strip()), 100.0, delta=1e-4)


if __name__ == "__main__":
    unittest.main()
