"""Fuzz the UDP receive path with malformed datagrams (Part 8 sections 8.14/8.15).

The transport carries a single IEEE-754 double per datagram. The test hosts a
real program on loopback, sends short/long/empty payloads and NaN/infinite bit
patterns, then a valid value, and checks that only the valid value is accepted
and that the program never reports a non-finite number.
"""

from __future__ import annotations

import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402

SERVER = """net host({port})
fn(main)
  say var(net_ok)
  set var(last) = 0
  set var(i) = 0
  while var(i) < 150
    set var(v) = receive()
    set var(last) = var(v)
    set var(i) = var(i) + 1
    wait 0.005
  end
  say var(last)
end
call fn(main)
"""
VALID = 2.5


# A fixed port outside the Windows dynamic range; ephemeral ports can fall in
# Hyper-V/WinNAT excluded ranges where bind() fails.
PORT = 39001


def destinations(port: int) -> list[tuple[str, int]]:
    """Loopback plus the machine's primary address.

    A generated program binds INADDR_ANY; on Windows the firewall can accept
    datagrams addressed to the LAN address while dropping those sent to
    127.0.0.1, so the test offers both.
    """
    targets = ["127.0.0.1"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            local = probe.getsockname()[0]
        if local and local != "127.0.0.1":
            targets.append(local)
    except OSError:
        pass
    return [(target, port) for target in targets]


class NetworkFuzzTests(unittest.TestCase):
    def test_malformed_datagrams_are_ignored_and_a_valid_one_is_accepted(self) -> None:
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        source = SERVER.format(port=PORT)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            path = temp_path / "server.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            c_file = temp_path / "server.c"
            c_file.write_text(
                emit_c(path, functions, top, variables, arrays), encoding="utf-8"
            )
            executable = temp_path / "server.exe"
            build_c(compiler[1], c_file, executable, release=True)
            process = subprocess.Popen(
                [str(executable)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready = process.stdout.readline().strip()
                self.assertEqual(ready, "1", "the program could not host on loopback")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    junk = [
                        b"",
                        b"\x00",
                        b"\x00" * 4,
                        b"\x00" * 7,
                        b"\x00" * 9,
                        b"\x00" * 16,
                        struct.pack("<d", float("nan")),
                        struct.pack("<d", float("inf")),
                        struct.pack("<d", float("-inf")),
                        bytes([0x7F, 0xF8, 0, 0, 0, 0, 0, 0]),
                        bytes(range(8)),
                    ]
                    for target in destinations(PORT):
                        for payload in junk:
                            sender.sendto(payload, target)
                    # Give the program time to consume the junk before the
                    # only value that must be accepted.
                    import time

                    time.sleep(0.3)
                    for target in destinations(PORT):
                        sender.sendto(struct.pack("<d", VALID), target)
                stdout, stderr = process.communicate(timeout=30)
                stdout = ready + "\n" + stdout
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        lines = [line.strip() for line in stdout.replace("\r\n", "\n").splitlines() if line.strip()]
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[-1], str(VALID), f"stdout={lines!r} stderr={stderr!r}")
        joined = " ".join(lines).lower()
        self.assertNotIn("nan", joined)
        self.assertNotIn("inf", joined)


if __name__ == "__main__":
    unittest.main()
