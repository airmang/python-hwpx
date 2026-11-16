# SPDX-License-Identifier: Apache-2.0
"""Read pairs for section and page settings, and ``section="all"`` on ``doc.page`` setters.

Up to 6.x ``doc.page`` could set columns, page-number controls, new numbers,
hide-on-this-page controls, start numbers, note shapes and the page border but
could not read them back (or only through ``hwpx.oxml`` dataclasses outside the
contract). These reads return ``hwpx.objects`` value types.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError, HwpxValueError
from hwpx.objects import (
    AutoNumber,
    BeginNumbers,
    ColumnDefinition,
    DocumentOptions,
    NoteShapeInfo,
    NumberRestart,
    PageBorder,
    PageHiding,
    PageNumberControl,
    StartNumbers,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HANCOM_PAGE_NUMBERS = FIXTURES / "hancom_saved" / "pages_controls_after_a_wide_table.hwpx"
GONGMUN = FIXTURES / "m3_gongmun_gold" / "mfds_admin_notice.hwpx"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    return reopened


def test_columns_read_back_what_set_columns_wrote_including_a_mid_section_change() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫")
    second = doc.add_paragraph("둘")
    doc.page.set_columns(2, same_gap=1134, separator_type="SOLID", separator_width="0.4 mm")
    doc.page.set_columns(3, paragraph=second, same_size=False, column_widths=[(1, 0), (2, 1), (1, 0)])

    first, changed = _reopen(doc).page.columns()
    assert isinstance(first, ColumnDefinition)
    assert (first.count, first.type, first.layout, first.same_size, first.gap) == (2, "NEWSPAPER", "LEFT", True, 1134)
    assert first.separator is not None and first.separator.type == "SOLID" and first.separator.width_mm == 0.4
    assert first.widths[0][1] == 1134 and first.widths[1][1] == 0
    assert first.paragraph is not None and first.paragraph.text == "첫"

    assert changed.count == 3 and changed.same_size is False and changed.separator is None
    widths = [width for width, _gap in changed.widths]
    assert widths[1] == pytest.approx(2 * widths[0], abs=2)
    assert changed.paragraph is not None and changed.paragraph.text == "둘"


def test_columns_widths_round_trip_through_set_columns() -> None:
    doc = HwpxDocument.new()
    doc.page.set_columns(2, same_size=False, column_widths=[(20000, 1000), (21520, 0)])
    (read,) = doc.page.columns()
    other = HwpxDocument.new()
    other.page.set_columns(2, same_size=False, column_widths=list(read.widths))
    assert other.page.columns()[0].widths == read.widths


def test_a_new_document_reports_one_single_column() -> None:
    (only,) = HwpxDocument.new().page.columns()
    assert only.count == 1 and only.widths[0][0] > 40000


def test_number_restarts_page_hidings_and_auto_numbers() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("하나")
    target = doc.add_paragraph("둘")
    doc.page.restart_page_number(target, number=5)
    doc.page.hide_page_elements(target, header=True, page_num=True)
    doc.page.set_page_number(format="page/total")
    reopened = _reopen(doc)

    assert reopened.page.number_restarts() == (
        NumberRestart(kind="PAGE", number=5, paragraph=reopened.page.number_restarts()[0].paragraph),
    )
    (restart,) = reopened.page.number_restarts()
    assert restart.paragraph is not None and restart.paragraph.text == "둘"
    (hiding,) = reopened.page.page_hidings()
    assert isinstance(hiding, PageHiding)
    assert (hiding.header, hiding.page_num, hiding.footer) == (True, True, False)
    kinds = [number.kind for number in reopened.page.auto_numbers()]
    assert kinds == ["PAGE", "TOTAL_PAGE"]  # the footer's numbers, once (not its second copy)
    assert all(isinstance(number, AutoNumber) for number in reopened.page.auto_numbers())


def test_page_number_controls_of_a_hancom_saved_file() -> None:
    doc = HwpxDocument.open(HANCOM_PAGE_NUMBERS)
    controls = doc.page.page_number_controls(section=0)
    assert controls and all(isinstance(control, PageNumberControl) for control in controls)
    assert controls[0].to_dict() == {"position": "BOTTOM_CENTER", "formatType": "DIGIT", "sideChar": "-"}


def test_hancom_gold_page_hidings_note_shape_and_page_borders() -> None:
    doc = HwpxDocument.open(GONGMUN)
    hidings = doc.page.page_hidings(section=0)
    assert hidings and all(hiding.page_num for hiding in hidings)
    shape = doc.page.footnote_shape(section=0)
    assert isinstance(shape, NoteShapeInfo)
    assert shape.separator_length == -1 and shape.between_notes == 284 and shape.numbering == "CONTINUOUS"
    both, even = doc.page.page_border(section=0), doc.page.page_border(page_type="EVEN", section=0)
    assert isinstance(both, PageBorder) and both.page_type == "BOTH" and both.offset_left == 1417
    assert even is not None and even.page_type == "EVEN"


def test_footnote_and_endnote_shape_write_and_read() -> None:
    doc = HwpxDocument.new()
    doc.page.set_footnote_shape(
        number_format="CIRCLED_DIGIT", suffix="", superscript=True, numbering="ON_SECTION", start=3,
        placement="MERGED_COLUMN", separator_type="DASH", separator_width_mm=0.4, separator_color="#FF0000",
        separator_length=12000, between_notes=400,
    )
    doc.page.set_endnote_shape(number_format="ROMAN_SMALL", placement="END_OF_SECTION")
    reopened = _reopen(doc)
    shape = reopened.page.footnote_shape()
    assert (shape.number_format, shape.suffix, shape.superscript) == ("CIRCLED_DIGIT", "", True)
    assert (shape.numbering, shape.start, shape.placement) == ("ON_SECTION", 3, "MERGED_COLUMN")
    assert shape.separator.to_dict() == {"type": "DASH", "widthMm": 0.4, "color": "#FF0000"}
    assert (shape.separator_length, shape.between_notes) == (12000, 400)
    endnote = reopened.page.endnote_shape()
    assert (endnote.number_format, endnote.placement) == ("ROMAN_SMALL", "END_OF_SECTION")


@pytest.mark.parametrize(
    "kwargs",
    [{"numbering": "ON_PAGE"}, {"placement": "EACH_COLUMN"}, {"start": 0}, {"between_notes": -1}],
)
def test_a_refused_endnote_shape_changes_nothing(kwargs: dict[str, object]) -> None:
    doc = HwpxDocument.new()
    before = doc.page.endnote_shape()
    with pytest.raises(HwpxValueError) as caught:
        doc.page.set_endnote_shape(number_format="ROMAN_SMALL", **kwargs)  # type: ignore[arg-type]
    assert caught.value.code == "page-note-shape-invalid"
    assert doc.page.endnote_shape() == before


def test_page_border_write_and_read() -> None:
    doc = HwpxDocument.new()
    fill = doc.styles.ensure_border_fill(border_color="#000000")
    doc.page.set_page_border(page_type="ODD", border_fill_id_ref=fill, text_border="CONTENT", offset_left=500)
    border = _reopen(doc).page.page_border(page_type="ODD")
    assert border is not None
    assert (border.border_fill_id_ref, border.text_border, border.offset_left) == (str(fill), "CONTENT", 500)
    assert border.to_dict()["offset"]["left"] == 500


def test_start_numbers_and_begin_numbers() -> None:
    doc = HwpxDocument.new()
    doc.page.set_start_numbers(page=7, table=2, page_starts_on="ODD")
    doc.parts.set_begin_numbers(footnote=4, equation=9)
    reopened = _reopen(doc)
    assert reopened.page.start_numbers() == StartNumbers(
        page_starts_on="ODD", page=7, picture=0, table=2, equation=0
    )
    assert reopened.parts.begin_numbers == BeginNumbers(
        page=1, footnote=4, endnote=1, picture=1, table=1, equation=9
    )
    with pytest.raises(HwpxValueError) as caught:
        doc.parts.set_begin_numbers(page=0)
    assert caught.value.code == "parts-begin-numbers-invalid"


def test_document_options_read_what_the_setters_write() -> None:
    doc = HwpxDocument.new()
    doc.parts.set_doc_option_link_info(page_inherit=True)
    doc.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)
    options = _reopen(doc).parts.document_options
    assert isinstance(options, DocumentOptions)
    assert options.target_program == "HWP201X"
    assert options.page_inherit is True and options.footnote_inherit is False
    assert (options.license_type, options.license_flag, options.license_lang) == ("CCL", 0, 6)
    assert options.to_dict()["layoutCompatibility"] == []


def test_section_all_changes_every_section_without_the_last_section_warning() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("하나")
    doc.add_section()
    doc.add_section()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        doc.page.set_margins(left=7000, section="all")
        setup = doc.page.setup(paper_size="B5", section="all")
        doc.page.set_footer(text="꼬리말", section="all")
        doc.page.set_footnote_shape(number_format="ROMAN_SMALL", section="all")
    assert setup.page_size.width_mm == pytest.approx(182, abs=0.5)
    for index in range(3):
        assert doc.page.margins(section=index).left == 7000
        assert doc.page.footnote_shape(section=index).number_format == "ROMAN_SMALL"
        assert doc.sections[index].properties.get_footer() is not None
    assert _reopen(doc).validate().ok


def test_section_all_is_refused_where_it_cannot_mean_anything() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxError) as wrong:
        doc.page.set_margins(left=7000, section="every")  # type: ignore[arg-type]
    assert wrong.value.code == "section-invalid-type"
    with pytest.raises(HwpxValueError) as caught:
        doc.page.set_columns(2, paragraph=0, section="all")
    assert caught.value.code == "page-section-all-invalid"
    with pytest.raises(Exception):
        doc.page.margins(section="all")  # type: ignore[arg-type]
