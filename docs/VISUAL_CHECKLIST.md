# Visual review checklist

The roadmap's 8.15 asks for a manual visual run. `python tools/visual_smoke.py`
builds and runs the visual examples, captures their client area at 960x600,
stores one PNG per example under `docs/screenshots/`, and fails on a blank or
regressed frame (`--check`, budgets in `tools/visual_budgets.json`). It cannot
say whether a picture *looks* right — that is what this checklist is for.

Run it after any renderer, text, sprite, camera or 3D change:

```
python tools/visual_smoke.py --check
```

Then open the PNGs and walk this list.

## Every shot

- [ ] The window is 960x600 and fully drawn — no black bands, no half-painted frame.
- [ ] Text is crisp, correctly aligned, and not clipped by the window edge.
- [ ] The background is the intended colour, not pure black from an uninitialised buffer.
- [ ] Nothing flickers when the example is watched live for ten seconds.

## `sprite_transform.png`

- [ ] The large sprite is clearly visible (scale 6 on a 32x32 asset), centred at 480,320, and rotates smoothly.
- [ ] Rotation is nearest-neighbour: jagged edges are expected, smearing is not.
- [ ] The small scaled copy at 110,400 is 140x140 and shows the flip when SPACE is pressed.
- [ ] Tint is warm on the rotating copy and normal again on the small one.

## `particles.png`

- [ ] Particles form a continuous fountain rather than a static clump.
- [ ] Particles fade as they age and gone ones do not reappear.
- [ ] The ground band is a straight rectangle with no gaps.

## `physics_boxes.png`

- [ ] The box and circle rest *on* the platform, not sunk into or floating above it.
- [ ] "Contacts" counts settle instead of climbing forever.
- [ ] Holding left/right pushes the box without it tunnelling through the platform.

## `first_world.png`

- [ ] Spheres are shaded with a visible light direction, not flat discs.
- [ ] The cube's faces have distinct shades and the grid recedes correctly.
- [ ] WASD/arrow input moves the camera without tearing or stretching.

## Known-good findings from the first run

- The sprite demo originally drew its "large copy" at scale 0.5 on a 32x32
  asset — a 16-pixel speck in a 960x600 window. Caught by reviewing the
  screenshot, fixed to scale 6.
- The examples load assets relative to their source/project directory. `--run`
  now uses that directory even when invoked from another caller directory; the
  starter sprite asset load is covered by `tests/test_commands.py`.

The latest screenshot review found the starter world objects partly clipped at
the bottom because its level camera looked above the ground plane. The sample
now sets `camera_angle(0, -22)`; the refreshed capture frames the cube, three
spheres and receding grid together. The automated smoke gate passes. A ten-
second live flicker check and interactive control check still require a person.

## Automated review record (2026-11-17)

python tools/visual_smoke.py --check passed for all seven captures at 960x600. Captures were reviewed for intended content, layout, clipping, and visible drawing artefacts. Keyboard/mouse interaction checks and watching each live scene for ten seconds were not exercised by this automated run; those remain manual checklist items.
