#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""List the python-hwpx names that moving code uses outside the engine's contract.

7.0 moves the converters (Markdown, HTML, ingest, mail merge, preview, ...) from
python-hwpx to python-hwpx-automation. Moved code may only use the engine's public
contract. This script reads the moving modules with :mod:`ast` (it does not import
them) and reports every use of something that is not in that contract:

* ``private-name``    -- ``from hwpx.x import _name`` (a name with a leading underscore)
* ``private-module``  -- an import from a module with an underscore in its path
                         (``hwpx._document.headings``, ``hwpx.oxml._document_primitives``)
* ``non-contract``    -- a public-looking name from a module the contract does not cover
                         (``hwpx.oxml.hyperlink_form.hyperlink_target``)
* ``private-member``  -- ``obj._member`` on anything but ``self``/``cls`` (``doc._root``)
* ``left-behind``     -- for a module of which only a part moves: a module-level name of
                         the part that stays (``exporter._section_xmls`` from ``export_markdown``)

It runs on its own (standard library only) so the receiving package can run the same
check after the move::

    python scripts/check_moved_private_names.py                 # table
    python scripts/check_moved_private_names.py --json          # machine-readable
    python scripts/check_moved_private_names.py --root other/src --target pkg/mod.py

Exit status is 1 when anything is reported, unless ``--report-only`` is given.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

#: The engine package whose contract the moved code must keep to.
ENGINE = "hwpx"

#: Modules (with the names in them) that are the engine's contract. ``"*"`` means every
#: name without a leading underscore. A module not listed here is not contract even when
#: its own name has no underscore: its path is open, but nothing promises its names.
#: Keep this in step with ``docs/stable-api.md``.
CONTRACT: dict[str, frozenset[str] | str] = {
    "hwpx": "*",
    "hwpx.document": frozenset({"HwpxDocument"}),
    "hwpx.model": "*",
    "hwpx.objects": "*",
    "hwpx.errors": "*",
    "hwpx.experimental": "*",
    # The object model lives here; hwpx.model names the same classes.
    "hwpx.oxml": "*",
    "hwpx.opc.package": frozenset({"HwpxPackage", "HwpxPackageError", "HwpxStructureError"}),
    "hwpx.table_patch": "*",
    "hwpx.equation": "*",
    # 7.0 promotions (docs/stable-api.md, "7.0: 엔진의 공개 읽기").
    "hwpx.oxml.namespaces": "*",
    "hwpx.oxml.run": frozenset({"text_element_content", "HwpxOxmlRun", "RunStyle", "RUN_CONTENT_KINDS"}),
    "hwpx.oxml.paragraph_heading": "*",
    "hwpx.oxml.hyperlink_form": frozenset({"hyperlink_target"}),
    "hwpx.oxml.table_sizes": frozenset({"cell_margins_of"}),
    "hwpx.oxml.section_format": frozenset({"PAGE_PORTRAIT", "PAGE_LANDSCAPE"}),
    "hwpx.opc.security": frozenset(
        {
            "HwpxSecurityError", "ZipGuardLimits", "guard_zip_file", "read_member", "read_zip_members",
            "guard_xml_bytes", "guard_xml_depth", "parse_xml_stdlib", "MAX_XML_BYTES", "MAX_XML_DEPTH",
            "MAX_ZIP_ENTRIES", "MAX_ZIP_MEMBER_BYTES", "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES",
            "MAX_ZIP_COMPRESSION_RATIO", "MAX_ZIP_MIMETYPE_BYTES", "MAX_ZIP_SMALL_PART_BYTES",
        }
    ),
    "hwpx.form_fit": "*",
    "hwpx.form_fit.measure": frozenset(
        {
            "char_advance", "estimate_text_width", "indented_widths", "text_style_from_refs",
            "resolve_slot_metrics", "TextStyle", "SlotMetrics",
        }
    ),
    "hwpx.tools.exporter": frozenset(
        {"export_text", "ListLabels", "NoteLabels", "NUMBER_TEXT_FORMATS", "number_text", "table_grid_text"}
    ),
    "hwpx.tools.archive_cli": frozenset({"input_file_problem"}),
}


