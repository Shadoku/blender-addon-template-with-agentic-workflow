# Plan: Oblique Rig add-on

Status: implemented, 2026-11-02. Converts the uploaded `oblique_rig.py` script
(a 2:1 depth oblique projection rig for pixel-art guides) into the extension in
`src/oblique_rig/`, verified by `python3 tools/check.py` on Blender 4.5 LTS and
5.2 LTS.

## 1. Why the script fails today

Run headless on Blender 5.2.3 it raises:

    AttributeError: 'GeometryNodeTransform' object has no attribute 'mode'

Verified API facts (probed in this session, both binaries in `~/.cache/blender/`):

| Thing | Blender 4.5.3 | Blender 5.2.3 |
|---|---|---|
| Transform Geometry matrix mode | `node.mode = "MATRIX"` (enum `COMPONENTS`/`MATRIX`); no `Mode` input socket | no `mode` attribute; `node.inputs["Mode"].default_value = "Matrix"` (menu socket, default `"Components"`) |
| Transform node matrix input | `inputs["Transform"]` (`NodeSocketMatrix`) | same |
| `FunctionNodeCombineMatrix` | 16 float inputs named `Column C Row R`, column-major order, output `Matrix` | same |
| `GeometryNodeCollectionInfo` | inputs `Collection`, `Separate Children`, `Reset Children`; `transform_space` in `ORIGINAL`/`RELATIVE`; output `Instances` | same |
| `GeometryNodeRealizeInstances` | inputs `Geometry`, `Selection`, `Realize All`, `Depth` | same |
| Render engine identifier | `BLENDER_EEVEE_NEXT` | `BLENDER_EEVEE` |
| `view_settings.look` identifier | `NONE` | `NONE` |
| `scene.eevee.taa_render_samples` | present | present |
| `render.filter_size` hard min | 0.0 | 0.0 |

Setting modifier inputs with `mod[socket.identifier] = value` works on 4.5 but
raises `TypeError: id properties not supported for this type` on 5.2, where the
value lives at `mod.properties.inputs.<identifier>.value`; `rig.py` wraps both.
Everything else in the script (interface sockets, `ShaderNodeVectorMath`
NORMALIZE/SCALE, camera data) works on both.

The demo objects use `bpy.ops.mesh.primitive_cube_add`, which needs an operator
context; the add-on builds meshes from vertex data instead so it works in
background mode and in tests.

## 2. What the add-on does

A sidebar panel (3D View > N panel > "Oblique Rig") with the rig settings and
three buttons:

- **Build Rig** (`oblique_rig.build`): idempotent. Creates or updates the
  source collection, the `ObliqueShear` node group, the rig object with its
  Geometry Nodes modifier, the orthographic camera, the sun, and the render
  settings, all from the scene settings. Re-running updates values; it never
  duplicates objects. Sets `scene.camera`.
- **Add Calibration Objects** (`oblique_rig.add_calibration`): two 1-unit cubes
  (front at y=0, back at y=3) and a 6x5 floor plane in the source collection.
  Skips objects that already exist.
- **Remove Rig** (`oblique_rig.remove`): deletes rig object, camera, sun, node
  group and (optionally, via a property on the operator) the source collection
  and calibration objects. Leaves user assets alone unless asked.

Settings (PropertyGroup on `Scene`, attribute `oblique_rig`):

| Property | Type | Default | Notes |
|---|---|---|---|
| `pixels_per_unit` | Int | 16 | min 1 |
| `resolution_x` | Int | 320 | min 1 |
| `resolution_y` | Int | 200 | min 1 |
| `slope_run` | Float | 2.0 | min 0 |
| `slope_rise` | Float | 1.0 | min 0 |
| `depth_scale` | Float | 0.6 | min 0, soft max 2; 1.0 cavalier, ~0.5 cabinet |
| `camera_height_fraction` | Float | 0.35 | fraction of the frame height the camera sits above z=0 |

Names are module constants in `core/oblique.py` (`SOURCE_COLLECTION =
"Oblique_Source"`, `RIG_NAME = "Oblique Rig"`, `NODEGROUP_NAME =
"ObliqueShear"`, `CAMERA_NAME = "Oblique Camera"`, `SUN_NAME = "Oblique Sun"`,
`CALIB_FRONT`, `CALIB_BACK`, `CALIB_FLOOR`).

