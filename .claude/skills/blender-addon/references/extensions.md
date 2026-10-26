# Blender extensions (4.2+) in one page

## Manifest (`blender_manifest.toml`, at the package root)

Required: `schema_version = "1.0.0"`, `id` (lowercase identifier, equals the
directory name), `version` (semver), `name`, `tagline` (max 64 chars, no trailing
punctuation), `maintainer` (`"Name <email>"`), `type = "add-on"`,
`blender_version_min` (>= `4.2.0`; this template uses `4.5.0`), `license`
(list of `"SPDX:..."`, e.g. `["SPDX:GPL-3.0-or-later"]`).

Optional: `blender_version_max`, `website`, `copyright = ["2026 Name"]`,
`tags` (fixed list; validate rejects unknown ones), `platforms`
(`windows-x64`, `windows-arm64`, `macos-x64`, `macos-arm64`, `linux-x64`),
`wheels = ["./wheels/x.whl"]`, `[permissions]` with `files`, `network`,
`clipboard`, `camera`, `microphone` (each a short reason), `[build]` with
`paths` or `paths_exclude_pattern`.

Every field that is present must be non-empty. No `bl_info` dict.

## CLI

```
blender --command extension validate src/<id>
blender --command extension build --source-dir src/<id> --output-dir dist   # dist/ must exist
blender --command extension install-file -r user_default --no-prefs [-e] dist/<id>-<ver>.zip
blender --command extension remove <id>
blender --command extension repo-add --directory DIR --source USER NAME
```
`--command` implies background mode.

## Module path

Installed as `bl_ext.<repository_module>.<id>` (`bl_ext.user_default.cool_tools`,
`bl_ext.blender_org.cool_tools`, `bl_ext.dev.cool_tools` in this kit's tests).
Therefore: relative imports only; `AddonPreferences.bl_idname = __package__`;
`context.preferences.addons[__package__]`; never hard-code the repository.

## Loading from a checkout (what tools/blender_bootstrap.py does)

```python
repo = bpy.context.preferences.extensions.repos.new(
    name="dev", module="dev", custom_directory="/abs/path/src"
)
repo.use_custom_directory = True
addon_utils.extensions_refresh(ensure_wheels=True)
mod = addon_utils.enable("bl_ext.dev.<id>", default_set=True)  # None => register() raised
```
Run with `BLENDER_USER_CONFIG`, `BLENDER_USER_SCRIPTS`, `BLENDER_USER_EXTENSIONS`
pointing at a temp dir so nothing touches the real profile.

## Wheels (third-party Python dependencies)

Put unmodified PyPI wheels (including transitive deps) in `./wheels/`, list
them in `wheels`, match the cp tag to Blender's Python (cp311 for 4.5, cp313
for 5.1+), download per platform with
`pip download --only-binary=:all: --python-version 3.13 --platform manylinux_2_28_x86_64 pkg`,
and use `--split-platforms` on build when wheels are platform-specific.

## Files and network

Write user data to `bpy.utils.extension_path_user(__package__, path="", create=True)`
(survives upgrades, removed on uninstall). Check `bpy.app.online_access`
before any network call and declare the `network` permission.

## Supported versions (October 2026)

| Blender | Python | Support |
|---|---|---|
| 4.2 LTS | 3.11 | ended July 2026 |
| 4.5 LTS | 3.11 | to July 2027 |
| 5.0 / 5.1 | 3.11 / 3.13 | not LTS |
| 5.2 LTS | 3.13 | to July 2028 |
