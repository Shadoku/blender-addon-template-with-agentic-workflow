---
name: blender-addon
description: Create, set up, and develop Blender 4.5+ add-ons (extensions) with a headless test loop so Claude can verify its own changes instead of asking the user to open Blender. Use this whenever the user wants to start a new Blender add-on or extension, add tests/CI/AI tooling to an existing add-on, write or run bpy tests, fix a failing check, convert a legacy bl_info add-on to a blender_manifest.toml extension, or asks how to verify Blender Python code works. Trigger on "blender add-on", "blender addon", "extension", "bpy", "blender_manifest.toml", "check.py", "headless blender", "test my operator", or any Blender scripting task where the outcome should be verified automatically, even if the user never says "test".
---

# Blender add-on kit

This skill gives every Blender add-on the same verifiable loop:
`python3 tools/check.py` lints (ruff + Blender-specific rules + manifest
validation), runs pure-Python unit tests, runs pytest inside headless Blender
with the add-on loaded as a real extension, then builds the zip and installs it
into a throw-away profile. It ends with `CHECK: PASS` or `CHECK: FAIL`. No
Blender UI is needed, so it works in CI and in Claude Code on the web.

The template repository that this skill ships with is the source of truth:
https://github.com/Shadoku/blender-addon-template-with-agentic-workflow

## Decide which mode applies

| Situation | Do |
|---|---|
| No add-on yet, or user asks for a new one | **Scaffold** |
| An add-on exists but no `tools/check.py` | **Adopt** the kit into it |
| `tools/check.py` exists | **Develop** with the loop |

Check with `ls tools/check.py src/*/blender_manifest.toml blender_manifest.toml` first.

## Scaffold a new add-on

1. Settle the inputs, defaulting rather than asking when the user did not say:
   `id` (lowercase, underscores; derived from the name), display name, a tagline
   (max 64 chars, no trailing punctuation), maintainer `"Name <email>"`.
2. Run the scaffolder from this skill's directory:
   ```
   python3 <skill-dir>/scripts/new_project.py <target-dir> --id cool_tools --name "Cool Tools" \
       --tagline "Does cool things to objects" --maintainer "Name <mail>"
   ```
   It copies the template (from the repository this skill lives in, or from
   `--template <path-or-git-url>`), runs `tools/new_addon.py` to rename the
   package, and runs `git init` when the target is not already in a repository.
   Several files are dotfiles (`.github/`, `.claude/`, `.blender-version`): use
   `ls -la` when checking what was written.
3. Make sure Blender is reachable: `check.py` looks at `$BLENDER`, `blender` on
   PATH, then `~/.cache/blender/<version>/blender`. `bash tools/install_blender.sh`
   downloads the pinned release (Linux/macOS, idempotent).
4. Run `python3 tools/check.py` in the new project. It must end with `CHECK: PASS`
   before you report success.
5. Replace the example "Space Evenly" operator and its tests with the user's first
   real feature when they describe one; otherwise leave it as a worked example.

## Adopt the kit into an existing add-on

```
python3 <skill-dir>/scripts/new_project.py <project-dir> --adopt
```
This copies only `tools/`, `tests/blender/conftest.py`, `tests/unit/test_lint_addon.py`,
`tests/lint_fixtures/`, `pyproject.toml`, `.blender-version`, CI, the session hook
and `CLAUDE.md` (as `CLAUDE.blender-addon.md` if one exists) and never touches
the add-on's own code. The add-on must live at `src/<id>/` with a
`blender_manifest.toml`; if it is a legacy root-level `bl_info` add-on, move it
there first, write a manifest (`references/extensions.md`), delete `bl_info`,
and switch absolute imports to relative ones. Expect `lint_addon` to surface
pre-existing problems; report them rather than silently rewriting unrelated code.

## Develop with the loop

The point of the kit is that you verify instead of asking the user to try it.

1. Write or adjust a test first: `tests/unit/` for logic in `core/`,
   `tests/blender/` for operators, properties, registration, UI. Run it and
   watch it fail (`python3 tools/check.py --only blender --filter=<name>`).
2. Implement. Logic in `src/<id>/core/` (no bpy), thin operators, properties
   as annotations in a PropertyGroup, handlers/timers/keymaps through
   `lifecycle.py`, preferences via `__package__`.
3. Run `python3 tools/check.py`. Read failures top-down; the earliest stage
   explains later ones. `--verbose` shows raw output.
4. Repeat until `CHECK: PASS`, then report with the `TESTS:` lines quoted and
   say explicitly that UI drawing is unverified headless.

What the check catches that reasoning alone misses: API removed or renamed
between 2.80 and 5.2 (rule BA007 and runtime `AttributeError`), wrong
`bl_idname` shapes, absolute imports that break under `bl_ext.<repo>.<id>`,
registration order errors, anything left registered after disable, manifest
errors, and tracebacks Blender prints while still exiting 0.

## Reference files

- `references/pitfalls.md`: the mistakes humans and agents make and the
  guardrail for each. Read before writing non-trivial bpy code.
- `references/testing.md`: fixtures, patterns, and what headless Blender cannot test.
- `references/extensions.md`: manifest fields, CLI, module path, wheels, permissions.

## Bundled files

- `scripts/new_project.py`: the scaffolder (new project or `--adopt`).
- The template itself is the repository root this skill lives in
  (`<skill-dir>/../../..`): `tools/check.py`, `tools/blender_bootstrap.py`,
  `tools/lint_addon.py`, `tools/install_blender.sh`, `tools/new_addon.py`,
  `tests/`, `src/my_addon/`.

Keep them in sync: when you improve the tools inside a project, port the change
back to the template repository.
