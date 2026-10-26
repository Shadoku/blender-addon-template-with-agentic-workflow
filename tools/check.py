#!/usr/bin/env python3
"""Run every automated check for this Blender add-on and print a compact report.

Stages (in order):
  lint     - ruff (style, imports, modernisation), tools/lint_addon.py (Blender-specific
             rules), and `blender --command extension validate` on the manifest
  unit     - pytest tests/unit with Blender's bundled Python (no bpy; milliseconds)
  blender  - pytest tests/blender inside headless Blender with the add-on loaded from
             src/ as a real extension (bl_ext.dev.<id>)
  package  - `extension build` into dist/, install the zip into an isolated profile,
             enable -> disable -> enable and fail on anything left registered

Usage:
  python3 tools/check.py                  # everything
  python3 tools/check.py --only blender   # one stage
  python3 tools/check.py --filter=spacing # pytest -k expression for unit and blender
  python3 tools/check.py --verbose        # full tool output for every stage
  python3 tools/check.py --setup          # only install Blender + dev deps, then exit

Exit code is 0 only when every stage passed. The last line is always
"CHECK: PASS" or "CHECK: FAIL (<stages>)" so the result is easy to spot.

Environment:
  BLENDER  - path to the Blender binary. If unset, PATH (blender) and
             ~/.cache/blender/<version>/blender are tried, where <version> comes from
             .blender-version. tools/install_blender.sh downloads it there.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DEPS_ROOT = (
    ROOT / ".blender-deps"
)  # one sub-directory per bundled Python version (3.11 for 4.5, 3.13 for 5.2)
REQUIREMENTS = ROOT / "tools" / "requirements-dev.txt"
STAGES = ("lint", "unit", "blender", "package")
STAGE_TIMEOUT = {"lint": 300, "unit": 300, "blender": 900, "package": 600}

# Lines matching any of these are known-benign headless noise and never fail a stage.
IGNORE_PATTERNS = [
    r"ALSA lib",
    r"XDG_RUNTIME_DIR",
    r"Unable to open a display",
    r"Color management: using fallback mode",
    r"Warning: Falling back to the standard locale",
    r"WARNING: Running pip as the 'root' user",
]

# A Blender stage fails if any of these appears in its output, even with exit code 0.
ERROR_LINE = re.compile(
    r"^(Traceback \(most recent call last\)|Exception in module register\(\)|"
    r"Error: |ERROR |RuntimeError|ValueError: bpy_struct|register_class\(\.\.\.\):|"
    r"Warning: '.*' does not contain|BOOTSTRAP: FAIL|PACKAGE: FAIL)"
)
TEST_MARK = re.compile(r"^::: TEST (START|END) (.+)$")
SUMMARY_PREFIXES = ("TESTS:", "PACKAGE:", "LINT:", "BOOTSTRAP: Blender")


# --------------------------------------------------------------------------- discovery
def blender_version() -> str:
    f = ROOT / ".blender-version"
    return f.read_text().strip() if f.exists() else "5.2.3"


def find_blender() -> str:
    candidates = []
    if os.environ.get("BLENDER"):
        candidates.append(os.environ["BLENDER"])
    p = shutil.which("blender")
    if p:
        candidates.append(p)
    candidates.append(str(Path.home() / ".cache" / "blender" / blender_version() / "blender"))
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit(
        "No Blender binary found. Set BLENDER=/path/to/blender, put `blender` on PATH, or run "
        f"`bash tools/install_blender.sh` to download {blender_version()}."
    )


def find_blender_python(blender: str) -> str:
    """Blender's bundled interpreter: <dir>/<X.Y>/python/bin/python3* (or inside Blender.app)."""
    exe = Path(blender).resolve()
    roots = [exe.parent, exe.parent.parent / "Resources"]  # linux layout, macOS .app layout
    for root in roots:
        for py in sorted(root.glob("[0-9].[0-9]*/python/bin/python3*")):
            if py.is_file() and os.access(py, os.X_OK) and not py.name.endswith("-config"):
                return str(py)
    sys.exit(f"Could not find Blender's bundled python next to {blender}")


def addon_dir() -> Path:
    manifests = sorted(SRC.glob("*/blender_manifest.toml"))
    if len(manifests) != 1:
        sys.exit(f"Expected exactly one src/<id>/blender_manifest.toml, found: {manifests}")
    return manifests[0].parent


