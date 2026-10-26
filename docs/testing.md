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
- `clean_scene` (autouse): removes all objects and orphan datablocks, calls
  `view_layer.update()`, and resets the add-on's PropertyGroup to defaults.
  It deliberately does not reload a file: `read_homefile` /
  `read_factory_settings` re-sync enabled add-ons from preferences and can
  silently drop a session-enabled add-on.
- `make_object(name, location=(0,0,0), select=True)`: an empty in the scene
  collection.
- `recording_layout`: records every `UILayout` call so `draw()` can be executed.

## Patterns

### Operators

```python
def test_spaces_objects(addon, make_object):
    a = make_object("A", (5, 0, 0))
    b = make_object("B", (0, 0, 0))
    addon.properties.get_settings(bpy.context).gap = 2.0
    assert bpy.ops.my_addon.space_evenly() == {"FINISHED"}
    assert (a.location.x, b.location.x) == pytest.approx((2.0, 0.0))
```

Test `poll()` with `bpy.ops.my_addon.space_evenly.poll()`. Messages passed to
`self.report` are printed to stdout in background mode; assert on data, not on
the message.

### Properties

Read as attributes. Expect clamping (`min=0.0` turns `-5` into `0`) and a
`TypeError` for an invalid enum identifier.

### Registration

`test_register.py` disables and re-enables the add-on within the session and
asserts that every class, the Scene property, the handler and the keymap item
are gone in between. The `package` stage repeats a generic version of this
against the installed zip by diffing `dir(bpy.types)` before and after.

### UI

```python
def test_panel_draws(addon, recording_layout):
    fake = type("P", (), {"layout": recording_layout})()
    addon.ui.MY_ADDON_PT_sidebar.draw(fake, bpy.context)
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
python3 tools/lint_addon.py src/my_addon
```

Set `BLENDER_USER_CONFIG` etc. yourself when running the bootstrap by hand, or
accept that `default_set=True` will mark the add-on enabled in your real
preferences for that Blender version.
