"""Exercise the actual transitional runtime framebuffer without creating a window."""

import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from compiler.build import build_c, find_compiler


class CircleRuntimeTests(unittest.TestCase):
    def test_viewport_bounded_circles_membership_opacity_and_extreme_inputs(self):
        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC is required for the transitional runtime regression")
        source = r'''#include "anvil_runtime.c"
#include <float.h>

static uint32_t expected_color(int alpha) {
  if (alpha <= 0) return 0x123456;
  if (alpha >= 255) return 0xff0028;
  return anvil_color((255*alpha + 0x12*(255-alpha))/255,
                     (0x34*(255-alpha))/255,
                     (0x28*alpha + 0x56*(255-alpha))/255);
}
int main(void) {
  const struct { double x,y,r; int alpha; } cases[] = {
    {20,18,9,255}, {20.25,18.75,9.125,128}, {3.5,2.25,-8.5,255},
    {20,18,0,255}, {20.25,18,0,255}, {1e-200,1e-200,0,255},
    {20,18,.25,0}, {20,18,9,-10}, {20,18,9,400},
    {3000000,3000000,1000000,255}, {1000000,0,1000000,255},
    {0,0,1073741824,128}, {0,0,1e150,255}, {0,0,1e308,128},
    {1e200,0,1e200,255}, {3e200,3e200,1e200,255}, {0,0,DBL_MAX,255},
    {DBL_MAX,DBL_MAX,1,255}, {-DBL_MAX,-DBL_MAX,1,255},
    {-1e150,0,1e150,255}, {0,-1e150,1e150,128},
    {-1e200,0,1e200,128}, {0,-1e200,1e200,255},
    {-DBL_MAX,0,DBL_MAX,255}, {0,-DBL_MAX,DBL_MAX,128},
    {1e150,0,1e150,255}, {0,1e150,1e150,128},
    {1e200,0,1e200,128}, {0,1e200,1e200,255},
    {DBL_MAX,0,DBL_MAX,255}, {0,DBL_MAX,DBL_MAX,128},
    {-7.071067811865475e199,-7.071067811865475e199,1e200,128},
    {7.071067811865475e199,-7.071067811865475e199,1e200,255},
    {-1125899906842623.0,0,1125899906842623.0,255},
    {0,-1125899906842623.0,1125899906842623.0,128},
    {-1125899906842624.0,0,1125899906842624.0,128},
    {0,-1125899906842624.0,1125899906842624.0,255},
    {-1125899906842625.0,0,1125899906842625.0,255},
    {0,-1125899906842625.0,1125899906842625.0,128},
    {-1125899906842623.5,0,1125899906842623.75,128},
    {0,-1125899906842623.5,1125899906842623.75,255},
    {NAN,0,1,255}, {0,INFINITY,1,255}, {0,0,-INFINITY,255}
  };
  size_t count = (size_t)ANVIL_WIDTH * ANVIL_HEIGHT;
  uint32_t *guarded = calloc(count + 2, sizeof(*guarded));
  if (!guarded) return 1;
  anvil_pixels = guarded + 1;
  guarded[0] = 0x00c0ffee;
  guarded[count+1] = 0x0badcafe;
  for (size_t i=0; i<sizeof(cases)/sizeof(cases[0]); ++i) {
    for (size_t pixel=0; pixel<count; ++pixel) anvil_pixels[pixel] = 0x123456;
    double x=cases[i].x, y=cases[i].y, radius=fabs(cases[i].r);
    anvil_circle(x,y,cases[i].r,300,-5,40,cases[i].alpha);
    for (int py=0; py<ANVIL_HEIGHT; ++py) {
      for (int px=0; px<ANVIL_WIDTH; ++px) {
        double dx=px-x, dy=py-y;
        int valid=isfinite(x) && isfinite(y) && isfinite(radius);
        int inside=0;
        if (valid) {
          if (fmax(radius,fmax(fabs(x),fabs(y))) <= 1e150)
            inside=dx*dx+dy*dy <= radius*radius;
          else
            inside=hypot(dx,dy) <= radius;
        }
        uint32_t expected=inside ? expected_color(cases[i].alpha) : 0x123456;
        if (anvil_pixels[(size_t)py*ANVIL_WIDTH+px] != expected) {
          printf("case=%zu pixel=%d,%d actual=%x expected=%x\n",i,px,py,
                 anvil_pixels[(size_t)py*ANVIL_WIDTH+px],expected);
          return 2;
        }
      }
    }
    if (guarded[0] != 0x00c0ffee || guarded[count+1] != 0x0badcafe) return 3;
  }
  /* Null framebuffer is also a defined no-op. */
  anvil_pixels = NULL;
  anvil_circle(0,0,DBL_MAX,255,255,255,255);
  free(guarded);
  printf("%zu circle cases: clipped completion, pixels, opacity and guards pass\n",
         sizeof(cases)/sizeof(cases[0]));
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp)
            harness, empty, executable = folder / "circle_probe.c", folder / "empty.c", folder / "circle_probe.exe"
            harness.write_text(source, encoding="utf-8")
            # Include the actual production runtime in the probe translation unit so
            # its private framebuffer can be inspected; do not link a second copy.
            empty.write_text("/* Runtime is included by circle_probe.c. */\n", encoding="utf-8")
            with mock.patch("compiler.build.RUNTIME", empty):
                build_c(compiler[1], harness, executable, release=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("44 circle cases", result.stdout)
