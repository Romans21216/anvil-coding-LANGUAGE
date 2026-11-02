import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.cli import main
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse
from tests.native_app import NativeApp


class NativeProjectTests(unittest.TestCase):
    def test_nested_project_without_c_toolchain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'src').mkdir()
            (root / 'lib.ANVL').write_text('fn(value)\n output 20\nend\n', encoding='utf-8')
            entry = root / 'src/main.ANVL'
            entry.write_text('include "../lib.ANVL"\nfn(main)\n output call fn(value)\nend\n', encoding='utf-8')
            project = root / 'game.ANVLproj'
            project.write_text('name="Project λ"\nentry="src/main.ANVL"\n[engine]\nfixed_hz=120\n', encoding='utf-8')
            output = root / 'game.exe'
            with mock.patch.object(sys, 'argv', ['anvil', str(project), '--backend', 'native', '-o', str(output)]), mock.patch('compiler.cli.find_compiler', side_effect=AssertionError('C lookup')), mock.patch('compiler.cli.build_c', side_effect=AssertionError('C build')):
                self.assertEqual(main(), 0)
            self.assertFalse(list(root.rglob('*.c')))
            if sys.platform == 'win32':
                result = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, '20'))

    def test_project_memory_settings_reach_native_array_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            entry = root / "main.ANVL"
            source = "fn(main)\n array scratch(4)\n output 9\nend\ncall fn(main)\n"
            entry.write_text(source, encoding="utf-8")
            project = root / "game.ANVLproj"
            project.write_text(
                'entry="main.ANVL"\n[memory]\n'
                "local_array_elements=4\nactive_call_memory_mib=2048\n",
                encoding="utf-8",
            )
            output = root / "game.exe"
            with mock.patch.object(
                sys, "argv", ["anvil", str(project), "--backend", "native", "-o", str(output)]
            ):
                self.assertEqual(main(), 0)
            expected = NativeCodegen(
                entry.resolve(),
                *parse(
                    entry.resolve(),
                    source,
                    include_root=root,
                    local_array_elements=4,
                    active_local_array_bytes=2048 * 1024 * 1024,
                ),
                active_local_array_bytes=2048 * 1024 * 1024,
            ).generate()
            self.assertEqual(output.read_bytes(), expected)

    def test_active_call_memory_budget_is_shared_across_native_recursion(self):
        if sys.platform != "win32":
            self.skipTest("native backend emits Windows PE executables")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            entry = root / "main.ANVL"
            entry.write_text(
                'include fn(recurse) -- "lib/arrays.ANVL"\n'
                "fn(main)\n output call fn(recurse -- arrays, 2)\nend\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            (root / "lib").mkdir()
            library = root / "lib" / "arrays.ANVL"
            library.write_text(
                "fn(recurse, depth)\n"
                " array cells(131000)\n"
                " if var(depth) > 0\n"
                "  output call fn(recurse, var(depth) - 1)\n"
                " end\n"
                " output 0\n"
                "end\n",
                encoding="utf-8",
            )
            project = root / "recursive.ANVLproj"
            project.write_text(
                'entry="main.ANVL"\n[memory]\n'
                "local_array_elements=131000\nactive_call_memory_mib=1\n",
                encoding="utf-8",
            )
            output = root / "recursive.exe"
            with mock.patch.object(
                sys,
                "argv",
                ["anvil", str(project), "--backend", "native", "-o", str(output)],
            ):
                self.assertEqual(main(), 0)
            result = subprocess.run(
                [str(output)], capture_output=True, text=True, timeout=10
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "local array allocation/budget error", result.stdout + result.stderr
            )
            self.assertIn("at line 2 (", result.stdout + result.stderr)
            self.assertIn(str(library.resolve()), result.stdout + result.stderr)

    def test_graphical_project_wiring_and_invalid_manifests(self):
        import contextlib
        import io
        from compiler.common import CompileError
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = 'scene 2d\nfn(draw)\n display rect(0,0,1,1)\nend\n'
            entry = root/'main.ANVL'; entry.write_text(source,encoding='utf-8')
            project=root/'game.ANVLproj'; output=root/'game.exe'
            project.write_text('name="Project λ"\nentry="main.ANVL"\n[engine]\nfixed_hz=30\n',encoding='utf-8')
            with mock.patch.object(sys,'argv',['anvil',str(project),'--backend','native','-o',str(output)]):self.assertEqual(main(),0)
            expected=NativeCodegen(entry.resolve(),*parse(entry.resolve(),source,include_root=root),fixed_hz=30,title='Project λ').generate()
            self.assertEqual(output.read_bytes(),expected)
            output.unlink()
            for contents in ('entry="../outside.ANVL"', 'entry="main.ANVL"\nextra=1', 'entry="main.ANVL"\nname=""') + tuple('entry="main.ANVL"\n[engine]\nfixed_hz='+value for value in ('0','241','true','1.5')):
                project.write_text(contents,encoding='utf-8')
                with self.subTest(contents=contents),mock.patch.object(sys,'argv',['anvil',str(project),'--backend','native','-o',str(output)]),contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(main(),1)
                    self.assertNotIn('Traceback',errors.getvalue())
                    self.assertFalse(output.exists())
            project.write_text('entry="main.ANVL"',encoding='utf-8')
            entry.write_text('scene 3d\nfn(draw)\n display cube(0,0,0,1)\nend\n',encoding='utf-8')
            with mock.patch.object(sys,'argv',['anvil',str(project),'--backend','native','-o',str(output)]), mock.patch('compiler.cli.build_c',side_effect=AssertionError('fallback')),contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(),1)
                self.assertIn(str(entry.resolve()),errors.getvalue())
                self.assertFalse(output.exists())

    def test_control_character_entries_have_clean_cli_errors(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            project = root/'bad.ANVLproj'
            for entry in ('\0', 'bad\npath', 'bad\tpath', 'bad\x01path'):
                project.write_text('entry=' + json.dumps(entry),encoding='utf-8')
                for backend in ('c','native'):
                    output=root/'result.exe'
                    with self.subTest(entry=entry,backend=backend):
                        result=subprocess.run([sys.executable,'-m','compiler.anvil',str(project),'--backend',backend,'-o',str(output)],capture_output=True,text=True,timeout=10)
                        self.assertEqual(result.returncode,1)
                        self.assertIn(str(project),result.stderr)
                        self.assertIn('entry must not contain control characters',result.stderr)
                        self.assertNotIn('Traceback',result.stderr)
                        self.assertFalse(output.exists())
                        self.assertFalse(list(root.glob('*.c')))

    @unittest.skipUnless(sys.platform == 'win32', 'native window execution')
    def test_clock_title_and_shutdown(self):
        source = '''scene 2d
set var(ticks) = 0
fn(update)
 add var(ticks) 1
 set var(dt) = delta()
 set var(error) = abs(time() - var(ticks) * delta())
end
fn(draw)
 display rect(0,0,1,1)
end
'''
        for hz in (1, 30, 120, 240):
            with self.subTest(hz=hz), NativeApp(source, generator_options={'fixed_hz': hz, 'title': 'Project λ 🚀'}) as app:
                app.wait(lambda: app.read('ticks') >= 2)
                self.assertAlmostEqual(app.read('dt'), 1 / hz, places=12)
                self.assertLess(app.read('error'), 1e-9)
                import ctypes
                from ctypes import wintypes
                app.user.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
                title = ctypes.create_unicode_buffer(100)
                app.user.GetWindowTextW(app.hwnd, title, 100)
                self.assertEqual(title.value, 'Project λ 🚀')
            self.assertEqual(app.result[0], 0)
