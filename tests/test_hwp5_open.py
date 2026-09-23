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


def make_hwp(*, flags: int = 1, extra_controls: list[rec.Record] | None = None) -> bytes:
    section = _section()
    if extra_controls:
        text = _extended(11, "gso ") + _u16(13)
        section += _paragraph(0, text, [(0, 0)], extra_controls)
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
