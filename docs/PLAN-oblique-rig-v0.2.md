# Plan: Oblique Rig 0.2, reference-rendering features

Status: implemented, 2026-11-02 (version 0.2.0; `check.py` passes on 4.5.3
and 5.2.3; section 7 lists the deviations). Builds on
`docs/PLAN-oblique-rig.md` (0.1: rig, camera, calibration, Add Selected, view
toggle). The add-on produces
references to paint over, never final art; every feature below is judged by
how much it improves that reference.

Features, in priority order:

| # | Feature | Why |
|---|---|---|
| A | Pixel-exact depth and camera | Back edges that land between pixels blur the reference. With defaults one unit of depth currently moves 14.31 px right and 7.16 px up. |
| B | Render Guide: layered passes to disk | The reference is the deliverable; today it is one F12 frame. |
| F | Outline pass with whole-pixel weights (user request) | Crisp, integer-width outlines, outer and inner, configurable. |
| C | Fit to content and footprint readout | Removes the guess-and-check loop on resolution and camera height; tells the painter the sprite size. |
| D | Directions and turnarounds | Game sprites need 4 or 8 facings with identical framing. |
| E | Guide overlays (floor grid, ground line, depth axis) | A ruler on every reference, pixel-exact once A is in. |
| G | Presets | Common slopes and resolutions in one click. |
| H | Depth-sort warning | Flags source objects that interpenetrate in 3D (changed from the screen-rect criterion, see section 7). |

## 1. Verified facts (this session, Blender 4.5.3 and 5.2.3 binaries in `~/.cache/blender/`)

Rendering headless:

| Fact | Detail |
|---|---|
| Cycles renders headless on CPU without extra libraries | 64x64 frame in 3.6 s |
| Workbench and EEVEE need `libEGL.so.1` | Without it Blender prints `Couldn't open libEGL.so.1` and **exits** (no Python exception; the whole test run dies). |
| With Mesa installed, both render headless through llvmpipe | `apt-get install -y libegl1 libgl1 libgles2 libglx-mesa0 libgl1-mesa-dri libegl-mesa0` (done in this container). Workbench 64x64: 5 s. EEVEE: 36 s (shader compile). **Use Workbench.** |
| Harmless noise | Each headless Workbench render prints `EGL Error (0x3009): EGL_BAD_MATCH ...` three times. It does not match `check.py`'s `ERROR_LINE` regex (`^Error: ` / `^ERROR `), so tests are not failed by it. |
| Detecting EGL in a test | `ctypes.util.find_library("EGL")` returns `None` when it is missing; skip render tests then. |
| Workbench flat pass is exact | `render.engine = "BLENDER_WORKBENCH"`, `scene.display.shading.light = "FLAT"`, `.color_type = "MATERIAL"`, `scene.display.render_aa = "OFF"`, `render.filter_size = 0`, `film_transparent = True`, `view_transform = "Standard"`, `look = "None"`: a material with `diffuse_color = (1, 0, 0, 1)` renders as (255, 0, 0) within +-1/255 and **zero partially transparent pixels**. |
| `scene.display.shading` properties | `light` (STUDIO/MATCAP/FLAT), `color_type` in MATERIAL, OBJECT, RANDOM, VERTEX, TEXTURE, SINGLE; `single_color`, `show_object_outline`, `object_outline_color`, `show_cavity`, `show_shadows`, `studio_light`. `scene.display.render_aa` in OFF, FXAA, 5, 8, 11, 16, 32. Same on both versions. |
| `render.engine` enum items list only EEVEE | Cycles and Workbench are registered dynamically; assigning the strings `"CYCLES"` / `"BLENDER_WORKBENCH"` works. Do not look them up in `enum_items`. |
| `view_settings.look` names depend on the view transform | Under Standard the item is `"None"`; `"NONE"` raises TypeError. `rig.setup_render` already falls back. |
| Compositor API differs | 5.2: `scene.compositing_node_group`, no `scene.node_tree`; 4.5: `scene.node_tree`/`use_nodes`. **We do not use the compositor**; outlines, grids and compositing are done in pure Python on pixel arrays. |
| Freestyle | Thickness is a float in pixels and strokes are anti-aliased. Not used. |
| numpy | numpy 2.x is bundled with Blender's Python, and `check.py` runs `tests/unit` with Blender's Python, so `core/` may import numpy (lint BA005 only bans bpy). |
| Image round trip | `bpy.data.images.load(path)` then `image.colorspace_settings.name = "Non-Color"` makes `pixels` the raw byte values / 255 (no colour management). Rows are bottom-up. Writing goes through our own PNG encoder so colours are byte-exact. |
| Modifier inputs | 4.5: `mod[identifier] = v`; 5.2: `mod.properties.inputs.<identifier>.value`. `rig.set_modifier_input` wraps both. |
| Transform Geometry matrix mode | 4.5: `node.mode = "MATRIX"`; 5.x: `node.inputs["Mode"].default_value = "Matrix"`. `rig.set_transform_mode_matrix` wraps both. |
| Test budget | `check.py` gives the blender stage 900 s. Keep headless renders to 64x48 or smaller and at most ~6 renders across the whole suite. |

