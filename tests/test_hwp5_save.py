# SPDX-License-Identifier: Apache-2.0
"""Saving documents as HWP 5.0 (``.hwp``) through ``save_to_path``."""

from __future__ import annotations

import base64
import io
import struct
import warnings
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.hwp5 import bodytext as bt
from hwpx.hwp5 import cfb
from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import docinfo as di
from hwpx.hwp5 import shapes as sh
from hwpx.hwp5 import records as rec
from hwpx.hwp5.errors import Hwp5Error
from hwpx.hwp5.fileheader import FileHeader, parse_file_header
from hwpx.hwp5.package import convert
from hwpx.hwp5.reader import read_hwp5
from hwpx.hwp5.writer import write_hwp5
from tests.test_hwp5_open import HP, _docinfo, _picture, _section, make_hwp

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _texts(document: HwpxDocument) -> list[str]:
    return ["".join(p.itertext()) for s in document.sections for p in s.element.iter(f"{HP}p")]


def test_a_new_document_saves_as_hwp_and_reopens(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    document.add_paragraph("둘째 문단")
    table = document.add_table(2, 2)
    table.set_cell_text(0, 0, "왼쪽 위")
    table.set_cell_text(1, 1, "오른쪽 아래")
    target = tmp_path / "새 문서.hwp"

    assert document.save_to_path(target) == target

    data = target.read_bytes()
    assert data[:8] == cfb.SIGNATURE
    header = parse_file_header(cfb.CompoundFile(data).read("FileHeader"))
    assert header.version == (5, 1, 1, 0) and header.compressed
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reopened = HwpxDocument.open(target)
    texts = _texts(reopened)
    assert "첫 문단" in texts and "둘째 문단" in texts
    cells = ["".join(tc.itertext()) for s in reopened.sections for tc in s.element.iter(f"{HP}tc")]
    assert cells == ["왼쪽 위", "", "", "오른쪽 아래"]


@pytest.mark.parametrize(
    "extras",
    [
        {},
        {"fields": True},
        {"highlights": True},
        {"label": True},
        {"markers": True},
        {"text_box": True},
        {"picture": True},
        {"memo": True},
        {"master_page": True},
        {"memo": True, "master_page": True},
        {"compose": True},
        {"drawings": True},
        {"forms": True},
        {"hidden_comment": True},
    ],
)
def test_hwp_to_hwpx_to_hwp_keeps_the_section_records(extras: dict[str, bool]) -> None:
    original = make_hwp(**extras)
    written = write_hwp5(convert(original).files)

    before = read_hwp5(original).sections[0].records
    after = read_hwp5(written).sections[0].records
    assert [(r.tag, r.level) for r in after] == [(r.tag, r.level) for r in before]
    for a, b in zip(before, after):
        if a.tag == rec.PARA_HEADER:
            # Only the "last paragraph of the list" bit may differ: the sample leaves it unset.
            assert a.payload[4:] == b.payload[4:]
        else:
            assert a.payload == b.payload, rec.TAG_NAMES.get(a.tag)


def test_saving_as_hwp_keeps_text_formatting_and_tables(tmp_path: Path) -> None:
    source = HwpxDocument.open(make_hwp())
    target = tmp_path / "out.hwp"
    source.save_to_path(target)
    reopened = HwpxDocument.open(target)
    assert _texts(reopened) == _texts(source)
    runs = [
        (r.get("charPrIDRef"), "".join(r.itertext()))
        for s in reopened.sections
        for r in s.element.iter(f"{HP}run")
        if "".join(r.itertext())
    ]
    assert ("1", "abc") in runs


def test_content_the_writer_cannot_express_is_refused_before_writing(tmp_path: Path) -> None:
    from lxml import etree

    document = HwpxDocument.new()
    document.add_paragraph("양식 개체가 있는 문서")
    [run] = list(document.sections[0].element.iter(f"{HP}run"))[-1:]
    combo = etree.SubElement(run, f"{HP}comboBox")
    for value in ("가", "나"):  # an HWP combo box keeps one value, not a list
        etree.SubElement(combo, f"{HP}listItem", displayText=value, value=value)
    document.sections[0].mark_dirty()
    target = tmp_path / "양식.hwp"
    with pytest.raises(Hwp5Error) as info:
        document.save_to_path(target)
    assert info.value.code == "hwp5-write-unsupported"
    assert info.value.context["unsupported"].get("comboBox/listItem") == 1
    assert not target.exists()


def test_a_check_box_made_with_the_api_saves_as_hwp(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("양식 개체가 있는 문서")
    document.fields.add_check_box("동의")
    [before] = list(document.sections[0].element.iter(f"{HP}checkBtn"))
    target = tmp_path / "양식.hwp"
    document.save_to_path(target)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reopened = HwpxDocument.open(target)
    [after] = list(reopened.sections[0].element.iter(f"{HP}checkBtn"))
    assert dict(after.attrib) == dict(before.attrib)
    names = ("formCharPr", "sz", "pos", "outMargin")
    assert [dict(after.find(f"{HP}{n}").attrib) for n in names] == [dict(before.find(f"{HP}{n}").attrib) for n in names]


def test_master_pages_save_as_hwp_under_the_section_and_on_its_last_paragraph(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    both = document.oxml.add_master_page(text="모든 쪽", page_type="BOTH")
    third = document.oxml.add_master_page(text="셋째 쪽", page_type="OPTIONAL_PAGE", page_number=3, page_duplicate=True)
    for page_id in (both, third):
        document.sections[0].properties.add_master_page_reference(page_id)
    target = tmp_path / "바탕쪽.hwp"
    document.save_to_path(target)

    [section] = read_hwp5(target.read_bytes()).sections
    secd = next(r for r in section.records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    props, last_paragraph_pages = struct.unpack_from("<I", secd.payload, 4)[0], struct.unpack_from("<H", secd.payload, 30)[0]
    assert (props >> 29, last_paragraph_pages) == (1, 1)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reopened = HwpxDocument.open(target)
    pages = [page.to_model() for page in reopened.oxml.master_pages]
    assert [(p.type, p.page_number, p.page_duplicate, p.paragraph_texts) for p in pages] == [
        ("BOTH", 0, False, ("모든 쪽",)),
        ("OPTIONAL_PAGE", 3, True, ("셋째 쪽",)),
    ]


def test_a_master_page_without_its_part_is_refused(tmp_path: Path) -> None:
    document = HwpxDocument.open(make_hwp())
    document.sections[0].properties.add_master_page_reference("masterpage9")
    target = tmp_path / "바탕쪽.hwp"
    with pytest.raises(Hwp5Error) as info:
        document.save_to_path(target)
    assert info.value.context["unsupported"] == {"masterPage": 1}
    assert not target.exists()


def test_a_picture_saves_as_hwp_with_its_image(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("그림이 있는 문서")
    document.add_picture(_PNG, "png")
    target = tmp_path / "그림.hwp"
    document.save_to_path(target)
    compound = cfb.CompoundFile(target.read_bytes())
    assert any(path.startswith("BinData/") for path in compound.stream_paths())
    reopened = HwpxDocument.open(target)
    [pic] = [p for s in reopened.sections for p in s.element.iter(f"{HP}pic")]
    image = pic.find("{http://www.hancom.co.kr/hwpml/2011/core}img")
    assert image is not None and image.get("binaryItemIDRef", "").startswith("image")


def test_hwpx_targets_are_unchanged(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("HWPX로 저장")
    target = tmp_path / "out.hwpx"
    document.save_to_path(target)
    assert target.read_bytes()[:2] == b"PK"


def test_a_container_holding_a_shape_the_writer_cannot_write_is_refused() -> None:
    from lxml import etree

    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        "<hp:p><hp:run><hp:container><hp:offset/><hp:orgSz/><hp:textart/></hp:container></hp:run></hp:p>"
        "</hs:sec>"
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"textart": 1}


def test_an_unknown_element_directly_in_a_section_is_refused() -> None:
    from lxml import etree

    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        "<hp:p/><hp:memogroup/><hp:unknownPart/></hs:sec>"
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"sec/unknownPart": 1}


def test_overlapped_characters_the_record_cannot_hold_are_refused() -> None:
    from lxml import etree

    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run>'
        '<hp:compose circleType="SHAPE_STAR" composeText="가"/>'
        '<hp:compose circleType="CHAR" charSz="300" composeText="나"/>'
        '<hp:compose composeText="다"><hp:charPr prIDRef="0"/></hp:compose>'
        "</hp:run></hp:p></hs:sec>"
    )
    records, unsupported = build_section_records(section)
    assert unsupported == {"compose": 2}
    [compose] = [r for r in records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tcps"]
    value = ct.Compose.decode(compose.payload)
    assert (value.text, value.circle, value.kind, value.size) == ("\u25ef다", 1, 0, -4)
    assert value.char_shapes == [0] + [ct.NO_CHAR_SHAPE] * 9


def test_a_memo_made_with_the_api_saves_as_hwp_with_its_body(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("메모가 달린 문단")
    document.notes.add_memo("검토 의견", anchor=paragraph, author="검토자")
    target = tmp_path / "메모.hwp"
    document.save_to_path(target)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reopened = HwpxDocument.open(target)
    [memo] = [b for s in reopened.sections for b in s.element.iter(f"{HP}fieldBegin") if b.get("type") == "MEMO"]
    params = {p.get("name"): p.text or "" for p in memo.find(f"{HP}parameters")}
    assert params["Author"] == "검토자"
    assert "".join(memo.find(f"{HP}subList").itertext()) == "검토 의견"


def _merged_table(covered_text: str) -> str:
    cells = []
    for col, span, width, text in ((0, 2, 14400, "합친 칸"), (1, 1, 0, covered_text), (2, 1, 7200, "셋째")):
        cells.append(
            f'<hp:tc><hp:subList><hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="0"/><hp:cellSpan colSpan="{span}" rowSpan="1"/>'
            f'<hp:cellSz width="{width}" height="{3600 if width else 0}"/></hp:tc>'
        )
    return (
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run>'
        f'<hp:tbl rowCnt="1" colCnt="3"><hp:tr>{"".join(cells)}</hp:tr></hp:tbl>'
        "</hp:run></hp:p></hs:sec>"
    )


def test_an_empty_cell_under_another_cells_span_is_left_out() -> None:
    from lxml import etree

    from hwpx.hwp5.section_writer import build_section_records

    records, unsupported = build_section_records(etree.fromstring(_merged_table("")))
    assert unsupported == {}
    [table] = [r for r in records if r.tag == rec.TABLE]
    assert struct.unpack_from("<HHH", table.payload, 4)[:2] == (1, 3)
    assert struct.unpack_from("<H", table.payload, 18)[0] == 2
    cells = [ct.CellHeader.decode(r.payload) for r in records if r.tag == rec.LIST_HEADER]
    assert [(c.col, c.col_span) for c in cells] == [(0, 2), (2, 1)]

    _, unsupported = build_section_records(etree.fromstring(_merged_table("가려진 글")))
    assert unsupported == {"tc/covered": 1}


@pytest.mark.parametrize(
    ("circle", "text", "record"),
    [
        ("CHAR", "가나", "\u3000가나"),
        ("SHAPE_LIGHT", "가", "\u263c가"),
        ("SHAPE_CIRCLE", "1", "\u2460"),
        ("SHAPE_CIRCLE", "12", "\U000f0289\U000f0294"),
        ("SHAPE_RECTANGLE", "3", "\U000f02b3"),
        ("SHAPE_CIRCLE", "77", "\u25ef77"),
    ],
)
def test_overlapped_characters_are_written_behind_their_frame(circle: str, text: str, record: str) -> None:
    from lxml import etree

    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run>'
        f'<hp:compose circleType="{circle}" composeText="{text}"/></hp:run></hp:p></hs:sec>'
    )
    records, unsupported = build_section_records(section)
    assert unsupported == {}
    [compose] = [r for r in records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tcps"]
    assert ct.Compose.decode(compose.payload).text == record


def test_binary_items_are_numbered_by_their_place() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("그림이 있는 문서")
    document.add_picture(_PNG, "png")
    stream = io.BytesIO()
    document.save_to_stream(stream)
    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as package:
        files = {name: package.read(name) for name in package.namelist()}
    # Another tool may name the only image item BIN0002.
    [(item_id, href)] = [
        (i.get("id"), i.get("href"))
        for i in etree.fromstring(files["Contents/content.hpf"]).iter("{http://www.idpf.org/2007/opf/}item")
        if (i.get("href") or "").startswith("BinData/")
    ]
    files["Contents/content.hpf"] = files["Contents/content.hpf"].replace(f'id="{item_id}"'.encode(), b'id="BIN0002"')
    files["Contents/content.hpf"] = files["Contents/content.hpf"].replace(href.encode(), b"BinData/BIN0002.png")
    files["Contents/section0.xml"] = files["Contents/section0.xml"].replace(f'"{item_id}"'.encode(), b'"BIN0002"')
    files["BinData/BIN0002.png"] = files.pop(href)

    written = read_hwp5(write_hwp5(files))
    assert [item.bin_id for item in di.decode_docinfo(written.docinfo).bin_data] == [1]
    assert written.compound.has_stream("BinData/BIN0001.png")
    [picture] = [r for s in written.sections for r in s.records if r.tag == rec.SHAPE_COMPONENT_PICTURE]
    assert sh.Picture.decode(picture.payload).bin_id == 1


def test_a_picture_finds_its_image_by_the_place_of_its_bindata_record() -> None:
    # The only BinData record keeps id 5; a picture refers to it by its place, 1.
    records = _docinfo()
    counts = struct.unpack("<18i", records[1].payload)
    records[1] = rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", 1, *counts[1:]))
    records.insert(2, rec.Record(rec.BIN_DATA, 1, di.BinDataItem(di.BIN_EMBEDDING, bin_id=5, extension="png").encode()))
    section = _section() + _picture()
    index = next(i for i, r in enumerate(section) if r.tag == rec.SHAPE_COMPONENT_PICTURE)
    picture = sh.Picture.decode(section[index].payload)
    picture.bin_id = 1
    section[index] = rec.Record(rec.SHAPE_COMPONENT_PICTURE, section[index].level, picture.encode())
    data = cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(records))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(section))),
            ("BinData/BIN0005.png", rec.deflate(_PNG)),
        ]
    )
    files = convert(data).files
    assert files["BinData/image1.png"] == _PNG
    [image] = [
        i for name, part in files.items() if name.startswith("Contents/section")
        for i in etree.fromstring(part).iter("{http://www.hancom.co.kr/hwpml/2011/core}img")
    ]
    assert image.get("binaryItemIDRef") == "image1"
