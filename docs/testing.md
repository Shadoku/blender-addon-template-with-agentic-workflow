# Testing a Blender add-on headless

## How the loop works

`tools/check.py` runs four stages. Each one has to pass for `CHECK: PASS`.

| Stage | Runs | Time |
|---|---|---|
| `lint` | ruff check + format, `tools/lint_addon.py`, `blender --command extension validate` | ~1 s |
| `unit` | `pytest tests/unit` under Blender's bundled Python (no bpy) | ~0.3 s |
| `blender` | `blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- --mode dev` | ~4 s (most of it the Workbench renders) |
| `package` | `extension build`, `extension install-file --no-prefs` into a temp profile, bootstrap `--mode package` | ~2.5 s |

The bootstrap mounts `src/` as a local extension repository called `dev`, so
the add-on imports as `bl_ext.dev.<id>` with `__package__` set exactly as it
would be for a user. It then enables the add-on with `addon_utils.enable`,
checks the return value (Blender prints a traceback and returns `None` when
`register()` raises, while still exiting 0), and runs pytest on
`tests/blender` with `-s` so Blender's own error output interleaves with the
test markers. `check.py` attributes every `Traceback`, RNA `Error:` and
`register_class` warning to the test that was running and fails it.

Every Blender process runs with `BLENDER_USER_CONFIG`, `BLENDER_USER_SCRIPTS`
and `BLENDER_USER_EXTENSIONS` pointed at a temporary directory, so tests never
read or write your real preferences.

The `package` stage builds into the repository's `dist/` directory. Two
`check.py` runs at the same time (say 5.2 and 4.5 in parallel) share it and
can delete or overwrite each other's zip mid-stage, failing `package` for
reasons that have nothing to do with the code. Run the two versions one after
the other.

## Fixtures (tests/blender/conftest.py)

- `addon`: the live module. `addon.operators`, `addon.properties`, ...
- `clean_scene` (autouse): removes all objects, collections, node groups and
  orphan datablocks, calls `view_layer.update()`, and resets the add-on's PropertyGroup to defaults.
  It deliberately does not reload a file: `read_homefile` /
  `read_factory_settings` re-sync enabled add-ons from preferences and can
  silently drop a session-enabled add-on.
- `make_object(name, location=(0,0,0), select=True)`: an empty in the scene
  collection.
- `recording_layout`: records every `UILayout` call so `draw()` can be executed.

## Patterns

### Operators

```python
def test_build_creates_pixel_grid_camera(addon):
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    cam = bpy.data.objects["Oblique Camera"]
    assert cam.data.type == "ORTHO"
    assert cam.data.ortho_scale == pytest.approx(20.0)  # 320 px / 16 px per unit
    assert bpy.context.scene.camera == cam
```

`tests/blender/test_build.py` also runs the operator twice and asserts there is
still exactly one of each object, which is how idempotency is pinned down;
`test_remove.py` asserts nothing named by the rig is left in `bpy.data`.
Test `poll()` with `bpy.ops.oblique_rig.build.poll()`. Messages passed to
`self.report` are printed to stdout in background mode; assert on data, not on
the message.

### Properties

Read as attributes. Expect clamping (`min=0.0` turns `-5` into `0`) and a
`TypeError` for an invalid enum identifier.

### Registration

`test_register.py` disables and re-enables the add-on within the session and
asserts that every class, the Scene property and the handler are gone in
between. The `package` stage repeats a generic version of this
against the installed zip by diffing `dir(bpy.types)` before and after.

### Evaluated geometry (Geometry Nodes)

Modifiers, Geometry Nodes included, are evaluated headless exactly as in the
UI: the depsgraph is real, only drawing is missing. So the output of a node
tree is testable, and `tests/blender/test_shear.py` uses it to prove the rig
works rather than only that it was assembled:

```python
bpy.ops.oblique_rig.build()
bpy.ops.oblique_rig.add_calibration()
depsgraph = bpy.context.evaluated_depsgraph_get()
rig_eval = bpy.data.objects["Oblique Rig"].evaluated_get(depsgraph)
mesh = rig_eval.to_mesh()
try:
    back = [v.co for v in mesh.vertices if 2.5 <= v.co.y <= 3.5]
    ...  # x and z shifted by 3*a and 3*b relative to the front cube, y unchanged
finally:
    rig_eval.to_mesh_clear()
```

Attributes stored by the node tree are readable the same way, which tests a
render pass's input without rendering. `tests/blender/test_edge_ids.py` turns
the rig's "Edge IDs" input on with `rig.set_modifier_input`, reads the corner
colour attribute `oblique_edge_id` from the evaluated mesh, decodes each value
with `core.edge_ids.island_index` and counts islands: 6 for a cube, 2 for a
flat two-quad plane whose middle edge is marked sharp (1 with Marked Sharp
off), 3 for a 24-segment cylinder at a 30-degree crease angle and 26 at 10.
It also asserts the decoded colours equal `island_color(i)` exactly and that
the evaluated mesh's `color_attributes.active_color_name` is the island
attribute, which is what Workbench 4.5 renders in VERTEX mode
(`docs/pitfalls.md`, section 16). The render test then only has to show that
the island boundaries reach the outline pass.

