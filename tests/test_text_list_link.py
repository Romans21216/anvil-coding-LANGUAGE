"""A text list that is only added to and counted must still link."""

from __future__ import annotations

import unittest

from tests.test_text_lists import compile_and_run

NL = chr(10)


def program(*lines: str) -> str:
    return NL.join(lines) + NL


SOURCE = program(
    "list names: text",
    "fn(main)",
    '  add names "ada"',
    '  add names "alan"',
    "  say count(names)",
    "end",
    "call fn(main)",
)


class TextListLinkTests(unittest.TestCase):
    def test_add_and_count_alone_still_link_on_both_backends(self) -> None:
        # The add path calls anvil_str_copy. If it does not set
        # _needs_string_helpers, the native backend fails with
        # KeyError: 'function:anvil_str_copy' at link time.
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                result = compile_and_run(SOURCE, backend)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), ["2"])


if __name__ == "__main__":
    unittest.main()
