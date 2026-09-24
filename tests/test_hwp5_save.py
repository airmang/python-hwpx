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
from tests.test_hwp5_open import HP, _IDENTITY, _docinfo, _extended, _paragraph, _picture, _section, _tracked_hwp, _u16, make_hwp

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
        {"text_art": True},
        {"forms": True},
        {"hidden_comment": True},
        {"picture_effects": True},
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


@pytest.mark.parametrize(
    ("old", "new", "kind"),
    [
        (b'textShape="RECTANGLE"', b'textShape="SPIRAL"', "textart/textShape"),
        (b'fontType="TTF"', b'fontType="OTF"', "textart/fontType"),
        (b'align="CENTER"', b'align="MIDDLE"', "textart/align"),
    ],
)
def test_a_text_art_name_with_no_code_is_refused(old: bytes, new: bytes, kind: str) -> None:
    files = convert(make_hwp(text_art=True)).files
    section = files["Contents/section0.xml"]
    assert section.count(old) == 1
    with pytest.raises(Hwp5Error) as refused:
        write_hwp5({**files, "Contents/section0.xml": section.replace(old, new)})
    assert refused.value.context["unsupported"] == {kind: 1}


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
        "<hp:p><hp:run><hp:container><hp:offset/><hp:orgSz/><hp:hologram/></hp:container></hp:run></hp:p>"
        "</hs:sec>"
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"hologram": 1}


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


_VIDEO_PATH = "C:" + chr(92) + "clips" + chr(92) + "intro.avi"


def _video_hwp() -> bytes:
    """A video that plays a linked file (the first BinData record) and shows
    an embedded picture (the second, whose stream is the first)."""

    records = _docinfo()
    counts = struct.unpack("<18i", records[1].payload)
    records[1] = rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", 2, *counts[1:]))
    link = di.BinDataItem(di.BIN_LINK, abs_path=_VIDEO_PATH, rel_path="..\\clips\\intro.avi")
    image = di.BinDataItem(di.BIN_EMBEDDING, bin_id=1, extension="png")
    records[2:2] = [rec.Record(rec.BIN_DATA, 1, link.encode()), rec.Record(rec.BIN_DATA, 1, image.encode())]
    common = ct.ObjectCommon("gso ", 0x040A2210, 0, 0, 22500, 15000, 0, (0, 0, 0, 0), 0, 0, "", bytes(2))
    component = sh.ShapeComponent("$vid", True, 0, 0, 0, 1, 22500, 15000, 22500, 15000, 1 << 19, 0, 11250, 7500, [_IDENTITY] * 3)
    controls = [
        rec.Record(rec.CTRL_HEADER, 1, common.encode()),
        rec.Record(rec.SHAPE_COMPONENT, 2, component.encode()),
        rec.Record(rec.VIDEO_DATA, 3, sh.Video(sh.VIDEO_LOCAL, 1, "", 2).encode()),
    ]
    section = _section() + _paragraph(0, _extended(11, "gso ") + _u16(13), [(0, 0)], controls)
    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(records))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(section))),
            ("BinData/BIN0001.png", rec.deflate(_PNG)),
        ]
    )


def _manifest_bins(files: dict[str, bytes]) -> list[dict[str, str]]:
    root = etree.fromstring(files["Contents/content.hpf"])
    return [dict(i.attrib) for i in root.iter("{http://www.idpf.org/2007/opf/}item") if "isEmbeded" in i.attrib]


def test_a_video_opens_with_its_linked_file_and_its_picture() -> None:
    converted = convert(_video_hwp())
    assert not converted.report.unconverted
    [video] = list(etree.fromstring(converted.files["Contents/section0.xml"]).iter(f"{HP}video"))
    attrs = {name: video.get(name) for name in ("videotype", "fileIDRef", "imageIDRef", "tag")}
    assert attrs == {"videotype": "Local", "fileIDRef": "video1", "imageIDRef": "image2", "tag": ""}
    assert [etree.QName(c).localname for c in video] == [
        "offset", "orgSz", "curSz", "flip", "rotationInfo", "renderingInfo", "sz", "pos", "outMargin",
    ]
    # The linked file is named by its path and has no part of its own.
    assert _manifest_bins(converted.files) == [
        {"id": "video1", "href": _VIDEO_PATH, "media-type": "video/avi", "isEmbeded": "0"},
        {"id": "image2", "href": "BinData/image2.png", "media-type": "image/png", "isEmbeded": "1"},
    ]
    assert sorted(name for name in converted.files if name.startswith("BinData/")) == ["BinData/image2.png"]


