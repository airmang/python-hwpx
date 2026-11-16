# SPDX-License-Identifier: Apache-2.0
"""``paragraph.insert_after``/``insert_before``: a paragraph at a chosen place (7.0 addition)."""
from __future__ import annotations

import io

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    return HwpxDocument.open(buffer.getvalue())


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("하나")
    doc.add_paragraph("셋")
    return doc


def test_insert_after_and_before_put_text_where_asked() -> None:
    doc = _doc()
    middle = doc.paragraphs[0].insert_after("둘")
    doc.paragraphs[2].insert_after("넷")
    doc.paragraphs[0].insert_before("영")
    assert [p.text for p in doc.paragraphs] == ["영", "하나", "둘", "셋", "넷"]
    assert middle.element is doc.paragraphs[2].element
    again = _reopened(doc)
    assert [p.text for p in again.paragraphs] == ["영", "하나", "둘", "셋", "넷"]
    assert again.validate().ok


def test_before_the_first_paragraph_the_new_one_starts_the_section() -> None:
    doc = _doc()
    size = doc.page.size()
    doc.paragraphs[0].insert_before("새 첫 줄")
    first = doc.sections[0].element.find(f"{HP}p")
    assert first.find(f"{HP}run/{HP}secPr") is not None
    assert len(list(doc.sections[0].element.iter(f"{HP}secPr"))) == 1
    assert _reopened(doc).page.size() == size


def test_the_new_paragraph_takes_the_shapes_of_its_neighbour() -> None:
    doc = HwpxDocument.new()
    source = doc.add_paragraph("기준", para_pr_id_ref=3, style=2, char_pr_id_ref=1)
    new = source.insert_after("옆")
    assert (new.element.get("paraPrIDRef"), new.element.get("styleIDRef")) == ("3", "2")
    assert new.element.find(f"{HP}run").get("charPrIDRef") == "1"


def test_a_copy_without_text_leaves_the_section_settings_behind() -> None:
    doc = _doc()
    copy = doc.paragraphs[0].insert_after()
    assert copy.text == "하나"
    assert copy.element.find(f".//{HP}secPr") is None
    assert len(list(doc.sections[0].element.iter(f"{HP}secPr"))) == 1
    assert copy.element.get("id") != doc.paragraphs[0].element.get("id")


def test_a_copied_form_field_gets_its_own_id_pair() -> None:
    doc = _doc()
    paragraph = doc.paragraphs[1]
    begin = paragraph.element.makeelement(f"{HP}fieldBegin", {"id": "77", "type": "CLICK_HERE", "name": "성명"})
    end = paragraph.element.makeelement(f"{HP}fieldEnd", {"beginIDRef": "77"})
    for marker in (begin, end):
        run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        ctrl = run.makeelement(f"{HP}ctrl", {})
        ctrl.append(marker)
        run.append(ctrl)
        paragraph.element.append(run)
    copy = paragraph.insert_after()
    (copied_begin,) = copy.element.iter(f"{HP}fieldBegin")
    (copied_end,) = copy.element.iter(f"{HP}fieldEnd")
    assert copied_begin.get("id") != "77"
    assert copied_end.get("beginIDRef") == copied_begin.get("id")
    assert begin.get("id") == "77" and end.get("beginIDRef") == "77"


def test_inside_a_cell() -> None:
    doc = _doc()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.text = "칸 첫 줄"
    cell.paragraphs[0].insert_after("칸 둘째 줄")
    assert [p.text for p in cell.paragraphs] == ["칸 첫 줄", "칸 둘째 줄"]
