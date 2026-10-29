"""Selective imports bind source-owned function/state identities on both backends."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.modules import called_functions
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse, parse_syntax
from tests.native_app import NativeApp


class SelectiveIncludeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8")
        return path

    def program(self, text):
        path = self.write("main.ANVL",text)
        return path,parse(path,text)

    def run_both(self, source, expected):
        path,program = self.program(source)
        native = self.root/"native.exe"
        native.write_bytes(NativeCodegen(path,*program).generate())
        result = subprocess.run([str(native)],capture_output=True,text=True,timeout=5)
        self.assertEqual((result.returncode,result.stdout),(0,f"{expected}\n"),result.stderr)
        compiler = find_compiler(None)
        self.assertIsNotNone(compiler,"C/native conformance needs the configured MSVC toolchain")
        cfile = self.write("generated.c",emit_c(path,*program))
        cexe = self.root/"c.exe"
        build_c(compiler[1],cfile,cexe,release=True)
        result = subprocess.run([str(cexe)],capture_output=True,text=True,timeout=5)
        self.assertEqual((result.returncode,result.stdout),(0,f"{expected}\n"),result.stderr)
        return program

    def test_syntax_is_pure_and_qualified_call_discovery_preserves_hyphens(self):
        program = parse_syntax(Path("entry.ANVL"),'include fn(move-fast) - "lib/player.ANVL" as input\nfn(main)\n call fn(move-fast - input, 3)\n output call fn(move-fast - input, 2) + call fn(move-fast,1)\nend\n')
        self.assertEqual((program.top[0].name,program.top[0].params),("move-fast",["input"]))
        self.assertEqual(called_functions(program.functions["main"].body),{"move-fast - input","move-fast"})
        for source in ('include fn(move) "x.ANVL"\n','include fn(move) - "x.txt"\n',
                       'include fn(move) - "player.v2.ANVL"\n','fn(main)\n include fn(move) - "x.ANVL"\nend\n'):
            with self.subTest(source=source),self.assertRaises(CompileError):
                parse_syntax(Path("entry.ANVL"),source)

    @unittest.skipUnless(sys.platform == "win32","executes native/C programs")
    def test_duplicate_function_helpers_globals_arrays_and_local_shadow_are_isolated(self):
        self.write("a.ANVL",'''array shared(2)
fn(move, number)
 add var(count) 1
 set array(shared,0) = var(number)
 output call fn(helper,array(shared,0)) + var(count)
end
fn(helper, number)
 array shared(1)
 set array(shared,0) = var(number)*2
 output array(shared,0)
end
fn(unused)
 output var(missing)
end
''')
        self.write("b.ANVL",'''array shared(2)
fn(move, number)
 add var(count) 10
 set array(shared,0) = var(number)
 output call fn(helper,array(shared,0)) + var(count)
end
fn(helper, number)
 output var(number)*3
end
''')
        program = self.run_both('''include fn(move) - "a.ANVL"
include fn(move) - "b.ANVL"
fn(helper,number)
 output 999
end
fn(move,number)
 output var(number)+100
end
fn(main)
 set local(a) = call fn(move - a,3)
 set local(b) = call fn(move - b,5)
 set local(c) = call fn(move - a,1)
 output local(a)*10000 + local(b)*100 + local(c) + call fn(move,1)
end
''',72605)
        imported = [fn.original_name for fn in program[0].values() if fn.original_name]
        self.assertEqual(imported.count("move"),2)
        self.assertEqual(imported.count("helper"),2)
        self.assertNotIn("unused",imported)

    @unittest.skipUnless(sys.platform == "win32","executes native/C programs")
    def test_nested_plain_helpers_and_file_local_qualifiers_bind_their_own_imports(self):
        self.write("one.ANVL","fn(value)\n output 10\nend\n")
        self.write("two.ANVL","fn(value)\n output 20\nend\n")
        self.write("helpers.ANVL",'include fn(value) - "one.ANVL" as math\nfn(helper)\n output call fn(value - math)\nend\n')
        self.write("player.ANVL",'include "helpers.ANVL"\ninclude fn(value) - "two.ANVL" as math\nfn(move)\n output call fn(helper) + call fn(value - math)\nend\n')
        self.run_both('include fn(move) - "player.ANVL"\nfn(main)\n output call fn(move - player)\nend\n',30)

    @unittest.skipUnless(sys.platform == "win32","executes native/C programs")
    def test_aliases_for_same_basename_recursion_nested_calls_and_runtime_names(self):
        self.write("left/player.ANVL",'fn(move-fast,n)\n if var(n) <= 0\n  output 0\n end\n output var(n) + call fn(move-fast,var(n)-1)\nend\nfn(run)\n output 7\nend\n')
        self.write("right/player.ANVL",'fn(move-fast,n)\n output var(n)*2\nend\n')
        self.run_both('include fn(move-fast) - "left/player.ANVL" as left\ninclude fn(run) - "left/player.ANVL" as left\ninclude fn(move-fast) - "right/player.ANVL" as right\nfn(main)\n output call fn(move-fast - right,call fn(move-fast - left,5)) + call fn(run - left)\nend\n',37)

    @unittest.skipUnless(sys.platform == "win32","executes generated own-window code")
    def test_repeated_aliases_share_state_and_initialization_runs_once(self):
        self.write("lib.ANVL",'set var(initialized) = var(initialized)+1\nfn(value)\n output var(initialized)\nend\n')
        source = 'include fn(value) - "lib.ANVL" as first\ninclude fn(value) - "./lib.ANVL" as second\nscene 2d\nfn(draw)\n set var(result) = call fn(value - first) + call fn(value - second)\nend\n'
        path,program = self.program(source)
        self.assertEqual(sum(n.kind=="set" for n in program[1]),1)
        with NativeApp(source,source_path=path) as app:
            app.wait(lambda:app.read("result")==2)
        self.assertEqual(app.result[0],0)
        # The same initializer is supported on the existing C console route.
        self.write("main.ANVL",source.replace('scene 2d\nfn(draw)\n set var(result) =','fn(main)\n output'))
        csource = (self.root/"main.ANVL").read_text(encoding="utf-8")
        parsed = parse(self.root/"main.ANVL",csource)
        compiler = find_compiler(None)
        self.assertIsNotNone(compiler)
        cfile = self.write("init.c",emit_c(self.root/"main.ANVL",*parsed))
        exe = self.root/"init.exe"
        build_c(compiler[1],cfile,exe,release=True)
        result = subprocess.run([str(exe)],capture_output=True,text=True,timeout=5)
        self.assertEqual((result.returncode,result.stdout),(0,"2\n"))

    def test_missing_exports_qualifiers_arity_alias_conflicts_and_boundaries_have_locations(self):
        self.write("a.ANVL","fn(move,x)\n output var(x)\nend\nfn(hidden)\n output 1\nend\n")
        self.write("b.ANVL","fn(move,x)\n output var(x)\nend\n")
        cases=[('include fn(missing) - "a.ANVL"\nfn(main)\n output 0\nend\n',"does not define function"),
               ('include fn(move) - "a.ANVL"\nfn(main)\n output call fn(move - ghost,1)\nend\n',"unknown module qualifier"),
               ('include fn(move) - "a.ANVL"\nfn(main)\n output call fn(hidden - a)\nend\n',"was not included"),
               ('include fn(move) - "a.ANVL"\nfn(main)\n call fn(move - a)\nend\n',"expects 1 argument"),
               ('include fn(move) - "a.ANVL"\nfn(main)\n output call fn(move - a,1,2)\nend\n',"expects 1 argument"),
               ('include fn(move) - "a.ANVL" as same\ninclude fn(move) - "b.ANVL" as same\nfn(main)\n output 0\nend\n',"names different files"),
               ('include fn(move) - "../a.ANVL"\nfn(main)\n output 0\nend\n',"resolve inside")]
        for source,message in cases:
            with self.subTest(message=message),self.assertRaises(CompileError) as caught:
                self.program(source)
            self.assertIn(message,str(caught.exception))
            self.assertIn(str(self.root/"main.ANVL")+":",str(caught.exception))

    def test_selected_errors_keep_original_source_and_unused_semantics_are_omitted(self):
        library=self.write("labels_\u03bb.ANVL","# header\nfn(value)\n output var(missing)\nend\n")
        with self.assertRaises(CompileError) as caught:
            self.program('include fn(value) - '+json.dumps(library.name)+' as labels\nfn(main)\n output call fn(value - labels)\nend\n')
        self.assertIn(str(library)+":3:",str(caught.exception))
        self.assertIn("'missing'",str(caught.exception))
        self.assertNotIn("_anvil_include_",str(caught.exception))
        library.write_text('fn(value)\n output call fn(unknown)\nend\n',encoding="utf-8")
        with self.assertRaisesRegex(CompileError,"unknown function 'unknown'"):
            self.program('include fn(value) - '+json.dumps(library.name)+' as labels\nfn(main)\n output 0\nend\n')

    def test_quoted_qualified_calls_and_function_hyphens_are_not_rewritten(self):
        self.write("lib.ANVL","fn(value)\n output 1\nend\n")
        text='call fn(value - ghost) var(missing) array(missing,0)'
        path,program=self.program('include fn(value) - "lib.ANVL"\nscene 2d\nfn(draw)\n display text('+json.dumps(text)+') -l(0,0)\nend\n')
        self.assertIn(text,program[0]["draw"].body[0].value)
        NativeCodegen(path,*program).generate()
        path,program=self.program('fn(move-player)\n output 9\nend\nfn(main)\n output call fn(move-player)\nend\n')
        self.assertIn("move-player",program[0])

    def test_mixed_cycles_expansion_limits_internal_identity_and_native_prefix_are_protected(self):
        self.write("a.ANVL",'include "main.ANVL"\nfn(value)\n output 1\nend\n')
        with self.assertRaisesRegex(CompileError,"include cycle"):
            self.program('include fn(value) - "a.ANVL"\nfn(main)\n output 0\nend\n')
        self.write("a.ANVL",'fn(value)\n output 1\nend\n')
        source='include fn(value) - "a.ANVL"\ninclude "a.ANVL"\nfn(main)\n output 0\nend\n'
        with mock.patch("compiler.modules.MAX_INCLUDE_FILES",2),self.assertRaisesRegex(CompileError,"graph exceeds"):
            self.program(source)
        with self.assertRaisesRegex(CompileError,"reserved for include identities"):
            self.program('fn(_anvil-include_1_f_value)\n output 1\nend\n')
        self.write("a.ANVL",'fn(_anvil_native_foo)\n output 1\nend\n')
        path,program=self.program('include fn(_anvil_native_foo) - "a.ANVL"\nfn(main)\n output call fn(_anvil_native_foo - a)\nend\n')
        with self.assertRaisesRegex(CompileError,"prefix _anvil_native_ is reserved"):
            NativeCodegen(path,*program)

    def test_expanded_byte_and_scoped_depth_limits_keep_source_locations(self):
        library = self.write("a.ANVL",'fn(value)\n output 1\nend\n'+'# padding\n'*40)
        source='include fn(value) - "a.ANVL"\ninclude "a.ANVL"\nfn(main)\n output 0\nend\n'
        physical=len(source.encode())+library.stat().st_size
        with mock.patch("compiler.modules.MAX_SOURCE_BYTES",physical+1),self.assertRaisesRegex(CompileError,"expanded include source"):
            self.program(source)
        library.write_text('fn(value)\n output '+'('*65+'1'+')'*65+'\nend\n',encoding="utf-8")
        path,program=self.program('include fn(value) - "a.ANVL"\nfn(main)\n output call fn(value - a)\nend\n')
        for generate in (lambda:NativeCodegen(path,*program).generate(),lambda:emit_c(path,*program)):
            with self.assertRaises(CompileError) as caught:
                generate()
            self.assertIn(str(library)+":2:",str(caught.exception))
            self.assertIn("nesting",str(caught.exception))
        library.write_text('fn(value)\n'+' if true\n'*129+' output 1\n'+' end\n'*129+'end\n',encoding="utf-8")
        with self.assertRaisesRegex(CompileError,"statement nesting exceeds 128"):
            self.program('include fn(value) - "a.ANVL"\nfn(main)\n output call fn(value - a)\nend\n')

    def test_nested_project_selective_import_builds_without_c(self):
        from compiler.cli import main
        self.write("lib/player.ANVL",'fn(move,n)\n output var(n)*3\nend\n')
        self.write("src/main.ANVL",'include fn(move) - "../lib/player.ANVL"\nfn(main)\n output call fn(move - player,7)\nend\n')
        project=self.write("game.ANVLproj",'name="Selective λ"\nentry="src/main.ANVL"\n[engine]\nfixed_hz=120\n')
        output=self.root/"game.exe"
        with mock.patch.object(sys,"argv",["anvil",str(project),"--backend","native","-o",str(output)]),mock.patch("compiler.cli.find_compiler",side_effect=AssertionError("C lookup")),mock.patch("compiler.cli.build_c",side_effect=AssertionError("C fallback")):
            self.assertEqual(main(),0)
        self.assertFalse(list(self.root.rglob("*.c")))
        if sys.platform=="win32":
            result=subprocess.run([str(output)],capture_output=True,text=True,timeout=5)
            self.assertEqual((result.returncode,result.stdout),(0,"21\n"))

    @unittest.skipUnless(sys.platform=="win32","executes native/C runtime diagnostics")
    def test_qualified_runtime_errors_keep_unicode_library_path(self):
        library=self.write("lib_λ_проба_日本_🙂.ANVL",'fn(value)\n array items(1)\n output array(items,2)\nend\n')
        path,program=self.program('include fn(value) - '+json.dumps(library.name)+' as labels\nfn(main)\n output call fn(value - labels)\nend\n')
        native=self.root/"error-native.exe"
        native.write_bytes(NativeCodegen(path,*program).generate())
        cfile=self.write("error.c",emit_c(path,*program))
        compiler=find_compiler(None)
        self.assertIsNotNone(compiler)
        cexe=self.root/"error-c.exe"
        build_c(compiler[1],cfile,cexe,release=True)
        for exe in (native,cexe):
            with self.subTest(backend=exe.name):
                result=subprocess.run([str(exe)],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,2)
                diagnostics=result.stdout+result.stderr
                self.assertIn(str(library).encode("utf-8"),diagnostics)
                self.assertTrue(b":3:" in diagnostics or b"line 3 " in diagnostics,diagnostics)

    def test_all_source_private_identity_references_are_rejected_before_backend_builds(self):
        import contextlib
        import io
        from compiler.cli import main
        self.write("lib.ANVL",'array secret(1)\nfn(move)\n output call fn(hidden) + array(secret,0)\nend\nfn(hidden)\n output 73\nend\n')
        cases=[('fn(main)\n output call fn(_anvil_include_1_f_hidden)\nend\n',3),
               ('fn(main)\n call fn(_anvil_include_1_f_hidden)\nend\n',3),
               ('fn(main)\n output call fn(move - lib,call fn(_anvil_include_1_f_hidden))\nend\n',3),
               ('fn(main)\n output 0\nend\ncall fn(_anvil_include_1_f_hidden)\n',5),
               ('fn(main)\n set array(_anvil_include_1_a_secret,0) = 42\n output call fn(move - lib)\nend\n',3),
               ('fn(main)\n output array(_anvil_include_1_a_secret,0)\nend\n',3),
               ('fn(main)\n output call fn(_anvil-include_1_f_hidden)\nend\n',3)]
        for body,line in cases:
            path=self.write("main.ANVL",'include fn(move) - "lib.ANVL"\n'+body)
            for backend in ('native','c'):
                output=self.root/(backend+'.exe')
                with self.subTest(backend=backend,body=body),mock.patch.object(sys,"argv",['anvil',str(path),'--backend',backend,'-o',str(output)]),mock.patch('compiler.cli.find_compiler',side_effect=AssertionError('backend reached')),contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(main(),1)
                    self.assertIn(str(path)+f':{line}:',errors.getvalue())
                    self.assertIn('reserved for include identities',errors.getvalue())
                    self.assertFalse(output.exists())
        # Comments and literals never become identifier references.
        text='call fn(_anvil_include_1_f_hidden) array(_anvil_include_1_a_secret,0)'
        path,program=self.program('include fn(move) - "lib.ANVL"\n# '+text+'\nscene 2d\nfn(draw)\n display text('+json.dumps(text)+') -l(0,0)\nend\n')
        NativeCodegen(path,*program).generate()
        emit_c(path,*program)

    @unittest.skipUnless(sys.platform=="win32","executes C UTF-8 literal payload")
    def test_c_metadata_literal_encoding_is_byte_exact_and_handles_supplementary_titles(self):
        from compiler.common import c_string_literal
        payload='A🙂f0é日本\\"\t\n\0\x01\x7f'
        source='#include <stdio.h>\n#include <io.h>\n#include <fcntl.h>\nint main(void) { const char value[] = '+c_string_literal(payload)+'; _setmode(_fileno(stdout),_O_BINARY); return fwrite(value,1,sizeof(value)-1,stdout)==sizeof(value)-1 ? 0 : 1; }\n'
        compiler=find_compiler(None)
        self.assertIsNotNone(compiler)
        exe=self.root/'literal.exe'
        build_c(compiler[1],self.write('literal.c',source),exe,release=True)
        result=subprocess.run([str(exe)],capture_output=True,timeout=5)
        self.assertEqual((result.returncode,result.stdout),(0,payload.encode('utf-8')))
        path,program=self.program('scene 2d\nfn(draw)\n display rect(0,0,1,1)\nend\n')
        title='Project🙂日本'
        generated=emit_c(path,*program,project_name=title)
        self.assertIn(c_string_literal(title),generated)
        build_c(compiler[1],self.write('title.c',generated),self.root/'title.exe',release=True)
