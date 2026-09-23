# SPDX-License-Identifier: Apache-2.0
"""Opening HWP 5.0 (``.hwp``) documents through ``HwpxDocument.open``.

Every document here is synthetic: records are built field by field with the
same codecs the reader uses.
"""

from __future__ import annotations

import io
import struct
import warnings
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.hwp5 import bodytext as bt
from hwpx.hwp5 import cfb
from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import docinfo as di
from hwpx.hwp5 import records as rec
from hwpx.hwp5.errors import Hwp5ConversionWarning, Hwp5Error
from hwpx.hwp5.fileheader import FileHeader

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _docinfo() -> list[rec.Record]:
    fonts = [di.FaceName(0x01, "함초롬바탕") for _ in range(7)]
    char_shapes = [di.CharShape(font_ids=[0] * 7), di.CharShape(font_ids=[0] * 7, props=0x2, text_color=0x0000FF)]
    fill = di.BorderFill(fill=di.Fill(di.FILL_SOLID, 0x00FFFFFF, 0, -1, additional=b"", alphas=b"\0"))
    para = di.ParaShape(props1=0x100)
    mappings = [0, 1, 1, 1, 1, 1, 1, 1, 2, len(char_shapes), 1, 0, 0, 1, 1, 0, 0, 0]
    records = [
        rec.Record(rec.DOCUMENT_PROPERTIES, 0, di.DocumentProperties().encode()),
        rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", *mappings)),
    ]
    records += [rec.Record(rec.FACE_NAME, 1, font.encode()) for font in fonts]
    records += [rec.Record(rec.BORDER_FILL, 1, di.BorderFill().encode()), rec.Record(rec.BORDER_FILL, 1, fill.encode())]
    records += [rec.Record(rec.CHAR_SHAPE, 1, shape.encode()) for shape in char_shapes]
    records += [rec.Record(rec.TAB_DEF, 1, di.TabDef().encode())]
    records += [rec.Record(rec.PARA_SHAPE, 1, para.encode())]
    records += [rec.Record(rec.STYLE, 1, di.Style("바탕글", "Normal").encode())]
    return records


def _para_header(chars: int, char_shapes: int, *, lines: int = 1, mask: int = 0, breaks: int = 0) -> bytes:
    return struct.pack("<IIHBBHHHIH", chars, mask, 0, 0, breaks, char_shapes, 0, lines, 0, 0)


def _control_mask(text: bytes) -> tuple[int, int]:
    """The control-character mask (paragraph break excluded) and section/column break bits."""

    chunks, _ = bt.split_text(text)
    mask = 0
    for chunk in chunks:
        if chunk.kind != "text" and chunk.code != 13:
            mask |= 1 << chunk.code
    ids = {chunk.control_id for chunk in chunks}
    return mask, (1 if "secd" in ids else 0) | (2 if "cold" in ids else 0)


def _extended(code: int, ctrl: str) -> bytes:
    return struct.pack("<HI", code, bt.ctrl_word(ctrl)) + b"\0" * 8 + struct.pack("<H", code)


def _line_seg() -> bytes:
    return struct.pack("<IiiiiiiiI", 0, 0, 1000, 1000, 850, 600, 0, 42520, 0x60000)


def _paragraph(level: int, text: bytes, shapes: list[tuple[int, int]], controls: list[rec.Record]) -> list[rec.Record]:
    units = len(text) // 2
    mask, breaks = _control_mask(text)
    out = [rec.Record(rec.PARA_HEADER, level, _para_header(units, len(shapes), mask=mask, breaks=breaks))]
    if units > 1:
        out.append(rec.Record(rec.PARA_TEXT, level + 1, text))
    out.append(rec.Record(rec.PARA_CHAR_SHAPE, level + 1, b"".join(struct.pack("<II", p, s) for p, s in shapes)))
    out.append(rec.Record(rec.PARA_LINE_SEG, level + 1, _line_seg()))
    out.extend(controls)
    return out


def _u16(value: int) -> bytes:
    return struct.pack("<H", value)


