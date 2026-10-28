import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.native_codegen import NativeCodegen
from compiler.native_x64 import X64Code
from compiler.parser import parse


@unittest.skipUnless(sys.platform == 'win32', 'native PE execution')
class NativeArrayTests(unittest.TestCase):
    def run_source(self, source, fail_import=None):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'arrays.ANVL'
            path.write_text(source, encoding='utf-8')
            generator = NativeCodegen(path, *parse(path, source))
            original = X64Code.rip_call_import
            def call(code, name):
                if name == fail_import:
                    code.mov_imm(0, 0)
                else:
                    original(code, name)
            with mock.patch.object(X64Code, 'rip_call_import', call):
                image = generator.generate()
            exe = path.with_suffix('.exe')
            exe.write_bytes(image)
            return subprocess.run([str(exe)], capture_output=True, text=True, timeout=8)

    def test_zeroing_shadowing_and_recursive_isolation(self):
        source = '''array data(2)
fn(recurse, n)
 array data(2)
 set array(data,0) = var(n)
 if var(n) > 0
  set local(child) = call fn(recurse,var(n)-1)
  output array(data,0) + local(child)
 end
 output array(data,1)
end
fn(main)
 set array(data,0) = 100
 output call fn(recurse,3) + array(data,0)
end
'''
        result = self.run_source(source)
        self.assertEqual((result.returncode, result.stdout), (0, '106\n'))

    def test_all_returns_free_and_rezero_storage(self):
        source = '''fn(early, n)
 array data(8192)
 if var(n) > 0
  set array(data,8191) = 7
  output array(data,8191)
 end
 output array(data,8191)
end
fn(implicit)
 array data(8192)
 set array(data,0) = 9
end
fn(main)
 set local(total) = 0
 for local(i) = 1 to 300
  add local(total) call fn(early,1)
  add local(total) call fn(early,0)
  add local(total) call fn(implicit)
 end
 output local(total)
end
'''
        result = self.run_source(source)
        self.assertEqual((result.returncode, result.stdout), (0, '2100\n'))

    def test_bounds_and_active_budget_diagnostics(self):
        for index in ('-1', '0.5', '2'):
            result = self.run_source('fn(main)\n array data(2)\n output array(data,' + index + ')\nend\n')
            self.assertEqual(result.returncode, 2)
            self.assertIn('array index error at line 3', result.stdout)
        result = self.run_source('fn(recurse)\n array data(8192)\n output call fn(recurse)\nend\nfn(main)\n output call fn(recurse)\nend\n')
        self.assertEqual(result.returncode, 2)
        self.assertIn('allocation/budget error', result.stdout)

    def test_heap_failure_is_controlled(self):
        result = self.run_source('fn(main)\n array data(2)\n output array(data,0)\nend\n', 'HeapAlloc')
        self.assertEqual(result.returncode, 2)
        self.assertIn('allocation/budget error', result.stdout)

    def test_parameter_abi_multiple_arrays_and_index_evaluates_once(self):
        names = ['p'+str(i) for i in range(16)]
        source = ('fn(value,' + ','.join(names) + ')\n array first(2)\n array second(2)\n'
                  ' set array(first,1) = ' + '+'.join('var('+n+')' for n in names) + '\n'
                  ' output array(first,1) + array(second,1)\nend\n'
                  'fn(next)\n add var(count) 1\n output 0\nend\n'
                  'fn(main)\n array buffer(2)\n set var(count) = 0\n'
                  ' set local(result) = call fn(value,' + ','.join(str(i) for i in range(1,17)) + ')\n set array(buffer,call fn(next)) = local(result)\n'
                  ' output array(buffer,0) + var(count)\nend\n')
        result = self.run_source(source)
        self.assertEqual((result.returncode,result.stdout),(0,'137\n'))

    def test_heap_release_failure_and_unused_library_selection(self):
        result = self.run_source('fn(main)\n array buffer(2)\n output 5\nend\n','HeapFree')
        self.assertEqual(result.returncode,2)
        self.assertIn('release error',result.stdout)
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/'unused.ANVL'
            source='fn(unused)\n array buffer(2)\n output array(buffer,0)\nend\nfn(main)\n output 7\nend\n'
            image=NativeCodegen(path,*parse(path,source)).generate()
            self.assertNotIn(b'HeapAlloc',image)
            self.assertNotIn(b'HeapFree',image)

    def test_loop_return_preserves_fraction_and_releases_storage(self):
        source='fn(value)\n array data(8192)\n while true\n  set array(data,1) = 1.25\n  output array(data,1)\n end\nend\nfn(main)\n set local(total) = 0\n for local(i) = 1 to 300\n  add local(total) call fn(value)\n end\n output local(total)\nend\n'
        result=self.run_source(source)
        self.assertEqual((result.returncode,result.stdout),(0,'375\n'))
