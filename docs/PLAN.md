# Plan: Blender add-on template with an agentic workflow

Status: **draft for review**, 2026-10-26. Nothing below is implemented yet.
Once agreed, each phase runs as its own plan -> tests -> implement -> check cycle
and this file is trimmed into `CLAUDE.md` + `docs/` reference pages.

## 1. Goal

Turn this repository into the Blender equivalent of the `godot_project` repo:
clone it, give the add-on a name, and from then on every change (by a human or
by Claude) is verified by one command that runs headless and ends in
`CHECK: PASS` or `CHECK: FAIL`. The workflow is always:

    plan -> write/adjust tests first (watch them fail) -> implement -> check -> report

The template must be honest about what headless Blender can and cannot verify,
and must steer an agent away from the well-known ways Blender add-on code goes
wrong (section 6).

## 2. What exists today

Three files from a 2019-era (Blender 2.80) boilerplate: `__init__.py` with a
legacy `bl_info`, `properties.py` that assigns `Scene.my_property` directly,
and `ui.py` with one Panel. No tests, no tooling, no CI, no manifest. It cannot
be installed as an extension in Blender 4.2+ (no `blender_manifest.toml`) and
still works only through the legacy add-on path.

## 3. Feasibility, verified in this session

Everything below was actually run in this cloud container, so the design is not
speculative.

| Check | Result |
|---|---|
| Download `blender-5.2.3-linux-x64.tar.xz` from download.blender.org | 14 s download, 23 s extract, 1.2 GB on disk |
| `blender -b --factory-startup --python probe.py` | 3.4 s wall clock per headless session |
| `--python-exit-code N` | exit code honoured when the script raises |
| Load the add-on **from the repo checkout** as a real extension | works: add a local repo (`preferences.extensions.repos.new(custom_directory=...)`) pointing at a dir that symlinks `src/my_addon`, then `addon_utils.enable("bl_ext.dev.my_addon")`. `__package__` is `bl_ext.dev.my_addon`, so relative imports behave exactly as for end users |
| `blender --command extension validate / build / install-file --enable / remove` | all work from the CLI |
| pytest inside Blender | Blender's bundled `python3.13 -m pip install --target .blender-deps pytest` takes 3 s; a pytest session inside Blender runs in 0.08 s |
| Bad `bl_idname` (`"my_bad_panel"` on a Panel) | Blender prints `Warning: 'my_bad_panel' does not contain '_PT_'`; catchable by the runner |
| `register()` that raises (PointerProperty to an unregistered PropertyGroup) | traceback printed, `addon_utils.enable()` returns `None`, **Blender still exits 0** -> the runner must check the return value and scan output, not trust the exit code |
| `Panel.draw()` in background mode | never called (no window). UI drawing is not testable headless |
| Reloading a file inside a test (`read_factory_settings` / `read_homefile`) | drops an add-on enabled only for the session unless enabled with `default_set=True`; prefer data-level cleanup between tests |
| Preferences leakage | `extension install-file --enable` wrote a real `~/.config/blender/5.2/config/userpref.blend`; tests must run with `BLENDER_USER_CONFIG`/`BLENDER_USER_SCRIPTS`/`BLENDER_USER_EXTENSIONS` pointed at a temp dir |

Versions available now: 5.2.3 (current stable and LTS, supported to July 2028),
4.5.15 LTS (to July 2027), 4.2.x LTS (oldest extension-capable line, end-of-life
July 2026). Blender 5.2 bundles Python 3.13.13; 4.5 and 5.0 bundle 3.11. The `bpy` PyPI wheel (5.2.3, Python 3.13 only) is an alternative for pure
data-API tests but lacks `addon_utils`-level realism and is not proposed here.

## 4. Target design

### 4.1 Repository layout (proposal B: package under `src/`)

