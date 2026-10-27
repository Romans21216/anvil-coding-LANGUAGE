import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RuntimeIntegrationTests(unittest.TestCase):
    def test_projected_sphere_bounds_contain_off_axis_silhouettes(self):
        from compiler.anvil import build_c, find_compiler

        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC is required to run the native projection regression test")

        harness = r'''#include "anvil_projection.h"
#include <stdio.h>

static int contains_projected_sphere(double cx, double cy, double depth,
                                     double radius, double focal) {
  AnvilPixelBounds bounds;
  if (!anvil_project_sphere_bounds(cx, cy, depth, radius, focal,
                                   960, 600, &bounds))
    return 0;
  for (int latitude = -90; latitude <= 90; latitude += 2) {
    const double lat = latitude * 0.017453292519943295769;
    for (int longitude = 0; longitude < 360; longitude += 2) {
      const double lon = longitude * 0.017453292519943295769;
      const double x = cx + radius * cos(lat) * cos(lon);
      const double y = cy + radius * sin(lat);
      const double z = depth + radius * cos(lat) * sin(lon);
      if (z <= 0.08) continue;
      const double sx = 480.0 + focal * x / z;
      const double sy = 324.0 - focal * y / z;
      if (sx < 0.0 || sx >= 960.0 || sy < 0.0 || sy >= 600.0) continue;
      const int px = (int)floor(sx);
      const int py = (int)floor(sy);
      if (px < bounds.min_x || px > bounds.max_x ||
          py < bounds.min_y || py > bounds.max_y)
        return 0;
    }
  }
  return 1;
}

int main(void) {
  const double focal = 685.6;
  if (!contains_projected_sphere(-3.25, 0.85, 8.7, 0.42, focal) ||
      !contains_projected_sphere(4.2, -1.1, 7.5, 1.25, focal) ||
      !contains_projected_sphere(-1.8, 2.0, 3.1, 0.8, focal) ||
      !contains_projected_sphere(0.0, 0.0, 0.82, 0.8, focal)) {
    puts("projected sphere silhouette escaped computed bounds");
    return 1;
  }
  puts("projected sphere samples remained within computed bounds");
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            c_file = temp_path / "projection_bounds.c"
            executable = temp_path / "projection_bounds.exe"
            c_file.write_text(harness, encoding="utf-8")
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run([str(executable)], capture_output=True,
                                    text=True, timeout=8)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("remained within computed bounds", result.stdout)

    def test_fixed_rate_and_queued_key_edge_at_runtime(self):
        from compiler.anvil import build_c, find_compiler

        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC is required to run the Windows runtime integration probe")

        harness = r'''#include "anvil_runtime.h"
#include <stdio.h>

static int updates;
static int key_seen;
static double first_step;
static double elapsed_at_end;
static int key_posted;

static double update(void) {
  updates++;
  if (updates == 1) {
    key_seen = (int)anvil_pressed(ANVIL_KEY_SPACE);
    first_step = anvil_delta();
  }
  if (updates == 4) {
    elapsed_at_end = anvil_time();
    PostQuitMessage(0);
  }
  return 0.0;
}

static double draw(void) {
  if (!key_posted) {
    HWND window = FindWindowA("AnvilNativeGameWindow", "Anvil Runtime Probe");
    if (window) {
      key_posted = 1;
      PostMessageA(window, WM_KEYDOWN, VK_SPACE, 0);
    }
  }
  return 0.0;
}

int main(void) {
  anvil_set_fixed_hz(10);
  anvil_run(update, draw, "Anvil Runtime Probe");
  printf("updates=%d pressed=%d step=%.3f elapsed=%.3f\n",
         updates, key_seen, first_step, elapsed_at_end);
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            c_file = temp_path / "runtime_probe.c"
            executable = temp_path / "runtime_probe.exe"
            c_file.write_text(harness, encoding="utf-8")
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run([str(executable)], capture_output=True,
                                    text=True, timeout=8)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + str(result.returncode))
        match = re.search(r"updates=(\d+) pressed=(\d+) step=([0-9.]+) elapsed=([0-9.]+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        updates, pressed, step, elapsed = match.groups()
        self.assertEqual(updates, "4")
        self.assertEqual(pressed, "1", "the posted key edge must reach the next fixed update")
        self.assertAlmostEqual(float(step), 0.1, places=3)
        self.assertGreaterEqual(float(elapsed), 0.25)
        self.assertLess(float(elapsed), 2.0)


if __name__ == "__main__":
    unittest.main()

