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

    def test_c_codegen_elides_unreachable_functions_and_keeps_transitive_calls(self):
        source_path = pathlib.Path("tree-shake.ANVL")
        source = (
            "fn(main)\n output call fn(used)\nend\n"
            "fn(used)\n output call fn(helper)\nend\n"
            "fn(helper)\n output 7\nend\n"
            "fn(unused)\n output 999\nend\n"
            "call fn(main)\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertIn("static double anvil_main(void);", generated)
        self.assertIn("static double anvil_used(void);", generated)
        self.assertIn("static double anvil_helper(void);", generated)
        self.assertNotIn("anvil_unused", generated)

    def test_c_codegen_uses_top_level_calls_instead_of_unused_main(self):
        source_path = pathlib.Path("explicit-entry.ANVL")
        source = (
            "fn(main)\n output 999\nend\n"
            "fn(actual)\n output 7\nend\n"
            "call fn(actual)\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertIn("static double anvil_actual(void);", generated)
        self.assertNotIn("anvil_main", generated)

    def test_explicit_top_level_call_can_reach_main_transitively(self):
        source_path = pathlib.Path("transitive-main.ANVL")
        source = (
            "fn(main)\n output 7\nend\n"
            "fn(actual)\n output call fn(main)\nend\n"
            "call fn(actual)\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertIn("static double anvil_main(void);", generated)
        self.assertIn("static double anvil_actual(void);", generated)

    def test_c_codegen_still_validates_unreachable_function_bodies(self):
        source = (
            "fn(main)\n output 1\nend\ncall fn(main)\n"
            "fn(unused)\n output var(missing)\nend\n"
        )

        with self.assertRaisesRegex(CompileError, "unknown variable 'missing'"):
            parse(pathlib.Path("unreachable-invalid.ANVL"), source)

    def test_c_codegen_roots_engine_callbacks_and_their_dependencies(self):
        source_path = pathlib.Path("engine-tree-shake.ANVL")
        source = (
            "scene 2d\n"
            "call fn(startup)\n"
            "fn(startup)\n output 0\nend\n"
            "fn(draw)\n call fn(draw_helper)\nend\n"
            "fn(update)\n call fn(update_helper)\nend\n"
            "fn(draw_helper)\n output 1\nend\n"
            "fn(update_helper)\n output 2\nend\n"
            "fn(main)\n output 3\nend\n"
            "fn(unused)\n output 999\nend\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        for function in ("startup", "draw", "update", "draw_helper", "update_helper"):
            self.assertIn(f"anvil_{function}", generated)
        self.assertNotIn("anvil_main", generated)
        self.assertNotIn("anvil_unused", generated)
        main_body = generated[generated.index("int main(void) {", generated.index("static double anvil_startup")):]
        self.assertLess(main_body.index("anvil_startup();"), main_body.index("anvil_run("))

    def test_c_codegen_keeps_callback_targets_and_drops_unreferenced_functions(self):
        source_path = pathlib.Path("callback-tree-shake.ANVL")
        source = (
            "set varl(callback) = fnref(target)\n"
            "call varl(callback)\n"
            "fn(target)\n output 7\nend\n"
            "fn(unused)\n output 999\nend\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertIn("anvil_target", generated)
        self.assertIn("anvil__anvil_callable_dispatch_", generated)
        self.assertNotIn("anvil_unused", generated)

    def test_c_codegen_prunes_unreachable_global_variables_and_arrays(self):
        source_path = pathlib.Path("storage-tree-shake.ANVL")
        source = (
            "array live_array(2)\n"
            "array dead_array(4096)\n"
            "set varl(initialized) = 5\n"
            "fn(main)\n"
            " set array(live_array, 0) = varl(initialized)\n"
            " output array(live_array, 0)\n"
            "end\n"
            "fn(unused)\n"
            " set varl(dead_value) = array(dead_array, 0)\n"
            " output varl(dead_value)\n"
            "end\n"
            "call fn(main)\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertIn("static double anvil_live_array[2];", generated)
        self.assertNotIn("anvil_dead_array", generated)
        self.assertIn("static double anvil_initialized;", generated)
        self.assertNotIn("anvil_dead_value", generated)

    def test_c_codegen_does_not_emit_shadowed_global_array_for_local_array(self):
        source_path = pathlib.Path("local-array-shadows-global.ANVL")
        source = (
            "language version 2\n"
            "array shared(64)\n"
            "fn(main)\n"
            " array shared(2)\n"
            " set array(shared, 0) = 9\n"
            " output array(shared, 0)\n"
            "end\n"
            "call fn(main)\n"
        )
        functions, top, variables, arrays = parse(source_path, source)

        generated = emit_c(source_path, functions, top, variables, arrays)

        self.assertNotIn("static double anvil_shared[64];", generated)
        self.assertIn("anvil_local_array_alloc(2", generated)

    def test_legacy_compiler_facade_reexports_phases(self):
        from compiler.codegen import emit_c as module_emit_c
        from compiler.parser import parse as module_parse

        self.assertIs(compatibility.parse, module_parse)
        self.assertIs(compatibility.emit_c, module_emit_c)
        self.assertTrue(callable(compatibility.main))


if __name__ == "__main__":
    unittest.main()
