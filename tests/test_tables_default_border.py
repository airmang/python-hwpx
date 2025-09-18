"""Integration tests for automatic table border fills."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP = f"{{{HP_NS}}}"
HH = f"{{{HH_NS}}}"


def test_add_table_injects_basic_border_fill_when_missing() -> None:
    document = HwpxDocument.new()

    header = document.headers[0]
    ref_list = header.element.find(f"{HH}refList")
    if ref_list is not None:
        existing = ref_list.find(f"{HH}borderFills")
        if existing is not None:
            ref_list.remove(existing)
    header.reset_dirty()

    section = document.sections[0]
    section.reset_dirty()

    table = document.add_table(2, 2, section=section)
    assert table is not None

    updates = document.oxml.serialize()

    assert header.part_name in updates
    header_root = ET.fromstring(updates[header.part_name])

    border_fills_element = header_root.find(f".//{HH}borderFills")
    assert border_fills_element is not None
    assert border_fills_element.get("itemCnt") == "1"

    border_fill_element = border_fills_element.find(f"{HH}borderFill")
    assert border_fill_element is not None
    border_id = border_fill_element.get("id")
    assert border_id == "0"
    assert border_fill_element.get("threeD") == "0"
    assert border_fill_element.get("shadow") == "0"
    assert border_fill_element.get("centerLine") == "NONE"
    assert border_fill_element.get("breakCellSeparateLine") == "0"

    slash = border_fill_element.find(f"{HH}slash")
    assert slash is not None
    assert slash.get("type") == "NONE"

    back_slash = border_fill_element.find(f"{HH}backSlash")
    assert back_slash is not None
    assert back_slash.get("type") == "NONE"

    for child_name in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
        child = border_fill_element.find(f"{HH}{child_name}")
        assert child is not None
        assert child.get("type") == "SOLID"
        assert child.get("width") == "0.12 mm"
        assert child.get("color") == "#000000"

    diagonal = border_fill_element.find(f"{HH}diagonal")
    assert diagonal is not None
    assert diagonal.get("type") == "SOLID"
    assert diagonal.get("width") == "0.1 mm"
    assert diagonal.get("color") == "#000000"

    assert section.part_name in updates
    section_root = ET.fromstring(updates[section.part_name])

    table_element = section_root.find(f".//{HP}tbl")
    assert table_element is not None
    assert table_element.get("borderFillIDRef") == border_id

    cells = section_root.findall(f".//{HP}tc")
    assert cells
    for cell in cells:
        assert cell.get("borderFillIDRef") == border_id
