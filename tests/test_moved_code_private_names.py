# SPDX-License-Identifier: Apache-2.0
"""What the code moving to python-hwpx-automation uses of the engine outside its contract.

``scripts/check_moved_private_names.py`` lists it. Before the move the list is pinned
here: the 7.0 promotions took the names that belong in the contract off it, and what is
left is the move stage's work (switch to the new public name, take a helper along, or a
public name another 7.0 package adds). The move stage makes the list empty; a new entry
means moving code started to lean on an engine internal again.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_moved_private_names.py"


def _checker():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("check_moved_private_names", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: What is left for the move stage (file:kind:module:name). See the 7.0 promotion report.
EXPECTED = (
    "hwpx/equation/mathml.py:non-contract:hwpx.equation.tokens:EQEDIT_MATHML_OPERATOR_COMMANDS",
    "hwpx/equation/render.py:non-contract:hwpx.equation.eqedit:EquationConversionError",
    "hwpx/equation/render.py:non-contract:hwpx.equation.eqedit:eqedit_to_latex",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:REFERENCE_CONSISTENCY_REPORT_VERSION",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:_ATTACHMENT_LINE_RE",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:_ATTACHMENT_REFERENCE_RE",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:_FIGURE_NUMBER_RE",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:_TABLE_NUMBER_RE",
    "hwpx/tools/doc_diff.py:left-behind:hwpx.tools.doc_diff:_paragraphs_from_source",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_HH",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_HP",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_ListLabels",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_NoteLabels",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_PARAGRAPH_BLOCKS",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_cell_paragraphs",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_emit_paragraph",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_header_xml",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_note_marks",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_section_blocks",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_section_xmls",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_table_cell_spans",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_table_cells_text",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_table_grid_text",
    "hwpx/tools/exporter.py:left-behind:hwpx.tools.exporter:_text_box_paragraphs",
    "hwpx/tools/exporter.py:private-name:hwpx.tools.toc_author:_OUTLINE_NAME_RE",
    "hwpx/tools/form_choices.py:private-name:hwpx.oxml._document_primitives:_clear_paragraph_layout_cache",
    "hwpx/tools/form_choices.py:private-name:hwpx.tools.table_navigation:_OCCURRENCE_RE",
    "hwpx/tools/form_choices.py:private-name:hwpx.tools.table_navigation:_collect_document_tables",
    "hwpx/tools/form_choices.py:private-name:hwpx.tools.table_navigation:_text_of_cell",
    "hwpx/tools/format_rules.py:private-name:hwpx.tools.archive_cli:_input_file_problem",
    "hwpx/tools/layout_preview.py:private-name:hwpx.oxml.section_format:_PAGE_PORTRAIT",
    "hwpx/tools/mail_merge.py:non-contract:hwpx.tools.package_validator:validate_editor_open_safety",
    "hwpx/tools/mail_merge.py:private-name:hwpx._document.ns.text:_paragraphs_everywhere",
    "hwpx/tools/markdown_export.py:non-contract:hwpx.equation.eqedit:EquationConversionError",
    "hwpx/tools/markdown_export.py:non-contract:hwpx.equation.eqedit:eqedit_to_latex",
    "hwpx/tools/markdown_export.py:private-member:doc:_package",
    "hwpx/tools/markdown_export.py:private-member:doc:_root",
    "hwpx/tools/markdown_export.py:private-name:hwpx.oxml._document_primitives:_text_element_content",
    "hwpx/tools/markdown_export.py:private-name:hwpx.tools.exporter:_ListLabels",
    "hwpx/tools/markdown_export.py:private-name:hwpx.tools.exporter:_header_xml",
    "hwpx/tools/markdown_export.py:private-name:hwpx.tools.exporter:_table_grid_text",
    "hwpx/tools/markdown_import.py:private-member:paragraph:_context_table_width",
    "hwpx/tools/markdown_import.py:private-module:hwpx._document.headings:resolve_heading_style",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:PathDirection",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:SearchDirection",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableCellReference",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableFillApplied",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableFillFailed",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableFillResult",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableFormSlot",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableFormSlotsResult",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableLabelCandidate",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableLabelMatch",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:TableLabelSearchResult",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_HP",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_HWPUNIT_PER_MM",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_IndexedTable",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_OCCURRENCE_RE",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_WHITESPACE_RE",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_cell_text",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_collect_document_tables",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_move",
    "hwpx/tools/table_navigation.py:left-behind:hwpx.tools.table_navigation:_text_of_cell",
)


def test_moving_code_uses_only_these_engine_internals() -> None:
    checker = _checker()
    found = checker.summary(checker.scan(ROOT / "src"))
    assert sorted(found) == sorted(EXPECTED)


def test_promoted_names_are_no_longer_reported() -> None:
    checker = _checker()
    names = {key.rsplit(":", 2)[-2] + "." + key.rsplit(":", 1)[-1] for key in checker.summary(checker.scan(ROOT / "src"))}
    for promoted in (
        "hwpx.opc.security.guard_zip_file",
        "hwpx.opc.security.read_member",
        "hwpx.opc.security.parse_xml_stdlib",
        "hwpx.opc.security.HwpxSecurityError",
        "hwpx.opc.security.MAX_ZIP_MIMETYPE_BYTES",
        "hwpx.oxml.hyperlink_form.hyperlink_target",
        "hwpx.oxml.namespaces.tag_local_name",
        "hwpx.oxml.namespaces.HP",
        "hwpx.oxml.table_sizes.cell_margins_of",
        "hwpx.oxml.paragraph_heading.paragraph_heading",
        "hwpx.form_fit.measure.estimate_text_width",
        "hwpx.form_fit.measure.char_advance",
        "hwpx.form_fit.measure.indented_widths",
        "hwpx.form_fit.measure.text_style_from_refs",
        "hwpx.form_fit.FitEngine",
        "hwpx.form_fit.resolve_slot_metrics",
    ):
        assert promoted not in names, promoted


def test_the_checker_finds_each_kind_of_use(tmp_path: Path) -> None:
    checker = _checker()
    package = tmp_path / "hwpx" / "tools"
    package.mkdir(parents=True)
    (tmp_path / "hwpx" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "moving.py").write_text(
        "from ..oxml._document_primitives import _clear_paragraph_layout_cache\n"
        "from ..oxml.hyperlink_form import hyperlink_target\n"
        "from ..oxml.hyperlink_form import hyperlink_parameters\n"
        "from .._document.headings import resolve_heading_style\n"
        "from ..model import Paragraph\n"
        "def f(doc, p):\n"
        "    return doc._root, p.element\n",
        encoding="utf-8",
    )
    target = checker.Target("hwpx/tools/moving.py")
    kinds = {(f.kind, f.name) for f in checker.scan(tmp_path, (target,))}
    assert kinds == {
        ("private-name", "_clear_paragraph_layout_cache"),
        ("non-contract", "hyperlink_parameters"),
        ("private-module", "resolve_heading_style"),
        ("private-member", "_root"),
    }
    with_members = {(f.kind, f.name) for f in checker.scan(tmp_path, (target,), members=True)}
    assert ("internal-member", "element") in with_members


def test_the_checker_runs_on_its_own() -> None:
    # -I: no site packages from the working tree, no PYTHONPATH -- the receiving package runs it so.
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--root", str(ROOT / "src"), "--json", "--report-only"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    rows = json.loads(result.stdout)
    assert {f"{r['file']}:{r['kind']}:{r['module']}:{r['name']}" for r in rows} == set(EXPECTED)
    failing = subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(ROOT / "src")], capture_output=True)
    assert failing.returncode == 1
