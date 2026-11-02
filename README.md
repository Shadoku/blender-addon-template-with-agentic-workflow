# Oblique Rig

A Blender extension (Blender 4.5 LTS through 5.2 LTS) that builds a 2:1
oblique projection rig for drawing pixel-art guides. Model or link your assets
in 3D, look through the rig's camera, and render a flat, unfiltered reference
to paint over.

## Why an oblique projection

In an oblique (cavalier or cabinet) projection the front of every object is
drawn face-on at its true shape: squares stay square, horizontals stay
horizontal, verticals stay vertical. Only the depth axis recedes, along a fixed
diagonal. With a 2:1 slope (two pixels across, one up) that diagonal is the
clean pixel staircase pixel artists already use, so edges in the guide match
the lines you would draw by hand.

Blender's cameras cannot produce this directly: an orthographic camera gives
axonometric views (isometric, dimetric), never an undistorted front face plus
a slanted depth axis. The rig gets there by shearing the scene instead of the
camera:

    X' = X + a*Y,   Z' = Z + b*Y,   Y' = Y
    (a, b) = Depth Scale * normalize(Slope Run, Slope Rise)

A straight-on orthographic camera looking along +Y then sees world X as screen
x and world Z as screen y, with depth pushed up and to the right. Y is left
untouched, so depth sorting and occlusion stay correct.

## What it builds

- **`Oblique_Source` collection**: where your assets go. It is hidden from
  renders; only the sheared copy renders.
- **`Oblique Rig` object** with a Geometry Nodes modifier (node group
  `ObliqueShear`): Collection Info pulls in the source collection, Transform
  Geometry applies the shear matrix, Realize Instances turns the result into a
  real mesh you can apply or export.
- **`Oblique Camera`**: orthographic, facing +Y, with its ortho scale sized so
  one Blender unit is exactly *Pixels per Unit* render pixels. Set as the scene
  camera.
- **`Oblique Sun`**: a sun lamp so shapes read in the render.
- **Flat render settings**: EEVEE with one sample, no pixel filter, transparent
  film, RGBA output, Standard view transform, resolution from the settings.
- **Calibration objects** (optional): a 1-unit cube at y=0, a second one 3
  units deep at y=3, and a 6x5 floor plane, all in the source collection. The
  back cube should sit up and to the right of the front one along the chosen
  slope.

## Install

1. Get the zip: a release asset, or build it with
   `python3 tools/check.py --only package --keep-dist` (writes `dist/oblique_rig-<version>.zip`).
2. In Blender: Edit > Preferences > Get Extensions, the drop-down at the top
   right > Install from Disk, pick the zip.

## Use

1. In the 3D View press N and open the **Oblique Rig** tab.
2. Adjust the settings (below) and press **Build Rig**.
3. Press **Add Calibration Objects** to check the slope, if you like.
4. Put your assets into `Oblique_Source`, or link them into it.
5. Press Numpad 0 to look through `Oblique Camera`; render with F12.

**Build Rig** is safe to press again: it updates the existing rig, camera,
lamp and render settings from the panel and never duplicates them. The shear
inputs also appear on the rig's `Oblique` modifier for quick experiments, but
the next Build Rig resets them to the panel values.

**Remove Rig** deletes the rig object, camera, sun and node group. Its
operator option also removes the source collection and the calibration
objects; without it your assets are left alone.

### Settings

| Setting | Default | What it does |
|---|---|---|
| Pixels per Unit | 16 | Render pixels per Blender unit; sets the camera's ortho scale (`max(res_x, res_y) / ppu`). |
| Resolution X / Y | 320 / 200 | Render size in pixels. |
| Slope Run / Slope Rise | 2 / 1 | Direction of the depth axis on screen. 2 / 1 is the pixel-art 2:1 slope; 1 / 1 gives 45 degrees. |
| Depth Scale | 0.6 | Length of one unit of depth relative to its true length. 1.0 = cavalier (true depth), about 0.5 = cabinet (squashed). |
| Camera Height | 0.35 | Where the camera sits above z=0, as a fraction of the frame height; raises or lowers the horizon of the guide. |

The add-on's preferences have one option: whether Build Rig reports a status
message.

## Compatibility

Blender 4.5 LTS to 5.2 LTS. Geometry Nodes and render-engine identifiers
changed between these versions; the add-on handles both (see
`docs/pitfalls.md`), and every change is tested on both.

## Development

This repository was created from a Blender add-on template built for
development with an AI coding assistant, and still carries its tooling. One
command lints the code, runs unit tests, runs tests inside a headless Blender
with the add-on loaded as a real extension, then builds the zip and installs it
into a throw-away profile:

```
$ python3 tools/check.py
blender: /home/me/.cache/blender/5.2.3/blender
[PASS] lint
[PASS] unit
[PASS] blender
[PASS] package
    PACKAGE: oblique_rig installs, enables, disables cleanly and re-enables

CHECK: PASS
```

`bash tools/install_blender.sh` downloads the pinned Blender
(`.blender-version`) into `~/.cache/blender`; `BLENDER=/path/to/blender
python3 tools/check.py` runs the check against another version (CI runs 4.5
LTS and 5.2 LTS). Python 3.9+ on the host is enough; pytest and ruff are
installed with Blender's bundled Python into `.blender-deps/`.

- `src/oblique_rig/core/`: the shear maths and mesh primitives, no `bpy`,
  unit-tested in milliseconds.
- `src/oblique_rig/rig.py`: the Blender-facing builders (node group, camera,
  render settings); `operators.py`, `ui.py`, `properties.py` stay thin.
- `tests/blender/`: operator tests, including one that evaluates the rig
  through the depsgraph and checks the sheared vertices.
- `CLAUDE.md`: the rules and loop for an AI assistant; `docs/pitfalls.md`
  and `docs/testing.md`: why the conventions exist and what headless Blender
  can verify.
- `.claude/skills/blender-addon/`: the reusable template skill
  (`tools/new_addon.py` was already run for this add-on).

## Credits and license

Started from Aaron Powell's (lunadigital) Blender add-on boilerplate. Licensed
under GPL-3.0-or-later, as required for add-ons that import `bpy` and are
distributed; see `LICENSE`.
