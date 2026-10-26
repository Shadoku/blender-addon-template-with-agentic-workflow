# SPDX-License-Identifier: GPL-3.0-or-later
"""Application handlers.

Every handler must be decorated with ``@persistent`` (otherwise Blender drops
it when a file is loaded) and must be removed in ``unregister`` (otherwise it
keeps firing after the add-on is disabled and raises on freed data).
``lifecycle.track_handler`` does the bookkeeping.
"""

import bpy
from bpy.app.handlers import persistent

from . import lifecycle


@persistent
def on_load_post(_filepath: str) -> None:
    """Runs after a .blend file is loaded. Replace the body with your own reset logic."""
    # Example: nothing to reset yet. Keep handlers short; never touch the UI here.
    return None


def register() -> None:
    lifecycle.track_handler(bpy.app.handlers.load_post, on_load_post)


def unregister() -> None:
    # lifecycle.cleanup() (called from __init__.unregister) removes tracked handlers.
    return None
