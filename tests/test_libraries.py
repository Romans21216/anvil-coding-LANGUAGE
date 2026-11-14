"""`library import name` pulls one-function files out of libraries-<name>/."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.modules import load_program  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

GCD = (
    "fn(gcd, a, b)\n"
    "  set local(x) = var(a)\n"
    "  set local(y) = var(b)\n"
    "  while local(y) != 0\n"
    "    set local(t) = local(y)\n"
    "    set local(y) = local(x) % local(y)\n"
    "    set local(x) = local(t)\n"
    "  end\n"
    "  output local(x)\n"
    "end\n"
)
LCM = (
    "fn(lcm, a, b)\n"
    "  set local(g) = call fn(gcd, var(a), var(b))\n"
    "  output var(a) / local(g) * var(b)\n"
    "end\n"
)
MAIN = (
    "library import math\n"
    "\n"
    "fn(main)\n"
    "  say call fn(gcd, 48, 18)\n"
    "end\n"
    "call fn(main)\n"
)


class LibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        library = self.base / "libraries-math"
        library.mkdir()
        (library / "gcd.ANVL").write_text(GCD, encoding="utf-8")
        (library / "lcm.ANVL").write_text(LCM, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_main(self, source: str = MAIN) -> pathlib.Path:
        path = self.base / "main.ANVL"
        path.write_text(source, encoding="utf-8")
        return path

    def test_imported_function_runs_on_both_backends(self) -> None:
        path = self._write_main()
        compiler = find_compiler(None)
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                functions, top, variables, arrays = parse(path, MAIN)
                executable = self.base / f"main_{backend}.exe"
                if backend == "native":
                    executable.write_bytes(
                        NativeCodegen(path, functions, top, variables, arrays).generate()
                    )
                else:
                    if compiler is None:
                        raise unittest.SkipTest("MSVC is not available")
                    c_file = self.base / "main.c"
                    c_file.write_text(
                        emit_c(path, functions, top, variables, arrays),
                        encoding="utf-8",
                    )
                    build_c(compiler[1], c_file, executable, True)
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=60
                )
                self.assertEqual(result.stdout.replace("\r\n", "\n"), "6\n")

    def test_a_function_nobody_calls_never_reaches_the_output(self) -> None:
        path = self._write_main()
        functions, top, variables, arrays = parse(path, MAIN)
        generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_gcd", generated)
        self.assertNotIn("anvil_lcm", generated)

    def test_the_used_function_makes_the_image_bigger(self) -> None:
        path = self._write_main()
        gcd_only = len(NativeCodegen(path, *parse(path, MAIN)).generate())
        both_source = MAIN.replace(
            "  say call fn(gcd, 48, 18)\n",
            "  say call fn(gcd, 48, 18)\n  say call fn(lcm, 4, 6)\n",
        )
        both_path = self._write_main(both_source)
        both = len(NativeCodegen(both_path, *parse(both_path, both_source)).generate())
        self.assertGreater(both, gcd_only)

    def test_a_missing_library_names_where_it_looked(self) -> None:
        path = self._write_main("library import algebra\n\nfn(main)\n  say 1\nend\ncall fn(main)\n")
        with self.assertRaises(CompileError) as caught:
            parse(path, path.read_text(encoding="utf-8"))
        message = str(caught.exception)
        self.assertIn("library 'algebra' not found", message)
        self.assertIn("libraries-algebra", message)

    def test_a_file_that_does_not_match_its_function_is_rejected(self) -> None:
        # One function per file, named after the file.
        (self.base / "libraries-math" / "gcd.ANVL").write_text(
            "fn(other, a)\n  output var(a)\nend\n", encoding="utf-8"
        )
        path = self._write_main()
        with self.assertRaises(CompileError) as caught:
            parse(path, path.read_text(encoding="utf-8"))
        self.assertIn("must define the function 'gcd'", str(caught.exception))

    def test_a_library_file_may_include_another_file(self) -> None:
        # The include registers its target under an aliased name; that must not
        # count as a second function in the library file.
        library = self.base / "libraries-math"
        (library / "helper.ANVL").write_text(
            "fn(helper, a)\n  output var(a) * 2\nend\n", encoding="utf-8"
        )
        (library / "twice.ANVL").write_text(
            'include fn(helper) -- "helper.ANVL"\n\n'
            "fn(twice, a)\n"
            "  output call fn(helper, var(a))\n"
            "end\n",
            encoding="utf-8",
        )
        path = self._write_main(
            "library import math\n\nfn(main)\n  say call fn(twice, 21)\nend\ncall fn(main)\n"
        )
        self.assertEqual(path.exists(), True)
        functions, top, variables, arrays = parse(path, path.read_text(encoding="utf-8"))
        self.assertIn("twice", functions)
        generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_twice", generated)

    def test_importing_the_same_library_twice_is_harmless(self) -> None:
        path = self._write_main(
            "library import math\nlibrary import math\n\n"
            "fn(main)\n  say call fn(gcd, 48, 18)\nend\ncall fn(main)\n"
        )
        functions, top, variables, arrays = parse(path, path.read_text(encoding="utf-8"))
        self.assertIn("gcd", functions)
        generated = emit_c(path, functions, top, variables, arrays)
        definition = "anvil_gcd(double anvil_gcd__a, double anvil_gcd__b) {"
        self.assertEqual(generated.count(definition), 1)

    def test_a_selectively_included_file_keeps_its_own_library_import(self) -> None:
        # The file states the dependency it has; the entry file should not have to
        # repeat it.
        (self.base / "ratio.ANVL").write_text(
            "library import math\n\n"
            "fn(ratio, a, b)\n"
            "  output call fn(gcd, var(a), var(b))\n"
            "end\n",
            encoding="utf-8",
        )
        source = (
            'include fn(ratio) -- "ratio.ANVL"\n\n'
            "fn(main)\n  say call fn(ratio--ratio, 48, 18)\nend\ncall fn(main)\n"
        )
        path = self._write_main(source)
        functions, top, variables, arrays = parse(path, source)
        self.assertIn("gcd", functions)
        generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_gcd", generated)
        self.assertIn("anvil_ratio__ratio", generated)

    def test_a_library_can_import_another_library(self) -> None:
        # libraries-a/f.ANVL says `library import b`; libraries-b sits at the
        # project root, one level above the library folder.
        second = self.base / "libraries-b"
        second.mkdir()
        (second / "g.ANVL").write_text(
            "fn(g, a)\n  output var(a) * 3\nend\n", encoding="utf-8"
        )
        (self.base / "libraries-math" / "linked.ANVL").write_text(
            "library import b\n\nfn(linked, a)\n  output call fn(g, var(a))\nend\n",
            encoding="utf-8",
        )
        source = (
            "library import math\n\nfn(main)\n  say call fn(linked, 7)\nend\n"
            "call fn(main)\n"
        )
        path = self._write_main(source)
        functions, top, variables, arrays = parse(path, source)
        self.assertIn("linked", functions)
        self.assertIn("g", functions)
        generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_g", generated)

    def test_libraries_that_import_each_other_are_a_diagnostic(self) -> None:
        # x imports y and y imports x. Before this was caught it recursed until
        # Python raised RecursionError, which is a compiler crash, not a message.
        (self.base / "libraries-x").mkdir()
        (self.base / "libraries-y").mkdir()
        (self.base / "libraries-x" / "xf.ANVL").write_text(
            "library import y\n\nfn(xf, a)\n  output call fn(yf, var(a))\nend\n",
            encoding="utf-8",
        )
        (self.base / "libraries-y" / "yf.ANVL").write_text(
            "library import x\n\nfn(yf, a)\n  output var(a) + 1\nend\n",
            encoding="utf-8",
        )
        source = "library import x\n\nfn(main)\n  say call fn(xf, 1)\nend\ncall fn(main)\n"
        path = self._write_main(source)
        with self.assertRaises(CompileError) as caught:
            parse(path, source)
        message = str(caught.exception)
        self.assertIn("circular library import", message)
        self.assertIn("libraries-x", message)
        self.assertIn("libraries-y", message)


if __name__ == "__main__":
    unittest.main()
