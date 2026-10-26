import bpy


class Settings(bpy.types.PropertyGroup):
    gap = bpy.props.FloatProperty(default=1.0)
