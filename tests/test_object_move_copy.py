"""Moving and copying objects, tables, paragraphs and memos inside one document; tables in map order.

Every edit keeps the document valid after a save and reopen, leaves the parts it did not touch byte for
byte, drops the line layout cache of the paragraphs it changed (and of the paragraphs holding their cells
and captions), and refuses what Hancom documents never hold before anything changes.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError, HwpxLookupError, HwpxTypeError, HwpxValueError
from hwpx.model import Equation, Memo, Paragraph, Picture, Shape, Table
from hwpx.oxml.formatting import _unit_length
from hwpx.oxml.namespaces import HP
from hwpx.tools.table_navigation import _collect_document_tables

FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _has_cache(element) -> bool:
    return element.find(f"{HP}linesegarray") is not None


def _offset_of(paragraph: Paragraph, element) -> int:
    """How many characters of the paragraph's text come before *element* (as ``paragraph.text`` counts)."""

    position = 0
    for run in paragraph.element.findall(f"{HP}run"):
        for child in run:
            if child is element:
                return position
            position += _unit_length(child)
    raise AssertionError("the element is not among the paragraph's runs")


def _cached(paragraph: Paragraph) -> Paragraph:
    """Give *paragraph* a line layout cache, as a Hancom-saved paragraph has."""

    cache = paragraph.element.makeelement(f"{HP}linesegarray", {})
    cache.append(cache.makeelement(f"{HP}lineseg", {"textpos": "0", "vertpos": "0", "vertsize": "1000",
                                                   "textheight": "1000", "baseline": "850", "spacing": "600",
                                                   "horzpos": "0", "horzsize": "42520", "flags": "393216"}))
    paragraph.element.append(cache)
    return paragraph


# -- objects: where they go ----------------------------------------------------------------------


def test_move_to_puts_the_object_in_front_of_the_character_at_offset() -> None:
    doc = HwpxDocument.new()
    source = doc.add_paragraph("원래 ")
    target = doc.add_paragraph("가나다라마")
    equation = source.add_equation("{a} over {b}")
    element = equation.element

    equation.move_to(target, offset=2)

    assert equation.paragraph.element is target.element
    assert target.text == "가나다라마" and source.text == "원래 "
    assert _offset_of(target, element) == 2
    run = element.getparent()
    texts = [child.text for child in run if child.tag == f"{HP}t"]
    assert texts == ["가나", "다라마"]  # the text node is divided, the object sits between its halves in one run
    assert source.objects == () and [type(o) for o in target.objects] == [Equation]
    assert _reopen(doc).sections[0].paragraphs[-1].text == "가나다라마"


@pytest.mark.parametrize("offset", [0, 1, 5, None])
def test_move_to_counts_offsets_as_paragraph_text_does(offset) -> None:
    doc = HwpxDocument.new()
    target = doc.add_paragraph("가나")
    target.add_run("\t다")  # a tab is one character
    target.add_run("\n라")  # so is a line break
    rectangle = doc.add_paragraph("").add_rectangle(2000, 1000)
    length = len(target.text)
    assert length == 6

    rectangle.move_to(target, offset=offset)

    assert target.text == "가나\t다\n라"
    assert _offset_of(target, rectangle.element) == (length if offset is None else offset)
    _reopen(doc)


def test_offset_zero_goes_after_the_section_settings_of_the_first_paragraph() -> None:
    doc = HwpxDocument.new()
    first = doc.paragraphs[0]
    first.text = "첫 문단"
    picture = doc.add_picture(PNG, "png", width=3000)
    assert first.element.find(f"{HP}run/{HP}secPr") is not None

    picture.move_to(first, offset=0)

    run = picture.element.getparent()
    names = [child.tag.rsplit("}", 1)[-1] for child in run]
    assert names.index("pic") > names.index("secPr")
    assert _offset_of(first, picture.element) == 0
    again = _reopen(doc)
    assert again.sections[0].paragraphs[0].text == "첫 문단"
    assert len(again.media.pictures) == 1


