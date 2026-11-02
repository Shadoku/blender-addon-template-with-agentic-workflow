"""Render Guides / Render Turnaround: real Workbench renders, checked pixel by pixel.

Workbench needs libEGL even headless, and without it Blender exits outright (no
Python exception), so the whole module is skipped before anything renders when
EGL is missing. Renders are 64x48 at 8 px per unit; the suite does seven (the
sharp-edge fixture adds a flat and an EDGES render).
"""

import ctypes.util
import math
import os
import sys

import pytest

if ctypes.util.find_library("EGL") is None:
    pytest.skip(
        "Workbench rendering needs libEGL (install Mesa: libegl1 libgl1-mesa-dri)", allow_module_level=True
    )

import bpy
import numpy as np

PASSES = ("flat", "ids", "silhouette", "outline", "grid", "composite")


def _addon():
    return sys.modules[os.environ["ADDON_MODULE"]]


def _reset_settings(settings) -> None:
    for prop in settings.bl_rna.properties:
        if prop.identifier != "rna_type":
            settings.property_unset(prop.identifier)


def _setup_scene(out_dir: str, **overrides) -> "bpy.types.PropertyGroup":
    """64x48 at 8 px/unit, 1 unit of depth = 8 px right and 4 px up; rig and calibration built."""
    settings = _addon().properties.get_settings(bpy.context)
    _reset_settings(settings)
    settings.resolution_x = 64
    settings.resolution_y = 48
    settings.pixels_per_unit = 8
    settings.pixel_exact = True
    settings.depth_px_right = 8
    settings.depth_px_up = 4
    settings.output_dir = out_dir
    settings.output_name = "guide"
    for key, value in overrides.items():
        setattr(settings, key, value)
    assert bpy.ops.oblique_rig.add_calibration() == {"FINISHED"}
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    return settings


def _srgb_byte(linear: float) -> int:
    srgb = linear * 12.92 if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055
    return round(srgb * 255)


def _close(color, expected, tolerance: int = 1) -> bool:
    return all(abs(int(c) - int(e)) <= tolerance for c, e in zip(color, expected, strict=True))


@pytest.fixture(scope="module")
def guides(tmp_path_factory) -> dict:
    """One Render Guides call with flat, ids, silhouette, outline, grid and composite enabled."""
    addon = _addon()
    out_dir = str(tmp_path_factory.mktemp("guides"))
    settings = _setup_scene(
        out_dir,
        pass_flat=True,
        pass_shaded=False,
        pass_ids=True,
        pass_silhouette=True,
        pass_composite=True,
        outline_enabled=True,
        outline_outer_px=1,
        outline_inner_px=1,
        inner_lines="OBJECTS",
        grid_enabled=True,
    )
    params = addon.properties.params_from_settings(settings)
    mesh_materials = {
        ob.name: [m.name if m else None for m in ob.data.materials]
        for ob in bpy.data.collections[addon.core.oblique.SOURCE_COLLECTION].objects
    }
    assert bpy.ops.oblique_rig.render_guides() == {"FINISHED"}

    images = {}
    for name in PASSES:
        path = os.path.join(out_dir, f"guide_{name}.png")
        images[name] = addon.render.read_rgba(path) if os.path.exists(path) else None
    return {
        "dir": out_dir,
        "images": images,
        "params": params,
        "mesh_materials_before": mesh_materials,
        "mesh_materials_after": {
            ob.name: [m.name if m else None for m in ob.data.materials]
            for ob in bpy.data.collections[addon.core.oblique.SOURCE_COLLECTION].objects
        },
        "material_names_after": {m.name for m in bpy.data.materials},
    }


