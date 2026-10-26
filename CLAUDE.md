# Blender add-on template (Blender 4.5 LTS – 5.2 LTS, extensions system)

Blender extension set up for AI-assisted development: every change is verified
by `python3 tools/check.py`, which runs headless without opening Blender's UI.
Trust its output over your own reasoning about whether code works. Blender's
Python API has changed in every release since 2.80; what you remember may be
outdated, what the check reports is current.

## Commands

| What | Command |
|---|---|
| Everything (lint, unit, blender, package) | `python3 tools/check.py` |
| Only the Blender tests | `python3 tools/check.py --only blender` |
| One test file or method (pytest `-k`) | `python3 tools/check.py --only blender --filter=space_evenly` |
| Fastest loop (pure logic only) | `python3 tools/check.py --only unit` |
| Full tool output | `python3 tools/check.py --verbose` |
| Install Blender + dev deps only | `python3 tools/check.py --setup` |
| Build the installable zip | `python3 tools/check.py --only package --keep-dist` (writes `dist/`) |
| Rename the template into your add-on | `python3 tools/new_addon.py --id cool_tools --name "Cool Tools" --tagline "..." --maintainer "Name <mail>"` |
| Run Blender with the add-on for a manual look (needs a display) | `blender --python-expr "import bpy;bpy.ops.preferences.extension_repo_add(...)` is clumsy; install `dist/*.zip` via Preferences > Get Extensions > Install from Disk instead |

`check.py` finds Blender via `$BLENDER`, then `blender` on PATH, then
`~/.cache/blender/<version>/blender` (installed by `tools/install_blender.sh`,
which the Claude Code session hook and CI both use). The pinned version is in
`.blender-version`; CI also runs the oldest supported LTS (`blender_version_min`
in the manifest). Dev dependencies (pytest, ruff) are installed with Blender's
bundled pip into `.blender-deps/pyX.Y/`; never `pip install` anything else.

## The development loop

1. Before changing behaviour, write or adjust a test that describes the intended
   behaviour: `tests/unit/` for logic in `core/` (no Blender needed),
   `tests/blender/` for operators, properties, registration and UI. Run it and
   watch it fail for the right reason.
2. Implement the change. Logic goes in `src/<id>/core/` (plain Python, no bpy);
   Blender-facing code stays thin.
3. Run `python3 tools/check.py`. Read the output from the top: the first failing
   stage usually explains the rest (a lint finding about a removed API is the
   same bug that makes the Blender tests raise `AttributeError`).
4. Fix and re-run until the last line is `CHECK: PASS`.
5. Only then report done, quoting the `TESTS:` lines.

Never say a change works without a passing check. If you cannot run Blender
(no binary, no network), say so explicitly instead of guessing.

## Reading failures

| Output | Meaning | Fix |
|---|---|---|
| `[FAIL] lint` + `BA007 ... was removed in X` | outdated API that still exists in training data | use the replacement named in the message; `docs/pitfalls.md` has the background |
| `[FAIL] lint` + `BA001`/`BA002` | `bl_idname` or class name breaks Blender's naming rules | operators `category.name` lowercase; UI classes `PREFIX_PT_name` with matching class name |
| `[FAIL] lint` + `BA004` | absolute import inside the package | `from . import x`; the module is `bl_ext.<repo>.<id>`, never `<id>` |
| `[FAIL] lint` + `BA005` | `core/` imports bpy | move the Blender call to an operator; pass plain values into core |
| `[FAIL] lint` + `--- ruff format failed` | formatting | run `.blender-deps/py3.13/bin/ruff format .` or `python3 -m ruff format .` with that dir on `PYTHONPATH` |
| `[FAIL] lint` + `extension validate` output | manifest problem (empty field, tagline punctuation, unknown tag) | fix `blender_manifest.toml`; every present field must be non-empty |
| `Exception in module register()` + `TypeError: PointerProperty(...) expected an RNA type` | PropertyGroup used before it was registered | register the group class before `register_scene_properties()` |
| `ValueError: register_class(...): already registered as a subclass` | class registered twice, or a previous `unregister()` did not remove it | every class exactly once in `CLASSES`; `unregister()` mirrors `register()` |
| `Warning: 'x' does not contain '_PT_'` | Blender rejected a UI `bl_idname` | rename to `PREFIX_PT_name` (same for `_MT_`, `_HT_`, `_UL_`, `_OT_`) |
| `KeyError: 'bpy_prop_collection[key]: key "..." not found'` | preferences looked up by a hard-coded module name | `context.preferences.addons[__package__]` |
| `RuntimeError: ... poll() failed, context is incorrect` | operator needs UI context that background mode lacks | read data from `context.view_layer` / `bpy.data` instead of calling that operator; UI-only operators are untestable headless |
| `AttributeError: 'NoneType' object has no attribute 'select_get'` | iterating `view_layer.objects` after deleting objects | `context.view_layer.update()` after removing data (the fixture does this) |
| `[FAIL] package` + `PACKAGE: FAIL leftover scene_attrs: [...]` | `unregister()` forgot to delete a Scene property / handler / class | delete it in `unregister()`; use `lifecycle.track_*` for handlers, timers, keymaps |
| `[FAIL] package` + `FATAL_ERROR` from `extension build` | manifest or file layout problem | check `[build] paths_exclude_pattern` and that `id` equals the directory name |
| `engine errors were printed (exit code was 0)` | Blender printed a traceback or RNA error during a test that still passed | the block names the test (`[during ...]`); fix the cause, do not silence it |
| `TIMEOUT after Ns` | a test or Blender hung | look for modal operators, timers that never return `None`, or a blocking network call |

