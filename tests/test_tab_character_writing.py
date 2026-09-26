"""A tab is written as an ``hp:tab`` element inside ``hp:t`` on every write path.

Hancom reads a tab only as that element; a raw tab character inside ``hp:t``
keeps it laying the paragraph out, so the document never finishes opening.
"""

from __future__ import annotations

import io
import re
import zipfile

from lxml import etree

from hwpx import HwpxDocument
from hwpx.body_patch import apply_body_ops
from hwpx.patch import paragraph_patch
from hwpx.table_patch import fill_cells

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _text_nodes(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    return re.findall(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", xml, re.S)


def _assert_no_raw_tab(data: bytes) -> None:
    assert not [node for node in _text_nodes(data) if "\t" in node]


def test_add_run_writes_a_tab_as_an_element() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_run("이름\t홍길동\t\t끝")
    data = doc.to_bytes()

    _assert_no_raw_tab(data)
    assert "이름<hp:tab/>홍길동<hp:tab/><hp:tab/>끝" in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == "이름\t홍길동\t\t끝"


def test_saving_leaves_the_document_tree_as_it_was() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("A\tB")
    doc.to_bytes()

    text = run.element.find(f"{HP}t")
    assert text is not None and text.text == "A\tB" and len(text) == 0


def test_a_tab_after_an_element_inside_the_text_is_written_as_an_element() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("앞")
    text = run.element.find(f"{HP}t")
    assert text is not None
    line_break = etree.SubElement(text, f"{HP}lineBreak")
    line_break.tail = "뒤\t끝"
    data = doc.to_bytes()

    _assert_no_raw_tab(data)
    assert "앞<hp:lineBreak/>뒤<hp:tab/>끝" in _text_nodes(data)


def test_replacing_text_with_a_tab_writes_an_element() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("원래 글")
    doc.text.replace("원래", "이름\t값")
    data = doc.to_bytes()

    _assert_no_raw_tab(data)
    assert any("이름<hp:tab/>값" in node for node in _text_nodes(data))


def _table_doc_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("원래 문단")
    doc.add_table(1, 1)
    return doc.to_bytes()


def test_fill_cells_writes_a_tab_as_an_element() -> None:
    result = fill_cells(_table_doc_bytes(), [{"table_index": 0, "row": 0, "col": 0, "text": "이름\t값"}])

    _assert_no_raw_tab(result.data)
    assert "이름<hp:tab/>값" in _text_nodes(result.data)
    assert HwpxDocument.open(result.data).tables.all[0].cell(0, 0).text == "이름\t값"


def test_paragraph_patch_writes_a_tab_as_an_element() -> None:
    result = paragraph_patch(_table_doc_bytes(), [{"paragraph_index": 1, "text": "이름\t값"}])

    _assert_no_raw_tab(result.data)
    assert "이름<hp:tab/>값" in _text_nodes(result.data)


def test_body_ops_replace_text_writes_a_tab_as_an_element() -> None:
    result = apply_body_ops(
        _table_doc_bytes(), [{"op": "replace_text", "find": "원래", "replace": "이름\t값", "count": 1}]
    )

    _assert_no_raw_tab(result.data)
    assert any("이름<hp:tab/>값" in node for node in _text_nodes(result.data))
