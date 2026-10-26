import bpy


def on_load(_path):
    pass


bpy.app.handlers.load_post.append(on_load)
