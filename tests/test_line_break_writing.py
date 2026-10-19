"""A line break typed into text ("\\n", "\\r\\n" or "\\r") is written as an
``hp:lineBreak`` inside ``hp:t``, the element Hancom writes for it.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.body_patch import apply_body_ops
from hwpx.patch import paragraph_patch


def _text_nodes(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    return re.findall(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", xml, re.S)


def _assert_no_raw_break(data: bytes) -> None:
    assert not [node for node in _text_nodes(data) if "\n" in node or "\r" in node or "&#13;" in node]


@pytest.mark.parametrize("line_break", ["\n", "\r\n", "\r"])
def test_add_paragraph_writes_a_line_break_as_an_element(line_break: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph(f"첫 줄{line_break}둘째 줄\t끝")
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "첫 줄<hp:lineBreak/>둘째 줄<hp:tab/>끝" in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == "첫 줄\n둘째 줄\t끝"


def test_setting_paragraph_text_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("원래")
    paragraph.text = "가\n나"
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "가<hp:lineBreak/>나" in _text_nodes(data)


def test_add_run_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_run("앞\n뒤")
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "앞<hp:lineBreak/>뒤" in _text_nodes(data)


def test_cell_text_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).text = "칸\n둘"
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "칸<hp:lineBreak/>둘" in _text_nodes(data)
    assert HwpxDocument.open(data).tables.all[0].cell(0, 0).text == "칸\n둘"


def _doc_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("원래 문단")
    return doc.to_bytes()


def test_paragraph_patch_writes_a_line_break_as_an_element() -> None:
    result = paragraph_patch(_doc_bytes(), [{"paragraph_index": 1, "text": "가\r\n나"}])

    _assert_no_raw_break(result.data)
    assert "가<hp:lineBreak/>나" in _text_nodes(result.data)


def test_body_ops_replace_text_writes_a_line_break_as_an_element() -> None:
    result = apply_body_ops(_doc_bytes(), [{"op": "replace_text", "find": "원래", "replace": "가\n나", "count": 1}])

    _assert_no_raw_break(result.data)
    assert any("가<hp:lineBreak/>나" in node for node in _text_nodes(result.data))
