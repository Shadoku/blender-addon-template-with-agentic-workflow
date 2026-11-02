# Testing a Blender add-on headless

## How the loop works

`tools/check.py` runs four stages. Each one has to pass for `CHECK: PASS`.

| Stage | Runs | Time |
|---|---|---|
| `lint` | ruff check + format, `tools/lint_addon.py`, `blender --command extension validate` | ~1 s |
| `unit` | `pytest tests/unit` under Blender's bundled Python (no bpy) | ~0.3 s |
| `blender` | `blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- --mode dev` | ~1 s |
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

`evaluated_depsgraph_get()` brings the depsgraph up to date, so call it again
after changing a setting. `to_mesh()` returns only the object's mesh
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
- Rendering output (Cycles/EEVEE can render headless but it is slow; keep
  render tests out of the default check).

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
