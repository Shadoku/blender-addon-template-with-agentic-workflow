# Blender add-on pitfalls and how this template guards against them

Compiled from the Blender Python API release notes (2.80 through 5.2), the API
"gotchas" pages, devtalk threads, the extensions review queue and add-on
authors' post-mortems, plus experiments run while building this template.
Each entry names the guardrail in this repo. `tools/lint_addon.py --list-rules`
prints the rule ids.

## 1. Outdated API from training data (agents, and humans copying old answers)

Most public bpy code targets 2.8 to 4.x, so a model recalls real but removed
API unless the exact Blender version is in front of it. Rule BA007 greps for
the frequent ones and names the replacement:

| Removed/renamed | Since | Use instead |
|---|---|---|
| `obj.select = True` | 2.80 | `obj.select_set(True)` / `obj.select_get()` |
| `scene.objects.active` | 2.80 | `context.view_layer.objects.active` |
| `scene.update()` | 2.80 | `context.view_layer.update()` or evaluate the depsgraph |
| `scene.objects.link(ob)` | 2.80 | `collection.objects.link(ob)` |
| `mat * vec`, `bpy.utils.register_module`, `INFO_HT_header` | 2.80 | `@`, classes tuple, `TOPBAR_HT_upper_bar` |
| `bl_info["wiki_url"]` | 2.83 | `doc_url`; for extensions `website` in the manifest |
| `prop = IntProperty()` | 2.80 | `prop: IntProperty()` (BA012) |
| Dict context overrides `bpy.ops.x(override)` | 4.0 | `with context.temp_override(...)` |
| Principled BSDF `Subsurface`, `Specular`, `Transmission`, `Coat`, `Sheen`, `Emission` | 4.0 | `... Weight`, `Specular IOR Level`, `Emission Color` |
| `NodeTree.inputs/outputs.new` | 4.0 | `tree.interface.new_socket()` |
| `Mesh.calc_normals()`, `MeshEdge.crease/bevel_weight` | 4.0 | computed on demand; attributes |
| `mesh.use_auto_smooth`, `calc_normals_split()` | 4.1 | `sharp_edge` attribute / Smooth by Angle; `Mesh.corner_normals` |
| `bpy.types.Sequence*` | 4.4 | `Strip*`, `sequence_editor.strips` |
| `bgl` module | 5.0 | `gpu` |
| `scene.node_tree`, `scene.use_nodes` | 5.0 | `scene.compositing_node_group` |
| `BLENDER_EEVEE_NEXT` | 5.0 | `BLENDER_EEVEE` |
| `action.fcurves/groups/id_root` | 5.0 | slotted actions (channelbags) |
| `scene["my_bpy_prop"]` dict access to a bpy.props value | 5.0 | attribute access |
| `brush.use_airbrush` etc. | 5.1 | `brush.stroke_method` |
| `modifier["Socket_1"]` for Geometry Nodes inputs | 5.2 | `modifier.properties.inputs.<id>.value` |

Also: enum identifiers are upper-case (`'CYCLES'`, not `"cycles"`); Blender
5.1 moved to Python 3.13, so cp311 wheels stop working on 5.1+.

Guardrails: `CLAUDE.md` states the exact versions; BA007; the `blender` stage
turns any remaining `AttributeError` into a red test.

## 2. Operators that need a UI context

`bpy.ops.view3d.*`, `bpy.ops.screen.*`, `object.mode_set` in some states and
most modal operators fail `poll()` in background mode with
`RuntimeError: ... poll() failed, context is incorrect`. There is no window to
`temp_override` with. Guardrail: logic in `core/` (BA005 keeps bpy out),
operators read `context.selected_objects` / `bpy.data` directly, and
`docs/testing.md` lists what stays unverified.

## 3. Module path under the extensions system

An extension imports as `bl_ext.<repository>.<id>`; the repository part
differs per installation (`user_default`, `blender_org`, a custom repo, our
`dev`). `import my_addon` or `preferences.addons["my_addon"]` raises
`ModuleNotFoundError` / `KeyError` for users even though it worked in your
checkout. Guardrails: BA004 (relative imports only), BA006 (`__package__` for
preferences), and the `package` stage installs the real zip.

## 4. Registration order and leaks

- `PointerProperty(type=Group)` before `register_class(Group)`:
  `TypeError: PointerProperty(...) expected an RNA type ... may not be registered`.
- Forgetting `del bpy.types.Scene.x` or a handler in `unregister()`: the next
  enable raises `already registered as a subclass`, or the handler fires on
  freed data (`ReferenceError`).
- Two copies of the same class name (old + new install) silently unregister
  each other.

Guardrails: one ordered `CLASSES` tuple in `__init__.py` with a mirrored
`unregister()`; `lifecycle.py` records handlers, timers and keymaps;
`tests/blender/test_register.py` and the `package` stage perform an
enable -> disable -> enable round trip and diff `bpy.types`.

## 5. Exit codes lie