def _section() -> list[rec.Record]:
    secd = struct.pack("<IIHHHIHHHHH", bt.ctrl_word("secd"), 0, 1134, 0, 0, 8000, 1, 0, 0, 0, 0) + b"\0" * 19
    page = struct.pack("<9II", 59528, 84186, 8504, 8504, 5668, 4252, 4252, 4252, 0, 0)
    note = struct.pack("<IHHHHiHHHBBI", 0, 0, 0, ord(")"), 1, -1, 850, 567, 283, 1, 1, 0)
    border = struct.pack("<IHHHHH", 1, 1417, 1417, 1417, 1417, 1)
    cold = struct.pack("<IHHHBBI", bt.ctrl_word("cold"), 0x1004, 0, 0, 0, 0, 0)
    first = _paragraph(
        0,
        _extended(2, "secd") + _extended(2, "cold") + _u16(13),
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, secd),
            rec.Record(rec.PAGE_DEF, 2, page),
            rec.Record(rec.FOOTNOTE_SHAPE, 2, note),
            rec.Record(rec.FOOTNOTE_SHAPE, 2, note),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.CTRL_HEADER, 1, cold),
        ],
    )
    # A tab stores its width, leader and type, padded with three spaces.
    tab = _u16(9) + struct.pack("<IBB", 4000, 0, 0) + " ".encode("utf-16-le") * 3 + _u16(9)
    body = "가나다 ".encode("utf-16-le") + "abc".encode("utf-16-le") + tab + "끝".encode("utf-16-le") + _u16(10)
    body += "둘째 줄".encode("utf-16-le") + _u16(13)
    second = _paragraph(0, body, [(0, 0), (4, 1), (7, 0)], [])
    common = struct.pack("<IIiiIIihhhhIi", bt.ctrl_word("tbl "), 0x082A2211, 0, 0, 42000, 3600, 0, 0, 0, 0, 0, 77, 0)
    common += _u16(0) + _u16(0)  # empty description, then two reserved bytes
    table = struct.pack("<IHHH4HHHH", 2, 1, 2, 0, 510, 510, 141, 141, 2, 1, 0)
    cells: list[rec.Record] = []
    for col, label in enumerate(("셀1", "셀2")):
        header = ct.CellHeader(1, 0x00200000, 0, col, 0, 1, 1, 21000, 3600, (510, 510, 141, 141), 1, 21000).encode()
        cells.append(rec.Record(rec.LIST_HEADER, 2, header))
        cells += _paragraph(2, label.encode("utf-16-le") + _u16(13), [(0, 0)], [])
    third = _paragraph(
        0,
        _extended(11, "tbl ") + _u16(13),
        [(0, 0)],
        [rec.Record(rec.CTRL_HEADER, 1, common), rec.Record(rec.TABLE, 2, table), *cells],
    )
    return first + second + third


def _field_end(ctrl: str, prop: int, editable: int, number: int = 0) -> bytes:
    params = struct.pack("<III", (bt.ctrl_word(ctrl) & 0xFFFFFF) | prop << 24, editable, number)
    return _u16(4) + params + _u16(4)


def _fields() -> list[rec.Record]:
    """A click-here field with a name and a hyperlink, each around some text."""

    text = _extended(3, "%clk") + "이름".encode("utf-16-le") + _field_end("%clk", 9, 1)
    text += " 링크 ".encode("utf-16-le") + _extended(3, "%hlk") + "누리집".encode("utf-16-le")
    text += _field_end("%hlk", 0, 0) + _u16(13)
    click = ct.FieldCtrl("%clk", 1, 9, "Clickhere:set:66:Direction:wstring:9:이름을 입력하세요 HelpState:wstring:0: ", 1234)
    link = ct.FieldCtrl("%hlk", 0, 0, "https\\://example.com/a;1;0;0;", 1235)
    return _paragraph(
        0,
        text,
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, click.encode()),
            rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("성명")),
            rec.Record(rec.CTRL_HEADER, 1, link.encode()),
        ],
    )


def _highlights(*, unmapped: bool = False) -> list[rec.Record]:
    """Two highlighter ranges in a paragraph of two runs; the first ends where
    the second run starts. *unmapped* adds a range tag kind OWPML has no form for."""

    text = "형광펜 칠한 글".encode("utf-16-le") + _u16(13)
    tags = [(0, 3, 2 << 24 | 0x00FFFF), (4, 7, 2 << 24 | 0xFFCCE5)]
    if unmapped:
        tags.insert(0, (0, 8, 0))
    records = _paragraph(0, text, [(0, 0), (3, 1)], [])
    header = bytearray(records[0].payload)
    struct.pack_into("<H", header, 14, len(tags))  # the range tag count
    records[0] = rec.Record(rec.PARA_HEADER, 0, bytes(header))
    records.append(rec.Record(rec.PARA_RANGE_TAG, 1, b"".join(struct.pack("<III", *tag) for tag in tags)))
    return records


