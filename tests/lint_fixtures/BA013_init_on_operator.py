import bpy


class THING_OT_do(bpy.types.Operator):
    bl_idname = "thing.do"
    bl_label = "Do"
    bl_options = {"REGISTER"}

    def __init__(self):
        self.x = 1
