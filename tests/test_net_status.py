"""Network statements report success through the `net_ok` variable."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402

# A UDP join needs no listening peer, so 127.0.0.1 succeeds deterministically
# while 256.0.0.1 is not a valid address.
JOIN_OK_SOURCE = (
    "fn(main)\n"
    '  net join("127.0.0.1", 9000)\n'
    "  say var(net_ok)\n"
    "end\n"
    "call fn(main)\n"
)

JOIN_BAD_SOURCE = (
    "fn(main)\n"
    '  net join("256.0.0.1", 9000)\n'
    "  say var(net_ok)\n"
    "end\n"
    "call fn(main)\n"
)


def run_c(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "net.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        c_file = temp_path / "net.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "net.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=30
        )


class NetworkStatusTests(unittest.TestCase):
    def test_a_valid_join_reports_one(self) -> None:
        result = run_c(JOIN_OK_SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "1\n")

    def test_an_invalid_address_reports_zero(self) -> None:
        result = run_c(JOIN_BAD_SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "0\n")

    def test_the_status_variable_is_registered_by_the_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "net.ANVL"
            path.write_text(JOIN_OK_SOURCE, encoding="utf-8")
            functions, top, variables, arrays = parse(path, JOIN_OK_SOURCE)
        self.assertIn("net_ok", variables)

    def test_the_generated_c_keeps_the_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "net.ANVL"
            path.write_text(JOIN_OK_SOURCE, encoding="utf-8")
            functions, top, variables, arrays = parse(path, JOIN_OK_SOURCE)
            generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_net_ok = (double)anvil_net_join", generated)
        self.assertNotIn("(void)anvil_net_join", generated)


if __name__ == "__main__":
    unittest.main()
