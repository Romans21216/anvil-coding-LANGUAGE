import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RuntimeIntegrationTests(unittest.TestCase):
    def test_near_plane_clips_segments_and_triangles(self):
        from compiler.anvil import build_c, find_compiler

        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC is required to run the native clipping regression test")

        harness = r'''#include "anvil_projection.h"
#include <stdio.h>

static int near_vertex(AnvilCameraVertex v) {
  return fabs(v.depth - 0.08) < 1e-12;
}

int main(void) {
  AnvilCameraVertex a = {0.0, 0.0, 0.01};
  AnvilCameraVertex b = {2.0, 4.0, 0.4};
  if (!anvil_clip_segment_near(&a, &b, 0.08) || !near_vertex(a) ||
      fabs(a.x - 0.358974358974359) > 1e-12 ||
      fabs(a.y - 0.717948717948718) > 1e-12 || b.depth != 0.4) {
    puts("crossing segment was not clipped at the near plane");
    return 1;
  }

  a = (AnvilCameraVertex){-1e308, 0.0, 0.01};
  b = (AnvilCameraVertex){1e308, 0.0, 0.4};
  if (!anvil_clip_segment_near(&a, &b, 0.08) || !near_vertex(a) ||
      !isfinite(a.x) || !isfinite(a.y)) {
    puts("finite extreme segment coordinates overflowed while clipping");
    return 10;
  }

  AnvilCameraVertex hidden_a = {0.0, 0.0, 0.01};
  AnvilCameraVertex hidden_b = {1.0, 1.0, 0.07};
  if (anvil_clip_segment_near(&hidden_a, &hidden_b, 0.08)) {
    puts("segment fully behind the near plane was retained");
    return 2;
  }

  AnvilCameraVertex input[3] = {{-1.0, 0.0, 0.01}, {1.0, 0.0, 0.4},
                                {0.0, 1.0, 0.5}};
  AnvilCameraVertex output[4];
  int count = anvil_clip_triangle_near(input, 0.08, output);
  if (count != 4 || !near_vertex(output[0]) ||
      !near_vertex(output[1]) || output[2].depth != 0.4 ||
      output[3].depth != 0.5) {
    puts("one-hidden-vertex triangle did not become a clipped quad");
    return 3;
  }

  input[0].depth = 0.01;
  input[1].depth = 0.02;
  input[2].depth = 0.5;
  count = anvil_clip_triangle_near(input, 0.08, output);
  if (count != 3 || !near_vertex(output[0]) ||
      !near_vertex(output[1]) || output[2].depth != 0.5) {
    puts("two-hidden-vertex triangle did not become a clipped triangle");
    return 4;
  }

  input[0].depth = 0.01;
  input[1].depth = 0.02;
  input[2].depth = 0.07;
  if (anvil_clip_triangle_near(input, 0.08, output) != 0) {
    puts("triangle fully behind the near plane was retained");
    return 5;
  }
  input[0].depth = 0.08;
  input[1].depth = 0.4;
  input[2].depth = 0.5;
  if (anvil_clip_triangle_near(input, 0.08, output) != 3) {
    puts("triangle on the clipping boundary was lost");
    return 6;
  }
  input[0] = (AnvilCameraVertex){-1e308, 0.0, 0.01};
  input[1] = (AnvilCameraVertex){1e308, 0.0, 0.4};
  input[2] = (AnvilCameraVertex){0.0, 1.0, 0.5};
  count = anvil_clip_triangle_near(input, 0.08, output);
  if (count != 4 || !isfinite(output[0].x) || !isfinite(output[1].x)) {
    puts("finite extreme triangle coordinates overflowed while clipping");
    return 11;
  }

  AnvilScreenPoint line_a = {-1e308, 300.0};
  AnvilScreenPoint line_b = {1e308, 300.0};
  if (!anvil_clip_screen_line(&line_a, &line_b, 960, 600) ||
      line_a.x != 0.0 || line_b.x != 959.0 || line_a.y != 300.0 ||
      line_b.y != 300.0) {
    puts("extreme screen line was not safely clipped to the viewport");
    return 12;
  }
  line_a = (AnvilScreenPoint){-1e308, -1e308};
  line_b = (AnvilScreenPoint){1e308, 1e308};
  if (!anvil_clip_screen_line(&line_a, &line_b, 960, 600) ||
      line_a.x != 0.0 || line_a.y != 0.0 || line_b.x != 599.0 ||
      line_b.y != 599.0) {
    puts("extreme diagonal was not clipped to finite viewport corners");
    return 13;
  }
  line_a = (AnvilScreenPoint){-1e308, 10.0};
  line_b = (AnvilScreenPoint){-1e308, 590.0};
  if (anvil_clip_screen_line(&line_a, &line_b, 960, 600)) {
    puts("screen line fully outside one edge was retained");
    return 14;
  }

  double hit_depth, nx, ny, nz;
  int near_cap;
  if (!anvil_intersect_sphere_near((AnvilCameraVertex){0.0, 0.0, 0.1},
                                   0.1, 0.0, 0.0, 0.08, &hit_depth, &nx,
                                   &ny, &nz, &near_cap) ||
      !near_cap || fabs(hit_depth - 0.08) > 1e-12 || nz != -1.0) {
    puts("sphere crossing the near plane did not produce a clipped cap");
    return 7;
  }
  if (!anvil_intersect_sphere_near((AnvilCameraVertex){0.0, 0.0, -0.1},
                                   0.2, 0.0, 0.0, 0.08, &hit_depth, &nx,
                                   &ny, &nz, &near_cap) ||
      !near_cap) {
    puts("sphere in front of the camera was lost at the near plane");
    return 8;
  }
  if (anvil_intersect_sphere_near((AnvilCameraVertex){0.0, 0.0, -0.3},
                                  0.2, 0.0, 0.0, 0.08, &hit_depth, &nx,
                                  &ny, &nz, &near_cap) ||
      anvil_intersect_sphere_near((AnvilCameraVertex){0.0, 0.0, 0.5}, 0.1,
                                  1.0, 0.0, 0.08, &hit_depth, &nx, &ny, &nz,
                                  &near_cap)) {
    puts("sphere fully clipped or outside the ray was retained");
    return 9;
  }
  puts("near-plane segment and triangle clipping cases passed");
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            c_file = temp_path / "near_plane_clip.c"
            executable = temp_path / "near_plane_clip.exe"
            c_file.write_text(harness, encoding="utf-8")
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=8
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("clipping cases passed", result.stdout)

    def test_resize_viewport_preserves_framebuffer_aspect_ratio(self):
        from compiler.anvil import build_c, find_compiler

        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC is required to run the native viewport regression test")

        harness = r'''#include "anvil_projection.h"