@dataclass(frozen=True)
class Target:
    """A moving module, or the part of one that moves (``names``: its top-level definitions)."""

    path: str
    names: frozenset[str] | None = None


#: What moves in 7.0 (out/split7 inventory). Paths are relative to ``--root``.
DEFAULT_TARGETS: tuple[Target, ...] = (
    Target("hwpx/tools/markdown_import.py"),
    Target("hwpx/tools/markdown_export.py"),
    Target(
        "hwpx/tools/exporter.py",
        frozenset(
            {
                "_MARKDOWN_ESCAPES", "_MATH_SPAN", "_UNSAFE_IN_MATH", "_HEADING_LINE",
                "_LIST_LINE", "_RULE_LINE", "_ORDERED_LINE", "_escape_markdown_plain",
                "escape_markdown", "_escape_line_start", "escape_line_starts",
                "_escape_markdown_block", "HEADING_MAX_CHARS", "_Headings", "_markdown_cell",
                "_escape_html", "export_html", "export_markdown",
            }
        ),
    ),
    Target("hwpx/tools/form_choices.py"),
    Target(
        "hwpx/tools/table_navigation.py",
        frozenset(
            {
                "_LabelCandidate", "_collapse_whitespace", "_normalize_label_text",
                "_LabelIndex", "_find_label_candidates", "_select_label_candidates",
                "_candidate_payload", "_cell_is_blank", "_cell_reference", "_escape_path_label",
                "_split_path", "_check_path_types", "_parse_path", "find_cell_by_label",
                "_cell_width_mm", "form_slots", "fill_by_path",
            }
        ),
    ),
    Target("hwpx/tools/mail_merge.py"),
    Target("hwpx/tools/layout_preview.py"),
    Target("hwpx/tools/document_viewer.py"),
    Target("hwpx/tools/format_rules.py"),
    Target("hwpx/tools/table_cleanup.py"),
    Target("hwpx/tools/report_utils.py"),
    Target(
        "hwpx/tools/doc_diff.py",
        frozenset(
            {
                "inspect_reference_consistency", "_attachment_numbers", "_numbering_violations",
                "_violation", "_paragraphs_from_document_plan",
            }
        ),
    ),
    Target("hwpx/ingest/__init__.py"),
    Target("hwpx/ingest/base.py"),
    Target("hwpx/ingest/hwpx_converter.py"),
    Target("hwpx/integrations/__init__.py"),
    Target("hwpx/integrations/langchain.py"),
    Target("hwpx/integrations/llama_index.py"),
    Target("hwpx/equation/render.py"),
    Target("hwpx/equation/mathml.py"),
)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    kind: str
    module: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.file}:{self.kind}:{self.module}:{self.name}"


def _module_of(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _absolute(module: str | None, level: int, current: str, is_package: bool) -> str:
    if level == 0:
        return module or ""
    base = current.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, module] if module else base)


def _is_private_module(module: str) -> bool:
    return any(part.startswith("_") and not part.startswith("__") for part in module.split("."))


def _in_contract(module: str, name: str | None) -> bool:
    allowed = CONTRACT.get(module)
    if allowed is None:
        return False
    if name is None or allowed == "*":
        return name is None or not name.startswith("_")
    return name in allowed


def _scope_nodes(tree: ast.Module, names: frozenset[str] | None) -> list[ast.stmt]:
    if names is None:
        return list(tree.body)
    picked: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            picked.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id in names for t in targets):
                picked.append(node)
    return picked


def _top_level_names(tree: ast.Module) -> dict[str, int]:
    defined: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined[node.name] = node.lineno
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined[target.id] = node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined[node.target.id] = node.lineno
    return defined


#: Members of the object model that are outside its contract (``tests/data/model_surface.json``)
#: and hand out or change raw XML. Reported only with ``members=True`` (``--members``): whether
#: ``.element`` joins the contract is an open decision, and until then moved code that walks
#: the XML needs it.
INTERNAL_MEMBERS = frozenset({"element", "mark_dirty", "remove_layout_caches", "remove_stale_layout_caches"})