```
blender_manifest.toml      <- NO. The manifest lives inside the package (below).
.blender-version           pinned Blender for the check (5.2.3)
src/my_addon/              the extension package; renamed by tools/new_addon.py
  blender_manifest.toml    id, version, blender_version_min = "4.2.0", SPDX license
  __init__.py              register()/unregister() only: ordered class list + props
  core/                    pure Python, MUST NOT import bpy; unit-tested on system Python
  operators.py             thin: read context, call core, write results
  properties.py            PropertyGroup(s) + the one PointerProperty on Scene
  ui.py                    Panels / menus; draw() only
  preferences.py           AddonPreferences keyed by __package__
tests/
  conftest.py              shared fixtures (clean_scene, make_cube, ...)
  unit/                    pytest on system Python, no Blender (milliseconds)
  blender/                 pytest inside headless Blender: operators, props, register round-trip
tools/
  check.py                 the one command (stages below), last line CHECK: PASS/FAIL
  install_blender.sh       pinned download into ~/.cache/blender/<version>, idempotent
  blender_bootstrap.py     runs inside Blender: isolate prefs, mount checkout as extension repo, run pytest
  lint_addon.py            Blender-specific static rules (section 4.3)
  new_addon.py             rename my_addon -> <id>, fill manifest fields
.claude/settings.json + hooks/session-start.sh   download Blender + pytest at session start (remote only)
.github/workflows/ci.yml   matrix: 4.5 LTS and 5.2 LTS, uploads the built zip
CLAUDE.md, README.md, docs/pitfalls.md, docs/testing.md
```

Why not the add-on at repo root (proposal A): tests and tools would ship inside
the zip unless excluded, and `--source-dir src/my_addon` keeps the package
boundary obvious to an agent (anything outside `src/` is never imported by Blender).

### 4.2 `tools/check.py` stages

| Stage | What runs | Catches |
|---|---|---|
| `lint` | `ruff check` + `ruff format --check`; `tools/lint_addon.py`; `blender --command extension validate src/my_addon` | syntax, unused imports, manifest errors, Blender-specific rules |
| `unit` | `pytest tests/unit` on system Python | logic bugs in `core/` in milliseconds |
| `blender` | `blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- pytest args` | registration errors, operator behaviour, property defaults, context misuse, outdated API (AttributeError at runtime) |
| `package` | `extension build` into `dist/`, `install-file` into a temp user config, enable -> disable -> enable again, assert every class and `Scene` property is gone after disable | unregister leaks, double-registration, files missing from the zip, install as a real user would |

Flags mirror the Godot script: `--only <stage>`, `--filter=<expr>` (passed to
pytest `-k`), `--verbose`, `--junit`, `--blender-version` override. The runner
fails a Blender stage on any of: non-zero exit, `addon_utils.enable()` returning
`None`, a `Traceback`, `Error:` / `Warning:` lines from `register_class`, or
pytest reporting failures. Known-benign headless noise is filtered by a small
ignore list, as in the Godot script.

### 4.3 Blender-specific static rules (`tools/lint_addon.py`)

Cheap AST/regex checks that encode the pitfalls list so an agent is stopped
before Blender is even launched:

- `bl_idname` shape: operators `lower.lower` with exactly one dot; Panel/Menu/
  Header/UIList classes contain `_PT_`/`_MT_`/`_HT_`/`_UL_` and the class name
  matches; Operator class names contain `_OT_`.
- No `bl_info` dict when `blender_manifest.toml` exists.
- No absolute `import my_addon` / `from my_addon import` inside the package;
  relative imports only.
- No `import bpy` under `src/my_addon/core/`.
- Preferences accessed via `__package__`, never a hard-coded string.
- Banned-API token list drawn from the table in section 6.1 (2.7x survivors,
  4.0/4.1 renames, 5.0 removals), each with the replacement in the message.
- `bl_options` must include `UNDO` on operators that write to `bpy.data`;
  no `threading`/`asyncio` imports inside the package; network modules only
  when the manifest declares the `network` permission.
- Every `bpy.app.handlers` callback is decorated `@persistent`; every
  `register()` has a matching `unregister()` that reverses the list.

### 4.4 Test helpers (`tests/conftest.py`)