@pytest.fixture(scope="module")
def edge_guides(tmp_path_factory) -> dict:
    """One Render Guides call with only the outline enabled and sharp-edge inner lines (2 renders)."""
    addon = _addon()
    out_dir = str(tmp_path_factory.mktemp("edge_guides"))
    settings = _setup_scene(
        out_dir,
        pass_flat=False,
        pass_shaded=False,
        pass_ids=False,
        pass_silhouette=False,
        pass_composite=False,
        outline_enabled=True,
        outline_outer_px=1,
        outline_inner_px=1,
        inner_lines="EDGES",
        grid_enabled=False,
    )
    scene = bpy.context.scene
    o = addon.core.oblique
    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    get = addon.rig.get_modifier_input
    before = {name: get(mod, name) for name in ("Edge IDs", "Crease Angle", "Marked Sharp")}
    view_before = scene.view_settings.view_transform
    color_type_before = scene.display.shading.color_type
    assert bpy.ops.oblique_rig.render_guides() == {"FINISHED"}
    return {
        "dir": out_dir,
        "files": sorted(os.listdir(out_dir)),
        "outline": addon.render.read_rgba(os.path.join(out_dir, "guide_outline.png")),
        "params": addon.properties.params_from_settings(settings),
        "inputs_before": before,
        "inputs_after": {name: get(mod, name) for name in before},
        "view": (view_before, scene.view_settings.view_transform),
        "color_type": (color_type_before, scene.display.shading.color_type),
    }


def _front_crease(params) -> tuple[int, range]:
    """Row and inner columns of the front cube's front/top crease (z = 1, y = 0, x -0.5..0.5).

    Weight-1 inner lines sit on the lower side of a horizontal boundary, so the
    line is the row just below the crease. The end columns are left out: at the
    left end the floor shows above the front face, a boundary in every mode.
    """
    a, b = params.shear()
    cam_x, _, cam_z = params.camera()
    res_x, res_y = params.effective_resolution()

    def project(point):
        return _addon().core.oblique.project_to_pixels(
            point, a, b, params.pixels_per_unit, cam_x, cam_z, res_x, res_y
        )

    x0, py = project((-0.5, 0.0, 1.0))
    x1, py1 = project((0.5, 0.0, 1.0))
    assert py == py1 == int(py), "pixel-exact: the crease lies on a pixel boundary"
    assert x0 == int(x0) and x1 == int(x1)
    return int(py) - 1, range(int(x0) + 1, int(x1))


def test_edges_mode_draws_the_front_top_crease(edge_guides) -> None:
    row, columns = _front_crease(edge_guides["params"])
    drawn = edge_guides["outline"][..., 3] > 0
    assert len(columns) >= 6
    assert drawn[row, columns.start : columns.stop].all(), drawn[row].astype(int)


def test_objects_mode_has_no_crease(guides) -> None:
    row, columns = _front_crease(guides["params"])
    drawn = guides["images"]["outline"][..., 3] > 0
    assert not drawn[row, columns.start : columns.stop].any(), drawn[row].astype(int)


def test_edges_pass_writes_only_the_outline(edge_guides) -> None:
    assert edge_guides["files"] == ["guide_outline.png"], "flat and edge-id renders are temporary"
    assert edge_guides["outline"].shape == (48, 64, 4)


def test_edges_pass_restores_inputs_and_settings(edge_guides) -> None:
    assert edge_guides["inputs_before"]["Edge IDs"] is False
    assert edge_guides["inputs_after"]["Edge IDs"] is False
    assert edge_guides["inputs_after"]["Crease Angle"] == pytest.approx(
        edge_guides["inputs_before"]["Crease Angle"]
    )
    assert edge_guides["inputs_after"]["Marked Sharp"] == edge_guides["inputs_before"]["Marked Sharp"]
    view_before, view_after = edge_guides["view"]
    assert view_after == view_before != "Raw"
    color_before, color_after = edge_guides["color_type"]
    assert color_after == color_before


def test_guard_restores_edge_inputs_without_rendering(addon, tmp_path) -> None:
    _setup_scene(str(tmp_path), crease_angle=math.radians(40), edge_marked_sharp=True)
    o = addon.core.oblique
    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    rig = addon.rig
    with addon.render.RenderSettingsGuard(bpy.context.scene):
        rig.set_modifier_input(mod, "Edge IDs", True)
        rig.set_modifier_input(mod, "Crease Angle", 0.1)
        rig.set_modifier_input(mod, "Marked Sharp", False)
    assert rig.get_modifier_input(mod, "Edge IDs") is False
    assert rig.get_modifier_input(mod, "Crease Angle") == pytest.approx(math.radians(40))
    assert rig.get_modifier_input(mod, "Marked Sharp") is True


def test_writes_exactly_the_enabled_passes(guides) -> None:
    assert sorted(os.listdir(guides["dir"])) == sorted(f"guide_{name}.png" for name in PASSES)
    for name in PASSES:
        assert guides["images"][name].shape == (48, 64, 4), name


