import sys
import unittest

from tests.native_app import NativeApp


@unittest.skipUnless(sys.platform == "win32", "native Win32 keyboard runtime")
class NativeKeyboardTests(unittest.TestCase):
    def test_key_edges_repeat_release_focus_and_numeric_arguments(self):
        source = """\
scene 2d
set var(edges) = 0
set var(same-frame) = 0
set var(ticks) = 0
set var(query-calls) = 0
set var(query-error) = 0
set var(spaces) = 0
fn(key)
  add var(query-calls) 1
  output 65
end
fn(update)
  add var(ticks) 1
  set var(held-now) = held(A)
  set var(fractional) = held(65.9)
  set var(queried) = held(call fn(key))
  if var(query-calls) != var(ticks)
    set var(query-error) = 1
  end
  set var(invalid) = held(-1) + held(256) + pressed(1e300)
  if pressed(A)
    add var(edges) 1
    if pressed(65)
      add var(same-frame) 1
    end
  end
  if pressed(SPACE)
    add var(spaces) 1
  end
  set var(space-held) = held(SPACE)
end
fn(draw)
  display rect(20,20,40,40) -rgb(90,180,240)
end
"""
        with NativeApp(source) as app:
            app.wait(lambda: app.read("ticks") >= 2)
            app.send(0x100, 65, 1)
            app.wait(lambda: app.read("held-now") == 1 and app.read("edges") == 1)
            self.assertEqual(app.read("same-frame"), 1)
            self.assertEqual(app.read("fractional"), 1)
            app.send(0x100, 65, 1 | (1 << 30))  # auto-repeat must not create another edge
            tick = app.read("ticks")
            app.wait(lambda: app.read("ticks") >= tick + 3)
            self.assertEqual(app.read("edges"), 1)
            self.assertEqual(app.read("same-frame"), 1)
            app.send(0x101, 65)
            app.wait(lambda: app.read("held-now") == 0)
            app.send(0x100, 32)
            app.send(0x101, 32)  # a tap entirely between updates is retained
            app.wait(lambda: app.read("spaces") == 1)
            self.assertEqual(app.read("space-held"), 0)
            app.send(0x100, 65)
            app.wait(lambda: app.read("edges") == 2 and app.read("held-now") == 1)
            app.send(0x008)  # focus loss clears held and pending state
            app.wait(lambda: app.read("held-now") == 0)
            app.send(0x104, 65)  # system-key message takes the same transition path
            app.wait(lambda: app.read("edges") == 3 and app.read("held-now") == 1)
            app.send(0x105, 65)
            app.wait(lambda: app.read("held-now") == 0)
            app.send(0x100, 999)
            app.send(0x100, (1 << 32) + 65)  # must not truncate a large WPARAM to A
            tick = app.read("ticks")
            app.wait(lambda: app.read("ticks") >= tick + 3)
            self.assertEqual(app.read("edges"), 3)
            self.assertEqual(app.read("held-now"), 0)
            self.assertEqual(app.read("invalid"), 0)
            self.assertEqual(app.read("query-error"), 0)
        self.assertEqual(app.result[0], 0, app.result)

    def test_draw_only_scene_observes_one_pressed_edge(self):
        source = """\
scene 2d
set var(edges) = 0
set var(draws) = 0
fn(draw)
  add var(draws) 1
  if pressed(SPACE)
    add var(edges) 1
  end
  set var(held-now) = held(SPACE)
  display rect(10,10,30,30)
end
"""
        with NativeApp(source) as app:
            app.wait(lambda: app.read("draws") >= 2)
            # Hold drawing so focus loss must clear an edge before any consumer runs.
            app.send(0x00B, 0)  # WM_SETREDRAW false
            app.send(0x100, 32)
            app.send(0x008)
            app.send(0x00B, 1)
            draw = app.read("draws")
            app.wait(lambda: app.read("draws") >= draw + 2)
            self.assertEqual(app.read("edges"), 0)
            self.assertEqual(app.read("held-now"), 0)
            app.send(0x100, 32)
            app.wait(lambda: app.read("edges") == 1 and app.read("held-now") == 1)
            draw = app.read("draws")
            app.wait(lambda: app.read("draws") >= draw + 3)
            self.assertEqual(app.read("edges"), 1)
            app.send(0x100, 32, 1 << 30)
            app.send(0x101, 32)
            app.wait(lambda: app.read("held-now") == 0)
            self.assertEqual(app.read("edges"), 1)
        self.assertEqual(app.result[0], 0, app.result)