def deps_dir(python: str) -> Path:
    """.blender-deps/pyX.Y for the given interpreter, so 4.5 (3.11) and 5.2 (3.13) can share a checkout."""
    out = subprocess.run(
        [python, "-c", "import sys; print(f'py{sys.version_info[0]}.{sys.version_info[1]}')"],
        capture_output=True,
        text=True,
        check=True,
    )
    return DEPS_ROOT / out.stdout.strip()


def ensure_deps(python: str, deps: Path, verbose: bool) -> None:
    """Install tools/requirements-dev.txt into `deps` with Blender's own pip (idempotent)."""
    stamp = deps / ".stamp"
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if stamp.exists() and stamp.read_text().strip() == digest:
        return
    print(f"installing dev dependencies into {deps.relative_to(ROOT)} with {python}")
    if deps.exists():
        shutil.rmtree(deps)
    cmd = [
        python,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--root-user-action=ignore",
        "--target",
        str(deps),
        "-r",
        str(REQUIREMENTS),
    ]
    if not verbose:
        cmd.insert(3, "--quiet")
    subprocess.run(cmd, check=True, cwd=ROOT)
    stamp.write_text(digest)


# --------------------------------------------------------------------------- running
def isolated_env(tmp: Path, deps: Path) -> dict[str, str]:
    """Environment that keeps Blender from reading or writing the real user profile."""
    env = dict(os.environ)
    for name in ("CONFIG", "SCRIPTS", "EXTENSIONS"):
        d = tmp / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        env[f"BLENDER_USER_{name}"] = str(d)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(deps) + os.pathsep + env.get("PYTHONPATH", "")
    env["CHECK_DEPS_DIR"] = str(deps)
    return env


def run(cmd: list[str], timeout: int, env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT, env=env)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"") + (e.stderr or b"")
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        return 124, out + f"\n[check.py] TIMEOUT after {timeout}s: {' '.join(cmd)}\n"


def is_noise(line: str) -> bool:
    return any(re.search(p, line) for p in IGNORE_PATTERNS)


def engine_errors(output: str) -> list[str]:
    """Error blocks (first line + indented continuation) attributed to the test running at the time."""
    blocks: list[str] = []
    current_test = None
    block: list[str] | None = None
    for line in output.splitlines():
        m = TEST_MARK.match(line)
        if m:
            current_test = m.group(2) if m.group(1) == "START" else None
            block = None
            continue
        if ERROR_LINE.match(line) and not is_noise(line):
            where = f" [during {current_test}]" if current_test else ""
            block = [line + where]
            blocks.append("\n".join(block))
        elif block is not None and line[:1] in (" ", "\t"):
            block.append(line)
            blocks[-1] = "\n".join(block)
        else:
            block = None
    return blocks


