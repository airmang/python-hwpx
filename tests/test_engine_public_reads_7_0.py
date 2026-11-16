# SPDX-License-Identifier: Apache-2.0
"""7.0: engine reads promoted to the contract for the code that moves to python-hwpx-automation.

Each name exists where docs/stable-api.md says, and gives the right value on documents
Hancom saved (tests/fixtures/hancom_saved).
"""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError, HwpxLookupError, HwpxValueError

SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _open(name: str) -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return HwpxDocument.open(SAVED / name)


def _reopened(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(document.to_bytes()))


# --------------------------------------------------------------------------- #
# hp:t text


def test_text_element_content_reads_hp_t_as_run_text_does() -> None:
    from hwpx.oxml.run import text_element_content

    document = _open("list_number_level3.hwpx")
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            texts = [text_element_content(t) for t in run.element.findall(f"{_HP}t")]
            assert "".join(texts) == run.text
    assert document.paragraphs[1].runs[0].text.endswith("목록 항목 1")


def test_text_element_content_writes_inline_tabs_as_the_tab_token() -> None:
    from xml.etree import ElementTree as ET

    from hwpx.oxml.run import text_element_content

    element = ET.fromstring(f'<t xmlns="{_HP[1:-1]}">성<fwSpace/>명<tab/>홍길동<lineBreak/>끝</t>')
    assert text_element_content(element) == "성　명\t홍길동\n끝"
    assert text_element_content(element, tab_token=" | ") == "성　명 | 홍길동\n끝"


# --------------------------------------------------------------------------- #
# Paragraph.clear_layout_cache / available_width


def test_clear_layout_cache_drops_the_cell_paragraph_and_its_holders_caches() -> None:
    document = _open("line_cache_table_cells.hwpx")
    table = document.tables[0]
    holder = document.paragraphs[[i for i, p in enumerate(document.paragraphs) if p.tables][0]]
    cell_paragraph = table.rows[0].cells[0].paragraphs[0]
    assert cell_paragraph.element.find(f"{_HP}linesegarray") is not None
    assert holder.element.find(f"{_HP}linesegarray") is not None
    before = zipfile.ZipFile(io.BytesIO(document.to_bytes()))

    assert cell_paragraph.clear_layout_cache() == 2
    assert cell_paragraph.element.find(f"{_HP}linesegarray") is None
    assert holder.element.find(f"{_HP}linesegarray") is None
    assert cell_paragraph.clear_layout_cache() == 0

    saved = document.to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(saved))
    assert reopened.validate().ok
    after = zipfile.ZipFile(io.BytesIO(saved))
    for name in before.namelist():
        if not name.startswith("Contents/section"):
            assert after.read(name) == before.read(name), name


def test_available_width_is_the_cell_or_text_width() -> None:
    document = _open("table_structure_merged_rows_base.hwpx")
    properties = document.sections[0].properties
    page, margins = properties.page_size, properties.page_margins
    body = document.paragraphs[0]
    assert body.available_width == page.drawn_width - margins.left - margins.right - margins.gutter == 42520

    cell = document.tables[0].rows[0].cells[0]
    inner = cell.margins
    assert cell.paragraphs[0].available_width == cell.width - inner.left - inner.right == 8980


# --------------------------------------------------------------------------- #
# Outline levels: paragraph shapes, style names, doc.styles


def test_heading_outline_level_reads_switched_levels_too() -> None:
    from hwpx.oxml.paragraph_heading import heading_outline_level

    document = _open("pages_outline_labels_paragraph_end_shape.hwpx")
    header = document.oxml.headers[0].element
    levels = {para_pr.get("id"): heading_outline_level(para_pr) for para_pr in header.iter(f"{_HH}paraPr")}
    # 개요 1..10 styles' shapes, 8 to 10 written in an hp:switch as Hancom does
    for level in range(1, 11):
        style = document.styles.outline_style(level)
        assert style is not None
        assert levels[str(style.para_pr_id_ref)] == level
    assert levels["0"] is None


def test_outline_style_level_reads_outline_style_names() -> None:
    from hwpx.oxml.paragraph_heading import outline_style_level

    assert outline_style_level("개요 3") == 3
    assert outline_style_level(" Outline 10 ") == 10
    assert outline_style_level("개요3") == 3
    assert outline_style_level("개요 3 강조") is None
    assert outline_style_level("바탕글") is None
    assert outline_style_level(None) is None


@pytest.mark.parametrize("source", ["new", "saved"])
def test_styles_outline_style_and_level_are_inverse(source: str) -> None:
    document = HwpxDocument.new() if source == "new" else _open("pages_outline_labels_paragraph_end_shape.hwpx")
    for level in range(1, 11):
        style = document.styles.outline_style(level)
        assert style is not None and style.name == f"개요 {level}"
        assert document.styles.outline_level(style) == level
        assert document.styles.outline_level(style.name) == level
    assert document.styles.outline_level("바탕글") is None
    assert document.styles.outline_level(0) is None


