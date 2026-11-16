# SPDX-License-Identifier: Apache-2.0
"""Opening ``.hwp`` files into what Hancom's own HWPX conversion holds.

Each case is a record shape seen in public ``.hwp`` files whose Hancom
conversion (saved by Hangul itself) differed from ours; the documents here
are synthetic, built record by record.
"""

from __future__ import annotations

import io
import struct
import warnings
import zipfile

from lxml import etree

from hwpx import HwpxDocument
from hwpx.hwp5 import bodytext as bt
from hwpx.hwp5 import cfb
from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import docinfo as di
from hwpx.hwp5 import records as rec
from hwpx.hwp5.fileheader import FileHeader
from hwpx.hwp5.header_xml import build_header
from hwpx.hwp5.package import convert
from tests.test_hwp5_open import HH, HP, _compound, _docinfo, _extended, _field_end, _paragraph, _section, _u16

_HS = "{http://www.hancom.co.kr/hwpml/2011/section}"


def _with_ranges(paragraph: list[rec.Record], tags: list[tuple[int, int, int, int]]) -> list[rec.Record]:
    """*paragraph* with range tags (start, end, kind, value), in that order."""

    header = bytearray(paragraph[0].payload)
    struct.pack_into("<H", header, 14, len(tags))
    payload = b"".join(struct.pack("<III", start, end, kind << 24 | value) for start, end, kind, value in tags)
    return [rec.Record(rec.PARA_HEADER, paragraph[0].level, bytes(header)), *paragraph[1:],
            rec.Record(rec.PARA_RANGE_TAG, paragraph[0].level + 1, payload)]


def _change(kind: int, minute: int, fourth: int) -> rec.Record:
    """A tracked change made at 19:*minute* on 2023-02-07 (Korean time) by author 1;
    a shape change (18, 19) names the shape it made in its fourth word."""

    shape = kind in (18, 19)
    payload = struct.pack("<I5HH5H", kind, 2023, 2, 7, 19, minute, 1, 0, 4 if shape else 0, 0, fourth, 0)
    return rec.Record(rec.TRACK_CHANGE, 1, payload + (bytes(4) if shape else b""))


def _tracked(paragraphs: list[rec.Record], changes: list[rec.Record]) -> bytes:
    """A document that tracks changes: its body in ViewText, a stand-in in BodyText."""

    author = struct.pack("<I", 3) + "편집자".encode("utf-16-le") + struct.pack("<II", 1, 0)
    docinfo = _docinfo()
    counts = list(struct.unpack("<18i", docinfo[1].payload))
    counts[16], counts[17] = len(changes), 1
    docinfo[1] = rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", *counts))
    docinfo += [*changes, rec.Record(rec.TRACK_CHANGE_AUTHOR, 1, author)]
    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1 | 1 << 14).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(docinfo))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(_section()))),
            ("ViewText/Section0", rec.deflate(rec.serialize_records(_section() + paragraphs))),
        ]
    )


def _open(data: bytes) -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return HwpxDocument.open(data)


def _paragraphs(document: HwpxDocument, text: str) -> list[etree._Element]:
    """The paragraphs whose own text nodes read *text*."""

    def own_text(p: etree._Element) -> str:
        return "".join("".join(t.itertext()) for run in p.iterchildren(f"{HP}run") for t in run.iterchildren(f"{HP}t"))

    return [p for s in document.sections for p in s.element.iter(f"{HP}p") if own_text(p) == text]


def _parts(data: bytes) -> dict[str, etree._Element]:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return {name: etree.fromstring(package.read(name)) for name in package.namelist() if name.endswith(".xml")}


def _shape_changes() -> bytes:
    """A paragraph whose two character shape runs carry tracked character
    shape changes, under a paragraph shape change, with an insertion; then a
    paragraph with a deletion."""

    first = _paragraph(0, "가나다라".encode("utf-16-le") + _u16(13), [(0, 0), (2, 1)], [])
    first = _with_ranges(first, [(0, 2, 16, 1), (0, 1, 18, 2), (1, 2, 18, 3), (2, 5, 18, 2), (0, 5, 19, 4)])
    second = _with_ranges(_paragraph(0, "마바".encode("utf-16-le") + _u16(13), [(0, 0)], []), [(0, 2, 17, 5)])
    changes = [_change(16, 21, 0), _change(18, 22, 1), _change(18, 23, 0), _change(19, 24, 0), _change(17, 25, 1)]
    return _tracked(first + second, changes)


