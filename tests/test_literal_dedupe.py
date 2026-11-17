"""Identical string literals share one .data block in the native image."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402


def generate(source: str) -> tuple[int, int]:
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "p.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        gen = NativeCodegen(path, functions, top, variables, arrays)
        image = gen.generate()
        return len(image), len(gen._data)


class LiteralDedupeTests(unittest.TestCase):
    def test_identical_literals_share_one_block(self) -> None:
        one = 'fn(main)\n  say "hello"\nend\ncall fn(main)\n'
        many = (
            "fn(main)\n"
            + "".join('  say "hello"\n' for _ in range(50))
            + "end\ncall fn(main)\n"
        )
        _image_one, data_one = generate(one)
        _image_many, data_many = generate(many)
        self.assertEqual(
            data_many,
            data_one,
            "the same literal must not be stored twice",
        )

    def test_distinct_literals_do_grow_the_data_section(self) -> None:
        distinct = (
            "fn(main)\n"
            + "".join(f'  say "line {i}"\n' for i in range(50))
            + "end\ncall fn(main)\n"
        )
        _image, data = generate(distinct)
        self.assertGreater(data, 300)


if __name__ == "__main__":
    unittest.main()
