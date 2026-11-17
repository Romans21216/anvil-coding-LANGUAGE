"""Every anvil_* function the generated C calls must carry a prototype.

C assumes `int f()` when no prototype is visible, which silently truncates a
double return. That is how anvil_list_get first handed back a list's count
instead of its value. The header is the contract; this test keeps the generated
code and the header from drifting apart again.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402

HEADER = (ROOT / "runtime" / "anvil_runtime.h").read_text(encoding="utf-8")
DECLARED = set(re.findall(r"\b(anvil_[A-Za-z0-9_]+)\s*\(", HEADER))

# Small programs that together touch the runtime paths this compiler emits:
# number formatting, numeric lists, text lists, and scalar assignment.
PROGRAMS = {
    "hello": 'fn(main)\n  say "hi"\n  say 1 + 1\nend\ncall fn(main)\n',
    "numeric list": (
        "list nums\n\nfn(main)\n  add nums 5\n  add nums 7\n  say count(nums)\n"
        "  say array(nums, 0)\n  remove nums 0\n  say array(nums, 0)\nend\n"
        "call fn(main)\n"
    ),
    "text list": (
        "list names: text\n\nfn(main)\n  add names \"ada\"\n  add names \"alan\"\n"
        "  say count(names)\n  say array(names, 1)\n  remove names 0\n"
        '  say array(names, 0)\nend\ncall fn(main)\n'
    ),
}


def definitions_and_imports(generated: str) -> set[str]:
    """Names the generated file itself defines or imports."""
    names = set(
        re.findall(
            r"^static\s+(?:double|void|char\s*\*|const\s+char\s*\*|int)\s+"
            r"(anvil_[A-Za-z0-9_]+)\s*\(",
            generated,
            re.M,
        )
    )
    names |= set(
        re.findall(
            r"__declspec\(dllimport\)\s+[A-Za-z_][\w\s\*]*?(anvil_[A-Za-z0-9_]+)\s*\(",
            generated,
        )
    )
    return names


class RuntimePrototypeTests(unittest.TestCase):
    def test_every_called_runtime_function_is_declared(self) -> None:
        for label, source in PROGRAMS.items():
            with self.subTest(program=label):
                with tempfile.TemporaryDirectory() as temp:
                    path = pathlib.Path(temp) / "sample.ANVL"
                    path.write_text(source, encoding="utf-8")
                    functions, top, variables, arrays = parse(path, source)
                    generated = emit_c(path, functions, top, variables, arrays)
                called = set(re.findall(r"\b(anvil_[A-Za-z0-9_]+)\s*\(", generated))
                local = definitions_and_imports(generated)
                declared = DECLARED | local
                # Anvil functions the program defines look like anvil_<name>( too.
                declared |= set(functions and {"anvil_" + name for name in functions})
                missing = sorted(called - declared)
                self.assertEqual(missing, [], f"{label}: {missing}")


if __name__ == "__main__":
    unittest.main()
