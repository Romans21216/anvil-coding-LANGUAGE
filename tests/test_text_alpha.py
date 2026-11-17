"""Text alpha: the C backend must blend glyph coverage, not ignore alpha (8.14).

TEXT_ALPHA_REVIEW found the C runtime returned early from `anvil_text` with
`(void)a`, so a `-rgba(...,0)` label drew fully opaque while the native backend
blended. The fix renders the run white-on-black into a scratch DIB and
composites the coverage through the same `anvil_pixel` path every other
primitive uses. These tests measure the drawn result rather than the return
value: the brightest texel of a white label on black must track the requested
alpha.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BLACK = 4278190080  # 0xFF000000, the value frame_capture reports for black


def scan_block(indent: str, name: str) -> list[str]:
    """Draw `MMMM` at one alpha, capture, and print the brightest red level."""
    lines = [
        f"{indent}set var(pix{name}) = frame_capture()",
        f"{indent}set var(best{name}) = 0",
        f"{indent}for local(x{name}) = 30 to 220",
        f"{indent}  for local(y{name}) = 30 to 90",
        f"{indent}    set var(v{name}) = floor((image_pixel(var(pix{name}), local(x{name}), local(y{name})) - {BLACK}) / 65536)",
        f"{indent}    if var(v{name}) > var(best{name})",
        f"{indent}      set var(best{name}) = var(v{name})",
        f"{indent}    end",
        f"{indent}  end",
        f"{indent}end",
        f'{indent}say "{name} " & var(best{name})',
    ]
    return lines


PROGRAM = "\n".join(
    [
        "scene 2d",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  clear rgba(0, 0, 0, 255)",
        "  add var(frame) 1",
        "  if var(frame) = 2",
        '    display text("MMMM") -l(40, 40) -rgba(255, 255, 255, 0)',
    ]
    + scan_block("    ", "a0")
    + [
        "  end",
        "  if var(frame) = 4",
        '    display text("MMMM") -l(40, 40) -rgba(255, 255, 255, 255)',
    ]
    + scan_block("    ", "a255")
    + [
        "  end",
        "  if var(frame) = 6",
        '    display text("MMMM") -l(40, 40) -rgba(255, 255, 255, 128)',
    ]
    + scan_block("    ", "a128")
    + [
        "  end",
        "  if var(frame) = 8",
        '    display text("MMMM MMMM") -l(40, 40) -wrap(60) -rgba(255, 255, 255, 128)',
    ]
    + scan_block("    ", "awrap")
    + [
        "  end",
        "end",
        "",
    ]
)


def build(root: pathlib.Path) -> pathlib.Path:
    source = root / "alpha.ANVL"
    source.write_text(PROGRAM, encoding="utf-8")
    executable = root / "alpha.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return executable


def run_until(executable: pathlib.Path, root: pathlib.Path, last_key: str,
              timeout: float = 45.0) -> list[str]:
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: list[str] = []
    assert process.stdout is not None
    deadline = time.monotonic() + timeout
    try:
        for line in process.stdout:
            lines.append(line.rstrip("\r\n"))
            if line.startswith(last_key) or time.monotonic() > deadline:
                break
    finally:
        process.kill()
        process.wait(timeout=30)
    return lines


class TextAlphaTests(unittest.TestCase):
    def test_text_alpha_blends_glyph_coverage(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root)
            lines = run_until(executable, root, "awrap ")
        values = {}
        for line in lines:
            key, _, value = line.partition(" ")
            if key in {"a0", "a255", "a128", "awrap"}:
                values[key] = int(value)
        self.assertEqual(sorted(values), ["a0", "a128", "a255", "awrap"], lines)
        # Alpha 0 must leave the black background exactly as it was.
        self.assertEqual(values["a0"], 0)
        # Alpha 255 must reach the full white of the glyph core.
        self.assertEqual(values["a255"], 255)
        # Half alpha lands on the mid grey; the blend truncates, so allow a
        # couple of levels either side of 128.
        self.assertGreaterEqual(values["a128"], 120)
        self.assertLessEqual(values["a128"], 135)
        # The wrapped line goes through the same path and must blend too.
        self.assertGreaterEqual(values["awrap"], 120)
        self.assertLessEqual(values["awrap"], 135)


if __name__ == "__main__":
    unittest.main()