def test_move_to_accepts_an_index_of_doc_paragraphs_and_keeps_ids() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("하나")
    doc.add_paragraph("둘")
    picture = doc.add_picture(PNG, "png", width=3000)
    ids = (picture.element.get("id"), picture.element.get("instid"))

    picture.move_to(1)

    assert picture.paragraph.element is doc.paragraphs[1].element
    assert (picture.element.get("id"), picture.element.get("instid")) == ids
    assert isinstance(doc.paragraphs[1].objects[0], Picture)


def test_move_to_drops_a_run_left_empty_and_clears_both_caches_only() -> None:
    doc = HwpxDocument.new()
    source = _cached(doc.add_paragraph("앞"))
    rectangle = source.add_rectangle(2000, 1000)
    bystander = _cached(doc.add_paragraph("그대로"))
    target = _cached(doc.add_paragraph("뒤"))
    runs = len(source.element.findall(f"{HP}run"))

    rectangle.move_to(target)

    assert len(source.element.findall(f"{HP}run")) == runs - 1
    assert not _has_cache(source.element) and not _has_cache(target.element)
    assert _has_cache(bystander.element)


def test_move_into_a_cell_clears_the_cell_and_the_paragraph_holding_the_table() -> None:
    doc = HwpxDocument.new()
    holder = _cached(doc.add_paragraph(""))
    table = holder.add_table(2, 2)
    cell_paragraph = _cached(table.cell(1, 1).paragraphs[0])
    equation = doc.add_paragraph("수식 ").add_equation("x^2")

    equation.move_to(cell_paragraph)

    assert cell_paragraph.equations[0].element is equation.element
    assert not _has_cache(cell_paragraph.element) and not _has_cache(holder.element)
    again = _reopen(doc)
    assert again.tables[0].cell(1, 1).paragraphs[0].equations[0].script == "x^2"


def test_moving_out_of_a_cell_clears_the_cell_and_its_holder() -> None:
    doc = HwpxDocument.new()
    holder = _cached(doc.add_paragraph(""))
    table = holder.add_table(1, 1)
    cell_paragraph = _cached(table.cell(0, 0).paragraphs[0])
    rectangle = cell_paragraph.add_rectangle(1000, 1000)
    _cached(cell_paragraph)
    _cached(holder)
    target = doc.add_paragraph("밖")

    rectangle.move_to(target)

    assert not _has_cache(cell_paragraph.element) and not _has_cache(holder.element)
    assert table.cell(0, 0).paragraphs[0].objects == ()


def test_a_text_box_moves_with_its_text_and_into_a_note() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("각주가 붙는 글")
    note = paragraph.add_footnote("각주 글")
    box = doc.add_paragraph("").add_rectangle(4000, 2000)
    box.set_draw_text("글상자 안")

    box.move_to(note.paragraphs[0])

    again = _reopen(doc)
    found = again.notes.footnotes[0].paragraphs[0].shapes
    assert len(found) == 1 and found[0].draw_text.text == "글상자 안"


# -- objects: copies -----------------------------------------------------------------------------


def test_copy_to_returns_a_new_object_with_fresh_ids_and_the_same_image() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png", width=3000)
    picture.set_caption("그림 설명")
    target = doc.add_paragraph("여기")
    before = doc.to_bytes()

    copy = picture.copy_to(target, offset=1)

    assert isinstance(copy, Picture) and copy.paragraph.element is target.element
    assert copy.element is not picture.element
    assert copy.element.get("id") != picture.element.get("id")
    assert copy.element.get("instid") != picture.element.get("instid")
    assert copy.item_id == picture.item_id  # the same BinData item
    assert copy.caption is not None and copy.caption.text == "그림 설명"
    caption_ids = {p.element.get("id") for p in picture.caption.paragraphs}
    assert not caption_ids & {p.element.get("id") for p in copy.caption.paragraphs}
    assert not any(node.tag == f"{HP}linesegarray" for node in copy.element.iter())
    assert _offset_of(target, copy.element) == 1
    again = _reopen(doc)
    assert len(again.media.pictures) == 2
    assert len(again.media.images) == len(HwpxDocument.open(before).media.images)


