import bpy
import pytest


def test_poll_requires_two_selected_objects(make_object) -> None:
    assert bpy.ops.my_addon.space_evenly.poll() is False
    make_object("A")
    assert bpy.ops.my_addon.space_evenly.poll() is False
    make_object("B", (1, 0, 0))
    assert bpy.ops.my_addon.space_evenly.poll() is True


def test_spaces_selected_objects_along_x(addon, make_object) -> None:
    a = make_object("A", (5.0, 1.0, 0.0))
    b = make_object("B", (0.0, 2.0, 0.0))
    c = make_object("C", (2.0, 3.0, 0.0))
    addon.properties.get_settings(bpy.context).gap = 2.0

    assert bpy.ops.my_addon.space_evenly() == {"FINISHED"}

    assert [a.location.x, b.location.x, c.location.x] == pytest.approx([4.0, 0.0, 2.0])
    assert [a.location.y, b.location.y, c.location.y] == pytest.approx([1.0, 2.0, 3.0]), (
        "other axes untouched"
    )


def test_respects_axis_and_ignores_unselected(addon, make_object) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.axis = "Z"
    settings.gap = 1.5
    a = make_object("A", (0, 0, 10.0))
    b = make_object("B", (0, 0, 4.0))
    bystander = make_object("Bystander", (0, 0, 7.0), select=False)

    bpy.ops.my_addon.space_evenly()

    assert (a.location.z, b.location.z) == pytest.approx((5.5, 4.0))
    assert bystander.location.z == pytest.approx(7.0)


def test_operator_is_undoable(addon) -> None:
    assert "UNDO" in addon.operators.MY_ADDON_OT_space_evenly.bl_options