def test_a_video_and_its_linked_file_save_back_as_hwp() -> None:
    original = _video_hwp()
    written = read_hwp5(write_hwp5(convert(original).files))

    items = di.decode_docinfo(written.docinfo).bin_data
    assert [(i.kind, i.abs_path, i.bin_id, i.extension) for i in items] == [
        (di.BIN_LINK, _VIDEO_PATH, 0, ""),
        (di.BIN_EMBEDDING, "", 1, "png"),
    ]
    assert written.compound.has_stream("BinData/BIN0001.png")
    before = read_hwp5(original).sections[0].records
    after = written.sections[0].records
    assert [(r.tag, r.level) for r in after] == [(r.tag, r.level) for r in before]
    video = [r.payload for r in after if r.tag == rec.VIDEO_DATA]
    assert video == [sh.Video(sh.VIDEO_LOCAL, 1, "", 2).encode()]


def test_a_video_whose_file_the_package_does_not_list_is_refused() -> None:
    files = convert(_video_hwp()).files
    root = etree.fromstring(files["Contents/content.hpf"])
    [item] = [i for i in root.iter("{http://www.idpf.org/2007/opf/}item") if i.get("id") == "video1"]
    item.getparent().remove(item)
    files["Contents/content.hpf"] = etree.tostring(root)
    with pytest.raises(Hwp5Error) as refused:
        write_hwp5(files)
    assert refused.value.context["unsupported"] == {"video/missing-file": 1}


def test_a_web_video_keeps_its_tag_and_an_unknown_kind_is_damaged() -> None:
    web = sh.Video(sh.VIDEO_WEB, tag='<iframe src="https://example.com/v"></iframe>', image=3)
    assert sh.Video.decode(web.encode()) == web
    with pytest.raises(Hwp5Error):
        sh.Video.decode(struct.pack("<IHH", 7, 1, 2))


def test_picture_effects_the_record_cannot_hold_are_refused() -> None:
    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:pic><hp:effects>'
        '<hp:glow alpha="0.5" radius="500"><hp:effectsColor type="CMYK"><hp:cmyk c="1" m="2" y="3" k="4"/>'
        '<hp:effect type="ALPHA" value="0.5"/></hp:effectsColor></hp:glow>'
        "</hp:effects></hp:pic></hp:run></hp:p></hs:sec>"
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"pic/effects/CMYK": 1, "pic/effects/ALPHA": 1}


#: The class of a Paintbrush picture's storage (an OLE object that is no chart).
_PAINT_CLSID = bytes.fromhex("0a00030000000000c000000000000046")
_CHART_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'
)


def _storage(clsid: bytes, streams: list[tuple[str, bytes]]) -> bytes:
    """An OLE object's storage as HWP keeps it: a length word, then a compound
    file whose root entry has *clsid* (at offset 80 of the entry)."""

    data = bytearray(cfb.build_compound_file(streams))
    root = (struct.unpack_from("<I", data, 48)[0] + 1) * 512
    data[root + 80 : root + 96] = clsid
    return struct.pack("<I", len(data)) + bytes(data)


def _chart_storage() -> bytes:
    return _storage(sh.HANCOM_CHART, [("Contents", b"chart"), ("OOXMLChartContents", _CHART_XML)])


