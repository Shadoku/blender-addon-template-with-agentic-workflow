# Blender Add-on Template with an Agentic Workflow

A starting point for Blender extensions (Blender 4.5 LTS through 5.2 LTS) built
for development with an AI coding assistant such as Claude Code. One command,
`python3 tools/check.py`, lints the code, runs unit tests, runs tests inside a
headless Blender with the add-on loaded as a real extension, then builds the
zip and installs it into a throw-away profile. It ends with `CHECK: PASS` or
`CHECK: FAIL`, so the assistant (or you) can verify every change without
opening Blender.

```
$ python3 tools/check.py
blender: /home/me/.cache/blender/5.2.3/blender
[PASS] lint (0.9s)
    LINT: ruff, lint_addon, extension validate all passed
[PASS] unit (0.3s)
    TESTS: 23 passed in 0.03s
[PASS] blender (0.9s)
    BOOTSTRAP: Blender 5.2.3 LTS Python 3.13.13 background=True
    TESTS: 15 passed, 0 failed, 0 skipped
[PASS] package (2.4s)
    PACKAGE: my_addon installs, enables, disables cleanly and re-enables
    PACKAGE: built dist/my_addon-0.1.0.zip (7005 bytes)

CHECK: PASS
```

## Quick start

```bash
git clone https://github.com/Shadoku/blender-addon-template-with-agentic-workflow my_cool_addon
cd my_cool_addon
python3 tools/new_addon.py --id cool_tools --name "Cool Tools" \
    --tagline "Does cool things to objects" --maintainer "Your Name <you@example.com>"
bash tools/install_blender.sh      # downloads the pinned Blender into ~/.cache/blender (Linux/macOS)
python3 tools/check.py             # must end with CHECK: PASS
```

Then describe the first feature to your assistant. `CLAUDE.md` tells it to
write a test first, implement, and run the check until it passes.

Requirements: Python 3.9+ on the host to run `check.py`; `curl`, `tar` (Linux)
or `hdiutil` (macOS) for the installer. On Windows install Blender yourself and
set `BLENDER=C:\...\blender.exe`. Everything else (pytest, ruff) is installed
by `check.py` with Blender's bundled Python into `.blender-deps/`.

## What is in the box

- `src/my_addon/`: a small but complete extension (manifest, PropertyGroup,
  operator with undo, sidebar panel, preferences, a persistent handler, a keymap)
  that demonstrates the conventions. The maths lives in `core/`, which never
  imports `bpy` and is unit-tested in milliseconds.
- `tests/`: unit tests, Blender tests (operator behaviour, property defaults,
  enable/disable round trip, panel `draw()` with a recording layout), and one
  fixture per lint rule.
- `tools/check.py`, `tools/blender_bootstrap.py`, `tools/lint_addon.py`: the
  verification loop. The linter encodes 13 Blender-specific rules, including a
  list of API that was removed between 2.80 and 5.2 and that language models
  keep producing.
- `.github/workflows/`: CI on 4.5 LTS and 5.2 LTS; a release workflow that
  attaches the zip when you push a `vX.Y.Z` tag.
- `.claude/`: a session hook that installs Blender in Claude Code on the web,
  and the `blender-addon` skill that scaffolds new projects from this template.
- `docs/pitfalls.md`: the common ways add-on code goes wrong (for humans and
  for agents) and how this template guards against each. `docs/testing.md`:
  what headless Blender can and cannot verify.

## Credits and license

Started from Aaron Powell's (lunadigital) Blender add-on boilerplate. Licensed
under GPL-3.0-or-later, as required for add-ons that import `bpy` and are
distributed; see `LICENSE`.