Blender exits 0 when a `--python` script raises unless `--python-exit-code N`
is passed, and `addon_utils.enable()` swallows a failing `register()` into a
printed traceback and a `None` return. `sys.exit()` inside Blender terminates
the process abruptly and looks like a crash. Guardrails: the bootstrap always
runs with `--python-exit-code 1`, checks the `enable()` return value, and
raises instead of `sys.exit`; `check.py` fails a stage on printed errors even
when the exit code is 0.

## 6. Wrong interpreter for dependencies

`pip install foo` on the host does nothing for Blender's bundled Python, and
installing into Blender's `site-packages` at runtime changes a shared
installation for every add-on. Blender 4.5 bundles Python 3.11, 5.1+ bundles
3.13, so compiled wheels must match. Guardrails: dev tools go into
`.blender-deps/pyX.Y` via Blender's own pip; runtime dependencies ship as
`wheels = [...]` in the manifest (download them with
`pip download --only-binary=:all: --python-version 3.13 --platform ...`).

## 7. Handlers and timers

Handlers are dropped on file load unless decorated with `@persistent`;
timers are dropped unless registered with `persistent=True`; both keep
running after the add-on is disabled unless removed. Altering data inside a
handler during render or playback can crash. Guardrails: BA011,
`lifecycle.track_handler/track_timer`, `test_handler_is_persistent`.

## 8. Dangling references

Blender frees and reallocates data on undo, mode switches and when arrays grow.
Holding an `Object`, `Mesh` or vertex reference across those points gives
`ReferenceError: StructRNA of type X has been removed` or a hard crash.
Editing data without an undo step corrupts the undo stack. Guardrails: store
names and look them up again; `bl_options = {"REGISTER", "UNDO"}` (BA008 makes
you declare `bl_options`); add all elements at once rather than in a loop.

## 9. Threads

`bpy` is not thread-safe; touching it from a thread crashes sooner or later.
Guardrail: BA009 forbids `threading`/`asyncio`/`concurrent`; `lifecycle.track_timer`
is the sanctioned way to get work back onto the main thread.

## 10. Naming rules

Operators: `bl_idname = "category.name"`, lowercase, exactly one dot, class
`CATEGORY_OT_name`. Panels/Menus/Headers/UILists: `PREFIX_PT_name` style for
both `bl_idname` and the class name. Blender prints
`Warning: 'x' does not contain '_PT_'` or raises on registration. Guardrails:
BA001, BA002, and `check.py` treats the warning as a failure.

## 11. Manifest and zip layout

Every field present in `blender_manifest.toml` must be non-empty; the tagline
is max 64 characters with no trailing punctuation; tags come from a fixed
list; `id` must equal the directory name; `bl_info` is ignored for extensions
and confuses readers. Guardrails: `extension validate` in `lint`, BA003,
`extension build` + `install-file` in `package`.

## 12. UI code never runs headless

`Panel.draw()` is not invoked without a window, so a typo in a property name
inside `draw()` only shows up when a human opens the panel. Guardrails:
`tests/blender/test_ui.py` calls `draw()` with a recording layout against real
context; keep `draw()` free of logic.

## 13. Writable paths and permissions

The extension's own directory can be read-only (system repository) and is
replaced on upgrade. Network use without a declared permission is rejected by
the extensions platform and ignores the user's offline preference. Guardrails:
use `bpy.utils.extension_path_user(__package__, create=True)` for files;
declare `[permissions]` in the manifest; BA010 flags network imports without it;
check `bpy.app.online_access` before connecting.

## 14. Test-infrastructure traps (found while building this template)

- Reloading a file in a test (`read_homefile`, `read_factory_settings`) can
  drop a session-enabled add-on. The fixtures wipe data instead.
- `extension install-file --enable` writes a real `userpref.blend`; always set
  `BLENDER_USER_CONFIG` / `BLENDER_USER_SCRIPTS` / `BLENDER_USER_EXTENSIONS`
  and pass `--no-prefs`. `check.py` does.
- `hasattr(bpy.ops.my.op, "x")` is always true (lazy lookup). Check
  registration through `bpy.types` or `addon_utils.check()`.
- Deleting objects leaves stale `None` entries in `view_layer.objects` until
  `view_layer.update()`.
- `bl_idname` read from an RNA *instance* (`prefs.bl_idname`) returns garbage;
  read it from the class.
- `@persistent` sets `fn._bpy_persistent = None`; test with `hasattr`, not
  `getattr(..., False)`.

## Sources

- Python API release notes: https://developer.blender.org/docs/release_notes/<version>/python_api/
  (2.80, 2.83, 4.0, 4.1, 4.2, 4.3, 4.4, 5.0, 5.1, 5.2)
- API gotchas: https://docs.blender.org/api/current/info_gotchas_operators.html ,
  info_gotchas_crashes.html , info_gotchas_threading.html
- Extensions: https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html ,
  addons.html , python_wheels.html ,
  https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html
- Handlers/timers: https://docs.blender.org/api/current/bpy.app.handlers.html ,
  https://docs.blender.org/api/current/bpy.app.timers.html
- bl_idname rules: https://devtalk.blender.org/t/potential-errors-final-bl-idname-requirements/4601
- Agent-generated bpy failures: https://www.strayspark.studio/blog/ai-hallucinating-blender-python-api-bpy-fix
- LTS schedule: https://www.blender.org/download/lts/