def test_character_shape_changes_open_on_their_runs_with_the_header_definitions() -> None:
    # Hancom's conversion of a .hwp with tracked character shape changes (kind 18) lists them as CharShape changes
    # naming the shape they made, and names on each run the last change that reaches into it (charTcId); the
    # paragraph names its paragraph shape change (paraTcId). Without the definitions Hangul draws deleted text.
    data = _shape_changes()
    document = _open(data)
    [first] = _paragraphs(document, "가나다라")
    assert first.get("paraTcId") == "4"
    assert [run.get("charTcId") for run in first.iter(f"{HP}run")] == ["3", "2"]
    # Every change range counts towards the mark ids, shape changes too.
    [second] = _paragraphs(document, "마바")
    assert [e.get("Id") for e in second.iter(f"{HP}deleteBegin")] == ["6"]
    assert dict(document.conversion_report.unconverted) == {} and dict(document.conversion_report.dropped) == {}

    head = etree.fromstring(convert(data).files["Contents/header.xml"])
    changes = [dict(e.attrib) for e in head.iter(f"{HH}trackChange")]
    assert changes == [
        {"type": "Insert", "date": "2023-02-07T10:21:00Z", "authorID": "1", "hide": "0", "id": "1"},
        {"type": "CharShape", "date": "2023-02-07T10:22:00Z", "authorID": "1", "hide": "0", "id": "2", "charshapeID": "1"},
        {"type": "CharShape", "date": "2023-02-07T10:23:00Z", "authorID": "1", "hide": "0", "id": "3", "charshapeID": "0"},
        {"type": "ParaShape", "date": "2023-02-07T10:24:00Z", "authorID": "1", "hide": "0", "id": "4", "parashapeID": "0"},
        {"type": "Delete", "date": "2023-02-07T10:25:00Z", "authorID": "1", "hide": "1", "id": "5"},
    ]
    assert [dict(e.attrib) for e in head.iter(f"{HH}trackChangeAuthor")] == [{"name": "편집자", "mark": "1", "id": "1"}]

    saved = HwpxDocument.open(document.to_bytes())
    assert [p.get("paraTcId") for p in _paragraphs(saved, "가나다라")] == ["4"]


def test_tracked_shape_changes_save_back_to_hwp_and_reopen_the_same() -> None:
    document = _open(_shape_changes())
    reopened = _open(document.to_bytes(format="hwp"))
    [first] = _paragraphs(reopened, "가나다라")
    assert first.get("paraTcId") == "4"
    assert [run.get("charTcId") for run in first.iter(f"{HP}run")] == ["3", "2"]
    head = _parts(reopened.to_bytes())["Contents/header.xml"]
    assert [e.get("type") for e in head.iter(f"{HH}trackChange")] == ["Insert", "CharShape", "CharShape", "ParaShape", "Delete"]
    assert [e.get("charshapeID") for e in head.iter(f"{HH}trackChange")][1:3] == ["1", "0"]


def test_marks_before_a_control_stay_in_text() -> None:
    # OWPML keeps change and highlighter marks only in text (hp:t); a deletion that begins at a field begins in a
    # text node of its own before the field, as Hancom writes it. A mark straight in the run is not read, and the
    # deleted content shows (the stray logo of a public document).
    text = _extended(3, "%clk") + "이름".encode("utf-16-le") + _field_end("%clk", 9, 1, 2) + "뒤".encode("utf-16-le") + _u16(13)
    click = ct.FieldCtrl("%clk", 1, 9, "Clickhere:set:0:", 1234, 2)
    paragraph = _paragraph(0, text, [(0, 0)], [rec.Record(rec.CTRL_HEADER, 1, click.encode())])
    data = _tracked(_with_ranges(paragraph, [(0, 10, 17, 1)]), [_change(17, 21, 1)])
    document = _open(data)
    [found] = _paragraphs(document, "이름뒤")
    marks = list(found.iter(f"{HP}deleteBegin", f"{HP}deleteEnd"))
    assert [etree.QName(m.getparent()).localname for m in marks] == ["t", "t"]
    begin_text = marks[0].getparent()
    assert etree.QName(begin_text.getnext()).localname == "ctrl"  # before the field
    assert marks[1].getparent().text == "이름"  # the end closes the field's text