`evaluated_depsgraph_get()` brings the depsgraph up to date, so call it again
after changing a setting (or the modifier inputs). `to_mesh()` returns only the object's mesh
component: it is empty when the tree outputs unrealized instances, which is
one reason the rig ends in Realize Instances (otherwise walk
`depsgraph.object_instances`). Free the mesh with `to_mesh_clear()`.

### UI

```python
def test_panel_draws(addon, recording_layout):
    fake = type("P", (), {"layout": recording_layout})()
    addon.ui.OBLIQUE_RIG_PT_sidebar.draw(fake, bpy.context)
    assert ("prop", ...) in ...  # see tests/blender/test_ui.py
```

This proves the method runs against real context and real property names. It
does not prove the panel looks right; nothing does, headless.

### Rendered output (tests/blender/test_render.py)

Workbench renders headless when libEGL is available (a GPU driver, or Mesa's
llvmpipe on a server; CI installs Mesa). Without it Blender does not raise: it
prints `Couldn't open libEGL.so.1` and exits, killing the whole test run. So
the module checks first and skips itself before importing anything that
renders:

```python
import ctypes.util
import pytest

if ctypes.util.find_library("EGL") is None:
    pytest.skip("Workbench rendering needs libEGL (install Mesa)", allow_module_level=True)
```

A skipped module shows up in `TESTS: ... skipped`; on a machine without EGL
the rest of the suite still runs, and the render code is simply unverified
there (say so when reporting).

The scene is small on purpose: the calibration objects at 64x48 px and 8 px
per unit, one unit of depth = 8 px right and 4 px up. A module-scoped fixture
calls Render Guides once with flat, ids, silhouette, outline, grid and
composite enabled; separate tests do one turnaround (two facings) and one
settings-guard render, and a second module fixture renders the outline with
sharp-edge inner lines (a flat and an EDGES render): seven renders in all, a
few seconds under llvmpipe.

The assertions are pixel-exact, because the passes are meant to be traced:

- exactly the enabled files exist, all 64x48;
- the flat pass has no partially transparent pixel, and its opaque colours are
  the two calibration materials (sRGB bytes within 1);
- the ids pass has the same alpha as the flat pass and exactly three colours
  (front cube, back cube, floor), and the temporary id materials are gone;
- the outline pass equals, pixel for pixel, `core.outline.outer_outline` plus
  `inner_lines` recomputed from the rendered flat and ids passes;
- the grid's ground line is a full-alpha row at the row the camera maths
  predicts;
- the composite is opaque wherever the flat pass is, with the outline on top;
- the turnaround sheet is exactly its frames side by side, and the render
  settings, the rig's Direction input and the user's materials are restored;
- in EDGES mode the front calibration cube's front/top crease is a run of
  outline pixels on the row `core.oblique.project_to_pixels` predicts for
  z = 1 (the row below the boundary), and the OBJECTS-mode outline has none
  there; only the outline file is written, and the Edge IDs, Crease Angle and
  Marked Sharp inputs, the view transform and the colour type are restored.

Images are read back with `render.read_rgba` (Non-Color, so `pixels` are the
raw bytes) and compared as numpy arrays, row 0 at the bottom. The `EGL Error
(0x3009): EGL_BAD_MATCH` lines each render prints are harmless and do not fail
a test (see `docs/pitfalls.md`, section 16).

### Handlers and timers

`lifecycle.track_handler` / `track_timer` register and record. Assert the
callback is in `bpy.app.handlers.load_post` after enable and absent after
disable. `hasattr(fn, "_bpy_persistent")` is how Blender marks `@persistent`.

### Deterministic data

Create objects with `bpy.data.objects.new` rather than `bpy.ops.mesh.primitive_*`
when you only need a transform; it is faster and does not depend on context.
Meshes the same way: the calibration objects come from vertex lists in
`core/primitives.py` fed to `mesh.from_pydata`, because `primitive_cube_add`
depends on the operator context and the active object.

## What headless Blender cannot verify

- Anything drawn: panel layout, icons, gizmos, overlays, `gpu` draw handlers.
- Operators whose `poll()` needs a window, area or region
  (`bpy.ops.view3d.*`, `bpy.ops.screen.*`, most modal operators). `temp_override`
  cannot help because there is no window to override with.
- Mouse/keyboard event handling in modal operators.
- Rendering without libEGL (Workbench and EEVEE need it; the render tests
  skip). With Mesa, Workbench renders are fast enough for the default check;
  EEVEE spends about 36 s compiling shaders, so keep it out of tests.

Keep logic out of these places so what remains untested is a thin shell, and
say "UI unverified" when reporting.

## Running pieces by hand

```bash
# Blender tests with a filter and full output
blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- --mode dev --filter poll --verbose
# Unit tests
PYTHONPATH=.blender-deps/py3.13 ~/.cache/blender/5.2.3/5.2/python/bin/python3.13 -m pytest tests/unit -q
# Lint
python3 tools/lint_addon.py src/oblique_rig
```

Set `BLENDER_USER_CONFIG` etc. yourself when running the bootstrap by hand, or
accept that `default_set=True` will mark the add-on enabled in your real
preferences for that Blender version.
