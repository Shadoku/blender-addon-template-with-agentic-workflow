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

Versions available now: 5.2.3 (current, labelled LTS), 4.5.15 LTS, 4.2.x LTS
(oldest extension-capable line). Blender 5.2 bundles Python 3.13.13; 4.5 bundles
3.11. The `bpy` PyPI wheel (5.2.3, Python 3.13 only) is an alternative for pure
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
- Banned-API token list (the 2.7x/3.x survivors agents keep producing; final
  list from section 6): `scene.objects.active`, `.select = `, `scene.update()`,
  `use_auto_smooth`, `import bgl`, `context_override` dicts, `wiki_url`, and
  Principled BSDF socket names renamed in 4.0.
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

PITFALLS_PLACEHOLDER

## 7. Decisions needed before phase 1

1. **Blender floor and pin**: `blender_version_min = "4.2.0"` with CI on 4.5 LTS
   and 5.2 LTS, pinned 5.2.3 for local checks. Alternative: floor 4.5 (drops
   the 4.2 line, which just left LTS support) and simplify.
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
