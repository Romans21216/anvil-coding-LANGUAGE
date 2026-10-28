"""Execute shared language contracts through both compiler backends."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.build import find_compiler


@unittest.skipUnless(sys.platform == "win32", "executes Windows PE output")
class NativeConformanceTests(unittest.TestCase):
    def test_global_local_and_parameter_namespaces_match_c(self):
        if not find_compiler(None):
            self.skipTest("C/native differential test requires MSVC")
        cases = [
            ("simple", "fn(main)\n set var(x) = 7\n set local(x) = 2\n output var(x) + local(x)\nend\n", "9"),
            ("writes", "fn(main)\n set var(x) = 7\n set local(x) = 2\n add var(x) 3\n sub local(x) 1\n output var(x) * 10 + local(x)\nend\n", "101"),
            ("parameters", "fn(change, x)\n add var(x) 3\n output var(x)\nend\nfn(main)\n set var(x) = 7\n set local(x) = 2\n output call fn(change, 10) * 100 + var(x) * 10 + local(x)\nend\n", "1372"),
            ("loops", "fn(main)\n set var(x) = 10\n set local(x) = 2\n while local(x) < 5\n  add local(x) 1\n  add var(x) 2\n end\n for local(i) = 1 to 3\n  sub var(x) 1\n end\n output var(x) * 10 + local(x)\nend\n", "135"),
            ("recursive", "fn(walk, n)\n set local(x) = var(n)\n if var(n) <= 0\n  output var(x) + local(x)\n end\n add var(x) 1\n output call fn(walk, var(n) - 1) + local(x)\nend\nfn(main)\n set var(x) = 7\n set local(x) = 100\n output call fn(walk, 3) * 1000 + var(x) * 10 + local(x)\nend\n", "16200"),
            ("included", 'include "library.ANVL"\nfn(main)\n set var(value) = 5\n set local(value) = 10\n output call fn(modify) * 100 + var(value) * 10 + local(value)\nend\n', "380"),
            ("zero-on-repeat", "fn(touch, flag)\n if var(flag)\n  set local(x) = 7\n end\n output local(x)\nend\nfn(main)\n output call fn(touch, 1) * 10 + call fn(touch, 0)\nend\n", "70"),
            ("loop-zero-and-parameter", "fn(touch, n)\n while var(n) < 0\n  set local(x) = 9\n end\n output local(x) + var(n)\nend\nfn(main)\n output call fn(touch, 13)\nend\n", "13"),
            ("recursive-zero", "fn(touch, n)\n if var(n) > 0\n  set local(x) = 7\n  output call fn(touch, var(n) - 1) + local(x)\n end\n output local(x)\nend\nfn(main)\n output call fn(touch, 3)\nend\n", "21"),
            ("temporary-local", "fn(main)\n set local(_temporary_1) = 5\n output 1 + local(_temporary_1)\nend\n", "6"),
            ("temporary-parameters", "fn(value, _temporary_1, _temporary_value)\n output max(var(_temporary_1),var(_temporary_value)) + sqrt(var(_temporary_1) * var(_temporary_1))\nend\nfn(main)\n output call fn(value,7,3)\nend\n", "14"),
            ("temporary-loop-array", "array values(3)\nfn(main)\n set local(_temporary_1) = 5\n for local(_temporary_value) = 0 to 2\n  set array(values,local(_temporary_value)) = local(_temporary_1) + local(_temporary_value)\n end\n add local(_temporary_1) array(values,2)\n output local(_temporary_1) + array(values,1)\nend\n", "18"),
            ("temporary-looking-budget", "fn(value, _temporary_17)\n output var(_temporary_17) + 1\nend\nfn(main)\n output call fn(value,41)\nend\n", "42"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "library.ANVL").write_text("fn(modify)\n set local(value) = 3\n add var(value) 2\n output local(value)\nend\n", encoding="utf-8")
            for name, source, expected in cases:
                entry = root / (name + ".ANVL")
                entry.write_text(source, encoding="utf-8")
                for backend in ("native", "c"):
                    with self.subTest(case=name, backend=backend):
                        output = root / (name + "-" + backend + ".exe")
                        command = [sys.executable, "-m", "compiler.anvil", str(entry), "--backend", backend, "--output", str(output)]
                        build = subprocess.run(command, capture_output=True, text=True, timeout=40)
                        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                        run = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        self.assertEqual(run.stdout.strip(), expected)
