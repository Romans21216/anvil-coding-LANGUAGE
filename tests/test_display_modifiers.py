"""Preserve display literals while parsing actual command suffixes."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.parser import parse


LITERALS = [
    'keep -rgb(1,2,3) literal',
    'keep -rgba(1,2,3,4) literal',
    'keep -rotate(1,2,3) literal',
    'keep -l(10,20) and -loc(30,40) literal',
    'quoted "-rgb(1,2,3)" \\ var(ghost) # literal',
]


def source_for(literal, suffix='-l(12,34) -rgb(9,8,7)'):
    return ('scene 2d\nfn(draw)\n display text(' + json.dumps(literal)
            + ') ' + suffix + '\nend\n')


class DisplayModifierTests(unittest.TestCase):
    def generate(self, source):
        path = pathlib.Path('display.ANVL')
        return emit_c(path, *parse(path, source))

    def test_quoted_modifiers_preserve_literal_and_real_style(self):
        for literal in LITERALS:
            with self.subTest(literal=literal):
                generated = self.generate(source_for(literal))
                expected = ('anvil_text(12.0, 34.0, ' + json.dumps(literal)
                            + ', 9.0, 8.0, 7.0, 255);')
                self.assertIn(expected, generated)

    def test_literal_color_text_does_not_override_default(self):
        generated = self.generate(source_for(LITERALS[0], '-l(0,0)'))
        self.assertIn('anvil_text(0.0, 0.0, ' + json.dumps(LITERALS[0])
                      + ', 255, 255, 255, 255);', generated)

    def test_multiple_colors_preserve_first_color_contract(self):
        generated = self.generate(source_for('first color',
                                 '-rgb(9,8,7) -l(0,0) -rgba(1,2,3,4)'))
        self.assertIn('"first color", 9.0, 8.0, 7.0, 255);', generated)

    def test_duplicate_and_unclosed_real_modifiers_are_source_located(self):
        for suffix in ('-l(0,0) -l(1,2)', '-l(0,0) -rotate(1,2,3) -rotate(4,5,6)',
                       '-l(0,0) -rgb(1,2,3'):
            with self.subTest(suffix=suffix), self.assertRaises(CompileError) as error:
                self.generate(source_for('literal -l(7,8) -rotate(1,2,3)', suffix))
            self.assertIn('display.ANVL:3:', str(error.exception))

    def test_modifiers_require_suffix_position_and_whitespace(self):
        for command in ('-rgb(1,2,3) rect(0,0,10,10)',
                        'rect(0,0,10,10)-rgb(1,2,3)'):
            with self.subTest(command=command), self.assertRaises(CompileError):
                self.generate('fn(draw)\n display ' + command + '\nend\n')

    def test_global_array_expressions_reach_shape_lowering(self):
        generated = self.generate('array values(1)\nfn(draw)\n display rect(array(values,0),0,10,10)\nend\n')
        self.assertIn('anvil_rect(anvil_array_get(anvil_values', generated)

    @unittest.skipUnless(sys.platform == 'win32', 'executes C-backed PE probe')
    def test_compiled_display_calls_preserve_text_and_nested_expressions(self):
        compiler = find_compiler(None)
        if not compiler:
            self.skipTest('MSVC is required for C display lowering probe')
        source = ('scene 2d\narray values(1)\nfn(draw)\n set var(x) = 2\n'
                  ' set local(y) = 3\n')
        for literal in LITERALS:
            source += ' display text(' + json.dumps(literal) + ') -l(12,34) -rgb(9,8,7)\n'
        source += (' display text("nested expressions")'
                   ' -l(max(var(x),1),min(5,local(y)))'
                   ' -rgb(min(9,8),max(2,3),abs(-7))\n'
                   ' set array(values,0) = 17\n'
                   ' display rect(array(values,0),0,10,10)\nend\n')
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'program.c').write_text(self.generate(source), encoding='utf-8')
            harness = root / 'display_probe.c'
            harness.write_text("""#define main generated_game_main
#define anvil_text capture_display_text
#define anvil_rect capture_display_rect
#include "program.c"
#undef main
#undef anvil_text
#undef anvil_rect
void capture_display_text(double x, double y, const char *text,
                          int r, int g, int b, int a) {
  printf("%.0f,%.0f|%d,%d,%d,%d|%s\\n", x, y, r, g, b, a, text);
}
void capture_display_rect(double x, double y, double w, double h,
                          int r, int g, int b, int a) {
  printf("rect:%.0f,%.0f,%.0f,%.0f\\n", x, y, w, h);
}
int main(void) { anvil_draw(); return 0; }
""", encoding='utf-8')
            output = root / 'display_probe.exe'
            build_c(compiler[1], harness, output, release=True)
            result = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = ['12,34|9,8,7,255|' + literal for literal in LITERALS]
        expected.append('2,3|8,3,7,255|nested expressions')
        expected.append('rect:17,0,10,10')
        self.assertEqual(result.stdout.splitlines(), expected)