def test_copy_to_renews_drawing_shape_ids_and_keeps_group_member_ids() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = next(o for p in doc.paragraphs for o in p.objects if isinstance(o, Shape) and o.shape_type == "container")
    target = doc.add_paragraph("")
    members = [node for node in group.element.iter() if node is not group.element and node.get("id") is not None]

    copy = group.copy_to(target)

    copied = [node for node in copy.element.iter() if node is not copy.element and node.get("id") is not None]
    assert copy.element.get("id") != group.element.get("id")
    for original, twin in zip(members, copied):
        if original.get("id") == "0":
            assert twin.get("id") == "0"
    original_inst = {node.get("instid") for node in group.element.iter() if node.get("instid")}
    copied_inst = {node.get("instid") for node in copy.element.iter() if node.get("instid")}
    assert not original_inst & copied_inst
    _reopen(doc)


def test_a_text_box_can_be_copied_into_its_own_text_but_not_moved_there() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(6000, 3000)
    box.set_draw_text("안쪽")
    inner = box.draw_text.paragraphs[0]

    with pytest.raises(HwpxValueError) as excinfo:
        box.move_to(inner)
    assert excinfo.value.code == "shape-move-into-itself"

    copy = box.copy_to(inner)
    assert copy.draw_text.text == "안쪽"
    _reopen(doc)


def test_copying_a_text_box_with_a_memo_gives_the_copy_its_own_memo() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(6000, 3000)
    box.set_draw_text("메모가 걸린 글")
    memo = doc.notes.add_memo("살펴볼 것", anchor=box.draw_text.paragraphs[0], section=0)
    assert memo.paragraph is not None

    copy = box.copy_to(doc.add_paragraph(""))

    memos = doc.sections[0].memo_group.memos
    assert len(memos) == 2 and memos[1].text == "살펴볼 것" and memos[1].id != memo.id
    fields = [node for node in copy.element.iter(f"{HP}fieldBegin") if node.get("type") == "MEMO"]
    assert len(fields) == 1
    numbers = [node.get("zorder") for section in doc.sections for node in section.element.iter(f"{HP}fieldBegin")
               if node.get("type") == "MEMO"]
    assert len(set(numbers)) == 2  # Hancom takes memos of one number for one memo
    assert memos[1].paragraph is not None and memos[1].paragraph.element is not memo.paragraph.element
    _reopen(doc)


def test_paragraph_and_table_copies_give_a_memo_anchor_its_own_memo() -> None:
    doc = HwpxDocument.new()
    anchored = doc.add_paragraph("메모가 걸린 글")
    memo = doc.notes.add_memo("원본", anchor=anchored, section=0)

    copy = anchored.insert_after()

    memos = doc.sections[0].memo_group.memos
    assert [m.text for m in memos] == ["원본", "원본"] and memos[1].id != memo.id
    assert memos[1].paragraph is not None and memos[1].paragraph.element is copy.element
    table = doc.add_paragraph("").add_table(1, 1)
    doc.notes.add_memo("칸 메모", anchor=table.cell(0, 0).paragraphs[0], section=0)
    table.copy_after()
    assert [m.text for m in doc.sections[0].memo_group.memos] == ["원본", "원본", "칸 메모", "칸 메모"]
    numbers = [node.get("zorder") for node in doc.sections[0].element.iter(f"{HP}fieldBegin")
               if node.get("type") == "MEMO"]
    assert len(numbers) == 4 and len(set(numbers)) == 4
    again = _reopen(doc)
    assert [m.text for m in again.sections[0].memos] == ["원본", "원본", "칸 메모", "칸 메모"]


def test_table_copy_to_may_go_into_its_own_cell_and_move_to_may_not() -> None:
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(2, 2)
    table.cell(0, 0).text = "원본"
    own_cell = table.cell(1, 1).paragraphs[0]

    with pytest.raises(HwpxValueError) as excinfo:
        table.move_to(own_cell)
    assert excinfo.value.code == "shape-move-into-itself"

    copy = table.copy_to(own_cell)
    assert isinstance(copy, Table) and copy.cell(0, 0).text == "원본"
    assert copy.element.get("id") != table.element.get("id")
    assert len(doc.tables.with_nested) == 2
    again = _reopen(doc)
    assert again.tables[0].cell(1, 1).tables[0].cell(0, 0).text == "원본"