def _ole_hwp(storage: bytes, *, kind: int = 0) -> bytes:
    """One OLE object of type *kind* whose storage is the only BinData item."""

    records = _docinfo()
    counts = struct.unpack("<18i", records[1].payload)
    records[1] = rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", 1, *counts[1:]))
    records.insert(2, rec.Record(rec.BIN_DATA, 1, di.BinDataItem(di.BIN_STORAGE, bin_id=1, extension="OLE").encode()))
    common = ct.ObjectCommon("gso ", 0x040A2210, 0, 0, 60000, 40000, 0, (0, 0, 0, 0), 0, 0, "", bytes(2))
    component = sh.ShapeComponent("$ole", True, 0, 0, 0, 1, 7200, 7200, 7200, 7200, 0xB0000, 0, 0, 0, [_IDENTITY] * 3)
    ole = sh.OleObject(1 | kind << 16, (7200, 7200), 1, 0, 0, 0, 0)
    controls = [
        rec.Record(rec.CTRL_HEADER, 1, common.encode()),
        rec.Record(rec.SHAPE_COMPONENT, 2, component.encode()),
        rec.Record(rec.SHAPE_COMPONENT_OLE, 3, ole.encode()),
    ]
    section = _section() + _paragraph(0, _extended(11, "gso ") + _u16(13), [(0, 0)], controls)
    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(records))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(section))),
            ("BinData/BIN0001.OLE", rec.deflate(storage)),
        ]
    )


def _ole_elements(files: dict[str, bytes]) -> list[etree._Element]:
    return [e for name, part in files.items() if name.startswith("Contents/section") for e in etree.fromstring(part).iter(f"{HP}ole")]


def test_a_hancom_chart_opens_as_the_chart_with_its_ole_object_to_fall_back_to() -> None:
    storage = _chart_storage()
    files = convert(_ole_hwp(storage, kind=3)).files

    assert files["Chart/chart1.xml"] == _CHART_XML
    assert files["BinData/ole1.ole"] == storage
    [ole] = _ole_elements(files)
    default = ole.getparent()
    switch = default.getparent()
    assert (default.tag, switch.tag, switch.getparent().tag) == (f"{HP}default", f"{HP}switch", f"{HP}run")
    [case, _] = switch
    assert case.get(f"{HP}required-namespace") == "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"
    [chart] = case
    assert chart.get("chartIDRef") == "Chart/chart1.xml"
    assert [etree.QName(child).localname for child in chart] == ["sz", "pos", "outMargin"]
    # Hancom calls every chart UNKNOWN, whatever type its record keeps.
    assert (ole.get("objectType"), ole.get("binaryItemIDRef"), ole.get("drawAspect")) == ("UNKNOWN", "ole1", "CONTENT")
    extent = ole.find("{http://www.hancom.co.kr/hwpml/2011/core}extent")
    assert (extent.get("x"), extent.get("y")) == ("7200", "7200")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        HwpxDocument.open(_ole_hwp(storage))


def test_an_ole_object_that_is_no_chart_opens_as_itself() -> None:
    files = convert(_ole_hwp(_storage(_PAINT_CLSID, [("Contents", b"picture")]), kind=1)).files

    assert not any(name.startswith("Chart/") for name in files)
    [ole] = _ole_elements(files)
    assert ole.getparent().tag == f"{HP}run"
    assert ole.get("objectType") == "EMBEDDED"


@pytest.mark.parametrize("storage, kind", [(_chart_storage(), 0), (_storage(_PAINT_CLSID, [("Contents", b"picture")]), 1)])
def test_an_ole_object_saves_back_to_its_record_and_storage(tmp_path: Path, storage: bytes, kind: int) -> None:
    target = tmp_path / "ole.hwp"
    HwpxDocument.open(_ole_hwp(storage, kind=kind)).save_to_path(target)

    written = read_hwp5(target.read_bytes())
    [item] = di.decode_docinfo(written.docinfo).bin_data
    assert (item.kind, item.extension) == (di.BIN_STORAGE, "OLE")
    raw = written.compound.read("BinData/BIN0001.OLE")
    assert (rec.inflate(raw, "BinData/BIN0001.OLE") if written.header.compressed else raw) == storage
    [ole] = [r for s in written.sections for r in s.records if r.tag == rec.SHAPE_COMPONENT_OLE]
    assert ole.payload == sh.OleObject(1 | kind << 16, (7200, 7200), 1, 0, 0, 0, 0).encode()
    [header] = [r for s in written.sections for r in s.records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "gso "]
    # Hancom marks the object of a chart with bit 28 of its header.
    assert bool(ct.ObjectCommon.decode(header.payload).props & 1 << 28) == (kind == 0)