def _markers() -> list[rec.Record]:
    """Page number place, page hiding, a new number, an auto number, a
    bookmark, an index mark and a dutmal in one paragraph."""

    text = _extended(21, "pgnp") + _extended(21, "pghd") + _extended(21, "nwno") + _extended(18, "atno")
    text += "쪽".encode("utf-16-le") + _extended(22, "bokm") + _extended(22, "idxm") + _extended(23, "tdut") + _u16(13)
    controls = [
        rec.Record(rec.CTRL_HEADER, 1, ct.PageNumberPosition(0x600, side_char=ord("-")).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.PageHiding(0x18).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.NewNumber(4, 12).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.AutoNumber(1, 1, suffix_char=ord(")")).encode()),
        rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bt.ctrl_word("bokm"))),
        rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("처음")),
        rec.Record(rec.CTRL_HEADER, 1, ct.IndexMark("가나", "다라").encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.Dutmal("협동조합", "coop", 1, 0, 0, 0, 1).encode()),
    ]
    return _paragraph(0, text, [(0, 0)], controls)


def _memo() -> list[rec.Record]:
    """A memo field; its body hangs on the paragraph after a ``MEMO_LIST`` record."""

    text = _extended(3, "%%me") + "검토".encode("utf-16-le") + _field_end("%%me", 0, 1, 1) + _u16(13)
    memo = ct.FieldCtrl("%unk", 1, 0, "", 4321, 1)
    records = _paragraph(0, text, [(0, 0)], [rec.Record(rec.CTRL_HEADER, 1, memo.encode())])
    body = ct.ListHeader(1, 0, bytes(10)).encode()
    records += [rec.Record(rec.MEMO_LIST, 1, struct.pack("<I", 1)), rec.Record(rec.LIST_HEADER, 1, body)]
    return records + _paragraph(1, "메모 내용".encode("utf-16-le") + _u16(13), [(0, 0)], [])


def _master_page() -> list[rec.Record]:
    """A master page: a paragraph list hung on the section's last paragraph."""

    header = struct.pack("<HIH", 1, 0, 0) + struct.pack("<II", 42520, 70868) + bytes(22)
    return [rec.Record(rec.LIST_HEADER, 1, header), *_paragraph(1, "바탕쪽".encode("utf-16-le") + _u16(13), [(0, 0)], [])]


def make_hwp(
    *,
    flags: int = 1,
    extra_controls: list[rec.Record] | None = None,
    fields: bool = False,
    highlights: bool = False,
    unmapped_range: bool = False,
    memo: bool = False,
    master_page: bool = False,
    label: bool = False,
    markers: bool = False,
) -> bytes:
    section = _section()
    if markers:
        section += _markers()
    if label:
        # A label sheet: the table carries the sheet layout as a parameter set.
        layout = dict(zip(ct.LABEL_ITEMS, (5670, 5670, 28346, 28346, 850, 850, 1, 2, 0, 59528, 84188)))
        index = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tbl ")
        section.insert(index + 1, rec.Record(rec.CTRL_DATA, 2, ct.label_parameter_set(layout)))
    if extra_controls:
        text = _extended(11, "gso ") + _u16(13)
        section += _paragraph(0, text, [(0, 0)], extra_controls)
    if fields:
        section += _fields()
    if highlights:
        section += _highlights(unmapped=unmapped_range)
    if memo:
        section += _memo()
    if master_page:
        section += _master_page()
    return _compound(section, flags=flags)


def _compound(section: list[rec.Record], *, flags: int = 1) -> bytes:
    compressed = bool(flags & 1)

    def pack(records: list[rec.Record]) -> bytes:
        raw = rec.serialize_records(records)
        return rec.deflate(raw) if compressed else raw

    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), flags).to_bytes()),
            ("DocInfo", pack(_docinfo())),
            ("BodyText/Section0", pack(section)),
            ("PrvText", "미리보기".encode("utf-16-le")),
        ]
    )


