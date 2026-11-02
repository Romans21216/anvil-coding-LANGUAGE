"""End-to-end C compiler coverage for the new Anvil authoring syntax."""

from __future__ import annotations

import json
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


class AuthoringSyntaxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build_and_run(self, source: str, name: str = "game"):
        entry = self.root / f"{name}.ANVL"
        generated = self.root / f"{name}.generated.c"
        executable = self.root / f"{name}.exe"
        entry.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--generated-c", str(generated), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return entry, generated, executable, run.stdout.strip()

    def test_v2_var_is_local_and_varl_is_global(self):
        _, generated, _, output = self.build_and_run(
            """language version 2
set varl(score) = 5
fn(adjust, value)
  set var(value) = var(value) + 2
  set varl(score) = varl(score) + 1
  output var(value) + varl(score)
end
fn(main)
  set var(score) = 99
  output call fn(adjust, 10) + var(score) + varl(score)
end
call fn(main)
"""
        )
        self.assertEqual(output, "123")
        text = generated.read_text(encoding="utf-8")
        self.assertIn("main__score", text)
        self.assertIn("score", text)

    def test_metadata_round_trips_through_compiled_executable(self):
        entry, _, executable, output = self.build_and_run(
            'name "Anvil 🙂 Project"\nauthor("Romans21216")\nversion("0.2.1")\n'
            "fn(main)\n  output 23\nend\ncall fn(main)\n",
            "metadata",
        )
        self.assertEqual(output, "23")
        inspected = subprocess.run(
            [sys.executable, str(COMPILER), str(executable), "--inspect-metadata"],
            capture_output=True,
        )
        self.assertEqual(inspected.returncode, 0, inspected.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            json.loads(inspected.stdout.decode("utf-8")),
            {"name": "Anvil 🙂 Project", "author": "Romans21216", "version": "0.2.1"},
        )

    def test_metadata_inspection_ignores_same_marker_in_program_text(self):
        entry = self.root / "marker-text.ANVL"
        executable = self.root / "marker-text.exe"
        entry.write_text(
            'scene 2d\nfn(draw)\n  display text("ANVL-METADATA-1") -l(0, 0)\nend\n',
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        inspected = subprocess.run(
            [sys.executable, str(COMPILER), str(executable), "--inspect-metadata"],
            capture_output=True,
        )
        self.assertEqual(inspected.returncode, 0, inspected.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(inspected.stdout.decode("utf-8")), {})

    def test_callback_invocation_evaluates_arguments_in_source_order(self):
        _, generated, _, output = self.build_and_run(
            """language version 2
set varl(counter) = 0
fn(next)
  add varl(counter) 1
  output varl(counter)
end
fn(pair, left, right)
  output var(left) * 10 + var(right)
end
fn(main)
  set var(callback) = fnref(pair)
  output call var(callback, call fn(next), call fn(next))
end
call fn(main)
""",
            "callbacks",
        )
        self.assertEqual(output, "12")
        self.assertIn("_anvil_callable_dispatch_1", generated.read_text(encoding="utf-8"))

    def test_global_callback_uses_explicit_varl_storage(self):
        _, _, _, output = self.build_and_run(
            "language version 2\n"
            "fn(double_value, value)\n  output var(value) * 2\nend\n"
            "set varl(callback) = fnref(double_value)\n"
            "fn(main)\n  output call varl(callback, 12)\nend\n"
            "call fn(main)\n",
            "global-callback",
        )
        self.assertEqual(output, "24")

    def test_double_dash_selective_import_and_qualified_callback(self):
        library = self.root / "lib" / "player.ANVL"
        library.parent.mkdir()
        library.write_text(
            "fn(move, distance)\n  output var(distance) + 3\nend\n", encoding="utf-8"
        )
        _, _, _, output = self.build_and_run(
            'include fn(move) -- "lib/player.ANVL"\n'
            "fn(main)\n"
            "  set var(callback) = fnref(move -- player)\n"
            "  output call var(callback, 10)\n"
            "end\ncall fn(main)\n",
            "qualified",
        )
        self.assertEqual(output, "13")

    def test_cleared_callback_reports_its_original_call_site(self):
        entry = self.root / "cleared.ANVL"
        executable = self.root / "cleared.exe"
        entry.write_text(
            "language version 2\n"
            "fn(target, value)\n  output var(value) + 1\nend\n"
            "fn(main)\n"
            "  set var(callback) = fnref(target)\n"
            "  set var(callback) = null\n"
            "  output call var(callback, 4)\n"
            "end\ncall fn(main)\n",
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn(f"{entry}:8: function reference is unset or invalid", run.stderr)

    def test_version_one_null_cleanup_remains_a_noop(self):
        _, _, _, output = self.build_and_run(
            "set var(score) = 21\n"
            "set var(score) = null\n"
            "fn(main)\n  set var(score) = null\n  output var(score)\nend\n"
            "call fn(main)\n",
            "legacy-null",
        )
        self.assertEqual(output, "21")

    def test_compact_local_host_uses_loopback_and_receives_udp(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        entry = self.root / "local-network.ANVL"
        executable = self.root / "local-network.exe"
        entry.write_text(
            f'netip("192.0.2.23")\nnethost({port}) --local\n'
            "fn(main)\n"
            "  set local(value) = 0\n"
            "  while local(value) = 0\n"
            "    set local(value) = receive()\n"
            "  end\n"
            "  output local(value)\n"
            "end\ncall fn(main)\n",
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--release", "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                sender.sendto(struct.pack("<d", 27.0), ("127.0.0.1", port))
                time.sleep(0.01)
            stdout, stderr = process.communicate(timeout=1)
        finally:
            sender.close()
            if process.poll() is None:
                process.terminate()
                process.communicate()
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(stdout.strip(), "27")


if __name__ == "__main__":
    unittest.main()
