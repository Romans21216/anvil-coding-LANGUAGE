import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

from compiler.common import CompileError
from compiler.native_x64 import minimal_exit_exe
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


class NativeRunMixin:
    """Compiles a snippet with the native backend and runs the EXE."""

    def _run_source(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            try:
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=5
                )
            except OSError as error:
                # Defender sometimes quarantines a freshly written tiny PE
                # (WinError 225). That is the scanner, not the compiler.
                if getattr(error, "winerror", None) == 225:
                    raise unittest.SkipTest(
                        "Windows Defender quarantined the generated EXE"
                    )
                raise
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


class NativeX64Tests(NativeRunMixin, unittest.TestCase):
    def test_native_backend_compiles_functions_and_multiple_arguments(self):
        source = """\
fn(combine, left, right)
  output var(left) * 10 + var(right)
end
fn(main)
  output call fn(combine, 3, 8)
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "38\n")

    def test_native_compute_builtin_keeps_numeric_expression_semantics(self):
        self.assertEqual(self._run_source("fn(main)\n output compute(2 + 3) * 2\nend\n"), "10\n")

    def test_native_key_constants_are_numeric_values(self):
        self.assertEqual(self._run_source("fn(main)\n output A + SPACE + UP + ESCAPE + ENTER\nend\n"), "175\n")

    def test_native_backend_prints_negative_integer_result(self):
        source = """\
fn(main)
  output -42
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "-42\n")

    def test_native_backend_prints_fractional_numbers(self):
        cases = {
            "17.875": "17.875\n",
            "-0.75": "-0.75\n",
            "0.000005": "0.000005\n",
            "0.123456789": "0.123457\n",
            "12.5": "12.5\n",
            "12.9999999": "13\n",
            "-1.9999999": "-2\n",
            "-9223372036854775808": "-9223372036854775808\n",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                source = f"fn(main)\n  output {expression}\nend\ncall fn(main)\n"
                self.assertEqual(self._run_source(source), expected)

    def test_native_backend_rejects_out_of_range_output(self):
        for expression in ("100000000000000000000", "-100000000000000000000"):
            with self.subTest(expression=expression), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "range.ANVL"
                source = f"fn(main)\n  output {expression}\nend\ncall fn(main)\n"
                path.write_text(source, encoding="utf-8")
                functions, top, variables, arrays = parse(path, source)
                executable = pathlib.Path(temp) / "range.exe"
                executable.write_bytes(
                    NativeCodegen(path, functions, top, variables, arrays).generate()
                )
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=5
                )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(
                result.stdout,
                "Anvil output out of range (the native backend prints up to 9.2e18)\n",
            )

    def test_native_backend_reports_nonfinite_arithmetic_with_source_line(self):
        for expression in ("0 / 0", "1 / 0"):
            with self.subTest(expression=expression), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "bad-math.ANVL"
                source = f"fn(main)\n  output {expression}\nend\ncall fn(main)\n"
                path.write_text(source, encoding="utf-8")
                functions, top, variables, arrays = parse(path, source)
                executable = pathlib.Path(temp) / "bad-math.exe"
                executable.write_bytes(
                    NativeCodegen(path, functions, top, variables, arrays).generate()
                )
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=5
                )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr, f"Anvil numeric error at line 2 ({path})\n"
            )

    def test_native_backend_compiles_loop_and_boolean_operators(self):
        source = """\
fn(main)
  set var(total) = 0
  set var(index) = 0
  while var(index) < 4
    add var(total) var(index)
    add var(index) 1
  end
  if var(total) = 6 and 2 > 1
    output var(total)
  else
    output 0
  end
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "6\n")

    def test_native_backend_short_circuits_boolean_side_effects(self):
        source = """\
fn(tick)
  add var(count) 1
  output 1
