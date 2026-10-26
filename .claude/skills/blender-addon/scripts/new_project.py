#!/usr/bin/env python3
"""Scaffold a new Blender add-on project from the template, or adopt the kit into an existing one.

    python3 new_project.py <target> --id cool_tools --name "Cool Tools" --tagline "..." --maintainer "Name <mail>"
    python3 new_project.py <existing-project> --adopt

The template is the repository this skill lives in (<skill-dir>/../../..). Pass
--template <path-or-git-url> to use another checkout or to clone it fresh.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = SKILL_DIR.parent.parent.parent  # repo root hosting .claude/skills/blender-addon
TEMPLATE_URL = "https://github.com/Shadoku/blender-addon-template-with-agentic-workflow"

# Paths copied by --adopt (never the add-on's own code).
ADOPT_PATHS = [
    "tools",
    "tests/blender/conftest.py",
    "tests/unit/test_lint_addon.py",
    "tests/lint_fixtures",
    "pyproject.toml",
    ".blender-version",
    ".editorconfig",
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".claude/settings.json",
    ".claude/hooks/session-start.sh",
    ".claude/skills/blender-addon",
    "docs/pitfalls.md",
    "docs/testing.md",
]
SKIP_ON_COPY = {
    ".git",
    ".blender-deps",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "docs/PLAN.md",
}


def resolve_template(spec: str | None) -> Path:
    if spec is None:
        if (DEFAULT_TEMPLATE / "tools" / "check.py").exists():
            return DEFAULT_TEMPLATE
        spec = TEMPLATE_URL
    path = Path(spec)
    if path.exists():
        return path.resolve()
    tmp = Path(tempfile.mkdtemp(prefix="blender-addon-template-"))
    print(f"cloning {spec} ...")
    subprocess.run(["git", "clone", "--depth", "1", "--quiet", spec, str(tmp)], check=True)
    return tmp


def copy_tree(src: Path, dst: Path, overwrite: bool) -> int:
    count = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in SKIP_ON_COPY for part in rel.parts) or str(rel) in SKIP_ON_COPY:
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        count += 1
    return count


def in_git_repo(path: Path) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"], capture_output=True
        ).returncode
        == 0
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument(
        "--template", help="path or git URL of the template (default: the repo this skill lives in)"
    )
    ap.add_argument("--adopt", action="store_true", help="add only the tooling to an existing add-on project")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--id")
    ap.add_argument("--name")
    ap.add_argument("--tagline")
    ap.add_argument("--maintainer")
    ap.add_argument("--website")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    template = resolve_template(args.template)
    print(f"template: {template}")

    if args.adopt:
        if not target.exists():
            sys.exit(f"{target} does not exist; drop --adopt to scaffold a new project")
        copied = 0
        for rel in ADOPT_PATHS:
            src = template / rel
            if not src.exists():
                continue
            if src.is_dir():
                copied += copy_tree(src, target / rel, args.force)
            else:
                dst = target / rel
                if dst.exists() and not args.force:
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        claude_md = target / "CLAUDE.md"
        shutil.copy2(
            template / "CLAUDE.md",
            target / ("CLAUDE.blender-addon.md" if claude_md.exists() else "CLAUDE.md"),
        )
        gi = target / ".gitignore"
        needed = [".blender-deps/", "dist/", "__pycache__/"]
        existing = gi.read_text().splitlines() if gi.exists() else []
        with gi.open("a") as f:
            for line in needed:
                if line not in existing:
                    f.write(line + "\n")
        print(
            f"adopted {copied} files into {target}. Next: move the add-on to src/<id>/ with a manifest if needed, then python3 tools/check.py"
        )
        return 0

    missing = [k for k in ("id", "name", "tagline", "maintainer") if getattr(args, k) is None]
    if missing:
        sys.exit(f"scaffolding needs --{' --'.join(missing)}")
    if target.exists() and any(target.iterdir()) and not args.force:
        sys.exit(f"{target} is not empty; use --force to write into it anyway")
    target.mkdir(parents=True, exist_ok=True)
    count = copy_tree(template, target, overwrite=True)
    print(f"copied {count} files to {target}")

    cmd = [
        sys.executable,
        str(target / "tools" / "new_addon.py"),
        "--id",
        args.id,
        "--name",
        args.name,
        "--tagline",
        args.tagline,
        "--maintainer",
        args.maintainer,
    ]
    if args.website:
        cmd += ["--website", args.website]
    subprocess.run(cmd, check=True, cwd=target)

    readme = target / "README.md"
    readme.write_text(
        f"# {args.name}\n\n{args.tagline}.\n\nBlender extension built from the "
        f"[blender-addon template]({TEMPLATE_URL}). Verify changes with `python3 tools/check.py`; "
        f"see `CLAUDE.md` for the development loop and `docs/` for testing notes and pitfalls.\n"
    )
    if not in_git_repo(target):
        subprocess.run(["git", "init", "--quiet"], cwd=target, check=True)
        print("initialised git repository")
    print("Next: bash tools/install_blender.sh (if Blender is not installed), then python3 tools/check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