def test_flat_pass_is_exact(guides, addon) -> None:
    flat = guides["images"]["flat"]
    alpha = flat[..., 3]
    assert not ((alpha > 0) & (alpha < 255)).any(), "anti-aliasing or filtering left partial alpha"
    assert (alpha == 255).sum() > 200, "the calibration objects should cover a good part of the frame"

    expected = [
        tuple(_srgb_byte(c) for c in color[:3])
        for color in (addon.rig.CALIB_CUBE_COLOR, addon.rig.CALIB_FLOOR_COLOR)
    ]
    colours = {tuple(int(v) for v in px[:3]) for px in flat[alpha == 255]}
    for colour in colours:
        assert any(_close(colour, e) for e in expected), f"unexpected colour {colour}, expected {expected}"
    for e in expected:
        assert any(_close(colour, e) for colour in colours), f"colour {e} missing from {colours}"


def test_ids_pass_has_one_flat_colour_per_object(guides) -> None:
    ids, flat = guides["images"]["ids"], guides["images"]["flat"]
    alpha = ids[..., 3]
    assert not ((alpha > 0) & (alpha < 255)).any()
    assert np.array_equal(alpha, flat[..., 3]), "same geometry as the flat pass"
    colours = {tuple(int(v) for v in px[:3]) for px in ids[alpha == 255]}
    assert len(colours) == 3, f"front cube, back cube and floor each get their own colour: {colours}"


def test_ids_pass_restores_materials(guides, addon) -> None:
    assert guides["mesh_materials_after"] == guides["mesh_materials_before"]
    leftovers = {n for n in guides["material_names_after"] if n.startswith(addon.render.ID_MATERIAL_PREFIX)}
    assert not leftovers


def test_material_labels_ignore_rounding_noise(guides, addon) -> None:
    """MATERIALS inner lines label the flat pass: one label per material, whatever the GPU's +-1 noise."""
    labels = addon.core.outline.label_image(addon.core.outline.merge_near_colors(guides["images"]["flat"]))
    assert set(np.unique(labels).tolist()) - {-1} == {0, 1}, "cube material and floor material"


def test_merge_near_colors_keeps_the_most_frequent(addon) -> None:
    image = np.zeros((1, 6, 4), dtype=np.uint8)
    image[0, :3] = (108, 144, 203, 255)
    image[0, 3] = (108, 145, 203, 255)
    image[0, 4] = (20, 30, 40, 255)
    merged = addon.core.outline.merge_near_colors(image)
    assert merged[0, :4].tolist() == [[108, 144, 203, 255]] * 4
    assert merged[0, 4].tolist() == [20, 30, 40, 255]
    assert merged[0, 5].tolist() == [0, 0, 0, 0]


def test_silhouette_is_black_where_flat_is_opaque(guides) -> None:
    flat, silhouette = guides["images"]["flat"], guides["images"]["silhouette"]
    opaque = flat[..., 3] == 255
    assert (silhouette[opaque] == (0, 0, 0, 255)).all()
    assert (silhouette[~opaque][..., 3] == 0).all()


def test_outline_matches_core(guides, addon) -> None:
    core_outline = addon.core.outline
    flat, ids, drawn = guides["images"]["flat"], guides["images"]["ids"], guides["images"]["outline"]
    labels = core_outline.label_image(addon.core.outline.merge_near_colors(ids))
    expected = core_outline.outer_outline(flat[..., 3], 1) | core_outline.inner_lines(labels, 1)
    mask = drawn[..., 3] > 0
    assert expected.sum() > 0
    assert mask.sum() == expected.sum()
    assert np.array_equal(mask, expected)
    assert (drawn[mask] == (0, 0, 0, 255)).all(), "default outline colour is opaque black"
    assert (mask & (flat[..., 3] == 255)).any(), "inner lines between the objects lie on the shape"


def test_grid_ground_line_is_full_alpha(guides) -> None:
    params = guides["params"]
    grid = guides["images"]["grid"]
    _, _, cam_z = params.camera()
    ground_row = round(48 / 2 - cam_z * params.pixels_per_unit)
    assert 0 <= ground_row < 48
    assert (grid[ground_row, :, 3] == 255).sum() >= 16
    assert ((grid[..., 3] > 0) & (grid[..., 3] < 255)).any(), (
        "the other grid lines use the grid colour's alpha"
    )


