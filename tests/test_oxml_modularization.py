"""Architecture and compatibility ratchets for the Feature 025 OXML split."""

from __future__ import annotations

import ast
import importlib
import io
import json
import re
import subprocess
import sys
import tokenize
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
# Owner size is counted in code lines (see _code_lines). Above the review line an
# owner is listed with why it stays one module; above the ceiling it must split.
OWNER_CODE_LINE_REVIEW = 1_300
OWNER_CODE_LINE_CEILING = 2_000
LARGE_OWNER_REASONS = {
    "header_part": (
        "HwpxOxmlHeader owns header.xml's refList: fonts, charPr, paraPr, tabs, numbering, "
        "border fills, styles, memo shapes, track changes and binData all allocate ids and keep "
        "itemCnt through the same helpers, so a split would share those privates across modules."
    ),
}
_NON_CODE_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
)

# The agent modules left in 5.0; their line-count ratchet went with them.
RATCHET_SOURCE_FILES = (
    "document.py",
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
        "ensure_paragraph_format": 11,
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
    # 78 -> 80: the Safe Write Contract adds public MutationReport and
    # PreservationDowngradeError to the package surface.
    # 80 -> 82: the document preview viewer surface is added
    # (render_document_viewer, DocumentViewer).
    # 82 -> 66 stable: the top-level surface is split into
    # stable/experimental/deprecated. __all__ keeps stable only (66); the
    # experimental (12) + deprecated (4) names stay importable via the module
    # __getattr__ (with DeprecationWarning). The legacy surface stays 82 — zero
    # names removed in that split.
    # 5.0: the application families left, so the stable surface is 34; the
    # HWP 5.0 error and warning then joined it beside HwpxError (36).
    # (4.x history: 66 -> 67 when the structured-exception
    # base HwpxError to the stable surface (see docs/stable-api.md 오류 계약 and
    # tests/test_stable_surface.py for the per-name contract).
    assert len(hwpx.__all__) == 36
    total_top_level = (
        set(hwpx.__all__)
        | set(hwpx._EXPERIMENTAL_EXPORTS)
        | set(hwpx._DEPRECATED_EXPORTS)
    )
    # 36 stable + 26 experimental + 0 deprecated. The deprecated layer emptied in
    # 5.0 because its 4.x notice said it would go in the next major; 5.2 added the
    # three equation-authoring names, 5.6 adds the edit-plan five and the
    # capabilities three to the experimental layer, and the page estimate adds
    # three more (estimate_pages, PageEstimate, EstimatedLine): 26 experimental.
    assert len(total_top_level) == 62
    # 110 -> 113: the paragraph tab-stop read model (TabStop, TabDefinition,
    # TabDefinitionList) fills the audit's gap #2 — hh:tabPr/tabItem were
    # frozen-template/unread; this is the "additive model extension" path
    # the completeness audit's route ①/③ anticipated for that gap.
    # 113 -> 120: the document-options/compatibility read models fill gap #13
    # and its R1 "genuinely code-blind" element — LayoutCompatibility,
    # CompatibleDocument (hh:layoutCompatibility/compatibleDocument) plus the
    # settings.xml first-ever read surface (ApplicationSettings, CaretPosition,
    # ConfigItem, ConfigItemSet, HwpxOxmlSettings) — settings.xml has no
    # vendored OWPML schema at all, inferred from the real corpus.
    # 120 -> 122: Caption/DrawText fill gap #3/#4 (hp:drawText/textMargin,
    # hp:caption) — shared live views reused by HwpxOxmlShape,
    # HwpxOxmlInlineObject, and HwpxOxmlTable rather than duplicated per host.
    # 122 -> 127: gap #15's part-hierarchy read models — version.xml
    # (HcfVersion), masterpage.xml (MasterPage), and history.xml (History,
    # HistoryEntry, DiffNode). version.xml/masterpage.xml are inferred
    # from the real corpus like settings.xml before them (and, like it, their
    # real roots/namespaces drifted from the vendored 2024-draft OWPML schema —
    # see version_part.py/master_page.py). history.xml has zero real examples
    # anywhere reachable (vendored corpus + ~250 accessible personal Hancom
    # documents), so History/HistoryEntry/DiffNode are schema-only and labeled
    # as such in history_part.py's module docstring.
    # 127 -> 128: ContainerMember (cycle 6.5 train 18) — doc.shapes.add_container
    # groups already-built rect/ellipse/polygon members (hp:container) into one
    # shape; the input-side constructor type callers use to place each member
    # at its own local (x, y) before the group's bounding box is derived.
    # 128 -> 132: ParagraphPropertyVersionBranch/ParagraphPropertyVersionSwitch +
    # their parse_* functions (cycle 6.6 train 21) — a typed read model for
    # hp:switch/case/default (DEV-018), the version-compat wrapper 236/237 real
    # files (99.6%) use to hold hh:paraPr's margin/lineSpacing one level deeper
    # than ParagraphProperty's direct-children loop was looking. Read-only by
    # design: the editing path already walked both branches correctly (DEV-018
    # confirmed by reading the code), so this closes a read-model gap only.
    # 132 -> 134: TabDefinitionVersionBranch/TabDefinitionVersionSwitch (cycle
    # 6.7 train 25, DEV-022) — the same hp:switch-blindness shape found in
    # hh:tabPr, but a different contract from DEV-018: hp:case's tabItem/@pos
    # is exactly half of hp:default's (34/34 pairs) and only hp:case declares
    # unit="HWPUNIT" -- an unwrapped real document settled which branch is the
    # real scale (hp:default matches it, hp:case does not), so tab_stops
    # prefers default, the opposite of DEV-018's case-preferred choice. Also
    # fixed the dedupe comparison in ensure_tab_definition (a real duplicate-
    # creation bug, not just a read gap) since it shared the same
    # direct-children-only blind spot.
    # 134 -> 136: PictureShadow/PictureGlow -- the input types add_picture's
    # shadow= and glow= take (hp:effects/hp:shadow, hp:glow), as ContainerMember
    # is add_container's.
    # 136 -> 137: PictureReflection -- add_picture's reflection= input type.
    assert len(oxml.__all__) == 137
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

    # Stable facades stay thin. The three agent seams that used to be bounded here
    # left in 5.0, so their caps left with them rather than lingering as dead
    # replacement god modules while compatibility remains frozen.
    assert line_count("oxml/_document_impl.py") <= 150
    assert line_count("oxml/document.py") <= 200
    assert line_count("document.py") <= 3_000


def _code_lines(source: str) -> int:
    """Lines that carry code: blank lines, comments and docstrings do not count."""
    docstrings: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in _NON_CODE_TOKENS:
            lines.update(line for line in range(token.start[0], token.end[0] + 1) if line not in docstrings)
    return len(lines)


def _owner_code_lines() -> dict[str, int]:
    return {name: _code_lines((SOURCE_ROOT / f"oxml/{name}.py").read_text(encoding="utf-8")) for name in OWNER_FILES}


def test_owner_files_stay_far_from_a_god_module() -> None:
    # Feature 025 split one 6,866-line file into owners; this keeps any of them from
    # growing back into one. It counts code, not comments or docstrings, so explaining
    # code never costs room. The old 1,600-physical-line cap sat at the size the owners
    # already had: seven of them stood within 75 lines of it and new code went to
    # whichever module had room left (objects.py, then dutmal_compose.py, then
    # drop_cap.py for paragraph.py's shapes). Split a module when it holds two jobs,
    # not when it reaches a number; the number below only stops a god module.
    owner_lines = _owner_code_lines()
    over = {name: lines for name, lines in owner_lines.items() if lines > OWNER_CODE_LINE_CEILING}
    assert not over, f"split these owners by responsibility: {over}"
    assert max(owner_lines.values()) / sum(owner_lines.values()) <= 0.25


def test_large_owner_files_say_why_they_stay_one_module() -> None:
    # Past the review line an owner needs a recorded reason to stay whole: decided once
    # per file, in review, instead of a wall each change has to route around. An entry
    # whose file has shrunk back goes, so the list says what is large now.
    large = {name for name, lines in _owner_code_lines().items() if lines > OWNER_CODE_LINE_REVIEW}
    assert large == set(LARGE_OWNER_REASONS), (
        f"add a reason for {sorted(large - set(LARGE_OWNER_REASONS))}, "
        f"drop the stale entries {sorted(set(LARGE_OWNER_REASONS) - large)}"
    )
    assert all(reason.strip() for reason in LARGE_OWNER_REASONS.values())


def test_code_line_count_skips_comments_docstrings_and_blank_lines() -> None:
    source = '"""Module."""\n\n# note\nclass A:\n    """Doc\n    more."""\n\n    x = (\n        1  # one\n    )\n'
    assert _code_lines(source) == 4


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
