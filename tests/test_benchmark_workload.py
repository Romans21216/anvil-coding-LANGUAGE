"""Differential check on the checked-in benchmark workload.

The benchmark workload exercises arrays, calls, recursion and loops without
backend-specific built-ins, so both backends must print the same value. This
catches semantic drift that the smaller numeric conformance cases miss.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.build import find_compiler

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKLOAD = ROOT / "tools" / "benchmarks" / "console_workload.ANVL"


@unittest.skipUnless(sys.platform == "win32", "executes Windows PE output")
class BenchmarkWorkloadTests(unittest.TestCase):
    def test_workload_prints_the_same_value_on_both_backends(self):
        if not find_compiler(None):
            self.skipTest("differential run requires MSVC")
        outputs = {}
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            for backend in ("c", "native"):
                executable = work / f"workload-{backend}.exe"
                build = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "compiler.anvil",
                        str(WORKLOAD),
                        "--backend",
                        backend,
                        "--output",
                        str(executable),
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                run = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=60
                )
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                outputs[backend] = run.stdout.strip()
        self.assertEqual(
            outputs["c"],
            outputs["native"],
            "the benchmark workload must be part of the shared language contract",
        )


if __name__ == "__main__":
    unittest.main()