def test_table_move_to_another_paragraph_keeps_its_id() -> None:
    doc = HwpxDocument.new()
    table = doc.add_paragraph("앞").add_table(1, 2)
    table_id = table.element.get("id")
    target = doc.add_paragraph("뒤에 붙는 글")

    table.move_to(target, offset=0)

    assert target.tables[0].element.get("id") == table_id
    assert table.paragraph.element is target.element
    _reopen(doc)


# -- objects: what is refused -------------------------------------------------------------------


def _floating_picture(doc: HwpxDocument, paragraph: Paragraph, frame: str) -> Picture:
    item = doc.media.add_image(PNG, "png")
    return paragraph.add_picture(
        str(item), width=3000, height=3000, treat_as_char=False,
        pos_overrides={"vertRelTo": frame, "horzRelTo": frame, "vertOffset": 1000, "horzOffset": 1000},
    )


def test_a_page_measured_floating_object_does_not_go_into_a_cell_and_nothing_changes() -> None:
    doc = HwpxDocument.new()
    source = doc.add_paragraph("도장")
    picture = _floating_picture(doc, source, "PAPER")
    cell_paragraph = doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]
    before = doc.to_bytes()

    with pytest.raises(HwpxValueError) as excinfo:
        picture.move_to(cell_paragraph)
    assert excinfo.value.code == "shape-move-place-unsupported"
    with pytest.raises(HwpxValueError):
        picture.copy_to(cell_paragraph)
    assert doc.to_bytes() == before
    assert picture.paragraph.element is source.element


def test_a_paragraph_measured_floating_object_keeps_its_frames_in_a_cell() -> None:
    doc = HwpxDocument.new()
    picture = _floating_picture(doc, doc.add_paragraph("떠 있는 그림"), "PARA")
    cell_paragraph = doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]
    position = picture.position

    picture.move_to(cell_paragraph)

    assert picture.position == position
    _reopen(doc)


def _boxes(doc: HwpxDocument) -> dict[str, Paragraph]:
    """A paragraph of a table cell, of a text box and of a footnote."""

    box = doc.add_paragraph("").add_rectangle(9000, 3000)
    box.set_draw_text("글상자")
    return {
        "cell": doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0],
        "text_box": box.draw_text.paragraphs[0],
        "note": doc.add_paragraph("각주").add_footnote("각주 글").paragraphs[0],
    }


@pytest.mark.parametrize("box", ["cell", "text_box", "note"])
def test_a_floating_object_not_kept_in_the_page_area_does_not_go_into_a_box(box: str) -> None:
    # add_picture(treat_as_char=False) writes vertRelTo=PARA, horzRelTo=COLUMN, flowWithText=0: in a
    # cell Hancom draws such a picture over the cells above it, and no Hancom document holds one in a
    # text box or a note.
    doc = HwpxDocument.new()
    item = doc.media.add_image(PNG, "png")
    picture = doc.add_paragraph("").add_picture(str(item), width=3000, height=3000, treat_as_char=False)
    target = _boxes(doc)[box]
    before = doc.to_bytes()
    position = picture.element.find(f"{HP}pos")
    assert (position.get("vertRelTo"), position.get("horzRelTo"), position.get("flowWithText")) == \
        ("PARA", "COLUMN", "0")

    for call in (picture.move_to, picture.copy_to):
        with pytest.raises(HwpxValueError) as excinfo:
            call(target)
        assert excinfo.value.code == "shape-move-place-unsupported"
        assert excinfo.value.context["flowWithText"] == "0" and excinfo.value.context["box"] == box
        assert "set_position" in excinfo.value.suggestion
    assert doc.to_bytes() == before  # nothing changed, the placement included

    picture.set_position(horz_rel_to="PARA")  # measured across from its paragraph: it may go in
    picture.move_to(target)
    assert picture.paragraph.element is target.element
    _reopen(doc)


