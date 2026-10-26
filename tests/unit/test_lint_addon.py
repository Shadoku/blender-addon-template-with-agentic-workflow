"""Each fixture under tests/lint_fixtures/ must trigger exactly the rule in its file name,
and the real add-on package must be clean."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import lint_addon  # noqa: E402

FIXTURES = ROOT / "tests" / "lint_fixtures"
FIXTURE_FILES = sorted(p for p in FIXTURES.rglob("BA*.py"))


@pytest.mark.parametrize("fixture", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixture_triggers_its_rule(fixture: Path) -> None:
    expected = fixture.stem.split("_")[0]
    findings = lint_addon.lint_source(
        fixture.read_text(),
        fixture,
        package="fixture_pkg",
        in_core=fixture.parent.name == "core",
        has_manifest=True,
        network_allowed=False,
    )
    rules = {f.rule for f in findings}
    assert expected in rules, f"expected {expected}, got {[str(f) for f in findings]}"


def test_outdated_api_fixture_reports_every_legacy_line() -> None:
    fixture = FIXTURES / "BA007_outdated_api.py"
    findings = [
        f
        for f in lint_addon.lint_source(
            fixture.read_text(),
            fixture,
            "fixture_pkg",
            in_core=False,
            has_manifest=True,
            network_allowed=False,
        )
        if f.rule == "BA007"
    ]
    assert len(findings) == 6, [str(f) for f in findings]


def test_every_rule_has_a_fixture() -> None:
    covered = {p.stem.split("_")[0] for p in FIXTURE_FILES}
    assert covered == set(lint_addon.RULES), set(lint_addon.RULES) ^ covered


def test_network_import_allowed_with_permission() -> None:
    src = "import urllib.request\n"
    findings = lint_addon.lint_source(
        src, Path("x.py"), "pkg", in_core=False, has_manifest=True, network_allowed=True
    )
    assert not [f for f in findings if f.rule == "BA010"]


def test_template_addon_is_clean() -> None:
    addon_dirs = sorted(p.parent for p in (ROOT / "src").glob("*/blender_manifest.toml"))
    assert len(addon_dirs) == 1
    findings = lint_addon.lint_package(addon_dirs[0])
    assert findings == [], [str(f) for f in findings]
