import bpy


class THING_OT_do(bpy.types.Operator):
    bl_idname = "Thing.Do.It"
    bl_label = "Do"
    bl_options = {"REGISTER"}