def test_a_chart_whose_part_no_longer_matches_its_ole_object_is_refused() -> None:
    files = convert(_ole_hwp(_chart_storage())).files
    files["Chart/chart1.xml"] = _CHART_XML.replace(b"/>", b"><c:roundedCorners val=\"1\"/></c:chartSpace>")

    with pytest.raises(Hwp5Error) as refused:
        write_hwp5(files)
    assert refused.value.context["unsupported"] == {"chart/changed": 1}


def test_a_chart_made_by_python_hwpx_saves_as_an_ole_object_holding_its_part(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("차트")
    document.shapes.add_chart(_CHART_XML, size=(30000, 20000))
    target = tmp_path / "chart.hwp"
    document.save_to_path(target)

    written = read_hwp5(target.read_bytes())
    [item] = di.decode_docinfo(written.docinfo).bin_data
    raw = written.compound.read(f"BinData/{item.stream_name}")
    stored = rec.inflate(raw, "BinData") if written.header.compressed else raw
    # A storage of the chart class holding only the chart part; Hancom draws
    # the chart from it and makes the other streams itself.
    assert cfb.CompoundFile(stored[4:]).root.clsid == sh.HANCOM_CHART
    assert cfb.CompoundFile(stored[4:]).stream_paths() == [sh.CHART_STREAM]
    assert sh.chart_xml(stored) == _CHART_XML
    [ole] = [r for s in written.sections for r in s.records if r.tag == rec.SHAPE_COMPONENT_OLE]
    assert ole.payload == sh.OleObject(1, (7200, 7200), 1, 0, 0, 0, 0).encode()
    [header] = [r for s in written.sections for r in s.records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "gso "]
    common = ct.ObjectCommon.decode(header.payload)
    assert (common.width, common.height, bool(common.props & 1 << 28)) == (30000, 20000, True)

    reopened = HwpxDocument.open(target)
    [chart] = [c for s in reopened.sections for c in s.element.iter(f"{HP}chart")]
    assert etree.QName(chart.getparent().getparent()).localname == "switch"
    assert reopened._package.read(chart.get("chartIDRef")) == _CHART_XML


def test_a_chart_whose_part_is_missing_is_refused() -> None:
    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run>'
        '<hp:chart id="1" chartIDRef="Chart/chart1.xml"/></hp:run></hp:p></hs:sec>'
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"chart": 1}


def _presentation_hwp(settings: ct.Presentation) -> bytes:
    """A document whose section definition holds *settings* as its parameter set."""

    section = _section()
    secd = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    section.insert(secd + 1, rec.Record(rec.CTRL_DATA, 2, settings.parameter_set().encode()))
    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(_docinfo()))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(section))),
        ]
    )


def _gradation() -> di.Fill:
    fill = di.Fill(di.FILL_GRADATION, grad_type=4, grad_angle=35, grad_center_x=80, grad_center_y=20, grad_step=255)
    fill.grad_colors, fill.additional, fill.alphas = [0xF1E6D4, 0xFFFFFF], bytes([50]), bytes(1)
    return fill


def test_presentation_settings_open_and_save_back_as_they_were(tmp_path: Path) -> None:
    settings = ct.Presentation(invert_text=1, show_time=0xFFFFFFFF, fill=_gradation())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(_presentation_hwp(settings))
    [element] = [e for s in document.sections for e in s.element.iter(f"{HP}presentation")]
    assert element.getparent().tag == f"{HP}secPr" and element.getparent()[-1] is element
    assert dict(element.attrib) == {
        "effect": "none", "soundIDRef": "", "invertText": "1", "autoshow": "0", "showtime": "4294967295", "applyto": "WholeDoc",
    }
    gradation = element.find("{http://www.hancom.co.kr/hwpml/2011/core}fillBrush/{http://www.hancom.co.kr/hwpml/2011/core}gradation")
    assert (gradation.get("type"), gradation.get("angle"), gradation.get("colorNum")) == ("SQUARE", "35", "2")
    assert [c.get("value") for c in gradation] == ["#D4E6F1", "#FFFFFF"]

    target = tmp_path / "presentation.hwp"
    document.save_to_path(target)
    written = read_hwp5(target.read_bytes())
    [data] = [
        c.payload
        for s in written.sections
        for r in s.records
        if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd"
        for c in r.children
        if c.tag == rec.CTRL_DATA
    ]
    assert data == settings.parameter_set().encode()


