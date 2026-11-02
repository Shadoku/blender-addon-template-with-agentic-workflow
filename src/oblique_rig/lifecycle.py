# SPDX-License-Identifier: GPL-3.0-or-later
"""Bookkeeping for things that must be undone in ``unregister``.

Handlers, timers and keymap items that outlive the add-on are the classic
source of "already registered", "unknown operator" and ReferenceError bugs.
Register them through these helpers and ``cleanup()`` removes them all.
"""

from collections.abc import Callable

import bpy

_handlers: list[tuple[list, Callable]] = []
_timers: list[Callable] = []
_keymaps: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []


def track_handler(handler_list: list, func: Callable) -> None:
    if func not in handler_list:
        handler_list.append(func)
    _handlers.append((handler_list, func))


def track_timer(func: Callable, first_interval: float = 0.0) -> None:
    """Register a bpy.app.timers callback that is removed on cleanup.

    Timers are the only safe way to get work back onto Blender's main thread;
    bpy must never be touched from another thread.
    """
    bpy.app.timers.register(func, first_interval=first_interval, persistent=True)
    _timers.append(func)


def track_keymap(km: bpy.types.KeyMap, kmi: bpy.types.KeyMapItem) -> None:
    _keymaps.append((km, kmi))


def remove_keymaps() -> None:
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except ReferenceError:
            pass
    _keymaps.clear()


def cleanup() -> None:
    for handler_list, func in _handlers:
        if func in handler_list:
            handler_list.remove(func)
    _handlers.clear()
    for func in _timers:
        if bpy.app.timers.is_registered(func):
            bpy.app.timers.unregister(func)
    _timers.clear()
    remove_keymaps()