## 2. Contracts

Three agents work in parallel in one tree. Each owns files; nobody edits another
agent's files. The contracts below are what they code against.

### 2.1 Settings (owner: Agent B, `properties.py`, group `OBLIQUE_RIG_Settings`)

Existing: `pixels_per_unit`, `resolution_x`, `resolution_y`, `slope_run`,
`slope_rise`, `depth_scale`, `camera_height_fraction`, `view_mode`.

New (name: type, default, limits, notes):

| Property | Type | Default | Notes |
|---|---|---|---|
| `pixel_exact` | Bool | True | When on, shear comes from `depth_px_*`, camera is pixel-snapped, resolutions are forced even on build; the float slope controls are hidden in the panel. |
| `depth_px_right` | Int | 16 | min 0, soft_max 64. Pixels one unit of depth moves right. |
| `depth_px_up` | Int | 8 | min 0, soft_max 64. Pixels one unit of depth moves up. |
| `camera_offset_x` | Float | 0.0 | unit LENGTH. Camera x; snapped to whole pixels in pixel-exact mode. Set by Fit. |
| `direction` | Float | 0.0 | subtype ANGLE (stored radians). Rotation of the source about Z before the shear. |
| `auto_seat` | Bool | True | After rotating, translate the whole source so its bounding-box front edge is at y = 0 and it is centred on x = 0. |
| `direction_count` | Int | 4 | min 1, max 16. Turnaround facings, evenly spaced starting at `direction`. |
| `output_dir` | String | `//guides/` | subtype DIR_PATH. |
| `output_name` | String | `guide` | Base file name. |
| `pass_flat` | Bool | True | Workbench FLAT + MATERIAL. |
| `pass_shaded` | Bool | True | Workbench STUDIO + MATERIAL. |
| `pass_ids` | Bool | False | Workbench FLAT + RANDOM (one flat colour per object). |
| `pass_silhouette` | Bool | False | Derived from the flat pass alpha, no extra render. |
| `pass_composite` | Bool | True | shaded (or flat) + grid + outline stacked, for a quick look. |
| `make_sheet` | Bool | True | Turnaround: also write one horizontal sprite sheet per pass. |
| `grid_enabled` | Bool | False | Guide overlay pass. |
| `grid_step` | Int | 1 | min 1. Units between grid lines. |
| `grid_extent` | Int | 8 | min 1. Units drawn each side of the origin, and in depth. |
| `grid_color` | FloatVector | (0.0, 0.8, 1.0, 0.6) | size 4, subtype COLOR, min 0, max 1. |
| `outline_enabled` | Bool | False | |
| `outline_outer_px` | Int | 1 | min 0, max 8. Weight of the silhouette outline. |
| `outline_inner_px` | Int | 1 | min 0, max 8. Weight of lines between objects/materials. |
| `outline_position` | Enum | OUTSIDE | OUTSIDE (grows the shape), INSIDE (eats into it). |
| `inner_lines` | Enum | OBJECTS | NONE, OBJECTS (object boundaries from the ids pass), MATERIALS (colour boundaries from the flat pass). |
| `outline_corners` | Bool | False | False: 4-connected steps (pixel-art diamond); True: 8-connected (square). |
| `outline_color` | FloatVector | (0, 0, 0, 1) | size 4, subtype COLOR. |
| `last_footprint` | String | "" | Read-only readout, set by Build/Fit: e.g. `48 x 72 px`. |
| `last_warnings` | String | "" | Read-only, set by Build/Fit: depth-sort warnings, `;`-separated. |

`properties.params_from_settings(settings) -> core.oblique.RigParams` (B writes
it) converts the group to the plain dataclass below, so `rig.py` and
`render.py` never read a PropertyGroup.