def test_presentation_settings_the_record_has_no_code_for_are_refused() -> None:
    from hwpx.hwp5.section_writer import build_section_records

    section = etree.fromstring(
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"><hp:p><hp:run><hp:secPr>'
        '<hp:presentation effect="overLeft" soundIDRef="" invertText="0" autoshow="0" showtime="0" applyto="WholeDoc">'
        '<hc:fillBrush><hc:winBrush faceColor="#FFFFFF" hatchColor="#FFFFFF" alpha="0"/></hc:fillBrush></hp:presentation>'
        "<hp:unknownPart/></hp:secPr></hp:run></hp:p></hs:sec>"
    )
    _, unsupported = build_section_records(section)
    assert unsupported == {"presentation": 1, "secPr/unknownPart": 1}


def test_parameter_sets_keep_their_arrays_and_binary_items() -> None:
    ps = ct.ParameterSet(
        0x0266,
        [
            ct.ParameterItem(0x4008, ct.PIT_ARRAY, ct.ParameterArray([(5, 0xFF0000), (5, 0)])),
            ct.ParameterItem(0x401E, ct.PIT_BINARY, b""),
        ],
    )
    payload = ps.encode()
    assert payload == bytes.fromhex("660202000000" "08400180" "02000000" "05000000ff00" "050000000000" "1e400280" "0000")
    assert ct.ParameterSet.decode(payload) == ps
    # hp:parameterset has no form for them, so a drawing object reports such a set.
    assert not ps.plain()


def test_a_header_python_hwpx_also_keeps_in_the_section_properties_is_written_once(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    document.page.set_header(text="머리말")
    target = tmp_path / "header.hwp"
    document.save_to_path(target)

    written = read_hwp5(target.read_bytes())
    heads = [r for s in written.sections for r in s.records if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "head"]
    assert len(heads) == 1
    reopened = HwpxDocument.open(target)
    assert ["".join(h.itertext()) for s in reopened.sections for h in s.element.iter(f"{HP}header")] == ["머리말"]


def test_the_lists_of_characters_kept_off_line_ends_open_and_save_back() -> None:
    words = di.ForbiddenChars(("", "", "!%),.:;?", "$([{"))
    records = _docinfo()
    records.insert(len(records), rec.Record(rec.FORBIDDEN_CHAR, 1, words.encode()))
    data = cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(records))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(_section()))),
        ]
    )
    files = convert(data).files
    head = etree.fromstring(files["Contents/header.xml"])
    listing = [w.text for w in head.iter("{http://www.hancom.co.kr/hwpml/2011/head}forbiddenWord")]
    # An empty list is written as a space, as Hancom does.
    assert listing == ["IAA=", "IAA=", "IQAlACkALAAuADoAOwA/AA==", "JAAoAFsAewA="]

    written = read_hwp5(write_hwp5(files))
    [record] = [r for r in written.docinfo.records if r.tag == rec.FORBIDDEN_CHAR]
    assert record.payload == words.encode()


def test_a_style_language_past_the_signed_range_opens_unsigned_and_saves_back() -> None:
    records = _docinfo()
    index = next(i for i, r in enumerate(records) if r.tag == rec.STYLE)
    records[index] = rec.Record(rec.STYLE, 1, di.Style("바탕글", "Normal", lang_id=0x8C00).encode())
    data = cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), 1).to_bytes()),
            ("DocInfo", rec.deflate(rec.serialize_records(records))),
            ("BodyText/Section0", rec.deflate(rec.serialize_records(_section()))),
        ]
    )
    files = convert(data).files
    [style] = etree.fromstring(files["Contents/header.xml"]).iter("{http://www.hancom.co.kr/hwpml/2011/head}style")
    assert style.get("langID") == "35840"

    written = read_hwp5(write_hwp5(files))
    assert [s.lang_id for s in di.decode_docinfo(written.docinfo).styles] == [0x8C00]


