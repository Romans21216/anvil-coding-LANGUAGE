"""Extension functions: C++/C# DLLs and Anvil sources, on both backends."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler import extensions  # noqa: E402
from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.modules import load_program  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

SOURCE_CPP = """
extern "C" __declspec(dllexport) double anvil_ext_gcd(double a, double b) {
  long x = (long)a, y = (long)b;
  if (x < 0) x = -x;
  if (y < 0) y = -y;
  while (y != 0) { long t = x % y; x = y; y = t; }
  return (double)x;
}
extern "C" __declspec(dllexport) double anvil_ext_lcm(double a, double b) {
  long x = (long)a, y = (long)b;
  if (x == 0 || y == 0) return 0.0;
  return (double)(x / (long)anvil_ext_gcd(a, b) * y);
}
"""

PROGRAM = "fn(main)\n  say gcd(48, 18)\n  say lcm(4, 6)\nend\ncall fn(main)\n"
EXPECTED = "6\n12\n"


def dev_command(compiler: pathlib.Path, directory: pathlib.Path, body: str) -> subprocess.CompletedProcess:
    """Run a command with the MSVC environment loaded (cl.exe needs it)."""
    install_root = compiler.parents[7]
    devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
    script = directory / "run.cmd"
    script.write_text(
        '@echo off\ncall "' + str(devcmd) + '" -arch=x64 >nul\nif errorlevel 1 exit /b %errorlevel%\n'
        + body
        + "\nexit /b %errorlevel%\n",
        encoding="utf-8",
    )
    return subprocess.run(
        ["cmd.exe", "/d", "/c", str(script)], capture_output=True, text=True, timeout=300
    )


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        found = find_compiler(None)
        if found is None:
            raise unittest.SkipTest("MSVC is not available")
        cls.compiler = pathlib.Path(found[1])
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = pathlib.Path(cls.temp.name)
        (cls.base / "mathx.cpp").write_text(SOURCE_CPP, encoding="utf-8")
        built = dev_command(cls.compiler, cls.base, "cd /d %~dp0\ncl /nologo /LD /O2 mathx.cpp /Fe:mathx.dll")
        if built.returncode != 0:
            cls.temp.cleanup()
            raise unittest.SkipTest(f"could not build the sample DLL: {built.stdout[-400:]}")
        cls.manifest = cls.base / "mathx.json"
        cls.manifest.write_text(
            json.dumps(
                {
                    "name": "mathx",
                    "kind": "dll",
                    "dll": "mathx.dll",
                    "lib": "mathx.lib",
                    "functions": [
                        {"name": "gcd", "symbol": "anvil_ext_gcd", "arity": 2},
                        {"name": "lcm", "symbol": "anvil_ext_lcm", "arity": 2},
                    ],
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        extensions.reset()
        cls.temp.cleanup()

    def setUp(self) -> None:
        extensions.reset()

    def tearDown(self) -> None:
        extensions.reset()

    def _run(self, source: str, backend: str) -> str:
        extensions.reset()
        manifest = extensions.load_manifest(self.manifest)
        extensions.register(manifest)
        work = pathlib.Path(tempfile.mkdtemp(dir=self.base))
        path = work / "program.ANVL"
        path.write_text(source, encoding="utf-8")
        program = load_program(path, source)
        executable = work / "program.exe"
        if backend == "native":
            executable.write_bytes(
                NativeCodegen(
                    path,
                    program.functions,
                    program.top,
                    program.variables,
                    program.arrays,
                ).generate()
            )
        else:
            c_file = work / "program.c"
            c_file.write_text(
                emit_c(
                    path,
                    program.functions,
                    program.top,
                    program.variables,
                    program.arrays,
                ),
                encoding="utf-8",
            )
            build_c(
                str(self.compiler), c_file, executable, True, extensions.libraries()
            )
        shutil.copyfile(manifest.dll, work / manifest.dll.name)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
        return result.stdout.replace("\r\n", "\n")

    def test_dll_functions_are_callable_on_both_backends(self) -> None:
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                self.assertEqual(self._run(PROGRAM, backend), EXPECTED)

    def test_arity_is_checked_against_the_manifest(self) -> None:
        with self.assertRaises(Exception) as caught:
            self._run("fn(main)\n  say gcd(1)\nend\ncall fn(main)\n", "c")
        self.assertIn("gcd() expects 2 argument(s), got 1", str(caught.exception))

    def test_a_builtin_name_cannot_be_shadowed(self) -> None:
        bad = self.base / "bad.json"
        bad.write_text(
            json.dumps(
                {
                    "name": "bad",
                    "kind": "dll",
                    "dll": "mathx.dll",
                    "lib": "mathx.lib",
                    "functions": [{"name": "sqrt", "symbol": "anvil_ext_gcd", "arity": 1}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(extensions.ExtensionError) as caught:
            extensions.register(extensions.load_manifest(bad))
        self.assertIn("already a builtin", str(caught.exception))

    def test_anvil_sourced_extensions_need_no_dll(self) -> None:
        source_file = self.base / "stats.ANVL"
        source_file.write_text(
            "fn(mean2, a, b)\n  output (var(a) + var(b)) / 2\nend\n", encoding="utf-8"
        )
        manifest_path = self.base / "stats.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "name": "stats",
                    "kind": "anvil",
                    "source": "stats.ANVL",
                    "functions": [{"name": "mean2", "arity": 2}],
                }
            ),
            encoding="utf-8",
        )
        extension = extensions.load_manifest(manifest_path)
        extensions.register(extension)
        self.assertEqual(extension.source, source_file.resolve())
        self.assertEqual(extensions.libraries(), [])
        self.assertEqual(extensions.dlls(), [])


if __name__ == "__main__":
    unittest.main()