def scan(root: Path, targets: tuple[Target, ...] = DEFAULT_TARGETS, *, members: bool = False) -> list[Finding]:
    """Every use, by the *targets* under *root*, of an engine name outside the contract."""

    moving = {_module_of(root / t.path, root) for t in targets if t.names is None}
    moving_names = {
        (_module_of(root / t.path, root), name) for t in targets if t.names is not None for name in t.names
    }
    findings: set[Finding] = set()
    for target in targets:
        path = root / target.path
        rel = target.path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        current = _module_of(path, root)
        is_package = path.name == "__init__.py"
        scope = _scope_nodes(tree, target.names)

        # Module-level imports bound to local names: needed for a partial target, whose
        # scope uses them without containing the import statement.
        bound: dict[str, tuple[str, str | None, int]] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                module = _absolute(node.module, node.level, current, is_package)
                for alias in node.names:
                    bound[alias.asname or alias.name] = (module, alias.name, node.lineno)

        def record_import(module: str, name: str | None, line: int) -> None:
            if not (module == ENGINE or module.startswith(ENGINE + ".")):
                return
            if module in moving or module == current or (module, name) in moving_names:
                return
            if name is not None and name.startswith("_"):
                kind = "private-name"
            elif _is_private_module(module):
                kind = "private-module"
            elif not _in_contract(module, name):
                kind = "non-contract"
            else:
                return
            findings.add(Finding(rel, line, kind, module, name or "<module>"))

        used_names: set[str] = set()
        for top in scope:
            for node in ast.walk(top):
                if isinstance(node, ast.ImportFrom):
                    module = _absolute(node.module, node.level, current, is_package)
                    for alias in node.names:
                        record_import(module, alias.name, node.lineno)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        record_import(alias.name, None, node.lineno)
                elif isinstance(node, ast.Name):
                    used_names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    attr = node.attr
                    if members and attr in INTERNAL_MEMBERS:
                        owner = node.value
                        if not (isinstance(owner, ast.Name) and owner.id in ("self", "cls")):
                            findings.add(Finding(rel, node.lineno, "internal-member", ast.unparse(owner)[:40], attr))
                    if attr.startswith("_") and not attr.startswith("__"):
                        owner = node.value
                        if isinstance(owner, ast.Name) and owner.id in ("self", "cls"):
                            continue
                        findings.add(Finding(rel, node.lineno, "private-member", ast.unparse(owner)[:40], attr))

        if target.names is not None:
            for name in sorted(used_names):
                if name in bound:
                    module, imported, line = bound[name]
                    record_import(module, imported, line)
            defined = _top_level_names(tree)
            for name in sorted(used_names - set(target.names)):
                if name in defined and not hasattr(builtins, name) and name not in bound:
                    findings.add(Finding(rel, defined[name], "left-behind", current, name))
        else:
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    module = _absolute(node.module, node.level, current, is_package)
                    for alias in node.names:
                        record_import(module, alias.name, node.lineno)
    return sorted(findings, key=lambda f: (f.file, f.kind, f.module, f.name, f.line))


def summary(findings: list[Finding]) -> list[str]:
    """One line per (file, kind, module, name) -- line numbers left out so the list is stable."""

    return sorted({f.key for f in findings})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "src")
    parser.add_argument("--target", action="append", default=[], help="a module path under --root (repeatable)")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    parser.add_argument("--report-only", action="store_true", help="exit 0 even when something is found")
    parser.add_argument("--members", action="store_true", help="also report model members outside the contract (.element ...)")
    args = parser.parse_args(argv)

    targets = tuple(Target(t) for t in args.target) or DEFAULT_TARGETS
    findings = scan(args.root, targets, members=args.members)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=1))
    else:
        for f in findings:
            print(f"{f.file}:{f.line}: {f.kind}: {f.module}.{f.name}")
        print(f"{len(findings)} use(s), {len(summary(findings))} distinct", file=sys.stderr)
    return 1 if findings and not args.report_only else 0


if __name__ == "__main__":
    raise SystemExit(main())