def test_styles_outline_style_rejects_levels_outside_the_outline() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        document.styles.outline_style(11)
    assert excinfo.value.code == "heading-level-out-of-range"
    with pytest.raises(HwpxLookupError) as missing:
        document.styles.outline_level("없는 스타일")
    assert missing.value.code == "style-not-found"


def test_styles_outline_style_is_none_without_outline_styles() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for style in header.element.iter(f"{_HH}style"):
        style.set("name", f"s{style.get('id')}")
        style.set("engName", f"s{style.get('id')}")
    for heading in list(header.element.iter(f"{_HH}heading")):
        heading.set("type", "NONE")
    header.mark_dirty()
    document = _reopened(document)
    assert document.styles.outline_style(1) is None
    assert all(document.styles.outline_level(style_id) is None for style_id in document.styles)


# --------------------------------------------------------------------------- #
# List labels, note numbers, number formats


def test_list_labels_are_the_labels_hancom_draws() -> None:
    from hwpx.tools.exporter import ListLabels, export_text

    document = _open("list_number_level3.hwpx")
    labels = ListLabels(document)
    assert [labels.label(i) for i in range(len(document.paragraphs))] == ["", "1)", "2)", "3)"]
    assert [labels.kind(i) for i in range(len(document.paragraphs))] == [None, "NUMBER", "NUMBER", "NUMBER"]
    # an index, the paragraph and its element are the same paragraph
    paragraph = document.paragraphs[2]
    assert labels.label(paragraph) == labels.label(paragraph.element) == labels.label(-2) == "2)"
    # export_text(list_labels=True) writes the same labels
    lines = export_text(document, list_labels=True).split("\n")
    assert lines == [f"{labels.label(i)} {p.text}".strip() for i, p in enumerate(document.paragraphs) if p.text]


def test_list_labels_count_outline_and_bullet_paragraphs() -> None:
    from hwpx.tools.exporter import ListLabels

    outline = ListLabels(_open("pages_outline_labels_paragraph_end_shape.hwpx"))
    assert [outline.label(i) for i in range(1, 8)] == ["(가)", "2)", "(가)", "3)", "(1)", "(가)", "①"]
    assert outline.kind(1) == "OUTLINE"
    bullets = ListLabels(_open("pages_bullet_and_number_labels.hwpx"))
    assert bullets.label(2) == "●" and bullets.kind(2) == "BULLET"
    assert bullets.label(0) == "" and bullets.kind(0) is None


def test_list_labels_reject_what_is_not_a_paragraph_of_the_document() -> None:
    from hwpx.tools.exporter import ListLabels

    document = _open("list_number_level3.hwpx")
    labels = ListLabels(document)
    with pytest.raises(HwpxError) as out_of_range:
        labels.label(99)
    assert out_of_range.value.code == "paragraph-not-found"
    other = HwpxDocument.new().paragraphs[0]
    with pytest.raises(HwpxError) as foreign:
        labels.label(other)
    assert foreign.value.code == "paragraph-not-in-document"


def test_list_labels_match_the_text_export_in_cells_and_text_boxes() -> None:
    from hwpx.tools import exporter

    for name in ("pages_table_cell_picture_in_a_bulleted_paragraph.hwpx", "pages_bullet_and_number_labels.hwpx"):
        document = _open(name)
        asked: dict[object, str] = {}
        original = exporter._ListLabels.label

        def spy(self, p, _original=original):  # type: ignore[no-untyped-def]
            asked.setdefault(p, _original(self, p))
            return asked[p]

        exporter._ListLabels.label = spy  # type: ignore[method-assign]
        try:
            exporter.export_text(document, list_labels=True)
        finally:
            exporter._ListLabels.label = original  # type: ignore[method-assign]
        labels = exporter.ListLabels(document)
        assert asked and all(labels.label(p) == value for p, value in asked.items())


def test_note_labels_number_foot_notes_in_document_order() -> None:
    from hwpx.tools.exporter import NoteLabels

    document = _open("pages_footnotes_6.hwpx")
    notes = NoteLabels(document)
    footnotes = [note for paragraph in document.paragraphs for note in paragraph.footnotes]
    assert [notes.label(note) for note in footnotes] == ["1)", "2)", "3)", "4)", "5)", "6)"]
    assert notes.label(footnotes[0].element) == "1)"
    assert notes.label(document.paragraphs[0].element) == ""


def test_number_text_writes_hancom_number_formats() -> None:
    from hwpx.tools.exporter import NUMBER_TEXT_FORMATS, number_text

    assert number_text(3, "HANGUL_SYLLABLE") == "다"
    assert number_text(3, "HANGUL_JAMO") == "ㄷ"
    assert number_text(4, "ROMAN_CAPITAL") == "IV"
    assert number_text(9, "ROMAN_SMALL") == "ix"
    assert number_text(2, "CIRCLED_DIGIT") == "②"
    assert number_text(27, "LATIN_SMALL") == "a"
    assert number_text(12) == "12"
    assert number_text(0, "HANGUL_SYLLABLE") == "0"
    assert number_text(1, "DECAGON_CIRCLE") is None
    assert {"DIGIT", "HANGUL_SYLLABLE", "CIRCLED_DIGIT", "ROMAN_CAPITAL"} <= NUMBER_TEXT_FORMATS


