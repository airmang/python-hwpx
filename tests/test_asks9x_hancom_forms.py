"""asks9x (나): calls whose output now takes Hancom's saved form -- a side with no line 0.1 mm wide, a table's
inner margins carried into the cells laid out with them, object ids no two objects of a document share, and
definitions a paragraph copied from another document finds already there reused. Each changes what an
existing call writes (so it waits for the owner's approval before merging)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.objects import CellMargins

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
OBJECTS = ("tbl", "pic", "rect", "ellipse", "line", "container", "equation")


def _border_sides(doc: HwpxDocument, fill_id: str) -> dict[str, tuple[str, str]]:
    fill = next(node for node in doc.oxml.headers[0].element.iter(f"{HH}borderFill") if node.get("id") == fill_id)
    return {child.tag.rsplit("}", 1)[-1]: (child.get("type"), child.get("width"))
            for child in fill if child.tag.endswith("Border")}


def test_a_side_with_no_line_is_written_0_1_mm_wide_as_hancom_writes_it() -> None:
    doc = HwpxDocument.new()
    plain = doc.styles.ensure_border_fill()  # 0.12 mm all round
    none = doc.styles.ensure_border_fill(base_border_fill_id_ref=plain, sides={side: None for side in (
        "left", "right", "top", "bottom")})
    assert set(_border_sides(doc, none).values()) == {("NONE", "0.1 mm")}
    mixed = doc.styles.ensure_border_fill(sides={"left": None})
    assert _border_sides(doc, mixed)["leftBorder"] == ("NONE", "0.1 mm")
    assert _border_sides(doc, mixed)["rightBorder"] == ("SOLID", "0.12 mm")
    assert doc.styles.ensure_border_fill(sides={"left": None}) == mixed  # the same definition again


def test_inner_margins_reach_the_cells_laid_out_with_them() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    own = table.cell(1, 1)
    own.element.set("hasMargin", "1")  # a cell with margins of its own keeps them
    before_own = dict(own.element.find(f"{HP}cellMargin").attrib)
    table.set_in_margins(left=141, right=141, top=200, bottom=200)
    for row, col in ((0, 0), (0, 1), (1, 0)):
        assert table.cell(row, col).element.find(f"{HP}cellMargin").attrib == {
            "left": "141", "right": "141", "top": "200", "bottom": "200"}
    assert dict(own.element.find(f"{HP}cellMargin").attrib) == before_own


def test_add_table_takes_its_inner_margins() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 2, in_margins=CellMargins(141, 141, 100, 100))
    assert table.in_margins == CellMargins(141, 141, 100, 100)
    assert {tuple(cell.element.find(f"{HP}cellMargin").attrib.values()) for cell in (table.cell(0, 0), table.cell(0, 1))} == {
        ("141", "141", "100", "100")}
    count = len(doc.paragraphs)
    import pytest

    from hwpx.errors import HwpxValueError

    with pytest.raises(HwpxValueError) as caught:
        doc.add_table(1, 1, in_margins=(1, 2, 3, 4))  # type: ignore[arg-type]
    assert caught.value.code == "table-margin-value" and len(doc.paragraphs) == count


def _object_ids(doc: HwpxDocument) -> list[tuple[str, str | None, str | None]]:
    out = []
    for section in doc.sections:
        for node in section.element.iter():
            if isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] in OBJECTS \
                    and node.getparent().tag.rsplit("}", 1)[-1] != "container":
                out.append((node.tag.rsplit("}", 1)[-1], node.get("id"), node.get("instid")))
    return out


def test_copies_give_every_object_an_id_no_other_object_has() -> None:
    doc = HwpxDocument.new(seed=3)
    paragraph = doc.add_paragraph("가")
    doc.shapes.add_rectangle(1000, 1000, paragraph=paragraph)
    paragraph.add_table(1, 1)
    paragraph.copy_to(doc.paragraphs[-1])
    paragraph.insert_after()
    doc.sections[0].insert_paragraphs(1, [paragraph])
    ids = _object_ids(doc)
    assert len(ids) == 8 and len({object_id for _, object_id, _ in ids}) == 8
    assert all(instid == object_id for kind, object_id, instid in ids if kind == "rect")  # as Hancom writes them


def test_an_object_new_to_a_document_never_takes_an_id_it_already_has() -> None:
    # two documents made with the same seed draw the same ids: copying into one used to share them
    source = HwpxDocument.new(seed=3)
    paragraph = source.add_paragraph("가")
    source.shapes.add_rectangle(1000, 1000, paragraph=paragraph)
    target = HwpxDocument.new(seed=3)
    target.add_paragraph("나")
    target.shapes.add_rectangle(500, 500, paragraph=target.paragraphs[-1])
    paragraph.copy_to(target.paragraphs[-1])
    target.shapes.add_rectangle(700, 700, paragraph=target.paragraphs[-1])
    ids = [object_id for _, object_id, _ in _object_ids(target)]
    assert len(ids) == 3 and len(set(ids)) == 3


def test_seeded_documents_stay_repeatable() -> None:
    def build() -> bytes:
        doc = HwpxDocument.new(seed=11, now=_NOW)  # now: two runs may straddle a clock second
        paragraph = doc.add_paragraph("가")
        doc.shapes.add_rectangle(1000, 1000, paragraph=paragraph)
        paragraph.insert_after()
        return doc.to_bytes()

    assert build() == build()


def test_a_copy_from_another_document_reuses_the_definitions_already_there() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("첫")
    bold = source.add_paragraph("굵은 글")
    bold.runs[0].bold = True
    target = HwpxDocument.new()
    target.add_paragraph("첫")
    there = target.add_paragraph("기존")
    there.runs[0].bold = True
    header = target.oxml.headers[0].element

    def counts() -> dict[str, int]:
        return {name: len(header.findall(f".//{HH}{name}")) for name in (
            "charPr", "paraPr", "borderFill", "tabPr", "style", "font")}

    before = counts()
    copy = bold.copy_to(target.paragraphs[-1])
    assert counts() == before  # every definition it needs was already there
    assert copy.runs[0].element.get("charPrIDRef") == there.runs[0].element.get("charPrIDRef")
    italic_source = HwpxDocument.new()
    italic_source.add_paragraph("첫")
    italic = italic_source.add_paragraph("기울인 글")
    italic.runs[0].italic = True
    copied = italic.copy_to(target.paragraphs[-1])
    after = counts()
    assert after["charPr"] == before["charPr"] + 1 and copied.runs[0].italic
    char_ids = sorted(int(node.get("id")) for node in header.iter(f"{HH}charPr"))
    assert char_ids == list(range(len(char_ids)))  # numbered on without a gap
    again = HwpxDocument.open(target.to_bytes())
    assert not again.validate().issues
    from hwpx.tools.id_integrity import check_id_integrity

    assert check_id_integrity(again).dangling == []
    assert again.paragraphs[-1].runs[0].italic and again.paragraphs[-2].runs[0].bold


def test_a_copy_reads_a_header_s_equal_fonts_as_one() -> None:
    # memos_in_fields (Hancom-saved) has 함초롬바탕 twice in its HANJA face (ids 0 and 6), as many Hancom
    # documents do. A copied character shape naming the first is the same as one there naming the other.
    path = Path(__file__).parent / "fixtures" / "hancom_saved" / "memos_in_fields.hwpx"
    with HwpxDocument.open(path) as source, HwpxDocument.open(path) as target:
        header = target.oxml.headers[0].element
        faces = [face for face in header.iter(f"{HH}fontface") if face.get("lang") == "HANJA"]
        names = [font.get("face") for font in faces[0].findall(f"{HH}font")]
        assert len(names) != len(set(names))  # the same font twice

        def counts() -> dict[str, int]:
            return {name: len(header.findall(f".//{HH}{name}")) for name in ("charPr", "paraPr", "style", "font")}

        before = counts()
        for paragraph in source.paragraphs:
            if paragraph.text:
                paragraph.copy_to(target.paragraphs[-1])
        assert counts() == before