def test_a_change_beginning_where_a_run_begins_begins_in_that_run() -> None:
    # Hancom puts what begins at a character shape boundary in the next run and what ends there in the run before.
    paragraph = _paragraph(0, "가나다".encode("utf-16-le") + _u16(13), [(0, 0), (2, 1)], [])
    data = _tracked(_with_ranges(paragraph, [(0, 2, 16, 1), (2, 4, 17, 2)]), [_change(16, 21, 0), _change(17, 22, 1)])
    [found] = _paragraphs(_open(data), "가나다")
    runs = [[etree.QName(e).localname for e in run.iter() if e.tag != f"{HP}run"] for run in found.iter(f"{HP}run")]
    assert runs == [["t", "insertBegin", "insertEnd"], ["t", "deleteBegin", "deleteEnd"]]


def test_the_run_of_a_paragraph_end_closes_with_text_after_a_control() -> None:
    # A paragraph holding a control whose last character shape covers only the paragraph end: Hancom writes that
    # run with an empty text node. A paragraph of plain text leaves it empty.
    text = _extended(3, "%clk") + "이름".encode("utf-16-le") + _field_end("%clk", 9, 1, 2) + "끝".encode("utf-16-le") + _u16(13)
    click = ct.FieldCtrl("%clk", 1, 9, "Clickhere:set:0:", 1234, 2)
    with_control = _paragraph(0, text, [(0, 0), (19, 1)], [rec.Record(rec.CTRL_HEADER, 1, click.encode())])
    plain = _paragraph(0, "글자".encode("utf-16-le") + _u16(13), [(0, 0), (2, 1)], [])
    document = _open(_compound(_section() + with_control + plain))
    [field_paragraph] = _paragraphs(document, "이름끝")
    [plain_paragraph] = _paragraphs(document, "글자")
    assert [len(run) for run in field_paragraph.iter(f"{HP}run")][-1] == 1
    assert field_paragraph.findall(f"{HP}run")[-1][0].tag == f"{HP}t"
    assert [len(run) for run in plain_paragraph.iter(f"{HP}run")] == [1, 0]


def test_border_and_fill_zero_refers_to_a_border_and_fill_of_nothing() -> None:
    # A .hwp refers to border and fill 0 for none (a page without a border, a shape without one); OWPML has no id 0,
    # so Hancom's conversion lists a border and fill of nothing and refers to that.
    section = _section()
    index = next(i for i, r in enumerate(section) if r.tag == rec.PAGE_BORDER_FILL)
    section[index] = rec.Record(rec.PAGE_BORDER_FILL, 2, struct.pack("<IHHHHH", 1, 1417, 1417, 1417, 1417, 0))
    parts = _parts(HwpxDocument.open(_compound(section)).to_bytes())
    fills = {e.get("id"): e for e in parts["Contents/header.xml"].iter(f"{HH}borderFill")}
    assert len(fills) == 3 and parts["Contents/header.xml"].find(f".//{HH}borderFills").get("itemCnt") == "3"
    blank = fills["3"]
    assert [(etree.QName(c).localname, c.get("type")) for c in blank] == [
        ("slash", "NONE"), ("backSlash", "NONE"), ("leftBorder", "NONE"), ("rightBorder", "NONE"),
        ("topBorder", "NONE"), ("bottomBorder", "NONE"), ("diagonal", "SOLID"),
    ]
    pages = [e.get("borderFillIDRef") for e in parts["Contents/section0.xml"].iter(f"{HP}pageBorderFill")]
    assert pages == ["3", "1", "1"]
    references = [e.get("borderFillIDRef") for part in parts.values() for e in part.iter() if e.get("borderFillIDRef") is not None]
    assert "0" not in references and set(references) <= set(fills)


def test_without_border_and_fill_zero_the_header_lists_only_the_documents_own() -> None:
    docinfo = _docinfo()
    index = next(i for i, r in enumerate(docinfo) if r.tag == rec.PARA_SHAPE)
    docinfo[index] = rec.Record(rec.PARA_SHAPE, 1, di.ParaShape(props1=0x100, border_fill_id=1).encode())
    data = cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(docinfo))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(_section()))),
        ]
    )
    head = _parts(HwpxDocument.open(data).to_bytes())["Contents/header.xml"]
    assert len(list(head.iter(f"{HH}borderFill"))) == 2
    assert head.find(f".//{HH}borderFills").get("itemCnt") == "2"