def test_form_fit_reads_number_formats_through_the_public_name() -> None:
    source = (Path(__file__).parents[1] / "src" / "hwpx" / "form_fit" / "measure.py").read_text(encoding="utf-8")
    assert "_NUMBER_FORMATS, _number_text\n" not in source
    assert "number_text as _number_text" in source


# --------------------------------------------------------------------------- #
# Table grid text


def test_table_grid_text_lays_cells_on_the_grid() -> None:
    from hwpx.tools.exporter import table_grid_text

    document = _open("table_structure_merged_rows_base.hwpx")
    table = document.tables[0]
    grid = table_grid_text(table)
    assert grid == tuple(tuple(cell.text for cell in row.cells) for row in table.rows)
    assert grid[0] == ("00", "01", "02")
    assert table_grid_text(table.element) == grid


def test_table_grid_text_leaves_merged_positions_empty() -> None:
    from hwpx.tools.exporter import table_grid_text

    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"{row}{col}"
    table.merge_cells(0, 0, 1, 1)
    grid = table_grid_text(_reopened(document).tables[0])
    assert grid == (("00\n01\n10\n11", "", "02"), ("", "", "12"), ("20", "21", "22"))


# --------------------------------------------------------------------------- #
# Constants, CLI check, input hardening, measurement


def test_page_orientation_constants_are_what_page_size_reports() -> None:
    from hwpx.oxml.section_format import PAGE_LANDSCAPE, PAGE_PORTRAIT

    assert (PAGE_PORTRAIT, PAGE_LANDSCAPE) == ("WIDELY", "NARROWLY")
    portrait = _open("table_structure_merged_rows_base.hwpx").sections[0].properties.page_size
    assert portrait.orientation == PAGE_PORTRAIT
    document = HwpxDocument.new()
    document.page.setup(orientation="LANDSCAPE")
    assert _reopened(document).sections[0].properties.page_size.orientation == PAGE_LANDSCAPE


def test_input_file_problem_names_what_a_tool_cannot_read(tmp_path: Path) -> None:
    from hwpx.tools.archive_cli import _input_file_problem, input_file_problem

    assert _input_file_problem is input_file_problem
    assert input_file_problem(tmp_path / "none.hwpx", tool="t") == f"file not found: {tmp_path / 'none.hwpx'}"
    assert "is a folder" in (input_file_problem(tmp_path, tool="t") or "")
    hwp = tmp_path / "old.hwp"
    hwp.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 32)
    assert "HWP 5.0" in (input_file_problem(hwp, tool="hwpx-x") or "")
    assert input_file_problem(hwp, tool="hwpx-x", accepts_hwp=True) is None
    assert input_file_problem(SAVED / "list_number_level3.hwpx", tool="t") is None


def test_input_hardening_contract_names_exist() -> None:
    from hwpx.opc import security

    for name in security.__all__:
        assert hasattr(security, name), name
    assert issubclass(security.HwpxSecurityError, ValueError)
    with zipfile.ZipFile(SAVED / "list_number_level3.hwpx") as archive:
        security.guard_zip_file(archive)
        root = security.parse_xml_stdlib(security.read_member(archive, "Contents/header.xml"), part_name="header")
    assert root.tag.endswith("head")
    assert "sharing_archive_reads" not in security.__all__


def test_measurement_names_are_the_form_fit_package_names() -> None:
    import importlib

    import hwpx.form_fit as form_fit

    # the package's measure() function shadows the module name as an attribute
    measure = importlib.import_module("hwpx.form_fit.measure")

    for name in ("char_advance", "estimate_text_width", "indented_widths", "text_style_from_refs",
                 "resolve_slot_metrics", "TextStyle", "SlotMetrics", "FitEngine"):
        assert name in form_fit.__all__, name
    assert form_fit.char_advance is measure.char_advance
    assert form_fit.text_style_from_refs is measure.text_style_from_refs
    width = form_fit.estimate_text_width("가나", 10.0)
    assert width == 2 * form_fit.char_advance("가", 10.0) > 0
    first, other = form_fit.indented_widths(10000.0, form_fit.TextStyle())
    assert first == other == 10000.0


def test_element_readers_are_in_the_contract() -> None:
    from hwpx.oxml.hyperlink_form import hyperlink_target
    from hwpx.oxml.namespaces import HP, tag_local_name
    from hwpx.oxml.table_sizes import cell_margins_of

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    paragraph.add_hyperlink("https://example.com", "링크")
    field = next(paragraph.element.iter(f"{HP}fieldBegin"))
    assert hyperlink_target(field) == paragraph.hyperlinks[0].url == "https://example.com"
    assert tag_local_name(f"{HP}fieldBegin") == "fieldBegin"
    table = document.add_table(1, 1)
    cell = table.cell(0, 0)
    assert cell_margins_of(cell.element, table.element) == cell.margins
