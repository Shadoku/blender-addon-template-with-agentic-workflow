# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs INSIDE Blender (launched by tools/check.py). Not importable from plain Python.

    blender -b --factory-startup --python-exit-code 1 --python tools/blender_bootstrap.py -- \
        --mode dev|package [--filter EXPR] [--junit FILE] [--verbose] [pytest args...]

dev mode:
  Mounts ``src/`` as a local extension repository named ``dev`` so the add-on
  imports as ``bl_ext.dev.<id>`` exactly like an installed extension, enables
  it, then runs pytest on ``tests/blender``. The add-on module name is passed to
  the tests through the ``ADDON_MODULE`` environment variable.

package mode:
  Expects the built zip to be installed already (check.py does that with
  ``blender --command extension install-file``) and enables
  ``bl_ext.user_default.<id>``, then disables and re-enables it, asserting that
  nothing is left behind in bpy.types, bpy.types.Scene, handlers or timers.

Exit status is non-zero on any failure (via --python-exit-code). Output lines
starting with ``BOOTSTRAP:``, ``TESTS:`` and ``PACKAGE:`` are what check.py reads.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parent.parent
DEPS = Path(os.environ.get("CHECK_DEPS_DIR", ROOT / ".blender-deps"))


def log(msg: str) -> None:
    print(f"BOOTSTRAP: {msg}", flush=True)


def addon_id() -> str:
    manifests = sorted((ROOT / "src").glob("*/blender_manifest.toml"))
    if len(manifests) != 1:
        raise RuntimeError(f"expected exactly one src/<id>/blender_manifest.toml, found {manifests}")
    data = tomllib.loads(manifests[0].read_text(encoding="utf-8"))
    if data["id"] != manifests[0].parent.name:
        raise RuntimeError(
            f"manifest id {data['id']!r} must equal its directory name {manifests[0].parent.name!r}"
        )
    return data["id"]


def enable(module: str) -> object:
    mod = addon_utils.enable(module, default_set=True, persistent=True)
    if mod is None:
        raise RuntimeError(f"addon_utils.enable({module!r}) returned None; see the traceback above")
    return mod


def snapshot() -> dict[str, object]:
    return {
        "types": set(dir(bpy.types)),
        "scene_attrs": set(dir(bpy.types.Scene)),
        "handlers": {
            name: len(getattr(bpy.app.handlers, name))
            for name in dir(bpy.app.handlers)
            if isinstance(getattr(bpy.app.handlers, name), list)
        },
    }


def diff(before: dict[str, object], after: dict[str, object]) -> list[str]:
    problems = []
    for key in ("types", "scene_attrs"):
        extra = sorted(after[key] - before[key])  # type: ignore[operator]
        if extra:
            problems.append(f"leftover {key}: {extra}")
    for name, count in after["handlers"].items():  # type: ignore[union-attr]
        if count != before["handlers"][name]:  # type: ignore[index]
            problems.append(f"handler list {name} changed from {before['handlers'][name]} to {count}")  # type: ignore[index]
    return problems


def mount_dev_repo() -> None:
    repos = bpy.context.preferences.extensions.repos
    repo = repos.new(name="dev", module="dev", custom_directory=str(ROOT / "src"))
    repo.use_custom_directory = True
    addon_utils.extensions_refresh(ensure_wheels=True)


def run_pytest(args: argparse.Namespace, module: str) -> int:
    sys.path.insert(0, str(DEPS))
    os.environ["ADDON_MODULE"] = module
    import pytest

    pytest_args = [
        "-p",
        "no:cacheprovider",
        "-s",
        "-ra",
        str(ROOT / "tests" / "blender"),
        "--rootdir",
        str(ROOT),
    ]
    if args.filter:
        pytest_args += ["-k", args.filter]
    if args.junit:
        pytest_args += ["--junitxml", args.junit]
    pytest_args += ["-v"] if args.verbose else ["-q"]
    pytest_args += args.pytest_args
    plugin = Summary()
    code = int(pytest.main(pytest_args, plugins=[plugin]))
    print(plugin.line(), flush=True)
    if code == 5:  # pytest: no tests collected. An empty suite must be noticed, not pass silently.
        print(
            "BOOTSTRAP: FAIL no tests collected under tests/blender (add tests/blender/test_*.py)", flush=True
        )
    return code


class Summary:
    """Prints marker lines so check.py can attribute engine errors to tests, and the TESTS: summary."""

    def __init__(self) -> None:
        self.counts = {"passed": 0, "failed": 0, "skipped": 0}

    def pytest_runtest_logstart(self, nodeid: str, location: tuple) -> None:
        print(f"::: TEST START {nodeid}", flush=True)

    def pytest_runtest_logfinish(self, nodeid: str, location: tuple) -> None:
        print(f"::: TEST END {nodeid}", flush=True)

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            self.counts[report.outcome] = self.counts.get(report.outcome, 0) + 1

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.counts["failed"] += 1

    def line(self) -> str:
        c = self.counts
        return f"TESTS: {c['passed']} passed, {c['failed']} failed, {c['skipped']} skipped"


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dev", "package"], required=True)
    ap.add_argument("--filter")
    ap.add_argument("--junit")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("pytest_args", nargs="*")
    args = ap.parse_args(argv)

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    aid = addon_id()
    log(f"Blender {bpy.app.version_string} Python {sys.version.split()[0]} background={bpy.app.background}")

    if args.mode == "dev":
        mount_dev_repo()
        module = f"bl_ext.dev.{aid}"
        enable(module)
        log(f"enabled {module} from {ROOT / 'src' / aid}")
        return run_pytest(args, module)

    module = f"bl_ext.user_default.{aid}"
    before = snapshot()
    enable(module)
    log(f"enabled installed package {module}")
    addon_utils.disable(module, default_set=True)
    problems = diff(before, snapshot())
    enable(module)
    log("re-enabled after disable")
    if problems:
        for p in problems:
            print(f"PACKAGE: FAIL {p}", flush=True)
        raise RuntimeError("unregister() left state behind; see PACKAGE: lines")
    print(f"PACKAGE: {aid} installs, enables, disables cleanly and re-enables", flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    if code:
        # Raise instead of sys.exit(): Blender turns an exception into the --python-exit-code status,
        # while sys.exit() terminates Blender abruptly and looks like a crash.
        raise RuntimeError(f"pytest finished with exit status {code}")
