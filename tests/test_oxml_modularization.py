"""Architecture and compatibility ratchets for the Feature 025 OXML split."""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import hwpx
import hwpx.oxml as oxml
import hwpx.oxml.document as document_facade
from hwpx.oxml import _document_primitives


DOCUMENT_EXPORTS = (
    "Any",
    "Bullet",
    "Callable",
    "DocumentNumbering",
    "ET",
    "GenericElement",
    "HC",
    "HC_NS",
    "HH",
    "HH_NS",
    "HP",
    "HP_NS",
    "HS",
    "HS_NS",
    "HWPML_COMPAT_ROOT_NAMESPACES",
    "Header",
    "HwpxOxmlDocument",
    "HwpxOxmlHeader",
    "HwpxOxmlHistory",
    "HwpxOxmlInlineObject",
    "HwpxOxmlMasterPage",
    "HwpxOxmlMemo",
    "HwpxOxmlMemoGroup",
    "HwpxOxmlNote",
    "HwpxOxmlParagraph",
    "HwpxOxmlRun",
    "HwpxOxmlSection",
    "HwpxOxmlSectionHeaderFooter",
    "HwpxOxmlSectionProperties",
    "HwpxOxmlShape",
    "HwpxOxmlTable",
    "HwpxOxmlTableCell",
    "HwpxOxmlTableRow",
    "HwpxOxmlVersion",
    "HwpxTableGridPosition",
    "Iterable",
    "Iterator",
    "LET",
    "Mapping",
    "MemoProperties",
    "MemoShape",
    "Optional",
    "PageMargins",
    "PageSize",
    "ParagraphProperty",
    "RunStyle",
    "SectionStartNumbering",
    "Sequence",
    "Style",
    "T",
    "TYPE_CHECKING",
    "TrackChange",
    "TrackChangeAuthor",
    "TypeVar",
    "annotations",
    "body",
    "dataclass",
    "deepcopy",
    "logger",
    "logging",
    "memo_shape_from_attributes",
    "parse_border_fills",
    "parse_bullets",
    "parse_header_element",
    "parse_int",
    "parse_paragraph_properties",
    "parse_styles",
    "parse_track_change_authors",
    "parse_track_change_config",
    "parse_track_changes",
    "register_owpml_namespaces",
    "tag_local_name",
    "tag_namespace",
    "track_change_author_to_xml",
    "track_change_to_xml",
    "uuid4",
)

OWNER_MODULES = {
    "DocumentNumbering": "hwpx.oxml.numbering",
    "HwpxOxmlDocument": "hwpx.oxml.document_parts",
    "HwpxOxmlHeader": "hwpx.oxml.header_part",
    "HwpxOxmlHistory": "hwpx.oxml.simple_parts",
    "HwpxOxmlInlineObject": "hwpx.oxml.objects",
    "HwpxOxmlMasterPage": "hwpx.oxml.simple_parts",
    "HwpxOxmlMemo": "hwpx.oxml.memo",
    "HwpxOxmlMemoGroup": "hwpx.oxml.memo",
    "HwpxOxmlNote": "hwpx.oxml.memo",
    "HwpxOxmlParagraph": "hwpx.oxml.paragraph",
    "HwpxOxmlRun": "hwpx.oxml.run",
    "HwpxOxmlSection": "hwpx.oxml.section",
    "HwpxOxmlSectionHeaderFooter": "hwpx.oxml.section_story",
    "HwpxOxmlSectionProperties": "hwpx.oxml.section_format",
    "HwpxOxmlShape": "hwpx.oxml.objects",
    "HwpxOxmlTable": "hwpx.oxml.table",
    "HwpxOxmlTableCell": "hwpx.oxml.table",
    "HwpxOxmlTableRow": "hwpx.oxml.table",
    "HwpxOxmlVersion": "hwpx.oxml.simple_parts",
    "HwpxTableGridPosition": "hwpx.oxml.table",
    "PageMargins": "hwpx.oxml.section_format",
    "PageSize": "hwpx.oxml.section_format",
    "RunStyle": "hwpx.oxml.run",
    "SectionStartNumbering": "hwpx.oxml.numbering",
}

OWNER_FILES = frozenset(module.rsplit(".", 1)[-1] for module in OWNER_MODULES.values()) | {
    "_document_primitives",
    "document_parts",
}

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "hwpx"
RATCHET_SOURCE_FILES = (
    "document.py",
    "agent/commands.py",
    "agent/document.py",
    "agent/story.py",
    "oxml/_document_impl.py",
    "oxml/_document_primitives.py",
    "oxml/document.py",
    "oxml/document_parts.py",
    "oxml/header_part.py",
    "oxml/memo.py",
    "oxml/numbering.py",
    "oxml/objects.py",
    "oxml/paragraph.py",
    "oxml/run.py",
    "oxml/section.py",
    "oxml/section_format.py",
    "oxml/section_story.py",
    "oxml/simple_parts.py",
    "oxml/table.py",
)

