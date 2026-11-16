"""Public reads the automation package asked of the 7.0 engine (asks2): Hancom's line widths and their
HWPUNIT, the section an object sits in, and every value of a numbering level. Each reads what the file
holds; none of them fits or guesses a value. (``FormField.editable``: test_form_field_editable_default.py.)"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.shape_position import LINE_WIDTH_UNITS_PER_MM, line_width_mm_for_units, line_width_units
from hwpx.oxml.utils import LINE_WIDTHS_MM

FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)


def _rewrite(data: bytes, part: str, old: bytes, new: bytes) -> bytes:
    """*data* with *old* replaced by *new* in *part* (the other parts as they were)."""

    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            body = source.read(info.filename)
            if info.filename == part:
                assert old in body
                body = body.replace(old, new)
            target.writestr(info, body)
    return out.getvalue()


# -- 1. Hancom's line widths and HWPUNIT -------------------------------------------------------


def test_the_line_width_list_is_hancoms_sixteen_widths_in_mm() -> None:
    assert LINE_WIDTHS_MM == (0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
    assert isinstance(LINE_WIDTHS_MM, tuple)


def test_every_listed_width_is_taken_by_a_border_and_reads_back() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, len(LINE_WIDTHS_MM))
    for col, width in enumerate(LINE_WIDTHS_MM):
        table.set_borders(f"{chr(ord('A') + col)}1", border_width_mm=width)
        border_fill = table.cell(0, col).border_fill
        assert border_fill is not None and border_fill.left.width_mm == width
    with pytest.raises(HwpxValueError) as caught:
        table.set_borders("A1", border_width_mm=0.45)  # between two listed widths: not fitted
    assert caught.value.code == "style-line-width-invalid"


def test_shape_line_widths_count_283_hwpunit_per_mm_cut_to_a_whole_unit() -> None:
    assert LINE_WIDTH_UNITS_PER_MM == 283
    assert line_width_units(0.12) == 33
    assert line_width_units(0.5) == 141
    assert line_width_units(0) == 0
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_rectangle(3000, 1500, line_width_mm=0.4)
    assert int(shape.element.find("{*}lineShape").get("width")) == line_width_units(0.4) == 113


def test_line_width_mm_for_units_gives_the_same_hwpunit_back() -> None:
    for units in [*range(0, 3000), 14150, 2**31 - 300]:
        assert line_width_units(line_width_mm_for_units(units)) == units, units


def test_line_width_conversions_refuse_what_is_not_a_width() -> None:
    for bad in (-0.1, float("nan"), "0.12 mm", True):
        with pytest.raises(HwpxValueError) as caught:
            line_width_units(bad)
        assert caught.value.code == "shape-picture-border-value"
    for bad in (-1, "x", True):
        with pytest.raises(HwpxValueError):
            line_width_mm_for_units(bad)


# -- 2. the section an object sits in ----------------------------------------------------------


def test_a_hancom_saved_picture_in_a_table_cell_names_its_section() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_table_cell_picture_first.hwpx")
    (picture,) = doc.media.pictures
    assert picture.section is doc.sections[0]
    assert doc.sections.index(picture.section) == 0
    for table in doc.tables.with_nested:
        assert table.section is doc.sections[0]


def test_a_picture_in_the_second_section_reads_that_section() -> None:
    doc = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / "error__20230728__test.hwpx")
    assert len(doc.sections) > 1
    for picture in doc.media.pictures:
        assert picture.section is picture.paragraph.section
        assert doc.sections.index(picture.section) >= 1


def test_objects_in_cells_boxes_notes_and_headers_answer_their_section() -> None:
    doc = HwpxDocument.new()
    second = doc.add_section()
    item = str(doc.media.add_image(PNG, "png"))
    body = second.add_paragraph("")
    outer = doc.add_table(2, 2, section=second)
    inner = outer.cell(0, 0).paragraphs[0].add_table(1, 1)
    box = body.add_rectangle(16000, 6000)
    note = body.add_footnote("각주")
    header = doc.page.set_header(text="머리말", section=second)
    places = {
        "body": body,
        "cell": outer.cell(1, 1).paragraphs[0],
        "nested cell": inner.cell(0, 0).paragraphs[0],
        "text box": box.set_draw_text("글상자").paragraphs[0],
        "note": note.paragraphs[0],
        "header": header.paragraphs[0],
    }
    for place, paragraph in places.items():
        picture = paragraph.add_picture(item, width=2000, height=1000)
        shape = paragraph.add_ellipse(2000, 1000)
        equation = paragraph.add_equation("a+b")
        for obj in (picture, shape, equation):
            assert obj.section is second, (place, obj)
            assert doc.sections.index(obj.section) == 1
    assert outer.section is second and inner.section is second and box.section is second
    first = doc.sections[0].add_paragraph("").add_rectangle(1000, 1000)
    assert first.section is doc.sections[0]


def test_an_object_on_a_master_page_has_no_section() -> None:
    doc = HwpxDocument.new()
    master = doc.parts.add_master_page(text="바탕쪽")
    shape = master.paragraphs[0].add_rectangle(2000, 1000)
    assert shape.section is None


# -- 3. every value a numbering level holds ----------------------------------------------------


def test_a_hancom_saved_numbering_reads_use_instance_width_as_written() -> None:
    doc = HwpxDocument.open(HANCOM / "list_start_0.hwpx")
    widths = {key: [level.use_instance_width for level in info.levels] for key, info in doc.styles.numberings.items()}
    assert widths["1"] == [True] * len(widths["1"])
    assert widths["2"][0] is True and widths["2"][1:] == [False] * (len(widths["2"]) - 1)
    level = doc.styles.numbering("2").level(2)
    assert level is not None and level.to_dict()["useInstanceWidth"] is False


def test_a_numbering_level_holds_every_attribute_of_its_para_head() -> None:
    doc = HwpxDocument.open(HANCOM / "list_start_0.hwpx")
    header = doc.oxml.headers[0].element
    for head in header.iter("{*}paraHead"):
        if head.getparent().tag.endswith("numbering"):
            assert set(head.attrib) == {
                "start", "level", "align", "useInstWidth", "autoIndent", "widthAdjust", "textOffsetType",
                "textOffset", "numFormat", "charPrIDRef", "checkable",
            }
    fields = {name for name in doc.styles.numbering("1").levels[0].__dataclass_fields__}
    assert {"start", "level", "alignment", "use_instance_width", "auto_indent", "width_adjust", "text_offset_type",
            "text_offset", "number_format", "char_pr_id_ref", "checkable"} <= fields


def test_a_para_head_that_leaves_attributes_out_reads_the_schema_defaults() -> None:
    data = HwpxDocument.open(HANCOM / "list_start_0.hwpx").to_bytes()
    header = zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml")
    start = header.index(b"<hh:paraHead", header.index(b"<hh:numbering "))
    end = header.index(b">", start)
    bare = b'<hh:paraHead level="1"'
    doc = HwpxDocument.open(_rewrite(data, "Contents/header.xml", header[start:end], bare))
    level = next(iter(doc.styles.numberings.values())).levels[0]
    assert (level.start, level.number_format, str(level.alignment)) == (1, "DIGIT", "LEFT")
    assert (level.use_instance_width, level.auto_indent, level.width_adjust) == (True, True, 0)
    assert (level.text_offset, level.text_offset_type, level.checkable) == (50, "PERCENT", False)
