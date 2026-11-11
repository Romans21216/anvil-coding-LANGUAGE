"""The benchmark measures real code volume and proves reachability trims dead code."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import bench_anvil  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402


def native_size(source: str) -> int:
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "bench.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        return len(NativeCodegen(path, functions, top, variables, arrays).generate())


class BenchmarkCaseTests(unittest.TestCase):
    def test_reachable_helpers_change_the_binary_size(self) -> None:
        self.assertGreater(native_size(bench_anvil.BIG), native_size(bench_anvil.TINY) * 2)

    def test_unreachable_helpers_are_trimmed_to_the_same_size(self) -> None:
        self.assertEqual(
            native_size(bench_anvil.BIG_TRIMMED), native_size(bench_anvil.TINY)
        )

    def test_the_benchmark_reports_every_case(self) -> None:
        names = {name for name, _source in bench_anvil.CASES}
        self.assertEqual(names, {"tiny", "texty", "big", "big_trim"})


if __name__ == "__main__":
    unittest.main()