@pytest.mark.parametrize("box", ["cell", "text_box", "note"])
def test_a_floating_object_kept_in_the_page_area_goes_into_a_box(box: str) -> None:
    doc = HwpxDocument.new()
    item = doc.media.add_image(PNG, "png")
    picture = doc.add_paragraph("").add_picture(
        str(item), width=3000, height=3000, treat_as_char=False,
        pos_overrides={"vertRelTo": "PARA", "horzRelTo": "COLUMN", "flowWithText": "1"},
    )
    target = _boxes(doc)[box]

    copy = picture.copy_to(target)

    assert copy.position == picture.position
    _reopen(doc)


def test_a_page_measured_copy_keeps_the_place_of_the_original() -> None:
    # Measured from the paper, the copy has the original's place on the page: on the same page it is
    # drawn exactly over it until set_position moves it.
    doc = HwpxDocument.new()
    picture = _floating_picture(doc, doc.add_paragraph("도장"), "PAPER")
    target = doc.add_paragraph("사본은 이 문단에 붙지만 쪽 위 자리는 원본과 같다")

    copy = picture.copy_to(target, offset=2)

    original = picture.element.find(f"{HP}pos")
    copied = copy.element.find(f"{HP}pos")
    assert dict(copied.attrib) == dict(original.attrib)
    assert copy.position == picture.position
    copy.set_position(horizontal_offset=9000)
    assert copy.position.horizontal_offset == 9000 and picture.position.horizontal_offset == 1000
    _reopen(doc)


def test_a_page_measured_object_moves_to_a_section_of_the_same_paper_only() -> None:
    doc = HwpxDocument.new()
    picture = _floating_picture(doc, doc.add_paragraph("도장"), "PAGE")
    same = doc.add_section()
    same_paragraph = doc.add_paragraph("같은 용지", section=same)
    picture.move_to(same_paragraph)
    assert picture.paragraph.element is same_paragraph.element

    other = doc.add_section()
    other.properties.set_page_size(orientation="LANDSCAPE")
    other_paragraph = doc.add_paragraph("가로 용지", section=other)
    with pytest.raises(HwpxValueError) as excinfo:
        picture.move_to(other_paragraph)
    assert excinfo.value.code == "shape-move-place-unsupported"
    _reopen(doc)


def test_a_group_member_a_removed_object_and_bad_places_are_refused() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = next(o for p in doc.paragraphs for o in p.objects if isinstance(o, Shape) and o.shape_type == "container")
    member = group.members[0]
    target = doc.paragraphs[0]
    with pytest.raises(HwpxValueError) as excinfo:
        member.move_to(target)
    assert excinfo.value.code == "shape-group-member-unsupported"
    with pytest.raises(HwpxValueError):
        member.copy_to(target)

    fresh = HwpxDocument.new()
    equation = fresh.add_paragraph("").add_equation("y")
    equation.remove()
    with pytest.raises(HwpxValueError) as excinfo:
        equation.move_to(fresh.add_paragraph(""))
    assert excinfo.value.code == "shape-not-in-document"

    other = HwpxDocument.new()
    live = fresh.add_paragraph("").add_equation("z")
    with pytest.raises(HwpxValueError) as excinfo:
        live.move_to(other.add_paragraph(""))
    assert excinfo.value.code == "paragraph-not-in-document"
    with pytest.raises(HwpxLookupError) as lookup:
        live.move_to(99)
    assert lookup.value.code == "paragraph-not-found"
    with pytest.raises(HwpxTypeError) as typed:
        live.move_to("첫 문단")  # type: ignore[arg-type]
    assert typed.value.code == "paragraph-invalid-type"
    for offset in (-1, 10, True, 1.5):
        with pytest.raises(HwpxError) as bad:
            live.move_to(fresh.paragraphs[0], offset=offset)  # type: ignore[arg-type]
        assert bad.value.code == "paragraph-range-invalid"


def test_objects_do_not_go_into_a_memo() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("메모 글", anchor=doc.add_paragraph("글"), section=0)
    equation = doc.add_paragraph("").add_equation("x")
    with pytest.raises(HwpxValueError) as excinfo:
        equation.move_to(memo.paragraphs[0])
    assert excinfo.value.code == "shape-move-place-unsupported"


