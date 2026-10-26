import bpy


def legacy(obj, scene, mat):
    obj.select = True
    scene.objects.active = obj
    scene.update()
    mat.node_tree.nodes["Principled BSDF"].inputs["Specular"].default_value = 0.5
    bpy.ops.object.delete({"selected_objects": [obj]})
    scene.render.engine = "cycles"