def test_tracked_changes_save_back_with_their_list_marks_and_stand_in() -> None:
    data = _tracked_hwp()
    written = read_hwp5(write_hwp5(convert(data).files))
    original = read_hwp5(data)
    assert written.header.has("track_changes")

    def listed(doc, tag):
        return [r.payload for r in doc.docinfo.records if r.tag == tag]

    for tag in (rec.TRACK_CHANGE, rec.TRACK_CHANGE_AUTHOR):
        assert listed(written, tag) == listed(original, tag)
    # BodyText holds a stand-in: the first paragraph with only its section and
    # column definitions; the body, with its change marks, is in ViewText.
    body = rec.parse_records(rec.inflate(written.compound.read("BodyText/Section0"), "BodyText"), "BodyText")
    assert [r.tag for r in body.records if r.level < 2] == [
        rec.PARA_HEADER, rec.PARA_TEXT, rec.PARA_CHAR_SHAPE, rec.CTRL_HEADER, rec.CTRL_HEADER,
    ]
    [tags] = [r.payload for s in written.sections for r in s.records if r.tag == rec.PARA_RANGE_TAG]
    assert tags == struct.pack("<III", 0, 2, 16 << 24 | 1)


def test_tracked_change_times_are_kept_in_local_time_and_deletions_hidden() -> None:
    from hwpx.hwp5.docinfo_writer import track_changes

    head = etree.fromstring(
        '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"><hh:refList><hh:trackChanges itemCnt="2">'
        '<hh:trackChange type="Insert" date="2023-02-07T10:21:00Z" authorID="1" hide="0" id="1"/>'
        '<hh:trackChange type="Delete" date="2026-08-08 09:05:00" authorID="1" hide="0" id="2"/>'
        "</hh:trackChanges></hh:refList></hh:head>"
    )
    changes, _ = track_changes(head)
    # A time in UTC moves to Korean time; one without a zone is local already.
    assert [(c.kind, c.time, c.words[3]) for c in changes] == [(16, (2023, 2, 7, 19, 21), 0), (17, (2026, 8, 8, 9, 5), 1)]


def test_a_document_saves_as_hwp_to_a_stream_and_to_bytes() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("스트림 문단")
    data = document.to_bytes(format="hwp")
    stream = io.BytesIO()
    assert document.save_to_stream(stream, format="hwp") is stream

    for blob in (data, stream.getvalue()):
        assert blob[:8] == cfb.SIGNATURE
        assert "스트림 문단" in _texts(HwpxDocument.open(blob))
    # HWPX stays the default.
    assert document.to_bytes()[:2] == b"PK"


def test_an_unknown_save_format_is_refused_before_anything_is_written() -> None:
    from hwpx.errors import HwpxValueError

    document = HwpxDocument.new()
    stream = io.BytesIO()
    with pytest.raises(HwpxValueError) as refused:
        document.save_to_stream(stream, format="pdf")  # type: ignore[arg-type]
    assert refused.value.code == "save-format-unsupported"
    assert stream.getvalue() == b""
    with pytest.raises(HwpxValueError):
        document.to_bytes(format="HWP")  # type: ignore[arg-type]


def test_hwp_bytes_are_refused_for_content_the_writer_cannot_express() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    section = document.sections[0].element
    settings = etree.SubElement(next(section.iter(f"{HP}secPr")), f"{HP}presentation")
    settings.set("effect", "overLeft")
    document.sections[0].mark_dirty()
    with pytest.raises(Hwp5Error) as refused:
        document.to_bytes(format="hwp")
    assert refused.value.code == "hwp5-write-unsupported"


def test_the_conversion_report_is_read_only_and_only_for_hwp() -> None:
    import dataclasses

    assert HwpxDocument.new().conversion_report is None
    report = HwpxDocument.open(make_hwp()).conversion_report
    assert report is not None
    assert dict(report.unconverted) == {} and dict(report.dropped) == {}
    with pytest.raises(TypeError):
        report.unconverted["shape"] = 1  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.dropped = {}  # type: ignore[misc]


def test_the_hwp_error_and_warning_are_exported_at_the_top_level() -> None:
    import hwpx
    from hwpx.hwp5 import errors

    assert hwpx.Hwp5Error is errors.Hwp5Error
    assert hwpx.Hwp5ConversionWarning is errors.Hwp5ConversionWarning


def test_the_package_layer_points_an_hwp_file_to_the_document() -> None:
    from hwpx.opc.package import HwpxPackage

    with pytest.raises(zipfile.BadZipFile, match="HwpxDocument.open"):
        HwpxPackage.open(make_hwp())