# -- objects: connectors -------------------------------------------------------------------------


def test_a_connector_lets_go_of_a_moved_shape_and_a_copied_group_keeps_its_own_links() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    left = paragraph.add_rectangle(2000, 2000, treat_as_char=False)
    right = paragraph.add_rectangle(2000, 2000, treat_as_char=False)
    left.set_position(horizontal_offset=0, vertical_offset=0)
    right.set_position(horizontal_offset=6000, vertical_offset=0)
    connector = paragraph.add_connector(left, right)
    ends = [end for end in connector.element if end.tag in (f"{HP}startPt", f"{HP}endPt")]
    assert ends[0].get("subjectIDRef") == left.inst_id

    left.move_to(doc.add_paragraph(""))

    assert ends[0].get("subjectIDRef") == "0" and ends[1].get("subjectIDRef") == right.inst_id
    _reopen(doc)


def test_a_copied_connector_lets_go_of_shapes_outside_the_copy() -> None:
    doc = HwpxDocument.open(HANCOM / "shape_curves_and_connectors.hwpx")
    connector = next(o for p in doc.paragraphs for o in p.objects
                     if isinstance(o, Shape) and o.shape_type == "connectLine")
    copy = connector.copy_to(doc.add_paragraph(""))
    for end in copy.element:
        if end.tag in (f"{HP}startPt", f"{HP}endPt"):
            assert end.get("subjectIDRef") == "0"
    _reopen(doc)


# -- objects: Hancom-saved documents ------------------------------------------------------------


def test_moving_an_equation_of_a_hancom_document_keeps_other_parts_byte_for_byte() -> None:
    doc = HwpxDocument.open(HANCOM / "equation_binom_upper.hwpx")
    before = _parts(doc.to_bytes())
    equation = doc.shapes.equations[0]
    source = equation.paragraph
    target = source.insert_after("옮겨 온 수식 앞")

    equation.move_to(target, offset=4)

    after = _parts(_reopen(doc).to_bytes())
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed == {"Contents/section0.xml"}
    again = HwpxDocument.open(doc.to_bytes())
    assert [e.script for e in again.shapes.equations] == [equation.script]


def test_copying_a_hancom_picture_into_a_cell_shares_its_image() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_cell_picture_among_text.hwpx")
    picture = doc.media.pictures[0]
    images = len(doc.media.images)
    before = _parts(doc.to_bytes())
    cell_paragraph = doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]

    copy = picture.copy_to(cell_paragraph)

    assert copy.item_id == picture.item_id
    after = _parts(_reopen(doc).to_bytes())
    assert len(HwpxDocument.open(doc.to_bytes()).media.images) == images
    assert {name for name in before if before[name] != after.get(name)} <= {"Contents/section0.xml"}


# -- paragraphs ----------------------------------------------------------------------------------


def test_move_after_moves_the_paragraph_itself() -> None:
    doc = HwpxDocument.new()
    a = doc.add_paragraph("가")
    b = _cached(doc.add_paragraph("나"))
    c = _cached(doc.add_paragraph("다"))
    b_id = b.element.get("id")

    b.move_after(c)

    assert [p.text for p in doc.paragraphs] == ["가", "다", "나"]
    assert doc.paragraphs[2].element is b.element and b.element.get("id") == b_id
    assert not _has_cache(b.element) and _has_cache(c.element)
    b.move_before(0)
    assert [p.text for p in doc.paragraphs] == ["나", "가", "다"]
    assert b.element.find(f"{HP}run/{HP}secPr") is not None  # it starts the section now
    assert a.element.find(f"{HP}run/{HP}secPr") is None
    _reopen(doc)


def test_the_first_paragraph_hands_its_section_settings_to_the_next() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("첫")
    second = doc.add_paragraph("둘")
    doc.add_paragraph("셋")

    first.move_after(2)

    assert [p.text for p in doc.paragraphs] == ["둘", "셋", "첫"]
    assert second.element.find(f"{HP}run/{HP}secPr") is not None
    assert first.element.find(f"{HP}run/{HP}secPr") is None
    again = _reopen(doc)
    assert again.sections[0].paragraphs[0].text == "둘"