@pytest.mark.parametrize("flags", [0, 1])
def test_open_hwp_builds_the_document_model(flags: int) -> None:
    document = HwpxDocument.open(make_hwp(flags=flags))

    texts = ["".join(p.itertext()) for p in document.sections[0].element.iter(f"{HP}p")]
    assert "가나다 abc끝둘째 줄" in texts
    tab = next(document.sections[0].element.iter(f"{HP}tab"))
    assert tab.get("width") == "4000"
    assert tab.tail == "끝"
    assert len(document.sections) == 1
    [table] = [t for s in document.sections for t in s.element.iter(f"{HP}tbl")]
    assert table.get("rowCnt") == "1" and table.get("colCnt") == "2"
    cells = ["".join(tc.itertext()) for tc in table.iter(f"{HP}tc")]
    assert cells == ["셀1", "셀2"]
    assert document._hwp5_report is not None and not document._hwp5_report.unconverted


def test_runs_follow_the_char_shape_boundaries() -> None:
    document = HwpxDocument.open(make_hwp())
    section = document.sections[0].element
    paragraph = [p for p in section.iter(f"{HP}p") if "abc" in "".join(p.itertext())][0]
    runs = [(r.get("charPrIDRef"), "".join(r.itertext())) for r in paragraph.iter(f"{HP}run")]
    assert runs == [("0", "가나다 "), ("1", "abc"), ("0", "끝둘째 줄")]
    header = etree.fromstring(document.package.read("Contents/header.xml"))
    bold = header.find(f".//{HH}charPr[@id='1']")
    assert bold is not None and bold.find(f"{HH}bold") is not None
    assert bold.get("textColor") == "#FF0000"


def test_first_paragraph_carries_the_section_setup() -> None:
    document = HwpxDocument.open(make_hwp())
    first = next(document.sections[0].element.iter(f"{HP}p"))
    page = first.find(f"{HP}run/{HP}secPr/{HP}pagePr")
    assert page is not None and page.get("width") == "59528" and page.get("height") == "84186"
    col = first.find(f"{HP}run/{HP}ctrl/{HP}colPr")
    assert col is not None and col.get("colCount") == "1"


def test_open_from_a_path_and_a_stream(tmp_path: Path) -> None:
    data = make_hwp()
    path = tmp_path / "문서.hwp"
    path.write_bytes(data)
    assert HwpxDocument.open(path).paragraphs
    assert HwpxDocument.open(io.BytesIO(data)).paragraphs
    assert HwpxDocument.open(str(path)).paragraphs


def test_unconverted_controls_are_reported_not_dropped_silently() -> None:
    shape = rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bt.ctrl_word("gso ")) + b"\0" * 44)
    with pytest.warns(Hwp5ConversionWarning, match="control-gso x1"):
        document = HwpxDocument.open(make_hwp(extra_controls=[shape]))
    assert document._hwp5_report.unconverted["control-gso"] == 1


def test_fields_open_as_field_begin_and_end() -> None:
    document = HwpxDocument.open(make_hwp(fields=True))
    section = document.sections[0].element
    begins = list(section.iter(f"{HP}fieldBegin"))
    assert [(b.get("type"), b.get("name"), b.get("editable")) for b in begins] == [
        ("CLICK_HERE", "성명", "1"),
        ("HYPERLINK", "", "0"),
    ]
    params = [{p.get("name"): p.text for p in b.find(f"{HP}parameters")} for b in begins]
    assert params[0]["Prop"] == "9" and params[0]["Direction"] == "이름을 입력하세요"
    assert params[1]["Path"] == "https://example.com/a"
    assert params[1]["Category"] == "HWPHYPERLINK_TYPE_URL"
    ends = [e.get("beginIDRef") for e in section.iter(f"{HP}fieldEnd")]
    assert ends == ["1234", "1235"]
    assert "이름 링크 누리집" in [paragraph.text for paragraph in document.paragraphs]
    assert not document._hwp5_report.unconverted


def test_highlights_open_as_markpen_marks_inside_the_text() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(highlights=True, unmapped_range=True))
    section = document.sections[0].element
    paragraph = [p for p in section.iter(f"{HP}p") if "형광펜" in "".join(p.itertext())][0]
    layout = []
    for run in paragraph.iter(f"{HP}run"):
        for t in run.iter(f"{HP}t"):
            parts = [t.text or ""]
            for child in t:
                parts += [etree.QName(child).localname + ":" + (child.get("color") or ""), child.tail or ""]
            layout.append((run.get("charPrIDRef"), [part for part in parts if part]))
    # The first range ends where the second run starts, so its end stays in the first run.
    assert layout == [
        ("0", ["markpenBegin:#FFFF00", "형광펜", "markpenEnd:"]),
        ("1", [" ", "markpenBegin:#E5CCFF", "칠한 ", "markpenEnd:", "글"]),
    ]
    # A range tag kind OWPML has no element for is counted, without a warning.
    assert document._hwp5_report.dropped == {"range-tag-0": 1}