def test_composite_is_opaque_wherever_flat_is(guides) -> None:
    flat, composite = guides["images"]["flat"], guides["images"]["composite"]
    opaque = flat[..., 3] == 255
    assert (composite[opaque][..., 3] == 255).all()
    outline_px = guides["images"]["outline"][..., 3] > 0
    assert (composite[outline_px] == (0, 0, 0, 255)).all(), "the outline is the top layer"


def test_settings_guard_restores_render_settings(addon, tmp_path) -> None:
    _setup_scene(str(tmp_path))
    scene = bpy.context.scene
    render = addon.render
    engine_before = scene.render.engine
    scene.render.filepath = "//before_"
    shading = scene.display.shading
    shading.light, shading.color_type = "STUDIO", "OBJECT"
    scene.display.render_aa = "8"
    scene.render.film_transparent = False
    direction_before = render.get_direction()
    assert direction_before is not None, "the rig exposes a Direction input"

    path = str(tmp_path / "guard_flat.png")
    with render.RenderSettingsGuard(scene):
        render.set_direction(direction_before + 1.0)
        render.render_pass(scene, "FLAT", path)
        assert scene.render.engine == "BLENDER_WORKBENCH"
        assert shading.light == "FLAT"

    assert os.path.exists(path)
    assert scene.render.engine == engine_before != "BLENDER_WORKBENCH"
    assert scene.render.filepath == "//before_"
    assert (shading.light, shading.color_type) == ("STUDIO", "OBJECT")
    assert scene.display.render_aa == "8"
    assert scene.render.film_transparent is False
    assert render.get_direction() == pytest.approx(direction_before)


def test_turnaround_writes_frames_and_sheet(addon, tmp_path) -> None:
    settings = _setup_scene(
        str(tmp_path),
        pass_flat=True,
        pass_shaded=False,
        pass_ids=False,
        pass_silhouette=False,
        pass_composite=False,
        outline_enabled=False,
        grid_enabled=False,
        direction_count=2,
        direction=math.radians(30),
        make_sheet=True,
    )
    direction_before = addon.render.get_direction()
    assert bpy.ops.oblique_rig.render_turnaround() == {"FINISHED"}

    assert sorted(os.listdir(tmp_path)) == [
        "guide_d00_flat.png",
        "guide_d01_flat.png",
        "guide_sheet_flat.png",
    ]
    read = addon.render.read_rgba
    frames = [read(str(tmp_path / f"guide_d{i:02d}_flat.png")) for i in range(2)]
    sheet = read(str(tmp_path / "guide_sheet_flat.png"))
    assert sheet.shape == (48, 128, 4)
    assert np.array_equal(sheet[:, :64], frames[0])
    assert np.array_equal(sheet[:, 64:], frames[1])
    assert not np.array_equal(frames[0], frames[1]), "30 and 210 degrees face different ways"
    assert addon.render.get_direction() == pytest.approx(direction_before)
    assert settings.direction == pytest.approx(math.radians(30))


def test_relative_output_dir_cancels_in_an_unsaved_file() -> None:
    settings = _setup_scene("//guides/")
    assert bpy.data.filepath == ""
    assert bpy.ops.oblique_rig.render_guides() == {"CANCELLED"}
    assert bpy.ops.oblique_rig.render_turnaround() == {"CANCELLED"}
    assert settings.output_dir == "//guides/"


def test_poll_needs_rig_and_camera(addon) -> None:
    ops = addon.operators_render
    assert not ops.OBLIQUE_RIG_OT_render_guides.poll(bpy.context)
    assert not ops.OBLIQUE_RIG_OT_render_turnaround.poll(bpy.context)
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert ops.OBLIQUE_RIG_OT_render_guides.poll(bpy.context)
    assert ops.OBLIQUE_RIG_OT_render_turnaround.poll(bpy.context)
    bpy.context.scene.camera = None
    assert not ops.OBLIQUE_RIG_OT_render_guides.poll(bpy.context)


def test_operators_write_files_not_scene_data(addon) -> None:
    ops = addon.operators_render
    for cls in ops.CLASSES:
        assert cls.bl_options == {"REGISTER"}
    assert {cls.bl_idname for cls in ops.CLASSES} == {
        "oblique_rig.render_guides",
        "oblique_rig.render_turnaround",
    }
    assert {cls.bl_label for cls in ops.CLASSES} == {"Render Guides", "Render Turnaround"}