end
fn(main)
  set var(count) = 0
  set var(and-result) = 0 and call fn(tick)
  set var(or-result) = 1 or call fn(tick)
  if var(count) = 0
    output 1
  else
    output 0
  end
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "1\n")

    def test_native_backend_handles_string_escapes(self):
        bs = chr(92)
        source = (
            "fn(main)\n"
            '  say "a' + bs + 'nb"\n'
            '  say "q' + bs + '"!"\n'
            '  say "p' + bs + bs + 'x"\n'
            '  say len("a' + bs + 'nb")\n'
            "end\ncall fn(main)\n"
        )
        self.assertEqual(
            self._run_source(source).replace("\r\n", "\n"), 'a\nb\nq"!\np\\x\n3\n'
        )

    def test_native_backend_runs_several_top_level_calls(self):
        source = """\
fn(first)
  say "a"
end

fn(second)
  say "b"
end

call fn(first)
call fn(second)
"""
        self.assertEqual(self._run_source(source).replace("\r\n", "\n"), "a\nb\n")

    def test_native_backend_runs_top_level_set_statements(self):
        source = """\
set var(base) = 10
set var(total) = var(base) * 2 + 1
set var(label) = "total="
seed(3)

fn(bump)
  set var(total) = var(total) + 1
end

fn(main)
  say var(label) & var(total)
  call fn(bump)
  say var(total)
  say rnd(1, 100)
end
call fn(main)
"""
        self.assertEqual(
            self._run_source(source).replace("\r\n", "\n"), "total=21\n22\n96\n"
        )

    def test_native_backend_supports_function_local_arrays(self):
        source = """\
fn(fill, n)
  array slots(3)
  for local(i) = 0 to 2
    set array(slots, local(i)) = var(n) + local(i)
  end
  array extra(2)
  set array(extra, 0) = array(slots, 0) * 10
  set array(extra, 1) = array(slots, 2)
  output array(extra, 0) + array(extra, 1)
end
fn(main)
  say call fn(fill, 1)
  say call fn(fill, 5)
end
call fn(main)
"""
        self.assertEqual(self._run_source(source).replace("\r\n", "\n"), "13\n57\n")

    def test_native_local_arrays_are_per_call(self):
        source = """\
fn(depth, n)
  array box(2)
  set array(box, 0) = var(n)
  if var(n) <= 0
    output array(box, 0)
  end
  set array(box, 1) = call fn(depth, var(n) - 1)
  output array(box, 0) + array(box, 1)
end
fn(main)
  say call fn(depth, 3)
end
call fn(main)
"""
        self.assertEqual(self._run_source(source).replace("\r\n", "\n"), "6\n")

    def test_native_local_array_bounds_error_reports_and_exits(self):
        source = """\
fn(bad)
  array tiny(2)
  set array(tiny, 5) = 1
end
fn(main)
  call fn(bad)
end
call fn(main)
"""
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "local-bounds.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "local-bounds.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=5
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Anvil array index error at line 3", result.stderr)

    def test_native_rejects_local_arrays_bigger_than_the_frame(self):
        source = (
            "fn(big)\n  array huge(600)\n  set array(huge, 0) = 1\nend\n"
            "fn(main)\n  call fn(big)\nend\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "local-big.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            with self.assertRaises(CompileError) as caught:
                NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertIn("native local arrays", str(caught.exception))

    def test_native_backend_supports_checked_global_array_reads_and_writes(self):
        source = """\
array values(4)
fn(next-index)
  add var(calls) 1
  output 2
end
fn(main)
  set var(calls) = 0
  set array(values, call fn(next-index)) = 17
  set array(values, 3) = array(values, 2) + 4
  output array(values, 2) + array(values, 3) + var(calls)
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "39\n")

    def test_native_backend_reports_global_array_bounds_errors(self):
        for index in ("-1", "2", "0.5"):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "array-bounds.ANVL"
                source = (
                    "array values(2)\n"
                    "fn(main)\n"
                    f"  output array(values, {index})\n"
                    "end\n"
                    "call fn(main)\n"
                )
                path.write_text(source, encoding="utf-8")
                functions, top, variables, arrays = parse(path, source)
                executable = pathlib.Path(temp) / "array-bounds.exe"
                executable.write_bytes(
                    NativeCodegen(path, functions, top, variables, arrays).generate()
                )
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=5
                )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr, f"Anvil array index error at line 3 ({path})\n"
            )

    def test_native_names_unsupported_builtins_and_suggests_spellings(self):
        cases = {
            'fn(main)\n  say image_load("a.bmp")\nend\ncall fn(main)\n':
                "image_load() is not available in the native x64 backend yet",
            "fn(main)\n  say random(1, 10)\nend\ncall fn(main)\n":
                "did you mean rnd(low, high)?",
        }
        for source, expected in cases.items():
            with tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "unsupported.ANVL"
                path.write_text(source, encoding="utf-8")
                functions, top, variables, arrays = parse(path, source)
                with self.assertRaises(CompileError) as caught:
                    NativeCodegen(path, functions, top, variables, arrays).generate()
            self.assertIn(expected, str(caught.exception))

    def test_native_accepts_text_arguments(self) -> None:
        program = (
            "fn(greet, who)\n  output \"hi \" & var(who)\nend\n"
            "fn(main)\n  say call fn(greet, \"ada\")\nend\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "text-args.ANVL"
            path.write_text(program, encoding="utf-8")
            functions, top, variables, arrays = parse(path, program)
            executable = pathlib.Path(temp) / "text-args.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=20
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "hi ada\n")

    def test_native_text_overflow_reports_and_exits(self):
        source = (
            'fn(main)\n  set var(w) = "' + "a" * 300 + '"\n  say len(var(w))\n'
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "text-overflow.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "text-overflow.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=5
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("text is limited to 255 characters", result.stderr)

    def test_native_backend_rejects_aggregate_array_data_before_pe_allocation(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for comment in ("", " # crosses cap"):
            with self.subTest(comment=comment), tempfile.TemporaryDirectory() as temp:
                source = pathlib.Path(temp) / "large-arrays.ANVL"
                executable = pathlib.Path(temp) / "large-arrays.exe"
                source.write_text(
                    "array a(1048576)\n"
                    "array b(1048576)\n"
                    f"array c(1048576){comment}\n"
                    "fn(main)\n  output 1\nend\ncall fn(main)\n",
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(root / "compiler" / "anvil.py"),
                        str(source),
                        "--backend",
                        "native",
                        "--output",
                        str(executable),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            self.assertEqual(result.returncode, 1)
            self.assertIn(f"{source}:3: direct native global data needs", result.stderr)
            self.assertIn("the limit is 16777216 bytes", result.stderr)
            self.assertFalse(executable.exists())

    def test_native_cli_builds_exe_without_generated_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(__file__).resolve().parents[1]
            source = pathlib.Path(temp) / "cli.ANVL"
            executable = pathlib.Path(temp) / "cli.exe"
            source.write_text("fn(main)\n  output 24\nend\ncall fn(main)\n", encoding="utf-8")
            build = subprocess.run(
                [
                    sys.executable,
                    str(root / "compiler" / "anvil.py"),
                    str(source),
                    "--backend",
                    "native",
                    "--output",
                    str(executable),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertIn("no C/Rust compiler", build.stdout)
            self.assertTrue(executable.is_file())
            self.assertFalse(source.with_suffix(".generated.c").exists())
            run = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=5
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "24\n")

    def test_native_backend_supports_inclusive_ascending_and_descending_for(self):
        source = """\
fn(main)
  set var(total) = 0
  for local(up) = 1 to 4
    add var(total) local(up)
  end
  for local(down) = 3 to 1 step -1
    add var(total) local(down)
  end
  for local(zero) = 1 to 3 step 0
    add var(total) 100
  end
  output var(total)
end
call fn(main)
"""
        self.assertEqual(self._run_source(source), "16\n")

    def test_custom_pe32_plus_image_executes_without_external_compiler(self):
        image = minimal_exit_exe(42)
        pe_offset = struct.unpack_from("<I", image, 0x3C)[0]
        self.assertEqual(image[:2], b"MZ")
        self.assertEqual(image[pe_offset:pe_offset + 4], b"PE\0\0")
        machine, sections = struct.unpack_from("<HH", image, pe_offset + 4)
        self.assertEqual(machine, 0x8664)
        self.assertEqual(sections, 3)
        optional = pe_offset + 4 + 20
        self.assertEqual(struct.unpack_from("<H", image, optional)[0], 0x20B)
        self.assertEqual(struct.unpack_from("<H", image, optional + 68)[0], 3)

        with tempfile.TemporaryDirectory() as temp:
            executable = pathlib.Path(temp) / "anvil-native-smoke.exe"
            executable.write_bytes(image)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=5
            )
        self.assertEqual(result.returncode, 42, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
