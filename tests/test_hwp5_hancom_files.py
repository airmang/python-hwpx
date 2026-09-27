# SPDX-License-Identifier: Apache-2.0
"""HWP 5.0 files that Hancom saved (author, version and dates removed): they
open with the values Hancom wrote and save back to the same records."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import records as rec
from hwpx.hwp5.package import convert
from hwpx.hwp5.reader import read_hwp5
from hwpx.hwp5.writer import write_hwp5

FIXTURES = Path(__file__).parent / "fixtures" / "hwp5"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def _package(name: str) -> dict[str, bytes]:
    with zipfile.ZipFile(FIXTURES / name) as package:
        return {n: package.read(n) for n in package.namelist() if not n.endswith("/")}


def _records(data: bytes, tag: int) -> list[bytes]:
    doc = read_hwp5(data)
    return [r.payload for r in doc.docinfo.records if r.tag == tag]


def _line_caches(data: bytes) -> list[bytes | None]:
    """Each body paragraph's line cache record, None where it has none."""

    out: list[bytes | None] = []
    for section in read_hwp5(data).sections:
        records = section.records
        for i, record in enumerate(records):
            if record.tag == rec.PARA_HEADER and record.level == 0:
                cache = next(
                    (r for r in records[i + 1 : i + 6] if r.tag == rec.PARA_LINE_SEG and r.level == 1), None
                )
                out.append(cache.payload if cache is not None else None)
    return out


def _flags(head: etree._Element) -> list[str]:
    layout = head.find(f".//{HH}layoutCompatibility")
    assert layout is not None
    return [etree.QName(child).localname for child in layout]


def _objects(data: bytes) -> list[ct.ObjectCommon]:
    doc = read_hwp5(data)
    return [
        ct.ObjectCommon.decode(r.payload)
        for s in doc.sections
        for r in s.records
        if r.tag == rec.CTRL_HEADER and r.payload[:4] == b" osg"
    ]


@pytest.mark.parametrize(
    "name",
    [
        "shadow_pers_leftbottom_28346x42520.hwp",  # past 16 bits
        "shadow_shear_righttop_offset_left.hwp",  # moved to the left
        "shadow_pers_leftbottom_8000x1000.hwp",  # a lean that rounds up
    ],
)
def test_a_shadowed_shape_opens_with_its_own_margin_and_saves_back(name: str) -> None:
    data = (FIXTURES / name).read_bytes()
    files = convert(data).files
    [shape] = list(etree.fromstring(files["Contents/section0.xml"]).iter(f"{HP}rect"))
    margin = shape.find(f"{HP}outMargin")
    assert margin is not None
    assert [margin.get(side) for side in ("left", "right", "top", "bottom")] == ["0", "0", "0", "0"]
    assert [o.margins for o in _objects(write_hwp5(files))] == [o.margins for o in _objects(data)]


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("border_doublewave.hwp", "DOUBLEWAVE"),
        ("border_thick3d.hwp", "THICK3D"),
        ("border_thickrev3d.hwp", "THICKREV3D"),
        ("border_3d.hwp", "3D"),
        ("border_rev3d.hwp", "REV3D"),
    ],
)
def test_a_border_line_opens_with_hancoms_name_and_saves_back(name: str, line: str) -> None:
    data = (FIXTURES / name).read_bytes()
    files = convert(data).files
    head = etree.fromstring(files["Contents/header.xml"])
    kinds = {side.get("type") for fill in head.iter(f"{HH}borderFill") for side in fill if etree.QName(side).localname in SIDES}
    assert line in kinds
    theirs = [r.payload for r in read_hwp5(data).docinfo.records if r.tag == rec.BORDER_FILL]
    ours = [r.payload for r in read_hwp5(write_hwp5(files)).docinfo.records if r.tag == rec.BORDER_FILL]
    assert ours == theirs


def test_an_object_with_no_width_basis_is_saved_as_hancom_saves_it() -> None:
    """Hancom saved this rectangle, which had no widthRelTo, as sized against the page."""

    data = (FIXTURES / "rect_no_width_rel_to.hwp").read_bytes()
    files = convert(data).files
    root = etree.fromstring(files["Contents/section0.xml"])
    [rect] = list(root.iter(f"{HP}rect"))
    size = rect.find(f"{HP}sz")
    assert size is not None and size.get("widthRelTo") == "PAGE"
    del size.attrib["widthRelTo"]
    files["Contents/section0.xml"] = etree.tostring(root)
    assert [o.props for o in _objects(write_hwp5(files))] == [o.props for o in _objects(data)]


@pytest.mark.parametrize("name", ["word_compat_35", "word_compat_4"])
def test_word_layout_flags_open_and_save_as_hancom_writes_them(name: str) -> None:
    """Hancom saved the same document as .hwp and as .hwpx: the flags open as
    Hancom's own package lists them and save to its words."""

    data = (FIXTURES / f"{name}.hwp").read_bytes()
    package = _package(f"{name}.hwpx")
    opened = etree.fromstring(convert(data).files["Contents/header.xml"])
    assert _flags(opened) == _flags(etree.fromstring(package["Contents/header.xml"]))
    written = write_hwp5(package)
    for tag in (rec.COMPATIBLE_DOCUMENT, rec.LAYOUT_COMPATIBILITY):
        assert _records(written, tag) == _records(data, tag)


def test_word_layout_flags_in_groups_are_skipped_as_hancom_skips_them() -> None:
    """The package holds grouping elements and one flag straight under them; Hancom saved only that flag."""

    data = (FIXTURES / "word_compat_groups.hwp").read_bytes()
    written = write_hwp5(_package("word_compat_groups.hwpx"))
    assert _records(written, rec.LAYOUT_COMPATIBILITY) == _records(data, rec.LAYOUT_COMPATIBILITY)


@pytest.mark.parametrize("name", ["heads_and_at_least", "heads_no_head_marked"])
def test_every_paragraph_keeps_its_line_cache_as_hancom_saves_it(name: str) -> None:
    """Numbered, outline, bullet and plain paragraphs, one of them with no head but a head mark."""

    data = (FIXTURES / f"{name}.hwp").read_bytes()
    theirs = _line_caches(data)
    assert theirs and all(cache is not None for cache in theirs)
    assert _line_caches(write_hwp5(_package(f"{name}.hwpx"))) == theirs


def test_at_least_line_spacing_is_saved_as_hancom_saves_it() -> None:
    data = (FIXTURES / "heads_and_at_least.hwp").read_bytes()
    written = write_hwp5(_package("heads_and_at_least.hwpx"))
    assert _records(written, rec.PARA_SHAPE) == _records(data, rec.PARA_SHAPE)