### 2.2 Core (owner: Agent A, `src/oblique_rig/core/`, pure Python + numpy, no bpy, no mathutils)

Pixel arrays are numpy `uint8` with shape `(height, width, 4)`, RGBA, straight
alpha, **row 0 at the bottom** (Blender's order). Masks are `bool (h, w)`.

`core/oblique.py` additions:

```python
@dataclass(frozen=True)
class RigParams:
    pixels_per_unit: int
    resolution_x: int
    resolution_y: int
    slope_run: float
    slope_rise: float
    depth_scale: float
    pixel_exact: bool
    depth_px_right: int
    depth_px_up: int
    camera_height_fraction: float
    camera_offset_x: float
    direction: float          # radians
    auto_seat: bool
    view_mode: str

    def shear(self) -> tuple[float, float]:
        """(a, b): pixel-exact -> (px_right/ppu, px_up/ppu); else shear_coefficients(...)."""
    def modifier_inputs(self) -> tuple[float, float, float]:
        """(Slope Run, Slope Rise, Depth Scale) to feed the node group so that it yields self.shear().
        pixel-exact -> (px_right, px_up, hypot(px_right, px_up) / ppu)."""
    def effective_resolution(self) -> tuple[int, int]:
        """Even resolutions when pixel_exact (round up), else unchanged."""
    def camera(self) -> tuple[float, float, float]:
        """(x, -100, z). pixel-exact: x and z snapped to whole pixels (multiples of 1/ppu)."""

def pixel_step_to_slope(px_right: int, px_up: int, pixels_per_unit: int) -> tuple[float, float, float]
    # ValueError if both steps are 0 or ppu <= 0
def snap_to_pixel(value_units: float, pixels_per_unit: int) -> float
def project_to_pixels(point, a, b, pixels_per_unit, cam_x, cam_z, res_x, res_y) -> tuple[float, float]
    # px = (x + a*y - cam_x)*ppu + res_x/2 ; py = (z + b*y - cam_z)*ppu + res_y/2  (bottom-left origin)
def screen_rect(points, a, b, pixels_per_unit, cam_x, cam_z, res_x, res_y) -> tuple[float, float, float, float]
    # (xmin, ymin, xmax, ymax) in pixels of the sheared points
def footprint_px(bounds_min_sheared, bounds_max_sheared, pixels_per_unit) -> tuple[int, int]
    # ceil of the sheared extent in pixels
@dataclass(frozen=True)
class FitResult: resolution_x: int; resolution_y: int; camera_offset_x: float; camera_height_fraction: float
def fit_frame(bounds_min_sheared, bounds_max_sheared, pixels_per_unit, padding_px, even=True) -> FitResult
    # frame = extent + 2*padding, rounded up to even; camera x = centre snapped to pixels;
    # camera_height_fraction chosen so that camera z == snapped centre z for that resolution_y
```

`core/outline.py` (numpy):

```python
def dilate(mask, steps: int, corners: bool = False) -> mask   # 4-connected per step; 8-connected with corners
def erode(mask, steps: int, corners: bool = False) -> mask
def outer_outline(alpha: np.ndarray, weight: int, position: str = "OUTSIDE", corners: bool = False) -> mask
    # OUTSIDE: dilate(shape, weight) & ~shape ; INSIDE: shape & ~erode(shape, weight); weight 0 -> empty
def label_image(rgba: np.ndarray) -> np.ndarray      # (h, w) int: unique opaque colour -> id, transparent -> -1
def inner_lines(labels: np.ndarray, weight: int, corners: bool = False) -> mask
    # pixels whose right or upper neighbour has a different label, both >= 0; then dilate(weight - 1)
def paint(mask, color_rgba: tuple[int, int, int, int]) -> np.ndarray  # (h, w, 4) uint8, colour where mask
```

`core/guides.py` (numpy):

```python
def line(canvas, x0: int, y0: int, x1: int, y1: int, color_rgba) -> None   # Bresenham, in place
def grid_layer(width, height, a_px: float, b_px: float, pixels_per_unit, cam_x_px: float, cam_z_px: float,
               step_units: int, extent_units: int, color_rgba) -> np.ndarray
    # floor z = 0: depth lines (constant y = k*step) are horizontal rows at py(k); x lines (constant x = i*step)
    # run along (a_px, b_px) per unit of depth; the ground line (k = 0) is drawn with full alpha.
    # cam_*_px are the camera position in pixels relative to the frame centre.
```

`core/compose.py` (numpy): `over(bottom, top) -> rgba` (straight-alpha "over"
with integer rounding), `stack(layers: list) -> rgba`, `sheet(frames: list,
columns: int | None = None) -> rgba` (frames of equal size, left to right,
rows wrap at `columns`).

`core/png.py` (stdlib only): `encode_rgba(pixels, bottom_up=True) -> bytes`,
`write_png(path, pixels, bottom_up=True) -> None`, `decode_rgba(data) -> np.ndarray`
(8-bit RGB/RGBA, non-interlaced, all five filter types; used by tests and to
read sheets back). zlib + struct, no PIL.

`core/presets.py`: `SLOPE_PRESETS: tuple[SlopePreset, ...]` with
`(identifier, label, right_per_unit, up_per_unit)` as fractions of
`pixels_per_unit`: `PIXEL_2_1` (1.0, 0.5) "2:1 cavalier", `CABINET_2_1`
(0.5, 0.25) "2:1 cabinet", `PIXEL_1_1` (0.5, 0.5) "1:1", `PIXEL_3_2` (0.75,
0.5) "3:2", `PIXEL_1_2` (0.5, 1.0) "1:2 (steep)"; `slope_preset(identifier,
pixels_per_unit) -> (px_right, px_up)` (rounded, at least 1 where the fraction
is non-zero). `RESOLUTION_PRESETS: tuple[(identifier, label, res_x, res_y,
ppu)]`: `R320_200_16`, `R640_360_16`, `R256_256_16`, `R128_128_8`,
`R512_288_32`.

`core/overlap.py`: `overlapping_pairs(items) -> list[tuple[str, str]]` where
each item is `(name, screen_rect, (y_min, y_max))`; a pair is reported when
the screen rects overlap (area > 0) and the depth ranges overlap (so the
painter cannot tell which is in front from the silhouette alone).

### 2.3 Rig and render (owners: Agent B `rig.py`; Agent C `render.py` + `operators_render.py`)

`rig.py` (B): `build(scene, params: RigParams) -> Object` replaces the
keyword-argument signature (keep `build_*` helpers). Node group gains inputs
`Direction` (float, radians, default 0) and `Auto Seat` (bool, default True):
Collection Info -> Transform (rotation Z = Direction) -> [Auto Seat: Bounding
Box -> translation (-(min.x+max.x)/2, -min.y, 0) via Switch] -> Transform
(shear matrix) -> Realize Instances. `set_modifier_input(mod, "Direction",
radians)` is what the turnaround uses to step facings. New
`rig.sheared_bounds(scene, rig_object) -> (min, max)` from the evaluated mesh,
and `rig.source_rects(scene, params) -> list[(name, rect, (ymin, ymax))]` per
source object for the overlap check.

`render.py` (C):

```python
class RenderSettingsGuard:   # context manager: saves/restores engine, display.shading.*, display.render_aa,
                             # render.filepath/filter_size/film_transparent/resolution*, image_settings.*,
                             # view_settings.view_transform/look, and modifier input "Direction"
def render_pass(scene, kind: str, path: str) -> None   # kind in FLAT, SHADED, IDS; Workbench as in section 1
def read_rgba(path: str) -> np.ndarray                 # load, Non-Color, foreach_get, reshape (h, w, 4) uint8
def write_rgba(path: str, pixels: np.ndarray) -> None  # core.png.write_png
def render_guides(scene, settings_snapshot, params, out_dir, name, direction: float | None = None) -> list[str]
    # renders the enabled passes, derives silhouette/outline/grid/composite in Python, returns written paths
```

Operators (C, `operators_render.py`): `oblique_rig.render_guides` ("Render
Guides") and `oblique_rig.render_turnaround` ("Render Turnaround"); both poll
for an existing rig and a camera; both `REGISTER` only (they write files, not
scene data; no `UNDO`). File names: `<name>_<pass>.png`, turnaround
`<name>_d<index:02d>_<pass>.png` and `<name>_sheet_<pass>.png`. The manifest
gets `[permissions] files = "Write guide renders to the chosen output folder"`.
The render operators resolve `//` with `bpy.path.abspath`; if the file is
unsaved and the path is relative, report an ERROR-free WARNING and cancel.

Operators (B, `operators.py`): `oblique_rig.fit_to_content` (option
`padding_px` int default 4), `oblique_rig.apply_slope_preset` (enum property
from `SLOPE_PRESETS`), `oblique_rig.apply_resolution_preset`. Build and Fit
update `last_footprint` and `last_warnings`.

UI (B, `ui.py`): split into sub-panels under `OBLIQUE_RIG_PT_sidebar`:
Projection (pixel-exact toggle, depth px pair or slope controls, preset menu
via `operator_menu_enum`, readout "1 unit depth = R px right, U px up"),
Frame (resolution pair + preset, ppu, camera height, camera x, Fit button,
footprint label, warnings label), Direction (angle, auto seat, count), Output
(dir, name, pass toggles, outline block, grid block, Render Guides, Render
Turnaround buttons by literal bl_idname strings `"oblique_rig.render_guides"`
/ `"oblique_rig.render_turnaround"` so `ui.py` does not import C's module),
Rig (Build, Add Selected, Add Calibration, Remove, view toggle, status). B
includes `operators_render.CLASSES` in `__init__.CLASSES`; until C's module
exists B may stub it as an empty tuple in a file C then replaces, or
coordinate by creating `operators_render.py` with `CLASSES: tuple = ()` first
thing (C owns it from then on).

## 3. Tests

Unit (`tests/unit/`, A): `test_oblique.py` additions (pixel step maths: 16/8
at ppu 16 -> a = 1.0, b = 0.5; `modifier_inputs` reproduces `shear()`; even
resolution; camera snapping; `project_to_pixels` for the origin and a sheared
point; `fit_frame` on a known box), `test_outline.py` (1-pixel shape, weight 1,
4-connected -> 4 outline pixels; corners -> 8; weight 2 -> 12; INSIDE on a 4x4
square with weight 1 -> 12 pixels; `inner_lines` between two touching colours
-> exactly one column of pixels; weight 0 -> empty), `test_guides.py` (row
positions of depth lines for a_px 16, b_px 8; Bresenham endpoints; ground line
alpha), `test_compose.py` (over with opaque/transparent/half; sheet geometry),
`test_png.py` (encode/decode round trip of random RGBA; bottom-up flag; PNG
signature and IHDR), `test_presets.py`, `test_overlap.py`.

Blender (`tests/blender/`, B): `test_pixel_exact.py` (build with defaults:
modifier inputs equal `modifier_inputs()`; a vertex at depth 1 moves exactly 1.0
right and 0.5 up in units; camera z is a multiple of 1/ppu; odd resolution 321
becomes 322 on the render settings), `test_direction.py` (direction 90 deg with
auto seat on an off-centre asymmetric source: evaluated bounds min y == 0 and
x centred; auto seat off leaves it where rotation put it), `test_fit.py`
(after build + calibration + fit: footprint matches evaluated bounds, resolution
even, camera x snapped, `last_footprint` text set), `test_presets.py`,
`test_overlap_warning.py` (two cubes at the same x, y 0..1 and y 0.5..1.5 ->
one warning; far apart -> none), updates to `test_properties.py` (defaults
table), `test_ui.py` (every setting drawn across the sub-panels, every operator
including the two render idnames), `test_register.py` (class list),
`test_build.py` where the `build` signature changed.

Blender render (`tests/blender/test_render.py`, C): module-level skip when
`ctypes.util.find_library("EGL") is None` **before any render** (a missing EGL
kills Blender). Scene: build, calibration, 64x48 at ppu 8, output to
`tmp_path`. One `render_guides` call with flat, ids, outline (outer 1, inner 1),
grid, silhouette, composite enabled, then assert: files exist; flat pass has
zero partial alpha and its opaque colour set is the calibration material
colours (give the calibration objects two distinct `diffuse_color` materials
in `rig.add_calibration_objects` so this is testable: B adds that); outline
pass pixel count equals `outer_outline(...)` recomputed from the flat alpha by
core; grid pass has a row of full-alpha pixels on the ground line; composite
is opaque wherever flat is. One `render_turnaround` call with
`direction_count = 2`, flat only, sheet on: two frames plus a sheet of width
2x64. Expected wall time: about 6 renders, under 60 s. Also a settings-guard
test that render settings are restored (engine, shading, filepath).

## 4. Infrastructure and docs (Agent D, after A, B, C)

- `.github/workflows/ci.yml`: step `sudo apt-get update && sudo apt-get install -y libegl1 libgl1 libgles2 libglx-mesa0 libgl1-mesa-dri libegl-mesa0` before the checks.
- `.claude/hooks/session-start.sh`: same install when running as root in the remote container (`apt-get` available), ignoring failure.
- `tools/install_blender.sh`: unchanged (binary only). `CLAUDE.md`: a "Reading failures" row for `Couldn't open libEGL.so.1` (install Mesa; render tests skip without it), the layout block (new modules), the commands table unchanged.
- `docs/pitfalls.md`: entries for headless GPU rendering (Mesa, Workbench over EEVEE, EGL_BAD_MATCH noise), `look` names depending on the view transform, `engine` enum items being incomplete.
- `docs/testing.md`: render tests, the skip rule, the pixel-exact assertions.
- `README.md`: the painter's workflow (Build -> Add Selected -> Fit -> Render Guides; turnarounds), every setting, the pass files and what to do with them in the paint program, outline and grid options, presets, CI note.
- Manifest version `0.2.0`.
- Final: `python3 tools/check.py` and `BLENDER=~/.cache/blender/4.5.3/blender python3 tools/check.py` both `CHECK: PASS`.

## 5. Work split

| Agent | Owns | Verifies with |
|---|---|---|
| A | `core/oblique.py` (additions), `core/outline.py`, `core/guides.py`, `core/compose.py`, `core/png.py`, `core/presets.py`, `core/overlap.py`, `tests/unit/` | `--only unit`, `--only lint` |
| B | `properties.py`, `rig.py`, `operators.py`, `ui.py`, `__init__.py`, `tests/blender/` except `test_render.py`, `conftest.py` if needed | full check on 5.2 and 4.5 (unit may be red until A lands) |
| C | `render.py`, `operators_render.py`, `blender_manifest.toml` permissions, `tests/blender/test_render.py` | `--only blender --filter=render`, then full check |
| D | docs, CI, hook, manifest version, final check on both versions, fixes anywhere | full check on both versions |

## 6. Out of scope

Animation frame ranges, EEVEE/Cycles passes (normals, depth), importing the
reference back into a paint program, per-object outline weights, anti-aliased
"soft" outlines.

## 7. Deviations from this plan

What the implementation does differently, and why:

- **Inner line width equals the weight.** The contract said "boundary pixels,
  then dilate(weight - 1)", which makes weight 2 three pixels wide. Instead
  weight N is an N-pixel line: odd weights grow the one-pixel boundary set by
  `(N - 1) // 2` on both sides, even weights start from the pixels on both
  sides of the boundary. Weight 1 is unchanged (the left/lower side).
- **Fit covers every touched pixel.** `fit_frame` sizes each axis as
  `ceil(max * ppu) - floor(min * ppu)` plus padding (the grid cells the
  content touches), not `ceil(extent)`; the two agree for grid-aligned
  bounds, and the frame edges always lie on the world pixel grid.
- **The grid uses floor.** Each grid point is drawn in the pixel that contains
  it (`floor`, with 1e-6 tolerance), not the nearest one, matching how the
  renderer covers a pixel from its lower-left corner.
- **The source is realized before seating.** Geometry Nodes' Bounding Box
  ignores instances, so the node group is Collection Info -> Realize ->
  Turn -> Seat -> Shear -> Realize rather than measuring the instances.
- **Ids via temporary materials.** Workbench's RANDOM colour is per object,
  and the rig is one realized object, so RANDOM gives one colour. The ids
  pass assigns each source object's data a temporary material with a distinct
  colour (whole sRGB bytes), renders with MATERIAL colour and restores the
  original slots.
- **Near-colour merge.** Workbench on 4.5 renders some faces with +-1 noise
  per channel, which split one material into several labels.
  `core.outline.merge_near_colors` snaps colours within 1 step to the most
  frequent one before `label_image` (used for both inner-line modes).
- **Overlap criterion changed to 3D interpenetration.** The screen-rect plus
  depth-range test fired on every calibration build (the floor's depth range
  contains the cubes and its rect covers theirs). `overlapping_pairs` now
  takes `(name, (xmin, ymin, zmin), (xmax, ymax, zmax))` world bounding
  boxes from `rig.source_boxes` (replacing `rig.source_rects`) and reports a
  pair when the boxes overlap by more than 1e-9 on all three axes. Touching
  (a cube on a floor) and one-behind-the-other do not count.
- Smaller items: `output_dir` declares `PATH_SUPPORTS_BLEND_RELATIVE` (else
  assigning `//guides/` warns); under the Standard view transform the look is
  set as `"None"` although `enum_items` lists `NONE`.
