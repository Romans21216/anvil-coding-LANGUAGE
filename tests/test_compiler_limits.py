import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


class CompilerLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.entry = self.root / 'main.ANVL'

    def command(self, source, backend, *, success=False, filename=None):
        self.entry.write_text(source, encoding='utf-8')
        args = [sys.executable, '-m', 'compiler.anvil', str(self.entry)]
        output = self.root / ('result.exe' if backend == 'native' else 'result.c')
        args += ['--backend', 'native', '--output', str(output)] if backend == 'native' else ['--emit-c', str(output)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('RecursionError', result.stderr)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
        else:
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(str(filename or self.entry), result.stderr)
            self.assertIn('nesting exceeds', result.stderr)
        return output

    def test_deep_grouping_nested_calls_and_unary_have_bounded_errors(self):
        expressions = ['(' * 1200 + '1' + ')' * 1200,
                       'abs(' * 1200 + '1' + ')' * 1200,
                       '- ' * 1200 + '1']
        mixed = '1'
        for _ in range(40):
            mixed = '- ' * 40 + 'call fn(identity, ' + mixed + ')'
        expressions.append(mixed)
        for backend in ('native', 'c'):
            for expression in expressions:
                with self.subTest(backend=backend, expression=expression[:15]):
                    self.command('fn(identity, value)\n output var(value)\nend\nfn(main)\n output ' + expression + '\nend\n', backend)

    def test_deep_statement_codegen_is_rejected_before_python_stack_exhaustion(self):
        source = 'fn(main)\n' + 'if true\n' * 1200 + 'output 1\n' + 'end\n' * 1200 + 'end\n'
        for backend in ('native', 'c'):
            with self.subTest(backend=backend):
                self.command(source, backend)

    def test_shallow_grouping_still_builds_and_native_runs(self):
        source = 'fn(main)\n output ' + '(' * 32 + '7' + ')' * 32 + '\nend\n'
        for backend in ('native', 'c'):
            output = self.command(source, backend, success=True)
            if backend == 'native' and sys.platform == 'win32':
                result = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
                self.assertEqual((result.returncode, result.stdout), (0, '7\n'))

    def test_quoted_parentheses_are_not_nesting(self):
        source = 'fn(main)\n output image_load(' + json.dumps('(' * 1400) + ')\nend\n'
        self.command(source, 'c', success=True)

    def test_included_deep_expression_identifies_library_line(self):
        library = self.root / 'lib.ANVL'
        library.write_text('fn(value)\n output ' + '(' * 1200 + '1' + ')' * 1200 + '\nend\n')
        source = 'include "lib.ANVL"\nfn(main)\n output call fn(value)\nend\n'
        for backend in ('native', 'c'):
            with self.subTest(backend=backend):
                self.command(source, backend, filename=library)

