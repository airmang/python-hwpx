# SPDX-License-Identifier: Apache-2.0
"""Elements the engine makes write their attributes in Hancom's order (A7, asks10b): the orders of
``tests/fixtures/hancom_saved``. These are the paths a scan of everything the test suite writes found still in
another order after #779 (``out/exec7/asks10b/attr_capture``)."""

from __future__ import annotations

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def test_a_cell_split_out_of_a_merge_writes_its_address_and_span_in_hancom_s_order() -> None:
    # all 20,787 hp:cellAddr and hp:cellSpan of hancom_saved: colAddr before rowAddr, colSpan before rowSpan
    with HwpxDocument.new() as doc:
        table = doc.add_paragraph("표").add_table(2, 3)
        table.merge_cells(0, 0, 0, 1)
        table.split_merged_cell(0, 0)
        for cell in table.element.iter(f"{HP}tc"):
            assert list(cell.find(f"{HP}cellAddr").attrib) == ["colAddr", "rowAddr"]
            assert list(cell.find(f"{HP}cellSpan").attrib) == ["colSpan", "rowSpan"]


def test_a_new_style_writes_hancom_s_order() -> None:
    # every hh:style of hancom_saved: ... charPrIDRef, nextStyleIDRef, langID, lockForm
    with HwpxDocument.new() as doc:
        style_id = doc.styles.ensure_style("새 스타일", eng_name="New", para_pr_id_ref="0", char_pr_id_ref="0",
                                           lang_id=1042)
        header = doc.oxml.headers[0].element
        style = next(node for node in header.iter(f"{HH}style") if node.get("id") == str(style_id))
        keys = list(style.attrib)
        hancom = ["id", "type", "name", "engName", "paraPrIDRef", "charPrIDRef", "nextStyleIDRef", "langID", "lockForm"]
        assert keys == [key for key in hancom if key in keys]


def test_an_attribute_added_to_a_style_goes_to_its_place() -> None:
    with HwpxDocument.new() as doc:
        style_id = doc.styles.ensure_style("새 스타일", para_pr_id_ref="0", char_pr_id_ref="0", lang_id=0)
        doc.styles.ensure_style("새 스타일", next_style_id_ref=style_id)
        header = doc.oxml.headers[0].element
        style = next(node for node in header.iter(f"{HH}style") if node.get("id") == str(style_id))
        keys = list(style.attrib)
        assert keys.index("nextStyleIDRef") < keys.index("langID")