Preferences: keep one bool `report_results` (status-bar message after build).
No keymap (drop the template's Ctrl+Shift+Alt+E binding and its test).
Keep the no-op `load_post` handler from the template; it costs nothing and
keeps the lifecycle test meaningful.

## 3. Module layout and the core API (contract between agents)

`src/oblique_rig/core/oblique.py` — pure Python, no bpy, no mathutils:

```python
SOURCE_COLLECTION, RIG_NAME, NODEGROUP_NAME, CAMERA_NAME, SUN_NAME: str
CALIB_FRONT, CALIB_BACK, CALIB_FLOOR: str
MODIFIER_NAME = "Oblique"

def shear_coefficients(slope_run: float, slope_rise: float, depth_scale: float) -> tuple[float, float]:
    """(a, b) = depth_scale * normalize(run, rise). Raises ValueError if run and rise are both 0
    or depth_scale < 0."""

def shear_matrix_columns(a: float, b: float) -> list[float]:
    """16 floats, column-major, for FunctionNodeCombineMatrix: identity with
    [column 2, row 1] = a and [column 2, row 3] = b, i.e. X' = X + a*Y, Z' = Z + b*Y."""

def shear_point(point: tuple[float, float, float], a: float, b: float) -> tuple[float, float, float]:
    """Apply the shear to one point (used by tests and docs)."""

def ortho_scale(resolution_x: int, resolution_y: int, pixels_per_unit: int) -> float:
    """max(res_x, res_y) / pixels_per_unit. Raises ValueError for non-positive inputs."""

def camera_location(resolution_y: int, pixels_per_unit: int, height_fraction: float) -> tuple[float, float, float]:
    """(0, -100, (res_y / ppu) * height_fraction)."""

def screen_offset_per_depth_unit(slope_run, slope_rise, depth_scale, pixels_per_unit) -> tuple[float, float]:
    """How many pixels right and up one unit of depth moves on screen. For
    run=2, rise=1, depth=1, ppu=16 this is (32/sqrt5, 16/sqrt5)."""
```

`src/oblique_rig/core/primitives.py` — pure Python:

```python
def cube(size: float = 1.0, center=(0.0, 0.0, 0.0)) -> tuple[list[tuple[float,float,float]], list[tuple[int,...]]]
def plane(size_x: float, size_y: float, center=(0.0, 0.0, 0.0)) -> tuple[list[...], list[tuple[int,...]]]
```
Vertices and quad faces, suitable for `mesh.from_pydata(verts, [], faces)`.

`src/oblique_rig/rig.py` — Blender-facing builders used by the operators
(`import bpy` allowed here, keep functions small and pure in intent):
`get_or_create_collection`, `build_shear_nodegroup`, `build_rig_object`,
`build_camera`, `setup_render`, `build_light`, `add_calibration_objects`,
`remove_rig`, plus `set_transform_mode_matrix(node)` which handles both the
4.5 property and the 5.x menu socket (see table above) and
`set_eevee_engine(scene)` which tries `BLENDER_EEVEE_NEXT` then `BLENDER_EEVEE`.

Node group: Group Input -> Collection Info (RELATIVE, Separate/Reset off) ->
Transform Geometry (matrix mode, matrix from Combine Matrix fed by
normalize(run, rise, 0) * depth) -> **Realize Instances** -> Group Output.
Realizing makes the rig object's evaluated mesh a real mesh, so
`rig.evaluated_get(depsgraph).to_mesh()` exposes the sheared vertices to tests
and to anyone exporting the guide. Interface inputs: Geometry, Source
Collection, Slope Run, Slope Rise, Depth Scale (min 0, max 2).

`operators.py`, `properties.py`, `ui.py`, `preferences.py`: as described in
section 2, following the template conventions (thin operators, `REGISTER`+`UNDO`,
annotations for properties, `__package__` for preferences).

## 4. Tests

Unit (`tests/unit/`), no Blender:
- `test_oblique.py`: 2:1 defaults give direction (2,1)/sqrt5 scaled by depth;
  matrix layout has `a` at index 4 and `b` at index 6, identity elsewhere;
  `shear_point` moves a point at depth 3 by (3a, 0, 3b) and leaves y alone;
  `ortho_scale(320, 200, 16) == 20`; `camera_location` z; ValueErrors.
- `test_primitives.py`: cube has 8 verts / 6 faces inside the expected bounds,
  plane has 4 verts / 1 face with the requested extents.
- Delete `test_spacing.py` and `core/spacing.py`.

Blender (`tests/blender/`), via `check.py`:
- `test_build.py`: `bpy.ops.oblique_rig.build()` returns `{"FINISHED"}` and
  creates collection, rig object with a NODES modifier pointing at the group,
  camera (ORTHO, `ortho_scale == 20`, rotation x == pi/2, `scene.camera` set),
  sun, render settings (resolution, `filter_size == 0`, film transparent,
  RGBA, Standard view transform, 1 TAA sample). Running build twice leaves
  exactly one of each object and one node group. Changing `depth_scale` and
  rebuilding updates the modifier input.
- `test_shear.py` (the test that proves the rig works): build, add
  calibration objects, `depsgraph = context.evaluated_depsgraph_get()`,
  `mesh = rig.evaluated_get(depsgraph).to_mesh()`; the vertices of the back
  cube (y in [2.5, 3.5]) are shifted in x and z by `3*a`/`3*b` relative to the
  front cube, with `a, b = shear_coefficients(2, 1, 0.6)`; y values are
  unchanged; the source collection has `hide_render` set.
- `test_calibration.py`: creates the three objects once, idempotent.
- `test_remove.py`: after remove with `include_source=True` nothing named by the
  rig remains in `bpy.data.objects`, `.collections`, `.node_groups`, `.cameras`,
  `.lights`, `.meshes`.
- `test_properties.py`: defaults from the table; clamping at min.
- `test_ui.py`: panel draw records every settings prop and the three operators.
- `test_register.py`: update for the new class names; remove the keymap assert.
- `conftest.py`: `_wipe_data` must also clear `bpy.data.node_groups` and
  `bpy.data.collections` (unlink children from the scene collection first) so
  tests are independent.

## 5. Docs

- `README.md`: describe the add-on (what an oblique 2:1 rig is, how to use the
  panel, where to put assets, what the sliders do, install from `dist/*.zip`),
  keep the "verification loop" section, note the repo still carries the
  template tooling.
- `CLAUDE.md`: already renamed by `tools/new_addon.py`; fix any examples that
  still describe the space-evenly operator (`--filter=space_evenly`,
  `addon.operators.MY_ADDON_OT_space_evenly`, `bpy.ops.my_addon.space_evenly`)
  to point at `oblique_rig.build` / `OBLIQUE_RIG_OT_build`.
- `docs/pitfalls.md`: add a short entry about Geometry Nodes node properties
  turning into menu sockets (Transform Geometry `mode` in 5.0) with the shim.
- `.claude/skills/blender-addon/` stays untouched (it is the reusable template;
  `git checkout` already reverted the renamer's edits there).

## 6. Work split

1. (done) `tools/new_addon.py --id oblique_rig ...`; skill dir and `docs/PLAN.md`
   reverted; `check.py` passes on the renamed template.
2. Agent A: `core/oblique.py`, `core/primitives.py`, `tests/unit/`.
   Verify with `python3 tools/check.py --only unit` and `--only lint`.
3. Agent B (parallel): `rig.py`, `operators.py`, `properties.py`, `ui.py`,
   `preferences.py`, `__init__.py`, `tests/blender/`, `conftest.py`. Verify with
   `python3 tools/check.py` on 5.2 and `BLENDER=~/.cache/blender/4.5.3/blender python3 tools/check.py` on 4.5.
4. Agent C (after A and B): docs from section 5, final full check on both
   Blender versions, fix anything left.
5. Commit on `claude/trusting-hawking-4d4ihj`, push.

## 7. Follow-up changes (2026-11-02)

- **Add Selected to Rig** (`oblique_rig.add_selected`): moves the selected
  objects into the source collection and seats each one with its evaluated
  world bounding-box front edge at y = 0 and its origin at z = 0 (option
  *Bottom to Floor* uses the lowest point instead). Rig-owned objects are
  skipped; children of objects being added are only relinked. Maths in
  `core.oblique.bounds` / `placement_offset`.
- **Calibration layout** starts at y = 0 (front cube y 0..1, back cube 3..4,
  floor 0..5). The earlier layout extended to y = -0.5, and the shear maps
  negative depth to negative z, so the sheared copies dipped below the floor
  line. `test_shear.py::test_nothing_shears_below_the_floor` guards this.
- **View toggle** (`view_mode`: Source / Sheared, default Sheared): per view
  layer, hides the source collection with the eye toggle and the rig object
  with `hide_set`, or the reverse. Eye hiding keeps the source in the depsgraph
  so Collection Info still feeds the rig (tested). Build applies the current
  mode.

## 8. Out of scope (for now)

Rendering the guide to disk from the panel, a one-click "import image as
reference" step, presets for other slopes (1:1, 3:2), per-object depth sorting
controls. Easy follow-ups once the rig is in.
