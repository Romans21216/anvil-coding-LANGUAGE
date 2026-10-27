import pathlib
import unittest

from compiler import anvil as compatibility
from compiler.codegen import emit_c
from compiler.common import CompileError, Node, ParsedProgram
from compiler.parser import parse, parse_syntax
from compiler.semantics import validate_program


class CompilerModuleTests(unittest.TestCase):
    def test_parse_semantics_codegen_boundaries_keep_legacy_result(self):
        source_path = pathlib.Path("module-boundaries.ANVL")
        source = "fn(main)\n  set var(answer) = 2\n  output var(answer) + 3\nend\ncall fn(main)\n"

        parsed = parse_syntax(source_path, source)
        self.assertIsInstance(parsed, ParsedProgram)
        self.assertIsInstance(parsed.functions["main"], Node)
        self.assertEqual(parsed.variable_references[0][0], "answer")

        validate_program(parsed)
        functions, top, variables, arrays = parse(source_path, source)
        generated = emit_c(source_path, functions, top, variables, arrays)
        self.assertIn("static double anvil_answer;", generated)
        self.assertIn("return anvil_check_number(", generated)
        self.assertIn("anvil_answer", generated)
        self.assertIn('printf("%.15g\\n", anvil_main());', generated)

    def test_semantic_phase_rejects_unresolved_variable_before_codegen(self):
        source_path = pathlib.Path("unresolved.ANVL")
        program = parse_syntax(source_path, "fn(main)\n  output var(missing)\nend\n")
        with self.assertRaisesRegex(
            CompileError, r"unresolved\.ANVL:2: unknown variable 'missing'"
        ):
            validate_program(program)

    def test_legacy_compiler_facade_reexports_phases(self):
        from compiler.codegen import emit_c as module_emit_c
        from compiler.parser import parse as module_parse

        self.assertIs(compatibility.parse, module_parse)
        self.assertIs(compatibility.emit_c, module_emit_c)
        self.assertTrue(callable(compatibility.main))


if __name__ == "__main__":
    unittest.main()
