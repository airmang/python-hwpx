"""asks9 (가): what hwpx-school needs to stop reading and writing HWPX XML itself, added without changing what any
existing call writes -- set_position's flowWithText/allowOverlap, a paragraph's inner paragraphs, the models of the
object walks, run pieces' child index and objects (headers, footers, every field start), whether hp:pos and
treatAsChar are written, measured tab widths, and editing a header or footer python-hwpx 6.x wrote twice."""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import FieldControl, FieldParameter, Hyperlink

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _png() -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _section_xml(doc: HwpxDocument) -> str:
    return zipfile.ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/section0.xml").decode("utf-8")


# --------------------------------------------------------------------------- set_position(flow_with_text, allow_overlap)

def test_set_position_writes_flow_with_text_and_allow_overlap_as_hancom_does() -> None:
    doc = HwpxDocument.new()
    shape = doc.shapes.add_rectangle(3000, 2000, paragraph=doc.add_paragraph("가"))
    shape.set_position(treat_as_char=False, text_wrap="IN_FRONT_OF_TEXT", flow_with_text=True, allow_overlap=True)
    pos = shape.element.find(f"{HP}pos")
    assert (pos.get("flowWithText"), pos.get("allowOverlap")) == ("1", "1")
    assert (shape.position.flow_with_text, shape.position.allow_overlap) == (True, True)
    shape.set_position(flow_with_text=False)
    assert (pos.get("flowWithText"), pos.get("allowOverlap")) == ("0", "1")  # None leaves the other
    with pytest.raises(HwpxValueError) as caught:
        shape.set_position(allow_overlap=1)  # type: ignore[arg-type]
    assert caught.value.code == "shape-position-value"
    assert pos.get("allowOverlap") == "1"


def test_set_position_without_the_new_arguments_writes_what_it_wrote() -> None:
    def build(**extra) -> bytes:
        doc = HwpxDocument.new(seed=7)
        shape = doc.shapes.add_rectangle(3000, 2000, paragraph=doc.add_paragraph("가"))
        shape.set_position(treat_as_char=False, vertical_offset=100, **extra)
        return doc.to_bytes()

    assert build() == build(flow_with_text=None, allow_overlap=None)


# --------------------------------------------------------------------------- ObjectPosition: hp:pos and treatAsChar written

def test_position_tells_a_missing_hp_pos_and_a_missing_treat_as_char_apart() -> None:
    doc = HwpxDocument.new()
    shape = doc.shapes.add_rectangle(3000, 2000, paragraph=doc.add_paragraph("가"))
    assert (shape.position.has_position, shape.position.treat_as_char_written) == (True, True)
    pos = shape.element.find(f"{HP}pos")
    del pos.attrib["treatAsChar"]
    read = shape.position
    assert (read.treat_as_char, read.has_position, read.treat_as_char_written) == (False, True, False)
    shape.element.remove(pos)
    read = shape.position
    assert (read.treat_as_char, read.has_position, read.treat_as_char_written) == (False, False, False)
    assert "hasPosition" not in read.to_dict()  # to_dict() as it was


# --------------------------------------------------------------------------- paragraph.iter_paragraphs()

def test_a_paragraphs_inner_paragraphs_are_the_documents_walk_narrowed_to_it() -> None:
    doc = HwpxDocument.new()
    holder = doc.add_paragraph("바깥")
    table = holder.add_table(2, 2)
    table.cell(0, 0).paragraphs[0].text = "칸"
    table.cell(1, 1).paragraphs[0].add_table(1, 1).cell(0, 0).paragraphs[0].text = "안 칸"
    box = doc.add_paragraph("상자 문단").add_rectangle(8000, 4000)
    box.set_draw_text("상자 안")
    ours = [(p.where, p.row, p.col, p.depth, p.paragraph.text) for p in holder.iter_paragraphs()]
    whole = [(p.where, p.row, p.col, p.depth, p.paragraph.text) for p in doc.text.iter_paragraphs()
             if p.owner is not None and p.owner.paragraph.element is holder.element or (
                 p.table is not None and p.depth == 2)]
    assert ours == whole
    assert ours[0] == ("cell", 0, 0, 1, "칸") and ours[-1] == ("cell", 0, 0, 2, "안 칸")
    assert holder.element not in [p.paragraph.element for p in holder.iter_paragraphs()]
    assert [p.paragraph.text for p in doc.paragraphs[-1].iter_paragraphs(where="text_box")] == ["상자 안"]
    assert list(doc.add_paragraph("빈").iter_paragraphs()) == []
    with pytest.raises(HwpxValueError) as caught:
        list(holder.iter_paragraphs(where="nowhere"))
    assert caught.value.code == "text-place-invalid"


# --------------------------------------------------------------------------- iter_objects models

