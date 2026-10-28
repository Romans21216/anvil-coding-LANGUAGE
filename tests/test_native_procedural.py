import math
import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse
from tests.native_app import NativeApp


def reference_noise(x, y, z):
    """Independent scalar reference of the documented gradient-noise algorithm."""
    mask = 0xFFFFFFFF
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    x, y, z = x - ix, y - iy, z - iz

    def corner(i, j, k):
        h = ((ix + i) * 374761393 + (iy + j) * 668265263 +
             (iz + k) * 2147483647) & mask
        h = ((h ^ (h >> 13)) * 1274126177) & mask
        h = (h ^ (h >> 16)) & 15
        a, b, c = x - i, y - j, z - k
        return (a+b, -a+b, a-b, -a-b, a+c, -a+c, a-c, -a-c,
                b+c, -b+c, b-c, -b-c, a+b, -a+b, -b+c, -b-c)[h]

    def fade(t):
        return t*t*t*(t*(t*6-15)+10)

    def lerp(a, b, t):
        return a + t*(b-a)

    u, v, w = fade(x), fade(y), fade(z)
    a = lerp(corner(0, 0, 0), corner(1, 0, 0), u)
    b = lerp(corner(0, 1, 0), corner(1, 1, 0), u)
    c = lerp(corner(0, 0, 1), corner(1, 0, 1), u)
    d = lerp(corner(0, 1, 1), corner(1, 1, 1), u)
    return lerp(lerp(a, b, v), lerp(c, d, v), w) * 0.7


@unittest.skipUnless(sys.platform == "win32", "runs emitted AMD64 PE executables")
class NativeProceduralTests(unittest.TestCase):
    def run_source(self, source, code=0):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "procedural.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            image = NativeCodegen(path, functions, top, variables, arrays).generate()
            exe = path.with_suffix(".exe")
            exe.write_bytes(image)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def test_math_primitives_bounds_and_once_only_arguments(self):
        checks = ['floor(-1.25) = -2', 'ceil(-1.25) = -1', 'floor(1.25) = 1',
                  'ceil(1.25) = 2', 'floor(0) = 0', 'ceil(-0) = 0',
                  'floor(1e100) = 1e100', 'ceil(-1e100) = -1e100',
                  'sqrt(81) = 9', 'abs(-4.5) = 4.5', 'abs(-0) = 0',
                  'min(-3,8) = -3', 'max(-3,8) = 8',
                  'floor(4503599627370495.5) = 4503599627370495',
                  'ceil(4503599627370495.5) = 4503599627370496']
        body = '\n'.join(f'  if {check}\n    add var(passed) 1\n  end' for check in checks)
        source = f'''fn(value, number)
  add var(calls) 1
  output var(number)
end
fn(main)
  set var(passed) = 0
  set var(calls) = 0
{body}
  set var(result) = min(call fn(value, 9), max(call fn(value, 2), call fn(value, 5)))
  output var(passed) = {len(checks)} and var(calls) = 3 and var(result) = 5
end
'''
        self.assertEqual(self.run_source(source), '1\n')

    def test_seeded_random_reference_repeat_and_integer_intervals(self):
        seed = 42
        values = []
        mask = (1 << 64) - 1
        for _ in range(20):
            seed ^= seed >> 12
            seed ^= (seed << 25) & mask
            seed ^= seed >> 27
            seed &= mask
            values.append(-10 + ((seed * 2685821657736338717) & mask) % 31)
        checks = '\n'.join(f'  if rnd(-10,20) != {value}\n    output 0\n  end' for value in values)
        source = f'''seed(42)
fn(main)
{checks}
  seed(42)
  if rnd(20,-10) != {values[0]}
    output 0
  end
  if rnd(2.1,2.9) != 3 or rnd(-1.2,-1.2) != -1
    output 0
  end
  seed(0)
  set var(first) = rnd(-100,100)
  seed(0)
  if rnd(-100,100) != var(first)
    output 0
  end
  seed(18446744073709549568)
  set var(high) = rnd(0,1000)
  seed(18446744073709549568)
  if rnd(0,1000) != var(high)
    output 0
  end
  for local(i) = 0 to 199
    set var(roll) = rnd(-3.5,8.5)
    if var(roll) < -3 or var(roll) > 8 or floor(var(roll)) != var(roll)
      output 0
    end
  end
  output 1
end
'''
        self.assertEqual(self.run_source(source), '1\n')

    def test_gradient_noise_and_fbm_match_scalar_reference(self):
        points = [(0.1, 0.2, 0.3), (-1.25, 2.5, -3.75), (12.999, -3.001, 0.001),
                  (10000.125, -20000.5, 30000.75), (0, 0, 0), (1, -2, 3)]
        checks = []
        for x, y, z in points:
            expected = reference_noise(x, y, z)
            checks.append(f'abs(noise({x},{y},{z}) - ({expected!r})) < 1e-12')
        for octaves in (0, 1, 4, 16, 99):
            total = norm = 0.0
            x, y, z, amplitude = .1, .2, .3, .5
            for _ in range(min(octaves, 16)):
                total += reference_noise(x, y, z) * amplitude
                norm += amplitude
                x, y, z, amplitude = x*2, y*2, z*2, amplitude*.5
            expected = total/norm if norm else 0
            checks.append(f'abs(fbm(.1,.2,.3,{octaves},2,.5) - ({expected!r})) < 1e-12')
        # The language currently requires a leading digit in decimal literals.
        checks = [check.replace('(.1,.2,.3', '(0.1,0.2,0.3').replace(', .5', ', 0.5').replace('2,.5','2,0.5') for check in checks]
        body = '\n'.join(f'  if {check}\n    add var(passed) 1\n  end' for check in checks)
        self.assertEqual(self.run_source(f'fn(main)\n set var(passed) = 0\n{body}\n output var(passed) = {len(checks)}\nend\n'), '1\n')

    def test_invalid_numeric_domains_exit_with_controlled_diagnostics(self):
        for expression, message in [('sqrt(-1)', 'numeric error'),
                                    ('rnd(-1e100,1)', 'random range error'),
                                    ('noise(2147483647,0,0)', 'noise coordinate range error'),
                                    ('noise(0,-2147483649,0)', 'noise coordinate range error')]:
            with self.subTest(expression=expression):
                output = self.run_source(f'fn(main)\n output {expression}\nend\n', 2)
                self.assertIn(message, output)
        for seed in ('-1', '18446744073709551616', '1e100'):
            with self.subTest(seed=seed):
                self.assertIn('seed range error', self.run_source(f'fn(main)\n seed({seed})\n output 1\nend\n', 2))

    def test_stack_parameters_and_large_local_displacements(self):
        params = ', '.join(f'p{i}' for i in range(16))
        arguments = ', '.join(str(i) for i in range(16))
        locals_ = '\n'.join(f' set local(v{i}) = {i}' for i in range(80))
        source = f'''fn(combine, {params})
{locals_}
 output var(p0) + var(p4) * 10 + var(p15) * 100 + local(v79)
end
fn(recurse, count, a, b, c, d, e, f)
 if var(count) <= 0
   output var(d) + var(e) + var(f)
 end
 output call fn(recurse, var(count) - 1, var(a), var(b), var(c), var(d) + 1, var(e) + 2, var(f) + 3)
end
fn(main)
 if call fn(recurse, 4, 1, 2, 3, 4, 5, 6) != 39
   output 0
 end
 output call fn(combine, {arguments})
end
'''
        self.assertEqual(self.run_source(source), '1619\n')

    def test_procedural_routines_work_in_generated_graphical_runtime(self):
        source = '''scene 2d
array samples(8)
seed(42)
call fn(initialize)
fn(initialize)
  for local(i) = 0 to 7
    set array(samples,local(i)) = fbm(local(i) / 8,0.2,0.3,4,2,0.5)
  end
  set var(ready) = 1
end
fn(draw)
  set var(result) = array(samples,1)
  display rect(10,10,40 + abs(var(result)) * 20,40)
end
'''
        with NativeApp(source) as app:
            app.wait(lambda: app.read('ready') == 1 and app.read('result') != 0)
            value = app.read('result')
            self.assertTrue(-1 < value < 1)
        self.assertEqual(app.result[0], 0, app.result)

    def test_explicit_main_arguments_use_normal_call_abi_and_side_effects(self):
        self.assertEqual(self.run_source('fn(main, value)\n output var(value)\nend\ncall fn(main, 7)\n'), '7\n')
        source = '''seed(42)
fn(next, value)
  add var(calls) 1
  output var(value) + var(calls)
end
fn(main, a, b, c, d, e, f)
  output var(a) + var(b)*10 + var(e)*100 + var(f)*1000
end
call fn(main, call fn(next, 0), call fn(next, 0), 3, 4, call fn(next, 0), rnd(7,7))
'''
        self.assertEqual(self.run_source(source), '7321\n')
        result = self.run_source('fn(main, value)\n output var(value)\nend\ncall fn(main, noise(0.1,0.2,0.3))\n')
        self.assertAlmostEqual(float(result), reference_noise(.1, .2, .3), delta=1e-6)


