#!/usr/bin/env python3
"""Blender-specific static checks for an extension package. Zero dependencies.

    python3 tools/lint_addon.py src/<id>          # exit 1 on any finding
    python3 tools/lint_addon.py --list-rules

These encode the ways add-on code goes wrong that a generic linter cannot see
(docs/pitfalls.md has the background for each). Rules:

  BA001  Operator bl_idname must be "category.name": lowercase, exactly one dot
  BA002  Class name must carry the type infix (_OT_, _PT_, _MT_, _HT_, _UL_) and match bl_idname for UI classes
  BA003  bl_info is not allowed next to blender_manifest.toml (the manifest replaces it)
  BA004  Imports inside the package must be relative (import <id> / bl_ext.* paths break per-repository)
  BA005  Nothing under core/ may import bpy, bmesh, mathutils or gpu
  BA006  preferences.addons[...] must be indexed with __package__, not a string literal
  BA007  Outdated API that was removed or renamed (2.8 through 5.x); message names the replacement
  BA008  Operators must declare bl_options explicitly (add 'UNDO' when writing to bpy.data)
  BA009  No threading/asyncio/concurrent.futures: bpy is not thread-safe, use bpy.app.timers
  BA010  Network modules require a [permissions] network entry in the manifest
  BA011  bpy.app.handlers callbacks must be decorated with @persistent
  BA012  Properties on Blender classes must be annotations (name: Prop()), not assignments (name = Prop())
  BA013  Panel/Menu/Operator classes may not define __init__ (Blender constructs them; forward *args if you must)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

BLENDER_UI_TYPES = {"Panel": "_PT_", "Menu": "_MT_", "Header": "_HT_", "UIList": "_UL_"}
OPERATOR_TYPES = {"Operator", "Macro"}
PROPERTY_CLASS_TYPES = {
    "PropertyGroup",
    "AddonPreferences",
    "Operator",
    "Macro",
    "Panel",
    "Menu",
    "Header",
    "UIList",
    "Node",
    "NodeTree",
    "NodeSocket",
    "Gizmo",
    "GizmoGroup",
    "RenderEngine",
    "KeyingSetInfo",
}
PROP_FUNCS = {
    "BoolProperty",
    "BoolVectorProperty",
    "CollectionProperty",
    "EnumProperty",
    "FloatProperty",
    "FloatVectorProperty",
    "IntProperty",
    "IntVectorProperty",
    "PointerProperty",
    "StringProperty",
}
CORE_FORBIDDEN = {"bpy", "bmesh", "mathutils", "gpu", "blf", "bl_ui", "bl_operators", "addon_utils"}
THREAD_MODULES = {"threading", "asyncio", "concurrent", "_thread", "multiprocessing"}
NETWORK_MODULES = {
    "urllib",
    "http",
    "socket",
    "requests",
    "ssl",
    "ftplib",
    "smtplib",
    "websocket",
    "websockets",
    "aiohttp",
    "httpx",
}
UI_IDNAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*_(PT|MT|HT|UL)_[A-Za-z0-9_]+$")
OP_IDNAME_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

# (regex, message). Matched against source text line by line, comments stripped.
OUTDATED_API: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\.select\s*=\s*(True|False)"),
        "obj.select = ... was removed in 2.80; use obj.select_set(bool) / obj.select_get()",
    ),
    (
        re.compile(r"scene\.objects\.active\b"),
        "scene.objects.active was removed in 2.80; use context.view_layer.objects.active",
    ),
    (
        re.compile(r"\bscene\.update\(\)"),
        "scene.update() was removed in 2.80; use context.view_layer.update() or evaluate the depsgraph",
    ),
    (
        re.compile(r"scene\.objects\.link\("),
        "scene.objects.link() was removed in 2.80; link to a collection: collection.objects.link(obj)",
    ),
    (
        re.compile(r"bpy\.utils\.register_module"),
        "register_module() was removed in 2.80; keep a classes tuple and register each class",
    ),
    (
        re.compile(r"\bINFO_HT_header\b"),
        "INFO_HT_header was replaced by TOPBAR_HT_upper_bar / STATUSBAR_HT_header in 2.80",
    ),
    (
        re.compile(r"[\"']wiki_url[\"']"),
        "bl_info['wiki_url'] became doc_url in 2.83 and lives in the manifest now (website)",
    ),
    (
        re.compile(r"\bimport bgl\b|\bfrom bgl import\b|\bbgl\."),
        "the bgl module was removed in 4.0/5.0; use the gpu module",
    ),
    (
        re.compile(r"use_auto_smooth"),
        "Mesh.use_auto_smooth was removed in 4.1; use the sharp_edge attribute or a Smooth by Angle modifier",
    ),
    (
        re.compile(r"\.calc_normals_split\(|\.free_normals_split\(|\.create_normals_split\("),
        "*_normals_split() were removed in 4.1; use Mesh.corner_normals",
    ),
    (
        re.compile(r"\.calc_normals\(\)"),
        "Mesh.calc_normals() was removed in 4.0; normals are computed on demand",
    ),
    (
        re.compile(r"\binputs\[[\"']Subsurface[\"']\]"),
        "Principled BSDF 'Subsurface' became 'Subsurface Weight' in 4.0",
    ),
    (
        re.compile(r"\binputs\[[\"']Specular[\"']\]"),
        "Principled BSDF 'Specular' became 'Specular IOR Level' in 4.0",
    ),
    (
        re.compile(r"\binputs\[[\"']Transmission[\"']\]"),
        "Principled BSDF 'Transmission' became 'Transmission Weight' in 4.0",
    ),
    (
        re.compile(r"\binputs\[[\"']Emission[\"']\]"),
        "Principled BSDF 'Emission' became 'Emission Color' in 4.0",
    ),
    (re.compile(r"\binputs\[[\"']Sheen[\"']\]"), "Principled BSDF 'Sheen' became 'Sheen Weight' in 4.0"),
    (
        re.compile(r"\binputs\[[\"']Clearcoat[\"']\]"),
        "Principled BSDF 'Clearcoat' became 'Coat Weight' in 4.0",
    ),
    (
        re.compile(r"node_tree\.(inputs|outputs)\.new\("),
        "NodeTree.inputs/outputs were removed in 4.0; use node_tree.interface.new_socket()",
    ),
    (
        re.compile(r"\bbpy\.ops\.[a-z_]+\.[a-z_]+\(\s*\{"),
        "dict context overrides were removed in 4.0; use `with context.temp_override(...)`",
    ),
    (re.compile(r"\bBLENDER_EEVEE_NEXT\b"), "BLENDER_EEVEE_NEXT was renamed back to BLENDER_EEVEE in 5.0"),
    (
        re.compile(r"\bscene\.node_tree\b"),
        "scene.node_tree was replaced by scene.compositing_node_group in 5.0",
    ),
    (
        re.compile(r"\bscene\.use_nodes\b"),
        "scene.use_nodes is deprecated since 5.0; compositing is enabled by assigning scene.compositing_node_group",
    ),
    (
        re.compile(r"\baction\.(fcurves|groups|id_root)\b"),
        "the legacy Action API (action.fcurves/groups/id_root) was removed in 5.0; use slotted actions (channelbags)",
    ),
    (
        re.compile(r"\bbpy\.data\.grease_pencils\b"),
        "bpy.data.grease_pencils holds GPv3 data in 4.3+; annotations moved to bpy.data.annotations in 5.0",
    ),
    (
        re.compile(r"\bbpy\.types\.Sequence\b|\bSequenceEditor\.sequences\b"),
        "VSE 'Sequence' types were renamed to 'Strip' in 4.4 (sequence_editor.strips)",
    ),
    (
        re.compile(r"\bbpy\.ops\.import_scene\.obj\b|\bbpy\.ops\.export_scene\.obj\b"),
        "the Python OBJ importer/exporter was removed in 4.0; use bpy.ops.wm.obj_import / obj_export",
    ),
    (
        re.compile(r"\.render\.engine\s*=\s*[\"'](cycles|eevee|workbench)[\"']"),
        "engine identifiers are upper-case: 'CYCLES', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'",
    ),
]


@dataclass
class Finding:
    rule: str
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


RULES = {
    line.split()[0]: line.split(maxsplit=1)[1]
    for line in (__doc__ or "").splitlines()
    if line.strip().startswith("BA")
}


def _base_names(cls: ast.ClassDef) -> set[str]:
    names = set()
    for b in cls.bases:
        if isinstance(b, ast.Attribute):
            names.add(b.attr)
        elif isinstance(b, ast.Name):
            names.add(b.id)
    return names


def _class_attr(cls: ast.ClassDef, name: str) -> ast.expr | None:
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    return None


def _str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _strip_comments(source: str) -> list[str]:
    return [line.split("#", 1)[0] if "#" in line else line for line in source.splitlines()]


def lint_source(
    source: str, path: Path, package: str, *, in_core: bool, has_manifest: bool, network_allowed: bool
) -> list[Finding]:
    out: list[Finding] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [Finding("BA000", path, e.lineno or 1, f"syntax error: {e.msg}")]

    def add(rule: str, node: ast.AST, msg: str) -> None:
        out.append(Finding(rule, path, getattr(node, "lineno", 1), msg))

    handler_decorated: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                name = d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", "")
                if name == "persistent":
                    handler_decorated.add(node.name)

    for node in ast.walk(tree):
        # imports ---------------------------------------------------------
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                mods = [node.module or ""] if node.level == 0 else []
            else:
                mods = [a.name for a in node.names]
            for mod in mods:
                top = mod.split(".")[0]
                if top == package or top == "bl_ext":
                    add(
                        "BA004",
                        node,
                        f"absolute import of {mod!r}; use a relative import (from . import ...)",
                    )
                if in_core and top in CORE_FORBIDDEN:
                    add("BA005", node, f"core/ must stay free of Blender modules, found import of {mod!r}")
                if top in THREAD_MODULES:
                    add(
                        "BA009",
                        node,
                        f"{mod!r} imported; bpy is not thread-safe, schedule work with bpy.app.timers instead",
                    )
                if top in NETWORK_MODULES and not network_allowed:
                    add(
                        "BA010",
                        node,
                        f"{mod!r} imported but the manifest declares no [permissions] network entry",
                    )
        # bl_info ---------------------------------------------------------
        if isinstance(node, ast.Assign) and has_manifest:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "bl_info":
                    add(
                        "BA003",
                        node,
                        "bl_info is ignored for extensions; put the metadata in blender_manifest.toml",
                    )
        # preferences.addons["literal"] -----------------------------------
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "addons"
        ):
            if _str(node.slice) is not None:
                add(
                    "BA006",
                    node,
                    f"preferences.addons[{_str(node.slice)!r}]: index with __package__ so it works in every repository",
                )
        # handlers.X.append(fn) -------------------------------------------
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            target = node.func.value
            chain = []
            while isinstance(target, ast.Attribute):
                chain.append(target.attr)
                target = target.value
            if "handlers" in chain and node.args and isinstance(node.args[0], ast.Name):
                fn = node.args[0].id
                if fn not in handler_decorated:
                    add(
                        "BA011",
                        node,
                        f"handler {fn!r} is appended to bpy.app.handlers but is not decorated with @persistent",
                    )
        # classes ----------------------------------------------------------
        if isinstance(node, ast.ClassDef):
            bases = _base_names(node)
            idname = _str(_class_attr(node, "bl_idname"))
            if bases & OPERATOR_TYPES:
                if idname is not None and not OP_IDNAME_RE.match(idname):
                    add(
                        "BA001",
                        node,
                        f"bl_idname {idname!r} must be lowercase 'category.name' with exactly one dot",
                    )
                if "_OT_" not in node.name:
                    add("BA002", node, f"operator class {node.name!r} should be named like CATEGORY_OT_name")
                if _class_attr(node, "bl_options") is None:
                    add(
                        "BA008",
                        node,
                        f"operator {node.name!r} declares no bl_options; use {{'REGISTER', 'UNDO'}} when it edits data, or {{'INTERNAL'}}",
                    )
            for base, infix in BLENDER_UI_TYPES.items():
                if base in bases:
                    if infix not in node.name:
                        add(
                            "BA002",
                            node,
                            f"{base} class {node.name!r} must contain {infix!r} (e.g. VIEW3D{infix}my_panel)",
                        )
                    if idname is not None and not UI_IDNAME_RE.match(idname):
                        add("BA002", node, f"{base} bl_idname {idname!r} must match [A-Z0-9_]+{infix}name")
            if bases & PROPERTY_CLASS_TYPES:
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                        fn = stmt.value.func
                        fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                        if fname in PROP_FUNCS:
                            names = ", ".join(getattr(t, "id", "?") for t in stmt.targets)
                            add(
                                "BA012",
                                stmt,
                                f"property {names!r} assigned with '='; declare it as an annotation: {names}: {fname}(...)",
                            )
                    if (
                        isinstance(stmt, ast.FunctionDef)
                        and stmt.name in {"__init__", "__new__"}
                        and (bases & (set(BLENDER_UI_TYPES) | OPERATOR_TYPES))
                    ):
                        add(
                            "BA013",
                            stmt,
                            f"{node.name!r} defines {stmt.name}; Blender instantiates these classes itself",
                        )

    for lineno, text in enumerate(_strip_comments(source), start=1):
        for pattern, message in OUTDATED_API:
            if pattern.search(text):
                out.append(Finding("BA007", path, lineno, message))
    return out


def lint_package(addon_dir: Path) -> list[Finding]:
    addon_dir = addon_dir.resolve()
    manifest = addon_dir / "blender_manifest.toml"
    has_manifest = manifest.exists()
    network_allowed = False
    findings: list[Finding] = []
    if has_manifest:
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            network_allowed = "network" in data.get("permissions", {})
            if data.get("id") != addon_dir.name:
                findings.append(
                    Finding(
                        "BA003",
                        manifest,
                        1,
                        f"manifest id {data.get('id')!r} must equal the directory name {addon_dir.name!r}",
                    )
                )
        except tomllib.TOMLDecodeError as e:
            findings.append(Finding("BA003", manifest, 1, f"manifest does not parse: {e}"))
    for py in sorted(addon_dir.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(addon_dir)
        findings.extend(
            lint_source(
                py.read_text(encoding="utf-8"),
                py,
                addon_dir.name,
                in_core=rel.parts[0] == "core",
                has_manifest=has_manifest,
                network_allowed=network_allowed,
            )
        )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("addon_dir", nargs="?", help="the extension package directory (src/<id>)")
    ap.add_argument("--list-rules", action="store_true")
    args = ap.parse_args()
    if args.list_rules:
        for rule, text in RULES.items():
            print(f"{rule}  {text}")
        return 0
    if not args.addon_dir:
        ap.error("addon_dir is required")
    findings = lint_package(Path(args.addon_dir))
    for f in findings:
        print(f)
    n_files = len(list(Path(args.addon_dir).rglob("*.py")))
    print(f"LINT: lint_addon checked {n_files} files, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