def test_paragraph_moves_into_and_out_of_cells_and_keeps_one_in_each() -> None:
    doc = HwpxDocument.new()
    holder = _cached(doc.add_paragraph(""))
    table = holder.add_table(1, 2)
    left = table.cell(0, 0).paragraphs[0]
    mover = doc.add_paragraph("칸으로 갈 문단")

    mover.move_after(left)
    assert [p.text for p in table.cell(0, 0).paragraphs] == ["", "칸으로 갈 문단"]
    assert not _has_cache(holder.element)

    with pytest.raises(HwpxValueError) as excinfo:
        table.cell(0, 1).paragraphs[0].move_after(mover)
    assert excinfo.value.code == "paragraph-remove-last"

    mover.move_after(holder)
    assert [p.text for p in table.cell(0, 0).paragraphs] == [""]
    assert doc.paragraphs[-1].element is mover.element
    _reopen(doc)


def test_paragraph_move_refusals_and_no_ops() -> None:
    doc = HwpxDocument.new()
    holder = doc.add_paragraph("표를 품은 문단")
    table = holder.add_table(1, 1)
    with pytest.raises(HwpxValueError) as excinfo:
        holder.move_after(table.cell(0, 0).paragraphs[0])
    assert excinfo.value.code == "paragraph-move-into-itself"

    a = doc.add_paragraph("가")
    b = doc.add_paragraph("나")
    before = doc.to_bytes()
    b.move_after(a)  # already there
    a.move_before(b)
    a.move_after(a)
    assert doc.to_bytes() == before

    only = HwpxDocument.new()
    single = only.paragraphs[0]
    with pytest.raises(HwpxValueError) as excinfo:
        single.move_after(only.add_paragraph("", section=only.add_section()))
    assert excinfo.value.code == "paragraph-remove-last"

    memo = doc.notes.add_memo("메모", anchor=a, section=0)
    with pytest.raises(HwpxValueError) as excinfo:
        b.move_after(memo.paragraphs[0])
    assert excinfo.value.code == "paragraph-move-place-unsupported"


def test_a_paragraph_moved_to_another_section_takes_its_memo_along() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("머리")
    anchored = doc.add_paragraph("메모가 걸린 문단")
    memo = doc.notes.add_memo("확인", anchor=anchored, section=0)
    second = doc.add_section()
    landing = doc.add_paragraph("둘째 구역", section=second)

    anchored.move_after(landing)

    assert anchored.section.element is second.element
    assert doc.sections[0].memo_group is None
    assert [m.text for m in second.memos] == ["확인"]
    assert second.memos[0].paragraph is not None
    again = _reopen(doc)
    assert [m.text for m in again.sections[1].memos] == ["확인"]
    assert again.sections[0].memos == []
    del memo


def test_moving_a_paragraph_of_a_hancom_document_changes_only_its_section() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_cell_picture_among_text.hwpx")
    before = _parts(doc.to_bytes())
    paragraphs = doc.sections[0].paragraphs
    last = paragraphs[-1]
    last.move_before(paragraphs[1] if len(paragraphs) > 2 else paragraphs[0])
    after = _parts(_reopen(doc).to_bytes())
    assert {name for name in before if before[name] != after.get(name)} <= {"Contents/section0.xml"}


# -- memos ---------------------------------------------------------------------------------------


def test_an_unanchored_memo_moves_to_another_section_at_an_index() -> None:
    doc = HwpxDocument.new()
    first = doc.notes.add_memo("하나", section=0)
    second_section = doc.add_section()
    there = [doc.notes.add_memo(text, section=1) for text in ("가", "나")]

    first.move_to(1, index=1)

    assert doc.sections[0].memo_group is None  # an emptied group goes
    assert [m.text for m in second_section.memo_group.memos] == ["가", "하나", "나"]
    assert first.group.section.element is second_section.element
    first.move_to(second_section, index=0)
    assert [m.text for m in second_section.memo_group.memos] == ["하나", "가", "나"]
    again = _reopen(doc)
    assert [m.text for m in again.sections[1].memos] == ["하나", "가", "나"]
    del there