class NativeProceduralCompileTests(unittest.TestCase):
    def test_entry_argument_arity_is_validated(self):
        for source in ('fn(main, value)\n output var(value)\nend\ncall fn(main)\n',
                       'fn(main)\n output 1\nend\ncall fn(main, 7)\n',
                       'fn(main, value)\n output var(value)\nend\n'):
            path = pathlib.Path('entry.ANVL')
            functions, top, variables, arrays = parse(path, source)
            with self.subTest(source=source), self.assertRaisesRegex(CompileError, r'entry.ANVL:.*(expects|cannot have parameters)'):
                NativeCodegen(path, functions, top, variables, arrays).generate()

    def test_runtime_routines_are_demand_loaded_and_private(self):
        for expression, present in [('sqrt(4)', False), ('noise(0,0,0)', True)]:
            source = f'fn(main)\n output {expression}\nend\n'
            path = pathlib.Path('sample.ANVL')
            functions, top, variables, arrays = parse(path, source)
            generator = NativeCodegen(path, functions, top, variables, arrays)
            generator.generate()
            self.assertEqual('_anvil_native_noise' in generator.functions, present)
            self.assertNotIn('_anvil_native_fbm', generator.functions)
        source = 'fn(_anvil_native_noise)\n output 1\nend\n'
        functions, top, variables, arrays = parse(path, source)
        with self.assertRaisesRegex(CompileError, 'reserved'):
            NativeCodegen(path, functions, top, variables, arrays)
        source = 'fn(main)\n output _anvil_native_hash(1,2,3)\nend\n'
        functions, top, variables, arrays = parse(path, source)
        with self.assertRaisesRegex(CompileError, 'reserved'):
            NativeCodegen(path, functions, top, variables, arrays).generate()
        source = 'fn(main)\n' + '\n'.join(f' set local(v{i}) = 0' for i in range(600)) + '\nend\n'
        functions, top, variables, arrays = parse(path, source)
        with self.assertRaisesRegex(CompileError, 'frame exceeds 4096'):
            NativeCodegen(path, functions, top, variables, arrays).generate()