def test_the_object_walks_give_pictures_and_equations_as_paragraph_objects_does() -> None:
    from hwpx.model import Equation, InlineObject, Picture

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    picture = paragraph.add_picture(doc.media.add_image(_png(), "png"), width=1000, height=1000)
    equation = paragraph.add_equation("a over b")
    for places in (list(doc.text.iter_objects()), list(paragraph.iter_objects())):
        kinds = {place.kind: place.object for place in places}
        assert isinstance(kinds["picture"], Picture) and isinstance(kinds["picture"], InlineObject)
        assert kinds["picture"].item_id == picture.item_id
        assert isinstance(kinds["equation"], Equation) and kinds["equation"].script == equation.script
        assert kinds["picture"] == picture and kinds["equation"] == equation


# --------------------------------------------------------------------------- run.content: child_index, header/footer, fields

def test_pieces_say_which_t_or_ctrl_of_the_run_they_are_in() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("앞")
    element = run.element
    t_tag = f"{HP}t"
    second = element.makeelement(t_tag, {})
    second.text = "뒤"
    element.append(second)
    pieces = run.content
    assert [(p.text, p.child_index) for p in pieces] == [("앞", 0), ("뒤", 1)]
    assert pieces[0].to_dict() == {"kind": "text", "name": "", "container": "t", "text": "앞", "attributes": {}}


def test_a_header_or_footer_control_piece_holds_the_story_to_read_and_edit() -> None:
    doc = HwpxDocument.new()
    doc.page.set_footer(text="꼬리말")
    pieces = [p for para in doc.paragraphs for r in para.runs for p in r.content if p.kind == "footer"]
    assert len(pieces) == 1
    story = pieces[0].object
    assert [p.text for p in story.paragraphs] == ["꼬리말"]
    assert story == doc.page.footers()[0]


def test_every_field_start_carries_an_object_with_its_parameters() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞 ")
    paragraph.add_hyperlink("https://example.com", "링크")
    paragraph.add_form_field("성명", prompt="이름")
    begins = [p for r in paragraph.runs for p in r.content if p.kind == "field_begin"]
    by_type = {p.attribute("type"): p.object for p in begins}
    assert isinstance(by_type["HYPERLINK"], Hyperlink)
    assert FieldParameter("Path", "https://example.com") in by_type["HYPERLINK"].parameters
    click = by_type["CLICK_HERE"]
    assert isinstance(click, FieldControl) and click.field_type == "CLICK_HERE" and click.name == "성명"
    assert click.element is begins[-1].element
    assert all(isinstance(parameter, FieldParameter) for parameter in click.parameters)


# --------------------------------------------------------------------------- add_run(tab_widths=)

def test_measured_tab_widths_are_written_in_hancoms_form() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("가\t나\t다", tab_widths=[1200, 3400])
    tabs = run.element.findall(f"{HP}t/{HP}tab")
    assert [list(tab.attrib.items()) for tab in tabs] == [
        [("width", "1200"), ("leader", "0"), ("type", "1")], [("width", "3400"), ("leader", "0"), ("type", "1")]]
    assert run.text == "가\t나\t다"
    for bad in ([1], [1, 2, 3], [1, -1], [1, 1.5], [True, 1]):
        before = len(paragraph.runs)
        with pytest.raises(HwpxValueError) as caught:
            paragraph.add_run("a\tb\tc", tab_widths=bad)
        assert caught.value.code == "paragraph-tab-widths" and len(paragraph.runs) == before
    plain = paragraph.add_run("x\ty")
    assert plain.element.find(f"{HP}t/{HP}tab").attrib == {}  # without it, as before


# --------------------------------------------------------------------------- a header/footer python-hwpx 6.x wrote twice

def _twice_written_footer(text: str) -> HwpxDocument:
    """A document whose footer is kept under hp:secPr and in a body hp:ctrl, as python-hwpx 6.x wrote it
    (Hancom's saved documents keep only the control: 16 stories in 16 of hancom_saved's 1,257 files)."""

    import copy

    doc = HwpxDocument.new()
    doc.page.set_footer(text=text)
    control = next(node for node in doc.sections[0].element.iter(f"{HP}footer"))
    sec_pr = next(doc.sections[0].element.iter(f"{HP}secPr"))
    sec_pr.append(copy.deepcopy(control))
    return HwpxDocument.open(doc.to_bytes())


@pytest.mark.parametrize("way", ["text_walk", "page_footers", "run_piece"])
def test_editing_a_twice_written_footer_any_public_way_reaches_both_copies(way: str) -> None:
    doc = _twice_written_footer("옛 꼬리말")
    assert _section_xml(doc).count("옛 꼬리말") == 2
    if way == "text_walk":
        places = [p for p in doc.text.iter_paragraphs(where="footer")]
        assert len(places) == 1  # one copy is walked
        paragraph = places[0].paragraph
    elif way == "page_footers":
        paragraph = doc.page.footers()[0].paragraphs[0]
    else:
        piece = next(p for para in doc.paragraphs for r in para.runs for p in r.content if p.kind == "footer")
        paragraph = piece.object.paragraphs[0]
    paragraph.runs[0].text = "새 꼬리말"
    xml = _section_xml(doc)
    assert xml.count("새 꼬리말") == 2 and "옛 꼬리말" not in xml
    footers = re.findall(r"<hp:footer\b.*?</hp:footer>", xml, re.S)
    assert len(footers) == 2 and footers[0] == footers[1]
