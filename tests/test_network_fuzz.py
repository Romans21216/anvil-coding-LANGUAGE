"""Fuzz the UDP packet envelope: malformed input must never be accepted.

Part 8 asks for malformed packets to be fuzzed before any Internet claim. The
runtime documents strict 24-byte framing; these tests hold it to that promise by
sending real datagrams from a Python socket into a program built by the C
backend.
"""

import pathlib
import random
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

MAGIC = b"ANVP"


def envelope(sequence, message_id, value, *, version=1, payload_type=1,
             reserved=b"\0\0", magic=MAGIC):
    return (
        magic
        + bytes((version, payload_type))
        + reserved
        + struct.pack(">II", sequence, message_id)
        + struct.pack(">d", value)
    )


def free_port() -> int:
    return random.randint(45000, 60000)


class PacketFuzzTests(unittest.TestCase):
    def _server(self, temporary: str, body: str):
        """Build and start a program that hosts on a free port and runs ``body``.

        Ports are chosen randomly, so a collision or a slow spawn is retried on a
        fresh port instead of failing the suite; the chosen port lands on
        ``self.port``.
        """
        folder = pathlib.Path(temporary)
        for attempt in range(3):
            port = free_port()
            source = folder / f"server{attempt}.ANVL"
            source.write_text(
                "fn(main)\n"
                f"  net host({port}) --local\n"
                '  print "ready"\n'
                + body
                + "end\n",
                encoding="utf-8",
            )
            executable = source.with_suffix(".exe")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            process = subprocess.Popen(
                [str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
            self.addCleanup(process.kill)
            first = process.stdout.readline().strip()
            if first == "ready":
                self.port = port
                return process
            process.kill()
            process.wait(timeout=10)
        self.fail("server did not report readiness on three ports")

    def test_malformed_datagrams_are_ignored(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            process = self._server(
                temporary,
                "  set local(n) = 0\n"
                "  while packet_id() < 0 and local(n) < 4000000\n"
                "    add local(n) 1\n"
                "    set var(v) = packet_receive()\n"
                "  end\n"
                '  print "id=" + packet_id() + " value=" + var(v)\n',
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.addCleanup(sock.close)
            malformed = [
                b"",
                MAGIC,
                b"ANVX" + bytes(20),
                bytes(23),
                bytes(25),
                envelope(1, 999, 1.0, version=0),
                envelope(1, 999, 1.0, version=2),
                envelope(1, 999, 1.0, payload_type=0),
                envelope(1, 999, 1.0, payload_type=2),
                envelope(1, 999, 1.0, reserved=b"\x01\0"),
                envelope(0, 999, 1.0),
                envelope(1, 999, float("nan")),
                envelope(1, 999, float("inf")),
                envelope(1, 999, 1.0) + b"trailing",
            ]
            for packet in malformed:
                sock.sendto(packet, ("127.0.0.1", self.port))
                time.sleep(0.004)
            sock.sendto(envelope(1, 7, 2.5), ("127.0.0.1", self.port))
            stdout, stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("id=7 value=2.5", stdout)
        self.assertNotIn("id=999", stdout)

    def test_replayed_and_stale_sequences_are_rejected(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            process = self._server(
                temporary,
                "  set var(last) = -1\n"
                "  set local(n) = 0\n"
                "  while packet_id() != 1 and local(n) < 8000000\n"
                "    add local(n) 1\n"
                "    set var(v) = packet_receive()\n"
                "    if packet_id() != var(last)\n"
                "      set var(last) = packet_id()\n"
                '      print "accept=" + var(last)\n'
                "    end\n"
                "  end\n",
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.addCleanup(sock.close)
            for sequence, message_id in ((5, 10), (5, 11), (4, 12), (6, 13), (7, 1)):
                sock.sendto(
                    envelope(sequence, message_id, float(message_id)),
                    ("127.0.0.1", self.port),
                )
                time.sleep(0.05)
            stdout, stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, stderr)
        accepted = [
            int(line.split("=", 1)[1])
            for line in stdout.splitlines()
            if line.startswith("accept=") and not line.endswith("=1")
        ]
        # The duplicate (sequence 5) and the stale (sequence 4) packets must not
        # disturb the stream; the newer sequence 6 is accepted.
        self.assertEqual(accepted, [10, 13])

    def test_a_malformed_flood_does_not_block_a_later_valid_packet(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            process = self._server(
                temporary,
                "  set local(n) = 0\n"
                "  while packet_id() < 0 and local(n) < 4000000\n"
                "    add local(n) 1\n"
                "    set var(v) = packet_receive()\n"
                "  end\n"
                '  print "id=" + packet_id() + " value=" + var(v)\n',
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.addCleanup(sock.close)
            junk = envelope(1, 999, 1.0, magic=b"JUNK")
            for _ in range(500):
                sock.sendto(junk, ("127.0.0.1", self.port))
                time.sleep(0.001)
            # UDP may drop under a flood, so repeat the valid packet with fresh
            # sequences until the server has one.
            for sequence in range(1, 200):
                sock.sendto(envelope(sequence, 7, 2.5), ("127.0.0.1", self.port))
                time.sleep(0.005)
                if process.poll() is not None:
                    break
                if sequence % 20 == 0:
                    time.sleep(0.05)
            stdout, stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("id=7 value=2.5", stdout)


if __name__ == "__main__":
    unittest.main()
