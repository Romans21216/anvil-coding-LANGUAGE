import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def compile_source(source, temp, name="probe.ANVL", emit_c=False, check=False,
                   build=True):
    path = pathlib.Path(temp) / name
    path.write_text(source, encoding="utf-8")
    arguments = [sys.executable, str(COMPILER), str(path)]
    if emit_c:
        arguments += ["--emit-c", str(path.with_suffix(".c"))]
    if check:
        arguments.append("--check")
    if build:
        arguments += ["-o", str(path.with_suffix(".exe"))]
    return path, subprocess.run(arguments, capture_output=True, text=True)


class TextAndPrintTests(unittest.TestCase):
    def run_program(self, source):
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            executable = path.with_suffix(".exe")
            self.assertTrue(executable.exists(), result.stdout)
            run = subprocess.run(
                [str(executable)], capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            return run.stdout.replace("\r\n", "\n").splitlines()

    def test_print_works_from_any_function_and_shares_one_number_format(self):
        lines = self.run_program(
            "fn(show, value)\n"
            '  print "value = " + var(value)\n'
            "  output 0\n"
            "end\n"
            "fn(main)\n"
            "  call fn(show, 12.5663706143592)\n"
            '  print "two: " + 1.5 + " and " + 2\n'
            "  print\n"
            '  print "literal"\n'
            "  output 0\n"
            "end\n"
        )
        self.assertEqual(
            lines,
            ["value = 12.5663706143592", "two: 1.5 and 2", "", "literal", "0"],
        )

    def test_display_text_joins_many_terms_through_the_string_pipeline(self):
        source = (
            "scene 2d\n"
            "fn(draw)\n"
            "  set local(x) = 2.5\n"
            '  display text("a=" + local(x) + " b=" + (local(x) * 2) + " c") -l(10, 10)\n'
            "end\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp, "hud.ANVL", emit_c=True)
            generated_path = path.with_suffix(".c")
            self.assertEqual(result.returncode, 0, result.stderr)
            generated = generated_path.read_text(encoding="utf-8")
        self.assertIn("anvil_str_cat(", generated)
        self.assertIn("anvil_str_num(", generated)
        self.assertNotIn("%.0f", generated)

    def test_else_if_chain_selects_exactly_one_branch(self):
        lines = self.run_program(
            "set var(score) = 84\n"
            "fn(grade)\n"
            "  if var(score) >= 90\n"
            "    output 4\n"
            "  else if var(score) >= 80\n"
            "    output 3\n"
            "  else if var(score) >= 70\n"
            "    output 2\n"
            "  else\n"
            "    output 1\n"
            "  end\n"
            "end\n"
            "fn(main)\n"
            "  output call fn(grade)\n"
            "end\n"
        )
        self.assertEqual(lines, ["3"])

    def test_quality_of_life_builtins(self):
        lines = self.run_program(
            "fn(main)\n"
            '  print "round " + round(2.715, 2) + " " + round(7 / 2) + " " + round(1234, -2)\n'
            '  print "clamp " + clamp(15, 0, 10) + " " + clamp(-4, 0, 10)\n'
            '  print "mod " + mod(-5, 3) + " " + mod(5, 3)\n'
            '  print "pow " + pow(2, 10) + " sign " + sign(-3.2) + " " + sign(0)\n'
            '  print "hypot " + hypot(3, 4) + " atan2 " + round(atan2(1, 1) * 4, 6)\n'
            '  print "log " + round(log(exp(2)), 6)\n'
            "  output 0\n"
            "end\n"
        )
        self.assertEqual(
            lines,
            [
                "round 2.72 4 1200",
                "clamp 10 0",
                "mod 1 2",
                "pow 1024 sign -1 0",
                "hypot 5 atan2 3.141593",
                "log 2",
                "0",
            ],
        )

    def test_text_builtins(self):
        lines = self.run_program(
            "fn(main)\n"
            '  print "upper " + upper("anvil rocks")\n'
            '  print "lower " + lower("ANVIL")\n'
            '  print "trim [" + trim("   spaced   ") + "]"\n'
            '  print "mid " + mid("abcdef", 2, 3) + " " + mid("abc", 1, 99)\n'
            '  print "replace " + replace("a-b-c", "-", "+")\n'
            '  print "len " + len("hello") + " ord " + ord("A") + " find " + find("hello world", "world")\n'
            '  print "chr " + chr(65) + chr(66) + chr(67)\n'
            '  print "equal " + ("abc" = "abc") + " " + ("abc" != "abd")\n'
            "  output 0\n"
            "end\n"
        )
        self.assertEqual(
            lines,
            [
                "upper ANVIL ROCKS",
                "lower anvil",
                "trim [spaced]",
                "mid cde bc",
                "replace a+b+c",
                "len 5 ord 65 find 6",
                "chr ABC",
                "equal 1 1",
                "0",
            ],
        )

    def test_utf8_code_point_operations_never_split_a_code_point(self):
        lines = self.run_program(
            "fn(main)\n"
            '  print "bytes " + len("é")\n'
            '  print "points " + utf8_len("é")\n'
            '  print "emoji points " + utf8_len("🙂")\n'
            '  print "char " + utf8_char("aé🙂", 1)\n'
            '  print "slice " + utf8_mid("aé🙂z", 1, 2)\n'
            '  print "past [" + utf8_char("a", 5) + "]"\n'
            "  output 0\n"
            "end\n"
        )
        self.assertEqual(
            lines,
            [
                "bytes 2",
                "points 1",
                "emoji points 1",
                "char é",
                "slice é🙂",
                "past []",
                "0",
            ],
        )

    def test_top_level_var_is_global_in_language_version_2(self):
        lines = self.run_program(
            "language version 2\n"
            "set var(score) = 7\n"
            "fn(main)\n"
            '  print "score " + varl(score)\n'
            "  output 0\n"
            "end\n"
        )
        self.assertEqual(lines, ["score 7", "0"])


class DiagnosticTests(unittest.TestCase):
    def test_error_reports_location_line_caret_and_help(self):
        source = (
            "fn(main)\n"
            '  print "score " + 1 * "x"\n'
            "  output 0\n"
            "end\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error: ", result.stderr)
        self.assertIn(f"--> {path}:2:", result.stderr)
        self.assertIn("^", result.stderr)
        self.assertIn("= help: ", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_name_gets_a_did_you_mean_hint(self):
        source = "fn(main)\n  output fllor(2.5)\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown name", result.stderr)
        self.assertIn("did you mean `floor(...)`?", result.stderr)

    def test_else_if_misuse_explains_the_alternative(self):
        source = "fn(main)\n  else if 1\n  end\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("'else if' must follow an if", result.stderr)
        self.assertIn("= help: ", result.stderr)

    def test_display_without_a_scene_warns_but_still_builds(self):
        source = "fn(main)\n  display rect(0, 0, 10, 10)\n  output 0\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp, check=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("warning: ", result.stderr)
            self.assertIn("has no effect without a scene", result.stderr)
            self.assertIn(f"--> {path}:2:", result.stderr)

    def test_output_inside_a_loop_warns_that_the_loop_runs_once(self):
        source = (
            "fn(main)\n"
            "  for local(i) = 0 to 3\n"
            "    output local(i)\n"
            "  end\n"
            "  output 0\n"
            "end\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path, result = compile_source(source, temp, check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("`output` returns from the function", result.stderr)


if __name__ == "__main__":
    unittest.main()