def clean(output: str) -> str:
    return "\n".join(
        line
        for line in output.splitlines()
        if line.strip() and not is_noise(line) and not line.startswith("Blender quit")
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=STAGES, help="run a single stage")
    ap.add_argument("--filter", help="pytest -k expression for the unit and blender stages")
    ap.add_argument("--verbose", action="store_true", help="print full tool output for every stage")
    ap.add_argument("--junit", help="write JUnit XML: <path>-unit.xml and <path>-blender.xml")
    ap.add_argument(
        "--setup",
        action="store_true",
        help="install Blender (via tools/install_blender.sh) and dev deps, then exit",
    )
    ap.add_argument(
        "--keep-dist", action="store_true", help="keep the zip built by the package stage in dist/"
    )
    args = ap.parse_args()

    if args.setup:
        subprocess.run(["bash", str(ROOT / "tools" / "install_blender.sh")], check=True)
    blender = find_blender()
    python = find_blender_python(blender)
    print(f"blender: {blender}")
    deps = deps_dir(python)
    ensure_deps(python, deps, args.verbose)
    if args.setup:
        print("setup complete")
        return 0

    addon = addon_dir()
    failed: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="blender-check-"))
    env = isolated_env(tmp, deps)

    def report(name: str, ok: bool, out: str, details: str, t0: float) -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name} ({time.time() - t0:.1f}s)")
        if args.verbose:
            print("    " + clean(out).replace("\n", "\n    "))
        elif not ok:
            print("    " + details.strip().replace("\n", "\n    "))
        else:
            for line in out.splitlines():
                if line.startswith(SUMMARY_PREFIXES):
                    print("    " + line)
        if not ok:
            failed.append(name)

    def wants(name: str) -> bool:
        return args.only is None or args.only == name

    # 1. lint ---------------------------------------------------------------
    if wants("lint"):
        t0 = time.time()
        outputs: list[str] = []
        ok = True
        for label, cmd in (
            ("ruff check", [python, "-m", "ruff", "check", "."]),
            ("ruff format", [python, "-m", "ruff", "format", "--check", "."]),
            ("lint_addon", [python, str(ROOT / "tools" / "lint_addon.py"), str(addon)]),
            ("extension validate", [blender, "--command", "extension", "validate", str(addon)]),
        ):
            code, out = run(cmd, STAGE_TIMEOUT["lint"], env)
            if code != 0:
                ok = False
                outputs.append(f"--- {label} failed (exit {code})\n{clean(out)}")
            elif args.verbose:
                outputs.append(f"--- {label}\n{clean(out)}")
        summary = "LINT: ruff, lint_addon, extension validate all passed" if ok else ""
        report("lint", ok, "\n".join(outputs) + "\n" + summary, "\n".join(outputs), t0)

    # 2. unit ---------------------------------------------------------------
    if wants("unit"):
        t0 = time.time()
        cmd = [
            python,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "-ra",
            str(ROOT / "tests" / "unit"),
            "--rootdir",
            str(ROOT),
        ]
        if args.filter:
            cmd += ["-k", args.filter]
        if args.junit:
            cmd += ["--junitxml", f"{args.junit}-unit.xml"]
        if args.verbose:
            cmd.append("-v")
        code, out = run(cmd, STAGE_TIMEOUT["unit"], env)
        summary = next(
            (ln for ln in reversed(out.splitlines()) if re.search(r"\d+ (passed|failed|error)", ln)), ""
        )
        out += f"\nTESTS: {summary.strip('= ')}" if summary else ""
        report("unit", code == 0, out, clean(out), t0)

    # 3. blender ------------------------------------------------------------
    def blender_cmd(mode: str, extra: list[str]) -> list[str]:
        return [
            blender,
            "-b",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "tools" / "blender_bootstrap.py"),
            "--",
            "--mode",
            mode,
            *extra,
        ]

    if wants("blender"):
        t0 = time.time()
        extra = []
        if args.filter:
            extra += ["--filter", args.filter]
        if args.junit:
            extra += ["--junit", str(Path(f"{args.junit}-blender.xml").resolve())]
        if args.verbose:
            extra.append("--verbose")
        code, out = run(blender_cmd("dev", extra), STAGE_TIMEOUT["blender"], env)
        errors = engine_errors(out)
        ok = code == 0 and not errors
        details = clean(out) if code != 0 else "\n".join(errors)
        if errors and code == 0:
            details = "engine errors were printed (exit code was 0):\n" + details
        report("blender", ok, out, details, t0)

    # 4. package ------------------------------------------------------------
    if wants("package"):
        t0 = time.time()
        dist = ROOT / "dist"
        dist.mkdir(exist_ok=True)
        for old in dist.glob("*.zip"):
            old.unlink()
        code, out = run(
            [
                blender,
                "--command",
                "extension",
                "build",
                "--source-dir",
                str(addon),
                "--output-dir",
                str(dist),
            ],
            STAGE_TIMEOUT["package"],
            env,
        )
        zips = sorted(dist.glob("*.zip"))
        ok = code == 0 and len(zips) == 1
        if ok:
            code2, out2 = run(
                [
                    blender,
                    "--command",
                    "extension",
                    "install-file",
                    "-r",
                    "user_default",
                    "--no-prefs",
                    str(zips[0]),
                ],
                STAGE_TIMEOUT["package"],
                env,
            )
            out += "\n" + out2
            ok = code2 == 0 and "FATAL" not in out2 and "Error" not in out2
        if ok:
            code3, out3 = run(blender_cmd("package", []), STAGE_TIMEOUT["package"], env)
            out += "\n" + out3
            errors = engine_errors(out3)
            ok = code3 == 0 and not errors
        if ok:
            out += f"\nPACKAGE: built {zips[0].relative_to(ROOT)} ({zips[0].stat().st_size} bytes)"
        report("package", ok, out, clean(out), t0)
        if not args.keep_dist:
            shutil.rmtree(dist, ignore_errors=True)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failed:
        print(f"CHECK: FAIL ({', '.join(failed)})")
        return 1
    print("CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
