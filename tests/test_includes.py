import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.cli import main
from compiler.codegen import emit_c
from compiler.common import CompileError, Node, ROOT, RUNTIME_C_NAMES
from compiler.modules import called_functions
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse, parse_syntax
from tests.native_app import NativeApp


class IncludeFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def load(self, source):
        path = self.write('main.ANVL', source)
        return path, parse(path, source)

class IncludeTests(IncludeFixture):
    def test_source_marking_and_call_discovery_do_not_recurse_on_block_depth(self):
        source = 'fn(main)\n' + 'if true\n' * 1500 + 'call fn(helper)\n' + 'end\n' * 1500 + 'end\nfn(helper)\n output 1\nend\n'
        parsed = parse_syntax(pathlib.Path('deep.ANVL'), source)
        self.assertEqual(called_functions(parsed.functions['main'].body), {'helper'})
        self.assertEqual(parsed.functions['main'].body[0].source, pathlib.Path('deep.ANVL'))

    def test_include_syntax_phase_does_not_read_files(self):
        program = parse_syntax(pathlib.Path('entry.ANVL'), 'include "missing.ANVL"\n')
        self.assertEqual(program.top[0].kind, 'include')
        self.assertEqual(program.top[0].line, 1)
        for source in ('fn(main)\n include "x.ANVL"\nend\n',
                       'include true\n', 'include "file.txt"\n',
                       'include "line\\n.ANVL"\n', 'include "C:/x.ANVL"\n'):
            with self.subTest(source=source), self.assertRaises(CompileError):
                parse_syntax(pathlib.Path('entry.ANVL'), source)

    def test_nested_diamond_includes_once_and_initializers_keep_order(self):
        common = self.write('lib/common.ANVL', 'array shared(2)\nset var(count) = 1\nfn(increment, value)\n output var(value) + 1\nend\n')
        self.write('lib/left.ANVL', 'include "common.ANVL"\nset var(count) = var(count) + 2\n')
        self.write('lib/right.ANVL', 'include "common.ANVL"\nset var(count) = var(count) + 4\n')
        path, (functions, top, variables, arrays) = self.load('include "lib/left.ANVL"\ninclude "lib/right.ANVL"\nfn(main)\n output call fn(increment, var(count))\nend\n')
        self.assertEqual(list(functions), ['main', 'increment'])
        self.assertEqual([(node.kind, node.value) for node in top], [('set', '1'), ('set', 'var(count) + 2'), ('set', 'var(count) + 4')])
        self.assertEqual(functions['increment'].source, common)
        self.assertEqual(arrays.locations['shared'], (common, 1))
        generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn(json.dumps(str(common)), generated)

    def test_cycles_missing_files_and_escape_have_include_locations(self):
        first = self.write('first.ANVL', 'include "second.ANVL"\n')
        self.write('second.ANVL', 'include "first.ANVL"\n')
        with self.assertRaisesRegex(CompileError, r'second.ANVL:1: include cycle:'):
            parse(first, first.read_text())
        for source, text in [('include "missing.ANVL"\n', 'cannot read include'),
                             ('include "../outside.ANVL"\n', 'inside')]:
            with self.subTest(source=source), self.assertRaisesRegex(CompileError, text):
                self.load(source)

    def test_duplicate_functions_and_arrays_name_both_files(self):
        for declaration in ('fn(shared)\n output 1\nend\n', 'array shared(2)\n'):
            first = self.write('first.ANVL', declaration)
            second = self.write('second.ANVL', declaration)
            with self.subTest(declaration=declaration), self.assertRaises(CompileError) as error:
                self.load('include "first.ANVL"\ninclude "second.ANVL"\nfn(main)\n output 0\nend\n')
            self.assertIn(str(first), str(error.exception))
            self.assertIn(str(second), str(error.exception))

    def test_included_reference_and_codegen_errors_keep_physical_location(self):
        library = self.write('lib.ANVL', 'fn(value)\n output var(missing)\nend\n')
        with self.assertRaises(CompileError) as error:
            self.load('include "lib.ANVL"\nfn(main)\n output call fn(value)\nend\n')
        self.assertIn(str(library) + ':2:', str(error.exception))
        library.write_text('fn(value)\n output mouse_held(1)\nend\n')
        path, program = self.load('include "lib.ANVL"\nfn(main)\n output call fn(value)\nend\n')
        with self.assertRaises(CompileError) as error:
            emit_c(path, *program)
        self.assertIn(str(library) + ':2:', str(error.exception))
        library.write_text('fn(value)\n output image_load("unused.bmp")\nend\n')
        path, program = self.load('include "lib.ANVL"\nfn(main)\n output call fn(value)\nend\n')
        with self.assertRaises(CompileError) as error:
            NativeCodegen(path, *program).generate()
        self.assertIn(str(library) + ':2:', str(error.exception))


    def test_included_configuration_and_callback_errors_keep_location(self):
        cases = [
            ('set var(x) = 7\n', 'fn(main)\n output var(x)\nend\n'),
            ('scene 3d\n', 'fn(draw)\n display rect(0,0,1,1)\nend\n'),
            ('clear rgba(1,2,3,4)\n', 'scene 2d\nfn(draw)\n display rect(0,0,1,1)\nend\n'),
            ('fn(update, dt)\n output 0\nend\n', 'scene 2d\nfn(draw)\n display rect(0,0,1,1)\nend\n'),
            ('fn(draw, dt)\n output 0\nend\n', 'scene 2d\n'),
            ('output 1\n', 'scene 2d\nfn(draw)\n display rect(0,0,1,1)\nend\n'),
        ]
        for library_source, entry_source in cases:
            library = self.write('configuration.ANVL', library_source)
            path, program = self.load('include "configuration.ANVL"\n' + entry_source)
            with self.subTest(library=library_source), self.assertRaises(CompileError) as error:
                NativeCodegen(path, *program).generate()
            self.assertIn(str(library) + ':1:', str(error.exception))

    def test_included_local_array_conflict_cli_reports_library_line(self):
        library = self.write('lib.ANVL', 'fn(value, parameter)\n array parameter(2)\n output 1\nend\n')
        entry = self.write('main.ANVL', 'include "lib.ANVL"\nfn(main)\n output call fn(value, 7)\nend\n')
        for options in (['--backend', 'native', '--output', str(self.root / 'out.exe')],
                        ['--emit-c', str(self.root / 'out.c')]):
            with self.subTest(options=options):
                result = subprocess.run([sys.executable, '-m', 'compiler.anvil', str(entry), *options],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertIn(str(library) + ':2:', result.stderr)
                self.assertIn('conflicts with a local variable or parameter', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_semantic_symbol_errors_identify_physical_declarations(self):
        for declaration in ('fn(array_get)\n output 0\nend\n',
                            'set var(array_get) = 1\n', 'array array_get(2)\n'):
            library = self.write('symbols.ANVL', '# header\n' + declaration)
            with self.subTest(declaration=declaration), self.assertRaises(CompileError) as error:
                self.load('include "symbols.ANVL"\nfn(main)\n output 0\nend\n')
            self.assertIn(str(library) + ':2:', str(error.exception))
            self.assertIn('reserved runtime name', str(error.exception))
        first = self.write('first.ANVL', '# header\nfn(foo-bar)\n output 0\nend\n')
        second = self.write('second.ANVL', '# header\n# header\nfn(foo_bar)\n output 0\nend\n')
        with self.assertRaises(CompileError) as error:
            self.load('include "first.ANVL"\ninclude "second.ANVL"\nfn(main)\n output 0\nend\n')
        self.assertIn(str(first) + ':2', str(error.exception))
        self.assertIn(str(second) + ':3', str(error.exception))
        self.assertIn("both map to C name 'anvil_foo_bar'", str(error.exception))

    def test_all_public_runtime_symbols_are_reserved(self):
        header = (ROOT / 'runtime/anvil_runtime.h').read_text(encoding='utf-8')
        names = set(re.findall(r'\b(anvil_[A-Za-z_][A-Za-z_0-9]*)\s*\(', header))
        self.assertTrue(names)
        self.assertFalse(names - RUNTIME_C_NAMES, names - RUNTIME_C_NAMES)

    def test_previously_missing_runtime_names_reject_all_symbol_kinds(self):
        for name in ('camera_control', 'camera_fov', 'set_fixed_hz', 'trace_finish', 'trace_sphere'):
            for declaration in (f'fn({name})\n output 0\nend\n', f'set var({name}) = 1\n', f'array {name}(2)\n'):
                library = self.write('reserved.ANVL', '# header\n' + declaration)
                entry = self.write('main.ANVL', 'include "reserved.ANVL"\nfn(main)\n output 0\nend\n')
                for options in (['--backend', 'native', '--output', str(self.root / 'out.exe')],
                                ['--emit-c', str(self.root / 'out.c')]):
                    with self.subTest(name=name, declaration=declaration, options=options):
                        result = subprocess.run([sys.executable, '-m', 'compiler.anvil', str(entry), *options],
                                                capture_output=True, text=True, timeout=10)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn(str(library) + ':2:', result.stderr)
                        self.assertIn('reserved runtime name', result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_graph_limits_and_invalid_utf8_are_controlled(self):
        self.write('one.ANVL', 'include "two.ANVL"\n')
        self.write('two.ANVL', 'fn(main)\n output 1\nend\n')
        for limit in ('MAX_INCLUDE_FILES', 'MAX_INCLUDE_DEPTH'):
            with mock.patch('compiler.modules.' + limit, 2), self.assertRaisesRegex(CompileError, 'exceeds'):
                self.load('include "one.ANVL"\n')
        with mock.patch('compiler.modules.MAX_SOURCE_BYTES', 40), self.assertRaisesRegex(CompileError, 'budget'):
            self.load('include "two.ANVL"\n' + '# padding padding padding\n')
        (self.root / 'bad.ANVL').write_bytes(b'\xff\xfe')
        with self.assertRaisesRegex(CompileError, 'cannot read include'):
            self.load('include "bad.ANVL"\n')

    def test_bom_spaces_and_library_only_entry(self):
        self.write('lib space.ANVL', '\ufefflanguage version 1\nfn(main)\n output 9\nend\n')
        path, (functions, top, variables, arrays) = self.load('include "lib space.ANVL" # comment\n')
        self.assertEqual(list(functions), ['main'])
        NativeCodegen(path, functions, top, variables, arrays).generate()

    def test_native_dependency_selection_excludes_unused_code_and_imports(self):
        self.write('library.ANVL', 'fn(used, value)\n output var(value) + 1\nend\nfn(unused)\n output image_load("missing.bmp")\nend\nfn(unused-input)\n output mouse_x()\nend\n')
        path, program = self.load('include "library.ANVL"\nfn(main)\n output call fn(used, 4)\nend\n')
        generator = NativeCodegen(path, *program)
        image = generator.generate()
        self.assertIn('function:used', generator.code.labels)
        self.assertNotIn('function:unused', generator.code.labels)
        self.assertNotIn('function:unused-input', generator.code.labels)
        self.assertNotIn(b'TrackMouseEvent', image)
        self.assertEqual(called_functions([Node('output', 1, value='"call fn(fake)" + call fn(real, call fn(nested))')]), {'real', 'nested'})

    def test_project_include_root_covers_entry_subdirectory(self):
        self.write('lib.ANVL', 'fn(value)\n output 42\nend\n')
        entry = self.write('src/main.ANVL', 'include "../lib.ANVL"\nfn(main)\n output call fn(value)\nend\n')
        manifest = self.write('game.ANVLproj', 'entry="src/main.ANVL"\n')
        generated = self.root / 'result.c'
        with mock.patch.object(sys, 'argv', ['anvil', str(manifest), '--emit-c', str(generated)]):
            self.assertEqual(main(), 0)
        self.assertIn('anvil_value', generated.read_text())
        with self.assertRaisesRegex(CompileError, 'inside'):
            parse(entry, entry.read_text())


@unittest.skipUnless(sys.platform == 'win32', 'executes native PE output')
class IncludeExecutionTests(IncludeFixture):
    def test_mutually_recursive_functions_across_included_units(self):
        self.write('even.ANVL', 'include "odd.ANVL"\nfn(is-even, number)\n if var(number) <= 0\n  output 1\n end\n output call fn(is-odd, var(number) - 1)\nend\n')
        self.write('odd.ANVL', 'fn(is-odd, number)\n if var(number) <= 0\n  output 0\n end\n output call fn(is-even, var(number) - 1)\nend\n')
        path, program = self.load('include "even.ANVL"\nfn(main)\n output call fn(is-even, 20)\nend\n')
        exe = self.root / 'recursive.exe'
        exe.write_bytes(NativeCodegen(path, *program).generate())
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
        self.assertEqual((result.returncode, result.stdout), (0, '1\n'))

    def test_long_unicode_source_diagnostic_uses_utf8_data(self):
        library = self.write('λ' * 80 + '.ANVL', 'fn(value)\n output 1 / 0\nend\n')
        source = 'include ' + json.dumps(library.name) + '\nfn(main)\n output call fn(value)\nend\n'
        path, program = self.load(source)
        exe = self.root / 'unicode-error.exe'
        exe.write_bytes(NativeCodegen(path, *program).generate())
        result = subprocess.run([str(exe)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(library).encode('utf-8'), result.stdout)
        self.assertGreater(len(result.stdout), 200)

    def test_native_include_entry_and_original_runtime_error_location(self):
        library = self.write('lib/helper.ANVL', 'fn(value, number)\n output var(number) + 1\nend\n')
        path, program = self.load('include "lib/helper.ANVL"\nfn(main, value)\n output var(value)\nend\ncall fn(main, call fn(value, 41))\n')
        exe = self.root / 'include.exe'
        exe.write_bytes(NativeCodegen(path, *program).generate())
        result = subprocess.run([str(exe)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.decode('utf-8').splitlines(), ['42'])
        library.write_text('fn(value, number)\n output var(number) / 0\nend\n')
        program = parse(path, path.read_text())
        exe.write_bytes(NativeCodegen(path, *program).generate())
        result = subprocess.run([str(exe)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(library).encode('utf-8'), result.stdout)
        self.assertIn(b'line 2', result.stdout)

    def test_included_graphical_callbacks_initialize_once(self):
        self.write('lib.ANVL', 'array shared(2)\nset var(initialized) = 0\nadd var(initialized) 1\nfn(value)\n output 42\nend\n')
        source = 'scene 2d\ninclude "lib.ANVL"\ninclude "lib.ANVL"\nfn(draw)\n set var(result) = call fn(value)\n display rect(10,10,20,20)\nend\n'
        path, program = self.load(source)
        with NativeApp(source, source_path=path) as app:
            app.wait(lambda: app.read('result') == 42)
            self.assertEqual(app.read('initialized'), 1)
        self.assertEqual(app.result[0], 0, app.result)
