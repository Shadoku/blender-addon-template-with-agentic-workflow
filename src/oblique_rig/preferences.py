# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences.

``bl_idname`` must be ``__package__``: the module name is ``bl_ext.<repo>.<id>``
and the repository part differs per installation, so a hard-coded string
raises ``KeyError`` for users.
"""

import bpy
from bpy.props import BoolProperty
from bpy.types import AddonPreferences


class OBLIQUE_RIG_Preferences(AddonPreferences):
    bl_idname = __package__

    report_results: BoolProperty(
        name="Report results",
        description="Show an info message in the status bar after building, calibrating or removing the rig",
        default=True,
    )

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.prop(self, "report_results")


CLASSES: tuple[type, ...] = (OBLIQUE_RIG_Preferences,)


def get_prefs(context: bpy.types.Context) -> OBLIQUE_RIG_Preferences:
    return context.preferences.addons[__package__].preferences