- `clean_scene`: autouse fixture that removes all datablocks via the data API
  (not a file reload), so tests are independent without unregistering the add-on.
- `addon` fixture exposing the live module (`bl_ext.dev.<id>`) so tests never
  hard-code the `bl_ext` path.
- `active(obj)` helper that sets `view_layer.objects.active` and selection the
  4.x way; `run_op(op, **kw)` that asserts `{'FINISHED'}` and surfaces
  `self.report` messages.
- A `register_roundtrip` test shipped with the template (enable, disable, enable)
  because it catches the single most common add-on bug class.

### 4.5 Documentation for the agent (`CLAUDE.md`)

Same shape as the Godot `CLAUDE.md`, which has already proven to work for this
loop: Commands table, the development loop, a "Reading failures" table with
Blender-specific signatures, Writing tests, Design for testability (bpy-free
`core/`, thin operators, never call `bpy.ops` from `core/`), Layout,
Conventions, and a short **API rules** section pointing at `docs/pitfalls.md`.

### 4.6 CI and session hook

GitHub Actions on push/PR: cache `~/.cache/blender`, `install_blender.sh`,
`check.py --junit`, upload junit + the built zip. Matrix over `.blender-version`
and the oldest supported LTS so `blender_version_min` is a tested claim, not a
hope. The `SessionStart` hook mirrors the Godot one (remote only): download the
pinned Blender, install pytest with its bundled pip, export `BLENDER=...`.

## 5. Phases

Each phase ends with `python3 tools/check.py` -> `CHECK: PASS` and a commit.

| # | Phase | Deliverables | Verify |
|---|---|---|---|
| 1 | Toolchain skeleton | `.blender-version`, `tools/install_blender.sh`, `tools/check.py` (lint + unit stages), session hook, CI, `.gitignore`, ruff config | check passes on an empty `tests/unit` placeholder; CI green |
| 2 | Convert the add-on to an extension | `src/my_addon/` with manifest, `core/`, thin operator + PropertyGroup + panel + preferences; delete root `__init__.py`/`properties.py`/`ui.py` | `extension validate`; `blender` stage loads it from the checkout |
| 3 | In-Blender test loop | `tools/blender_bootstrap.py`, `tests/blender/` examples (operator, property default, poll, register round-trip), `package` stage | deliberately broken `register()` turns the check red; fixing it turns it green |
| 4 | Guardrails | `tools/lint_addon.py` with the rules in 4.3, `docs/pitfalls.md` (section 6 expanded with sources), "Reading failures" table | each rule has a fixture file under `tests/lint_fixtures/` that must fail |
| 5 | Template ergonomics | `tools/new_addon.py` rename/scaffold, README rewrite, release workflow that attaches the zip on tag | scaffold into a temp dir, run its check, PASS |
| 6 | Optional: hosted skill | `.claude/skills/blender-addon/` mirroring `godot-project` (SKILL.md, references, scaffolder) so other repos can adopt the kit | skill eval prompts like the Godot ones |

Estimated size: phases 1-4 are the core and are each a single PR-sized change.

## 6. Pitfalls to design against