def test_a_character_shape_without_border_and_fill_refers_to_the_blank_one() -> None:
    info = di.decode_docinfo(rec.parse_records(rec.serialize_records(_docinfo()), "DocInfo"))
    info.char_shapes[0].border_fill_id = 0
    head = etree.fromstring(build_header(info, 1))
    assert [e.get("borderFillIDRef") for e in head.iter(f"{HH}charPr")] == ["3", "2"]
    assert len(list(head.iter(f"{HH}borderFill"))) == 3


def test_an_image_fill_keeps_contrast_before_brightness() -> None:
    # The image of a fill keeps its contrast first, then its brightness, as a picture does; Hancom's conversion
    # of a fill stored as (-50, 70) is contrast -50, brightness 70.
    raw = struct.pack("<IBbbBH", di.FILL_IMAGE, 1, -50, 70, 0, 1) + struct.pack("<I", 0) + b"\0"
    fill = di.Fill.read(di.Cursor(raw, "fill"))
    assert (fill.image_contrast, fill.image_bright) == (-50, 70)
    out = di.Builder()
    fill.write(out)
    assert out.bytes() == raw
    brush = etree.Element("borderFill")
    from hwpx.hwp5.header_xml import fill_brush

    fill_brush(brush, fill)
    image = brush.find(".//{http://www.hancom.co.kr/hwpml/2011/core}img")
    assert (image.get("bright"), image.get("contrast")) == ("70", "-50")


def _described_table(description: str) -> list[rec.Record]:
    """The table of the test section again, with a description."""

    section = _section()
    index = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tbl ")
    payload = section[index].payload
    # The table's common block ends with an empty description and two reserved bytes.
    words = description.encode("utf-16-le")
    section[index] = rec.Record(rec.CTRL_HEADER, 1, payload[:-4] + _u16(len(words) // 2) + words + _u16(0))
    return section


def test_a_table_keeps_its_description_without_carriage_returns() -> None:
    # Hancom's conversion keeps a table's description (hp:shapeComment, where a picture keeps its own) and writes
    # every description with line feeds only.
    document = HwpxDocument.open(_compound(_described_table("표 설명\r\n둘째 줄")))
    [table] = list(document.sections[0].element.iter(f"{HP}tbl"))
    children = [etree.QName(c).localname for c in table]
    assert children[:5] == ["sz", "pos", "outMargin", "shapeComment", "inMargin"]
    assert table.find(f"{HP}shapeComment").text == "표 설명\n둘째 줄"
    back = HwpxDocument.open(document.to_bytes(format="hwp"))
    assert back.sections[0].element.find(f".//{HP}tbl/{HP}shapeComment").text == "표 설명\n둘째 줄"


def test_an_equation_script_keeps_its_outer_spaces() -> None:
    # Hancom writes xml:space="preserve" on a script that starts or ends with a space (and only then).
    common = ct.ObjectCommon("eqed", 0x000A2211, 0, 0, 3000, 1500, 0, (56, 56, 0, 0), 301, 0, "", bytes(2))
    paragraphs: list[rec.Record] = []
    for script in ("a over b ", "a  over b"):
        equation = ct.EquationEdit(0, script, 1000, 0, 850, ct.EQUATION_VERSION, ct.EQUATION_FONT)
        paragraphs += _paragraph(
            0,
            _extended(11, "eqed") + _u16(13),
            [(0, 0)],
            [rec.Record(rec.CTRL_HEADER, 1, common.encode()), rec.Record(rec.EQEDIT, 2, equation.encode())],
        )
    parts = _parts(HwpxDocument.open(_compound(_section() + paragraphs)).to_bytes())
    scripts = [(e.text, e.get("{http://www.w3.org/XML/1998/namespace}space")) for e in parts["Contents/section0.xml"].iter(f"{HP}script")]
    assert scripts == [("a over b ", "preserve"), ("a  over b", None)]


def test_a_section_stream_with_two_section_definitions_opens_as_two_sections() -> None:
    # A file not written by Hancom can keep two sections in one stream, the second starting at a paragraph that
    # defines a section; Hancom's conversion starts a section there.
    data = HwpxDocument.open(_compound(_section() + _section())).to_bytes()
    parts = _parts(data)
    assert [name for name in parts if name.startswith("Contents/section")] == ["Contents/section0.xml", "Contents/section1.xml"]
    assert parts["Contents/header.xml"].get("secCnt") == "2"
    for name in ("Contents/section0.xml", "Contents/section1.xml"):
        assert len(list(parts[name].iter(f"{HP}secPr"))) == 1
        assert parts[name].tag == f"{_HS}sec"
    reopened = HwpxDocument.open(data)
    assert len(reopened.sections) == 2