## Writing tests

- `tests/unit/test_*.py`: plain pytest. Import `core/` modules by file path with
  `load_core_module("name")` (see `test_spacing.py`), never through `bpy`.
- `tests/blender/test_*.py`: pytest running inside Blender with the add-on
  already enabled. Fixtures from `conftest.py`:
  - `addon`: the live package (`addon.operators.MY_ADDON_OT_space_evenly`).
    Never hard-code `bl_ext.dev.my_addon`; read `ADDON_MODULE` from the environment.
  - `clean_scene` (autouse): wipes datablocks and resets the add-on's settings
    between tests without reloading a file.
  - `make_object(name, location, select)`: an empty linked to the scene collection.
  - `recording_layout`: a fake `UILayout` so `Panel.draw()` can be executed.
- Call operators as `bpy.ops.my_addon.space_evenly()` and assert on
  `{"FINISHED"}` plus the resulting data. Check `poll()` separately.
- Any `Traceback`, RNA `Error:` or `register_class` warning printed during a test
  fails that test even when its assertions pass.
- Headless mode has no window: `draw()` is never invoked by Blender, `bpy.ops.view3d.*`
  and modal operators cannot run, nothing renders. Test the data the UI reads and
  the functions it calls instead.
- Run tests without `check.py` only through the bootstrap:
  `blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- --mode dev --filter name`.

## Design for testability

- Put rules and maths in `src/<id>/core/` as plain functions and classes. They
  need no Blender and test in milliseconds. `tools/lint_addon.py` fails the
  check if anything there imports bpy.
- Keep operators thin: read context, call core, write results, `self.report`.
  Store names rather than object references between calls.
- `bl_options = {"REGISTER", "UNDO"}` on every operator that writes to `bpy.data`.
- Properties live in a `PropertyGroup` attached once to `bpy.types.Scene`
  (`properties.py`); declare them as annotations, read them as attributes.
- Register handlers, timers and keymaps through `lifecycle.py` so a disable
  removes them. Handlers must be `@persistent`.
- Never touch bpy from another thread; hand work back with `bpy.app.timers`.
- Need network or file access? Declare it in the manifest `[permissions]`
  table and check `bpy.app.online_access` before connecting.

## Layout

```
.blender-version            pinned Blender used by check.py, CI and the session hook
src/<id>/                   the extension package (this is what gets zipped)
  blender_manifest.toml     id, version, blender_version_min, license, permissions
  __init__.py               register()/unregister(): ordered CLASSES tuple only
  core/                     pure Python logic; no bpy allowed
  operators.py              thin operators + keymaps
  properties.py             PropertyGroup + the one PointerProperty on Scene
  ui.py                     panels/menus, draw() only
  preferences.py            AddonPreferences keyed by __package__
  handlers.py / lifecycle.py   persistent handlers and the cleanup registry
tests/unit/                 pytest, plain Python
tests/blender/              pytest inside headless Blender
tests/lint_fixtures/        one file per lint rule; each must fail that rule
tools/check.py              the one command to verify the project
tools/blender_bootstrap.py  runs inside Blender: isolate prefs, mount src/ as a repo, run pytest
tools/lint_addon.py         Blender-specific static rules (BA001-BA013)
tools/install_blender.sh    downloads the pinned Blender into ~/.cache/blender
tools/new_addon.py          renames the template into your add-on
docs/pitfalls.md            why each rule and convention exists, with sources
docs/testing.md             what headless Blender can and cannot verify
.github/workflows/          ci.yml (4.5 LTS + 5.2 LTS matrix), release.yml (zip on tag)
```

## Conventions

- Python 3.11 compatible (Blender 4.5 LTS); ruff enforces style with
  `target-version = "py311"`. Type hints on public functions.
- Blender class names: `<ID>_OT_name`, `<ID>_PT_name`, `<ID>_MT_name`, where
  `<ID>` is the add-on id upper-cased. Operator `bl_idname`: `<id>.name`.
- Relative imports only inside the package. `__package__` for preferences.
- Version lives in the manifest only; tag releases `v<version>`.
- Commit `dist/` never; `.blender-deps/` never.
- When you improve `check.py`, the bootstrap, the linter or these docs, also
  update `.claude/skills/blender-addon/` so other projects get the fix.

## This repository also hosts the skill

`.claude/skills/blender-addon/` is a reusable Claude Code skill that scaffolds
new add-ons from this repository and documents the loop. Install it for all
projects with `cp -r .claude/skills/blender-addon ~/.claude/skills/`.