#include <stdio.h>

static int viewport_is(int cw, int ch, int x, int y, int w, int h) {
  AnvilViewport viewport;
  if (!anvil_compute_viewport(cw, ch, 960, 600, &viewport)) return 0;
  return viewport.x == x && viewport.y == y &&
         viewport.width == w && viewport.height == h;
}

int main(void) {
  AnvilViewport invalid;
  if (!viewport_is(960, 600, 0, 0, 960, 600) ||
      !viewport_is(1200, 600, 120, 0, 960, 600) ||
      !viewport_is(600, 800, 0, 212, 600, 375) ||
      !viewport_is(1280, 720, 64, 0, 1152, 720) ||
      anvil_compute_viewport(0, 600, 960, 600, &invalid) ||
      anvil_compute_viewport(600, 0, 960, 600, &invalid) ||
      anvil_compute_viewport(600, 800, 0, 600, &invalid)) {
    puts("resizable viewport bounds or aspect ratio are incorrect");
    return 1;
  }
  puts("resizable viewport preserves aspect ratio and centers letterboxing");
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            c_file = temp_path / "viewport_resize.c"
            executable = temp_path / "viewport_resize.exe"
            c_file.write_text(harness, encoding="utf-8")
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=8
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("preserves aspect ratio", result.stdout)

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

