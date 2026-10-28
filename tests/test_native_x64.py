import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

from compiler.native_x64 import minimal_exit_exe
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


class NativeX64Tests(unittest.TestCase):
    def _run_source(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=5
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

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
            self.assertEqual(result.stdout, "Anvil output out of range\n")

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
            self.assertEqual(result.stdout, "Anvil numeric error at line 2\n")

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
            self.assertEqual(
                result.stdout, "Anvil array index error at line 3\n"
            )

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