def test_a_label_sheet_table_keeps_its_layout() -> None:
    document = HwpxDocument.open(make_hwp(label=True))
    [label] = list(document.sections[0].element.iter(f"{HP}label"))
    assert label.getparent().tag == f"{HP}tbl" and label.getparent()[-1] is label
    assert dict(label.attrib) == {
        "topmargin": "5670",
        "leftmargin": "5670",
        "boxwidth": "28346",
        "boxlength": "28346",
        "boxmarginhor": "850",
        "boxmarginver": "850",
        "labelcols": "1",
        "labelrows": "2",
        "landscape": "WIDELY",
        "pagewidth": "59528",
        "pageheight": "84188",
    }
    assert not document._hwp5_report.unconverted


def test_numbering_bookmark_index_and_dutmal_controls_open() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(markers=True))
    section = document.sections[0].element

    def one(name: str) -> etree._Element:
        [element] = list(section.iter(f"{HP}{name}"))
        return element

    assert dict(one("pageNum").attrib) == {"pos": "BOTTOM_RIGHT", "formatType": "DIGIT", "sideChar": "-"}
    hiding = one("pageHiding")
    assert [hiding.get(name) for name in ("hideHeader", "hideBorder", "hideFill")] == ["0", "1", "1"]
    assert dict(one("newNum").attrib) == {"num": "12", "numType": "TABLE"}
    auto = one("autoNum")
    assert (auto.get("num"), auto.get("numType")) == ("1", "FOOTNOTE")
    assert auto.find(f"{HP}autoNumFormat").get("suffixChar") == ")"
    assert one("bookmark").get("name") == "처음"
    assert [key.text for key in one("indexmark")] == ["가나", "다라"]
    dutmal = one("dutmal")
    assert (dutmal.get("posType"), dutmal.get("align")) == ("BOTTOM", "LEFT")
    assert [dutmal.find(f"{HP}mainText").text, dutmal.find(f"{HP}subText").text] == ["협동조합", "coop"]


def test_a_table_name_is_counted_and_presentation_settings_are_reported() -> None:
    section = _section()
    table = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tbl ")
    section.insert(table + 1, rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("표 이름")))
    secd = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    # A presentation parameter set: set 0x021B holding the set 0x0219.
    section.insert(secd + 1, rec.Record(rec.CTRL_DATA, 2, bytes.fromhex("1b020100000019020080190200000000")))
    with pytest.warns(Hwp5ConversionWarning, match="presentation x1"):
        document = HwpxDocument.open(_compound(section))
    # The table name has no OWPML form: counted, not warned about.
    assert document._hwp5_report.dropped == {"table-name": 1}
    assert document._hwp5_report.unconverted == {"presentation": 1}


def test_memo_bodies_and_master_pages_are_reported() -> None:
    with pytest.warns(Hwp5ConversionWarning) as caught:
        document = HwpxDocument.open(make_hwp(memo=True, master_page=True))
    assert document._hwp5_report.unconverted == {"memo-body": 1, "master-page": 1}
    assert "memo-body x1" in str(caught[0].message)


def test_master_pages_under_the_section_definition_are_reported() -> None:
    section = _section()
    # The master page list follows the section definition's page border fills.
    index = max(i for i, r in enumerate(section) if r.tag == rec.PAGE_BORDER_FILL)
    section[index + 1 : index + 1] = [
        rec.Record(rec.LIST_HEADER, 2, _master_page()[0].payload),
        *_paragraph(2, "바탕쪽".encode("utf-16-le") + _u16(13), [(0, 0)], []),
    ]
    with pytest.warns(Hwp5ConversionWarning, match="master-page x1"):
        HwpxDocument.open(_compound(section))


def test_password_protected_hwp_is_refused_with_its_code() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(Hwp5Error) as info:
            HwpxDocument.open(make_hwp(flags=1 | 2))
    assert info.value.code == "hwp5-password"


def test_the_converted_package_saves_as_hwpx(tmp_path: Path) -> None:
    document = HwpxDocument.open(make_hwp())
    target = tmp_path / "out.hwpx"
    document.save_to_path(target)
    reopened = HwpxDocument.open(target)
    assert [p.text for p in reopened.paragraphs] == [p.text for p in document.paragraphs]