def test_an_anchored_memo_stays_with_its_anchor() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("고리 있음", anchor=doc.add_paragraph("글"), section=0)
    doc.notes.add_memo("다른 메모", section=0)
    doc.add_section()
    with pytest.raises(HwpxValueError) as excinfo:
        memo.move_to(1)
    assert excinfo.value.code == "note-memo-anchor-elsewhere"
    memo.move_to(0, index=1)  # within its own section it may change place
    assert [m.text for m in doc.sections[0].memo_group.memos] == ["다른 메모", "고리 있음"]
    assert memo.paragraph is not None


def test_memo_copy_to_makes_an_unanchored_copy_with_a_new_id() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("원본 메모", anchor=doc.add_paragraph("글"), section=0)
    doc.add_section()

    copy = doc.sections[0].memos[0].copy_to(1, index=0)

    assert isinstance(copy, Memo) and copy.text == "원본 메모" and copy.id != memo.id
    assert copy.paragraph is None
    assert [m.text for m in doc.sections[1].memo_group.memos] == ["원본 메모"]
    para_ids = {p.element.get("id") for p in memo.paragraphs}
    assert not para_ids & {p.element.get("id") for p in copy.paragraphs}
    _reopen(doc)


def test_memos_hancom_keeps_in_fields_copy_but_do_not_move() -> None:
    doc = HwpxDocument.open(HANCOM / "memos_in_fields.hwpx")
    memo = doc.sections[0].memos[0]
    assert type(memo).__name__ == "HwpxOxmlFieldMemo"
    doc.add_section()
    with pytest.raises(HwpxValueError) as excinfo:
        memo.move_to(1)
    assert excinfo.value.code == "note-memo-anchor-elsewhere"
    copy = memo.copy_to(1)
    assert copy.text == memo.text and copy.memo_shape_id_ref == memo.memo_shape_id_ref
    _reopen(doc)


def test_memo_index_and_section_refusals() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("메모", section=0)
    for bad in (-1, 5):
        with pytest.raises(HwpxLookupError) as excinfo:
            memo.copy_to(0, index=bad)
        assert excinfo.value.code == "note-memo-index-value"
    with pytest.raises(HwpxTypeError):
        memo.copy_to(0, index="0")  # type: ignore[arg-type]
    with pytest.raises(HwpxLookupError) as lookup:
        memo.move_to(3)
    assert lookup.value.code == "section-not-found"
    other = HwpxDocument.new()
    with pytest.raises(HwpxValueError):
        memo.move_to(other.sections[0])


# -- tables in map order ------------------------------------------------------------------------


def _map_order(doc: HwpxDocument) -> list:
    return [entry.table.element for entry in _collect_document_tables(doc)]


def test_with_nested_lists_the_tables_as_the_map_numbers_them() -> None:
    doc = HwpxDocument.new()
    outer = doc.add_paragraph("").add_table(2, 2)
    inner = outer.cell(0, 1).add_table(1, 1)
    inner.cell(0, 0).add_table(1, 1)
    outer.cell(1, 0).add_table(1, 1)
    doc.add_paragraph("").add_table(1, 1)

    tables = doc.tables.with_nested

    assert isinstance(tables, tuple) and all(isinstance(t, Table) for t in tables)
    assert [t.element for t in tables] == _map_order(doc)
    assert len(tables) == len(doc.tables.map()["tables"]) == 5
    assert len(doc.tables.all) == 2
    assert tables[1].element is inner.element
    assert any(tables[1].paragraph.element is p.element for p in outer.cell(0, 1).paragraphs)


@pytest.mark.parametrize("name", [
    "auto_grow_cell_filled.hwpx",
    "cell_border_vmerge_base.hwpx",
    "pages_cell_table_as_character_and_a_picture_behind_the_text.hwpx",
    "pages_cell_picture_in_a_table_as_character.hwpx",
])
def test_with_nested_matches_the_map_on_hancom_documents(name: str) -> None:
    doc = HwpxDocument.open(HANCOM / name)
    assert [t.element for t in doc.tables.with_nested] == _map_order(doc)
