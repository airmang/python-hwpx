"""paragraph.line_segments: the line layout Hancom saved (hp:linesegarray), read only, as a public value type."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.objects import LineSegment
from hwpx.oxml.namespaces import HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
FIELDS = {"textpos": "text_position", "vertpos": "vertical_position", "vertsize": "height",
          "textheight": "text_height", "baseline": "baseline", "spacing": "spacing", "horzpos": "horizontal_position",
          "horzsize": "width", "flags": "flags"}


@pytest.mark.parametrize("name", ["pages_objects_among_text_equation.hwpx",
                                  "pages_table_vertical_cells_over_the_page_end.hwpx"])
def test_every_saved_line_reads_back_as_written(name: str) -> None:
    doc = HwpxDocument.open(HANCOM / name)
    seen = 0
    paragraphs = [p for s in doc.sections for p in s.paragraphs]
    paragraphs += [c for p in paragraphs for o in p.objects if o.element.tag == f"{HP}tbl"
                   for row in o.rows for cell in row.cells for c in cell.paragraphs]
    for paragraph in paragraphs:
        written = paragraph.element.findall(f"{HP}linesegarray/{HP}lineseg")
        segments = paragraph.line_segments
        assert isinstance(segments, tuple) and len(segments) == len(written)
        for segment, element in zip(segments, written):
            assert isinstance(segment, LineSegment)
            for attribute, field in FIELDS.items():
                assert getattr(segment, field) == int(element.get(attribute)), (attribute, field)
            seen += 1
    assert seen


def test_lines_follow_each_other_down_the_page() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    tops = [segment.vertical_position for p in doc.sections[0].paragraphs for segment in p.line_segments]
    assert tops == sorted(tops) and len(set(tops)) == len(tops)
    first = doc.sections[0].paragraphs[0].line_segments[0]
    assert first.to_dict()["verticalPosition"] == first.vertical_position
    assert set(first.to_dict()) == {"textPosition", "verticalPosition", "height", "textHeight", "baseline",
                                    "spacing", "horizontalPosition", "width", "flags"}


def test_a_new_or_edited_paragraph_has_no_saved_lines() -> None:
    assert HwpxDocument.new().add_paragraph("새 문단").line_segments == ()
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    paragraph = doc.sections[0].paragraphs[0]
    assert paragraph.line_segments
    paragraph.text = "고친 글"
    assert paragraph.line_segments == ()


def test_a_negative_number_hancom_wrote_unsigned_reads_signed() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    paragraph = doc.sections[0].paragraphs[0]
    paragraph.element.find(f"{HP}linesegarray/{HP}lineseg").set("horzpos", str(2**32 - 100))
    assert paragraph.line_segments[0].horizontal_position == -100
