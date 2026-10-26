import bpy


class MyPanel(bpy.types.Panel):
    bl_idname = "my_panel"
    bl_label = "Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
