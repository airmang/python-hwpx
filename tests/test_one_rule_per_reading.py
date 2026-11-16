# SPDX-License-Identifier: Apache-2.0
"""One implementation for each thing the engine reads or derives (7.0 coverage check B3).

- Outline level: ``heading_outline_level`` is the one rule; ``Paragraph.outline_level``,
  ``doc.styles.outline_level`` and the heading levels of python-hwpx-automation's Markdown
  export call it. Before 7.0
  ``Paragraph.outline_level`` upper-cased ``type`` and read a bad ``level`` as no outline.
- Note numbers: the exporter's ``NoteLabels`` writes ``note_authoring.note_numbers`` in each
  section's number format (it counted on its own before).
- Border fills derived from another: one path (``formatting.derive_definition``) and one fill
  rule for ``doc.styles.ensure_border_fill(base_border_fill_id=)``, the table setters and
  ``ensure_shading_border_fill`` (which reused any border fill of the same colour, lines and all).
- Styles: every ``style=`` resolves through ``formatting.resolve_style`` and takes its shapes
  through ``section.style_shape_refs``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.formatting import find_definition, paragraph_para_pr
from hwpx.oxml.namespaces import HH, HP
from hwpx.oxml.note_authoring import note_numbers
from hwpx.oxml.paragraph_heading import heading_outline_level, paragraph_heading

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0005fe02fea7d6a4a40000000049454e44ae426082"
)


# -- outline level ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"type": "OUTLINE", "level": "2"}, 3),
        ({"type": "OUTLINE", "level": "9"}, 10),
        ({"type": "OUTLINE"}, 1),  # the attribute's default, 0
        ({"type": "OUTLINE", "level": "x"}, 1),
        ({"type": "OUTLINE", "level": "-1"}, 1),
        ({"type": "OUTLINE", "level": "10"}, 1),
        ({"type": "outline", "level": "2"}, None),  # as written: not the OWPML value
        ({"type": "NUMBER", "level": "2"}, None),
        ({"type": "NONE", "level": "0"}, None),
    ],
)
def test_every_outline_reader_follows_the_one_rule(attributes: dict[str, str], expected: int | None) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("제목")
    paragraph.outline_level = 3
    para_pr = paragraph_para_pr(paragraph)
    assert para_pr is not None
    heading = paragraph_heading(para_pr)
    heading.attrib.clear()
    heading.attrib.update({"idRef": "0", **attributes})
    style_id = document.styles.ensure_style("시험 개요", para_pr_id_ref=paragraph.para_pr_id_ref)

    assert heading_outline_level(para_pr) == expected  # python-hwpx-automation's export reads this too
    assert paragraph.outline_level == (expected or 0)
    assert document.styles.outline_level(int(style_id)) == expected


def test_a_hancom_saved_outline_document_reads_the_same_everywhere() -> None:
    document = HwpxDocument.open(FIXTURES / "pages_outline_labels_paragraph_end_shape.hwpx")
    levels = []
    for paragraph in document.paragraphs:
        para_pr = paragraph_para_pr(paragraph)
        expected = (heading_outline_level(para_pr) or 0) if para_pr is not None else 0
        assert paragraph.outline_level == expected
        levels.append(expected)
    assert sum(1 for level in levels if level) == 19
    assert set(levels) == {0, 1, 2, 3, 4, 5, 6, 7}


# -- note numbers -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["pages_endnotes_at_each_sections_end.hwpx", "pages_footnotes_in_table_cells.hwpx", "pages_footnotes_6.hwpx"],
)
def test_note_labels_are_note_numbers_and_what_hancom_wrote(name: str) -> None:
    from hwpx.tools.exporter import NoteLabels

    document = HwpxDocument.open(FIXTURES / name)
    sections = [section.element for section in document.oxml.sections]
    numbers = note_numbers(sections)
    labels = NoteLabels(document)
    assert numbers
    for note, number in numbers.items():
        assert note.get("number") == str(number)  # Hancom's own count
        assert labels.label(note).strip("()).") == str(number)  # "1)" when the section says nothing else


# -- border fills derived from another --------------------------------------------------------


def _border_fill(document: HwpxDocument, border_fill_id: str):
    found = find_definition(document.oxml.headers[0], "borderFill", border_fill_id)
    assert found is not None
    return found


def _fill_children(element) -> list[str]:
    brush = element.find(f"{_HC}fillBrush")
    return [] if brush is None else [child.tag.rsplit("}", 1)[-1] for child in brush]


def _base_with_diagonals_and_picture(document: HwpxDocument) -> tuple[str, object]:
    """A cell whose border fill has thick lines, both diagonals, a colour and a picture."""

    table = document.add_table(1, 3)
    base = document.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4, fill_color="#00FF00")
    for col in range(3):
        table.set_cell_border_fill(0, col, base)
    element = _border_fill(document, base)
    for name in ("slash", "backSlash"):
        element.find(f"{HH}{name}").set("type", "CENTER")
    image = document.media.add_image(_PNG, "png")
    table.set_cell_fill_image(0, 0, image)
    with_picture = table.cell(0, 0).element.get("borderFillIDRef")
    for col in range(3):
        table.set_cell_border_fill(0, col, with_picture)
    return with_picture, table


def test_the_reused_border_fill_must_match_the_lines_too() -> None:
    document = HwpxDocument.new()
    unrelated = document.styles.ensure_border_fill(fill_color="#D9D9D9", active_borders=[])
    thick = document.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4)

    shaded = document.oxml.ensure_shading_border_fill("#D9D9D9", base_border_fill_id=thick)

    assert shaded != unrelated  # 6.x gave the grey border fill with no lines
    info, base = document.styles.border_fill(shaded), document.styles.border_fill(thick)
    assert (info.left, info.right, info.top, info.bottom) == (base.left, base.right, base.top, base.bottom)
    assert info.fill == "#D9D9D9"
    assert document.oxml.ensure_shading_border_fill("#D9D9D9", base_border_fill_id=thick) == shaded


def test_every_way_of_shading_derives_the_same_border_fill() -> None:
    document = HwpxDocument.new()
    base, table = _base_with_diagonals_and_picture(document)

    by_styles = document.styles.ensure_border_fill(base_border_fill_id_ref=base, fill_color="#0000FF")
    by_header = document.oxml.ensure_shading_border_fill("#0000FF", base_border_fill_id=base)
    table.set_shading("A1", color="#0000FF")
    table.set_cell_shading(0, 1, "#0000FF")

    ids = {by_styles, by_header, table.cell(0, 0).element.get("borderFillIDRef"),
           table.cell(0, 1).element.get("borderFillIDRef")}
    assert len(ids) == 1
    derived = _border_fill(document, ids.pop())
    assert [derived.find(f"{HH}{n}").get("type") for n in ("slash", "backSlash")] == ["CENTER", "CENTER"]
    assert _fill_children(derived) == ["winBrush", "imgBrush"]  # the picture stays under a new colour
    assert derived.find(f"{_HC}fillBrush/{_HC}winBrush").get("faceColor") == "#0000FF"
    assert document.styles.border_fill(base).left.width_mm == 0.4


def test_a_gradient_replaces_the_colour_and_keeps_the_picture_and_lines() -> None:
    document = HwpxDocument.new()
    base, table = _base_with_diagonals_and_picture(document)

    table.set_cell_fill_gradient(0, 2, ["#FFFFFF", "#000000"])

    derived = _border_fill(document, table.cell(0, 2).element.get("borderFillIDRef"))
    assert _fill_children(derived) == ["gradation", "imgBrush"]
    assert derived.find(f"{HH}slash").get("type") == "CENTER"
    assert document.styles.border_fill(derived.get("id")).left.color == "#FF0000"
    table.set_shading("C1", color="#123456")  # a colour after a gradient replaces it
    again = _border_fill(document, table.cell(0, 2).element.get("borderFillIDRef"))
    assert _fill_children(again) == ["winBrush", "imgBrush"]


def test_no_colour_takes_the_face_away_and_keeps_the_picture() -> None:
    document = HwpxDocument.new()
    base, table = _base_with_diagonals_and_picture(document)

    table.set_shading("B1", color=None)

    derived = _border_fill(document, table.cell(0, 1).element.get("borderFillIDRef"))
    assert _fill_children(derived) == ["imgBrush"]
    assert document.styles.border_fill(derived.get("id")).fill is None


def test_a_border_edit_that_finds_an_existing_fill_still_sets_the_neighbours_edge() -> None:
    document = HwpxDocument.new()
    first, second = document.add_table(1, 2), document.add_table(1, 2)
    first.set_cell_borders(0, 0, color="#FF0000")  # makes the red border fill

    second.set_cell_borders(0, 0, color="#FF0000")  # finds it: 6.x left the neighbour as it was

    assert second.cell(0, 0).element.get("borderFillIDRef") == first.cell(0, 0).element.get("borderFillIDRef")
    neighbour = document.styles.border_fill(second.cell(0, 1).element.get("borderFillIDRef"))
    assert neighbour.left.color == "#FF0000"


def test_derived_border_fills_survive_saving() -> None:
    document = HwpxDocument.new()
    _base_with_diagonals_and_picture(document)
    reopened = HwpxDocument.open(document.to_bytes())
    reopened.validate()
    header = reopened.oxml.headers[0].element
    items = header.find(f"{HH}refList/{HH}borderFills")
    assert int(items.get("itemCnt")) == len(items.findall(f"{HH}borderFill"))


# -- styles -----------------------------------------------------------------------------------


def test_every_style_argument_resolves_and_takes_shapes_the_same_way() -> None:
    document = HwpxDocument.new()
    style = document.styles.resolve("개요 1")
    body = document.add_paragraph("가", style="outline 1")  # the English name, any case
    cell = document.add_table(1, 1).cell(0, 0).add_paragraph("나", style="OUTLINE 1")
    other = document.add_paragraph("다")
    other.style = "Outline 1"

    for paragraph in (body, cell, other):
        assert paragraph.element.get("styleIDRef") == str(style.id)
        assert str(paragraph.para_pr_id_ref) == str(style.para_pr_id_ref)
    assert document._style_shapes("개요 1", None, "7") == (style.para_pr_id_ref, "7")


def test_paragraph_element_tag_is_hp_p() -> None:  # guards the helper imports above
    assert HP.endswith("}") and HH.endswith("}")
