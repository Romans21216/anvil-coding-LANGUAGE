import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

from compiler.native_x64 import Pe32Plus, minimal_exit_exe
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse

ROOT = pathlib.Path(__file__).resolve().parents[1]

class NativeX64Tests(unittest.TestCase):
    def test_generated_native_executable_advertises_its_icon_resources(self):
        source = "fn(main)\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "icon.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            exe = NativeCodegen(path, functions, top, variables, arrays).generate()

        pe_offset = struct.unpack_from("<I", exe, 0x3C)[0]
        optional_offset = pe_offset + 4 + 20
        resource_rva, resource_size = struct.unpack_from("<II", exe, optional_offset + 128)
        self.assertGreater(resource_rva, 0)
        self.assertGreater(resource_size, 0)

    def test_native_executable_embeds_anvil_icon_resources(self):
        icon = (ROOT / "assets" / "icons" / "anvil-executable.ico").read_bytes()
        exe = Pe32Plus(b"\xC3", [("KERNEL32.dll", "ExitProcess")], icon=icon).build()
        pe_offset = struct.unpack_from("<I", exe, 0x3C)[0]
        coff_offset = pe_offset + 4
        section_count = struct.unpack_from("<H", exe, coff_offset + 2)[0]
        optional_size = struct.unpack_from("<H", exe, coff_offset + 16)[0]
        optional_offset = coff_offset + 20
        resource_rva, resource_size = struct.unpack_from("<II", exe, optional_offset + 128)
        self.assertEqual(section_count, 4)
        self.assertGreater(resource_size, 0)

        section_table = optional_offset + optional_size
        resource_section = None
        for index in range(section_count):
            offset = section_table + index * 40
            name, virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
                "<8sIIII", exe, offset
            )
            if name.rstrip(b"\0") == b".rsrc":
                resource_section = (virtual_address, raw_offset)
                break
        self.assertIsNotNone(resource_section)
        section_rva, raw_offset = resource_section
        root_offset = raw_offset + resource_rva - section_rva
        named, identifiers = struct.unpack_from("<HH", exe, root_offset + 12)
        self.assertEqual((named, identifiers), (0, 2))
        type_entries = [struct.unpack_from("<II", exe, root_offset + 16 + index * 8)
                        for index in range(identifiers)]
        self.assertEqual({entry[0] for entry in type_entries}, {3, 14})

        def directory_entries(relative_offset):
            directory = root_offset + relative_offset
            count = struct.unpack_from("<H", exe, directory + 14)[0]
            return [struct.unpack_from("<II", exe, directory + 16 + i * 8)
                    for i in range(count)]

        group_type = next(entry for entry in type_entries if entry[0] == 14)
        group_id = directory_entries(group_type[1] & 0x7FFFFFFF)[0]
        language = directory_entries(group_id[1] & 0x7FFFFFFF)[0]
        data_entry_offset = root_offset + (language[1] & 0x7FFFFFFF)
        group_rva, group_size = struct.unpack_from("<II", exe, data_entry_offset)
        group_offset = raw_offset + group_rva - section_rva
        reserved, kind, icon_count = struct.unpack_from("<HHH", exe, group_offset)
        self.assertEqual((reserved, kind, icon_count), (0, 1, 7))
        self.assertEqual(group_size, 6 + 14 * icon_count)

    def test_native_icon_resource_rejects_truncated_ico(self):
        with self.assertRaisesRegex(ValueError, "valid ICO"):
            Pe32Plus(b"\xC3", [], icon=b"bad").build()

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
            self.assertEqual(result.stdout, f"Anvil numeric error at line 2 ({path})\n")

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
                result.stdout, f"Anvil array index error at line 3 ({path})\n"
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
