# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python logic. Nothing in this package may import bpy.

Keep rules, maths and data transformations here so they run under plain
pytest (tests/unit) without launching Blender. Operators call into this
package and only translate between Blender data and plain values.
"""
