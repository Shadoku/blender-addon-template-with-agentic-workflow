#!/usr/bin/env python3
"""Turn the template into your add-on: rename the package and fill in the manifest.

    python3 tools/new_addon.py --id cool_tools --name "Cool Tools" \
        --tagline "Short description without trailing period" \
        --maintainer "Jane Doe <jane@example.com>" [--website URL] [--dry-run]

What it does (idempotent; run it once right after cloning):
  * renames src/my_addon -> src/<id>
  * rewrites the manifest fields (id, name, tagline, maintainer, copyright, website)
  * replaces the placeholder identifiers everywhere in src/, tests/, docs and CLAUDE.md:
      my_addon  -> <id>          (module name, bl_idname prefix, Scene attribute)
      MY_ADDON  -> <ID>          (Blender class-name prefix)
      My Addon  -> <Name>        (UI labels)
  * leaves tools/ and .github/ untouched (they discover the add-on from src/*/blender_manifest.toml)

Then run `python3 tools/check.py` and commit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER_ID = "my_addon"
PLACEHOLDER_NAME = "My Addon"
TEXT_SUFFIXES = {".py", ".toml", ".md", ".txt", ".yml", ".yaml", ".json"}
SEARCH_DIRS = ("src", "tests", "docs", ".claude/skills")
SEARCH_FILES = ("CLAUDE.md", "README.md")


def find_addon_dir() -> Path:
    manifests = sorted((ROOT / "src").glob("*/blender_manifest.toml"))
    if len(manifests) != 1:
        sys.exit(f"expected exactly one src/<id>/blender_manifest.toml, found {manifests}")
    return manifests[0].parent


def valid_id(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise argparse.ArgumentTypeError(
            "id must be lowercase letters, digits and underscores, starting with a letter"
        )
    if value in {"bl_ext", "bpy", "core", "tests", "tools"}:
        raise argparse.ArgumentTypeError(f"{value!r} would shadow an existing module")
    return value


def set_toml_field(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{key}\s*=.*$", re.MULTILINE)
    line = f'{key} = "{value}"'
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    # Insert after the type line so the manifest stays readable.
    return re.sub(r"^(type\s*=.*)$", rf"\1\n{line}", text, count=1, flags=re.MULTILINE)


def set_toml_list(text: str, key: str, values: list[str]) -> str:
    rendered = ", ".join(f'"{v}"' for v in values)
    pattern = re.compile(rf"^{key}\s*=.*$", re.MULTILINE)
    line = f"{key} = [{rendered}]"
    return pattern.sub(line, text, count=1) if pattern.search(text) else text + f"\n{line}\n"


def iter_text_files(current_id: str) -> list[Path]:
    files: list[Path] = []
    for d in SEARCH_DIRS:
        base = ROOT / d
        if base.exists():
            files += [p for p in base.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES]
    files += [ROOT / f for f in SEARCH_FILES if (ROOT / f).exists()]
    return [p for p in files if ".blender-deps" not in p.parts and "__pycache__" not in p.parts]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, type=valid_id, help="extension id, e.g. cool_tools")
    ap.add_argument("--name", required=True, help='display name, e.g. "Cool Tools"')
    ap.add_argument("--tagline", required=True, help="one line, max 64 chars, no trailing punctuation")
    ap.add_argument("--maintainer", required=True, help='"Name <email>"')
    ap.add_argument("--website")
    ap.add_argument("--copyright-holder", help="defaults to the maintainer's name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if len(args.tagline) > 64 or args.tagline.rstrip()[-1:] in ".!?":
        sys.exit(
            "tagline must be at most 64 characters and not end with punctuation (extension validate rejects it)"
        )

    addon_dir = find_addon_dir()
    current_id = addon_dir.name
    current_name = PLACEHOLDER_NAME
    manifest = addon_dir / "blender_manifest.toml"
    m = re.search(r'^name\s*=\s*"(.*)"', manifest.read_text(encoding="utf-8"), re.MULTILINE)
    if m:
        current_name = m.group(1)

    replacements = [
        (current_id, args.id),
        (current_id.upper(), args.id.upper()),
        (current_name, args.name),
    ]
    print(f"renaming {current_id!r} -> {args.id!r}, {current_name!r} -> {args.name!r}")

    changed = 0
    for path in iter_text_files(current_id):
        text = path.read_text(encoding="utf-8")
        new = text
        for old, rep in replacements:
            new = new.replace(old, rep)
        if new != text:
            changed += 1
            print(f"  edit  {path.relative_to(ROOT)}")
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")

    text = manifest.read_text(encoding="utf-8")
    holder = args.copyright_holder or args.maintainer.split("<")[0].strip()
    text = set_toml_field(text, "id", args.id)
    text = set_toml_field(text, "name", args.name)
    text = set_toml_field(text, "tagline", args.tagline)
    text = set_toml_field(text, "maintainer", args.maintainer)
    text = set_toml_list(text, "copyright", [f"{dt.date.today().year} {holder}"])
    if args.website:
        text = set_toml_field(text, "website", args.website)
    print(f"  edit  {manifest.relative_to(ROOT)} (manifest fields)")
    if not args.dry_run:
        manifest.write_text(text, encoding="utf-8")

    target = ROOT / "src" / args.id
    if addon_dir != target:
        print(f"  move  src/{current_id} -> src/{args.id}")
        if not args.dry_run:
            shutil.rmtree(addon_dir / "__pycache__", ignore_errors=True)
            shutil.move(str(addon_dir), str(target))

    print(f"{changed} files edited{' (dry run)' if args.dry_run else ''}. Next: python3 tools/check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