# Residual C901 debt is enumerated per function. A diagnostic may disappear or
# decrease, but no new function or higher score can enter the touched runtime
# seams without an explicit review and baseline update.
C901_LIMITS = {
    "document.py": {
        "_iter_form_field_matches": 13,
        "remove_image": 14,
        "set_paragraph_format": 17,
    },
    "agent/commands.py": {
        "_add": 16,
        "_apply_set": 34,
        "_move": 15,
        "_preflight": 21,
        "_refresh_copy_identities": 18,
        "_remove": 12,
        "apply_document_commands": 29,
    },
    "agent/document.py": {"_project_paragraph": 16},
    "oxml/_document_primitives.py": {
        "_border_fill_is_basic_solid_line": 18,
        "_border_fill_matches": 15,
        "_remove_stale_paragraph_layout_cache": 11,
    },
    "oxml/document_parts.py": {
        "ensure_run_style": 37,
        "from_package": 15,
        "modifier": 21,
        "serialize": 14,
    },
    "oxml/header_part.py": {
        "ensure_char_property": 12,
        "ensure_shading_border_fill": 13,
    },
    "oxml/paragraph.py": {"add_tracked_delete": 12},
    "oxml/run.py": {"replace_text": 34},
    "oxml/section.py": {"add_paragraph": 11},
    "oxml/section_story.py": {"_update_apply_reference": 14},
    "oxml/table.py": {
        "_build_cell_grid": 13,
        "merge_cells": 18,
        "split_merged_cell": 26,
    },
}

_C901_MESSAGE = re.compile(r"`(?P<name>[^`]+)` is too complex \((?P<score>\d+) > 10\)")


def _runtime_owner_edges(source_root: Path) -> dict[str, set[str]]:
    edges = {name: set() for name in OWNER_FILES}
    for name in OWNER_FILES:
        tree = ast.parse((source_root / f"{name}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.level != 1 or not node.module:
                continue
            target = node.module.split(".", 1)[0]
            if target in OWNER_FILES:
                edges[name].add(target)
    return edges


def _assert_acyclic(edges: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise AssertionError(f"OXML owner import cycle reaches {name}: {edges}")
        if name in visited:
            return
        visiting.add(name)
        for child in edges[name]:
            visit(child)
        visiting.remove(name)
        visited.add(name)

    for name in edges:
        visit(name)


def test_frozen_facade_exports_remain_exact() -> None:
    # 78 -> 80: S-089 P1 adds the Safe Write Contract's public MutationReport and
    # PreservationDowngradeError to the package surface.
    assert len(hwpx.__all__) == 80
    assert len(oxml.__all__) == 110
    assert tuple(document_facade.__all__) == DOCUMENT_EXPORTS


def test_facades_and_owner_modules_share_exact_class_objects() -> None:
    for name, module_name in OWNER_MODULES.items():
        owner: ModuleType = importlib.import_module(module_name)
        expected = getattr(owner, name)
        assert expected.__module__ == module_name
        assert getattr(oxml, name) is expected
        assert getattr(document_facade, name) is expected


def test_document_uuid4_monkeypatch_reaches_identity_owner(monkeypatch) -> None:
    class _FixedUuid:
        int = 0x12345678

    monkeypatch.setattr(document_facade, "uuid4", lambda: _FixedUuid())

    assert _document_primitives.uuid4().int == _FixedUuid.int
    assert _document_primitives._paragraph_id() == str(_FixedUuid.int & 0x7FFFFFFF)


def test_document_uuid4_delete_reaches_identity_owner() -> None:
    original = document_facade.uuid4
    try:
        del document_facade.uuid4
        assert not hasattr(document_facade, "uuid4")
        assert not hasattr(_document_primitives, "uuid4")
    finally:
        document_facade.uuid4 = original


def test_owner_modules_have_no_facade_back_reference_or_import_cycle() -> None:
    source_root = Path(oxml.__file__).parent
    edges = _runtime_owner_edges(source_root)

    assert all("_document_impl" not in targets for targets in edges.values())
    for name in OWNER_FILES:
        source = (source_root / f"{name}.py").read_text(encoding="utf-8")
        assert "_document_impl" not in source
    _assert_acyclic(edges)


def test_touched_runtime_file_sizes_stay_bounded() -> None:
    def line_count(relative: str) -> int:
        return len((SOURCE_ROOT / relative).read_text(encoding="utf-8").splitlines())

    # Stable facades stay thin, and the three agent seams may not become new
    # replacement god modules while compatibility remains frozen.
    assert line_count("oxml/_document_impl.py") <= 150
    assert line_count("oxml/document.py") <= 200
    assert line_count("document.py") <= 3_000
    assert line_count("agent/commands.py") <= 1_600
    assert line_count("agent/document.py") <= 850
    assert line_count("agent/story.py") <= 250

    owner_lines = {
        name: line_count(f"oxml/{name}.py")
        for name in OWNER_FILES
    }
    largest_owner_lines = max(owner_lines.values())
    assert largest_owner_lines <= 1_600
    assert largest_owner_lines / sum(owner_lines.values()) <= 0.25


def test_touched_runtime_c901_debt_only_ratchets_down() -> None:
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--no-cache",
        "--select",
        "C901",
        "--output-format",
        "json",
        *[str(SOURCE_ROOT / relative) for relative in RATCHET_SOURCE_FILES],
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode in {0, 1}, result.stderr or result.stdout

    observed: dict[str, dict[str, int]] = {}
    for diagnostic in json.loads(result.stdout or "[]"):
        assert diagnostic["code"] == "C901", diagnostic
        match = _C901_MESSAGE.fullmatch(diagnostic["message"])
        assert match is not None, diagnostic
        relative = (
            Path(diagnostic["filename"])
            .resolve()
            .relative_to(SOURCE_ROOT.resolve())
            .as_posix()
        )
        name = match.group("name")
        score = int(match.group("score"))
        assert relative in C901_LIMITS, (relative, name, score)
        assert name in C901_LIMITS[relative], (relative, name, score)
        assert score <= C901_LIMITS[relative][name], (relative, name, score)
        assert name not in observed.setdefault(relative, {}), (relative, name)
        observed[relative][name] = score
