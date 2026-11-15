"""library import: folders of one-function-per-file, loaded into the program."""

import pathlib
import tempfile
import unittest

from compiler.common import CompileError
from compiler.parser import parse


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def library(self, name, *files):
        folder = self.root / f"libraries-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        for file_name, body in files:
            (folder / f"{file_name}.ANVL").write_text(body, encoding="utf-8")
        return folder

    def program(self, source, name="main.ANVL"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def parse_program(self, path):
        return parse(path, path.read_text(encoding="utf-8"))


class LibraryImportTest(LibraryFixture):
    def test_import_brings_in_every_file_as_a_function(self):
        self.library(
            "algebra",
            ("double", "fn(double, n)\n  output var(n) * 2\nend\n"),
            ("triple", "fn(triple, n)\n  output var(n) * 3\nend\n"),
        )
        path = self.program(
            "library import algebra\n\n"
            "fn(main)\n  output call fn(double, 2)\nend\n"
            "call fn(main)\n"
        )
        functions, top, variables, arrays = self.parse_program(path)
        self.assertIn("double", functions)
        self.assertIn("triple", functions)

    def test_a_file_must_define_the_function_named_after_it(self):
        self.library("algebra", ("double", "fn(twice, n)\n  output var(n) * 2\nend\n"))
        path = self.program("library import algebra\n")
        with self.assertRaises(CompileError) as raised:
            self.parse_program(path)
        self.assertIn("a library file must define the function 'double'", str(raised.exception))

    def test_two_functions_in_one_file_are_rejected(self):
        self.library(
            "algebra",
            ("double", "fn(double, n)\n  output var(n) * 2\nend\nfn(triple, n)\n  output var(n) * 3\nend\n"),
        )
        path = self.program("library import algebra\n")
        with self.assertRaises(CompileError):
            self.parse_program(path)

    def test_a_missing_library_says_where_it_looked(self):
        path = self.program("library import algebra\n")
        with self.assertRaises(CompileError) as raised:
            self.parse_program(path)
        message = str(raised.exception)
        self.assertIn("not found", message)
        self.assertIn("libraries-algebra", message)

    def test_importing_the_same_library_twice_is_harmless(self):
        self.library("algebra", ("double", "fn(double, n)\n  output var(n) * 2\nend\n"))
        path = self.program(
            "library import algebra\nlibrary import algebra\n\n"
            "fn(main)\n  output call fn(double, 2)\nend\n"
            "call fn(main)\n"
        )
        functions, top, variables, arrays = self.parse_program(path)
        self.assertIn("double", functions)

    def test_a_library_in_a_parent_folder_is_found(self):
        self.library("algebra", ("double", "fn(double, n)\n  output var(n) * 2\nend\n"))
        path = self.program(
            "library import algebra\n", name="projects/game/main.ANVL"
        )
        functions, top, variables, arrays = self.parse_program(path)
        self.assertIn("double", functions)

    def test_import_below_top_level_is_refused(self):
        path = self.program(
            "fn(main)\n  library import algebra\nend\ncall fn(main)\n"
        )
        with self.assertRaises(CompileError) as raised:
            self.parse_program(path)
        self.assertIn("must be at top level", str(raised.exception))


class ShippedLibrariesTest(unittest.TestCase):
    def test_the_demo_imports_five_shipped_folders(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        path = root / "examples" / "libraries_demo.ANVL"
        functions, top, variables, arrays = parse(path, path.read_text(encoding="utf-8"))
        for name in ("gcd", "primes-below", "celsius-to-fahrenheit", "area-rect", "reflect-y"):
            self.assertIn(name, functions)

    def test_every_shipped_library_file_names_its_own_function(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for folder in sorted(root.glob("libraries-*")):
            self.assertTrue(folder.is_dir(), folder)
            for file in sorted(folder.glob("*.ANVL")):
                text = file.read_text(encoding="utf-8")
                self.assertIn(f"fn({file.stem}", text, f"{file} does not define fn({file.stem}, ...)")