(Filled from this session's research; see `docs/pitfalls.md` once phase 4 lands.)

Research (official release notes, the Python API "gotchas" pages, devtalk,
the extensions review queue, and add-on authors' post-mortems) plus this
session's own experiments. Ranked by how often they bite; each row names the
guardrail the template will carry. Full write-up with sources goes into
`docs/pitfalls.md` in phase 4.

### 6.1 Mistakes agents make (version drift)

Public bpy code mostly targets 2.8-4.x, so a model recalls *real but outdated*
API unless the exact Blender version is in front of it. The check loop is the
arbiter, but a static banned-token list stops the obvious ones before Blender
starts:

| Era | Still-generated code | Current form |
|---|---|---|
| 2.7x | `obj.select = True`, `scene.objects.active`, `scene.update()`, `scene.objects.link()`, `mat * vec`, `bpy.utils.register_module`, `INFO_HT_header`, `bl_info["wiki_url"]`, `prop = IntProperty()` | `select_set()`, `view_layer.objects.active`, `view_layer.update()`, `collection.objects.link()`, `@`, class tuple + `register_classes_factory`, `TOPBAR_*`, manifest, `prop: IntProperty()` |
| 4.0 | Principled BSDF `Subsurface`/`Specular`/`Transmission`/`Coat`/`Sheen`/`Emission` sockets, `NodeTree.inputs/outputs`, `Mesh.calc_normals`, `MeshEdge.crease`, dict context overrides `bpy.ops.x(override)` | `* Weight` / `Specular IOR Level` / `Emission Color`, `tree.interface.new_socket()`, attributes, `context.temp_override(...)` |
| 4.1 | `mesh.use_auto_smooth`, `calc_normals_split`, `node.outputs[i]` by index | `sharp_edge` attribute / Smooth by Angle, `Mesh.corner_normals`, socket identifiers |
| 5.0 | `import bgl`, `scene.node_tree` + `scene.use_nodes`, `BLENDER_EEVEE_NEXT`, `action.fcurves`, `scene["my_bpy_prop"]` dict access to `bpy.props` values, `GPencil*` types | `gpu`, `scene.compositing_node_group`, `BLENDER_EEVEE`, slotted actions, attribute access, `Annotation*` / `GreasePencil` |
| 5.1 | Python 3.11 wheels (cp311) | Python 3.13 (cp313); pure Python is unaffected |

Also: lower-case enum values (`"cycles"` vs `'CYCLES'`), `bpy.ops.view3d.*` /
`object.mode_set` in background mode (no window, so `poll()` fails with
"context is incorrect"), and `pip install` into the host Python instead of
Blender's bundled interpreter.

### 6.2 Top pitfalls and the guardrail for each

| # | Pitfall | Guardrail in the template |
|---|---|---|
| 1 | Outdated or mixed-era API (table above) | exact Blender + Python version stated in `CLAUDE.md`; banned-token lint; the `blender` stage is the arbiter |
| 2 | `bpy.ops` that need a UI context, called from logic or from tests in `-b` mode | logic lives in bpy-free `core/`; operators are thin; docs list what is untestable headless |
| 3 | Absolute imports or hard-coded module name under `bl_ext.<repo>.<id>` (`import my_addon`, `preferences.addons["my_addon"]` -> KeyError) | relative-import lint; `AddonPreferences.bl_idname = __package__`; `package` stage installs the real zip |
| 4 | Registration order and leaks: PointerProperty before its class, missing `del bpy.types.Scene.x`, "already registered as a subclass" on reload | ordered `classes` tuple, mirrored `unregister()`, shipped enable -> disable -> enable round-trip test asserting no leftover `bpy.types` attrs, handlers, timers, keymaps |
| 5 | Blender exits 0 on Python exceptions; `addon_utils.enable()` returns `None` and only prints | `--python-exit-code 1` always; runner checks the `enable()` result and scans output for `Traceback` / `Exception in module register()` / `register_class` warnings (verified in section 3) |
| 6 | Dependencies installed into the wrong interpreter; cp311 wheels on 5.1+ | tests never `pip install`; runtime deps ship as manifest `wheels` built with `--python-version 3.13`; bootstrap prints `sys.version` from inside Blender |
| 7 | Handlers and timers without `@persistent`, or not removed in `unregister()` | small registry helper that tracks and removes them; lint that every `bpy.app.handlers` callback is `@persistent`; round-trip test covers removal |
| 8 | Dangling `StructRNA` references across undo, `mode_set`, or data removal (`ReferenceError`, or a crash) | convention: store names, not objects, across operator calls; `bl_options = {'REGISTER', 'UNDO'}` on data-modifying operators; lint for the missing option |
| 9 | Threads touching bpy | lint for `threading`/`asyncio` inside the package; documented `bpy.app.timers` queue pattern |
| 10 | `bl_idname` and class-name convention violations (`OBJECT_PT_x`, `category.name`) | regex lint plus Blender's own `register_class` warnings treated as failures |
| 11 | Manifest and zip layout errors (empty strings, tagline punctuation, unknown tags, `bl_info` alongside a manifest) | `extension validate` in `lint`, `extension build` + `install-file --no-prefs` in `package` |
| 12 | `bpy.props` assigned with `=` instead of an annotation; dict access to prop values (broke in 5.0) | lint; template code reads props as attributes only |
| 13 | UI `draw()` code never runs headless, so UI bugs hide until a human opens Blender | tests call `Panel.draw()` directly with a recording fake layout; draw methods stay thin; the check report says "UI unverified" |
| 14 | Enum casing and renamed enum values | tests set enums through the API; optional `fake-bpy-module-5.2` stubs + pyright for literal checking |
| 15 | Writing into the extension's own directory (wiped on upgrade, read-only in system repos) or assuming network access | `bpy.utils.extension_path_user(__package__, create=True)`; `[permissions]` declared in the manifest; lint for `urllib`/`requests`/`socket` without the `network` permission |

### 6.3 Test-infrastructure pitfalls found in this session

- A file reload inside a test (`read_factory_settings`, `read_homefile`) drops
  an add-on that was enabled for the session only. Use data-level cleanup
  between tests, or enable with `default_set=True`.
- Headless `extension install-file --enable` writes a real `userpref.blend`.
  Always isolate with `BLENDER_USER_CONFIG` / `BLENDER_USER_SCRIPTS` /
  `BLENDER_USER_EXTENSIONS` pointed at a temp dir, and pass `--no-prefs`.
- `hasattr(bpy.ops.my.op, ...)` is always true (lazy lookup); check
  registration state through `bpy.types` / `addon_utils.check()`.
- `sys.exit()` inside Blender looks like a crash; raise instead and let
  `--python-exit-code` set the status.
- `--factory-startup` ignores `PYTHONPATH`; the bootstrap inserts the
  repo-local pytest target dir onto `sys.path` itself.

### 6.4 Ecosystem notes that shaped the design

- Legacy `bl_info` add-ons still load in 5.2 but are deprecated since 4.2 with
  no removal date; the template goes extension-only.
- 4.2 LTS reached end-of-life in July 2026. 4.5 LTS (Python 3.11) is supported
  to July 2027, 5.2 LTS (Python 3.13) to July 2028. Hence the CI matrix.
- `pytest-blender` and `blender-addon-tester` exist but document only 2.8x-3.x
  and no `bl_ext` support, so the template uses plain pytest launched by its own
  bootstrap (verified above) rather than depending on them.
- `fake-bpy-module-<version>` (nutti) is the practical stub source; there is no
  official stubs package. Optional in this template, not required by the check.
- `bpy.utils.register_cli_command` (4.2+) could later expose
  `blender -c <id>-test` as a nicer entry point; not needed for phase 3.
- The `blender-mcp` project's lesson applies here too: give the model structured
  feedback (which stage, which line, which class) rather than a raw dump.

## 7. Decisions needed before phase 1

1. **Blender floor and pin**: `blender_version_min = "4.2.0"` (the manifest
   minimum) with CI on 4.5 LTS and 5.2 LTS, pinned 5.2.3 for local checks.
   Alternative: floor 4.5, since 4.2 is end-of-life and untested either way.
   Both lines must stay pure Python (3.11 vs 3.13).
2. **Layout**: package under `src/<id>/` (recommended, above) vs add-on at repo root.
3. **Test runner**: pytest inside Blender via bundled pip (recommended; agents
   know it and `-k` filtering/fixtures come free) vs stdlib `unittest` (zero
   downloads, clunkier).
4. **Legacy `bl_info`**: drop it (extension-only). Keeping both is possible but
   doubles the test surface for a line of Blender that is end-of-life.
5. **Scaffolder and skill** (phases 5-6): wanted now, later, or not at all?
6. **License and attribution**: keep GPL-3.0-or-later (required for anything
   that imports bpy and is distributed) and credit the original lunadigital
   boilerplate in the README.
