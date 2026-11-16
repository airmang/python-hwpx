# SPDX-License-Identifier: Apache-2.0
"""asks7: writes hwpx-school still did through ``.element`` for lack of a public API.

- ``obj.move_to``/``copy_to`` into a paragraph whose last run ends in an empty ``hp:t`` put the
  object in front of it (``[obj][t/]``), the form Hancom saves (hancom_saved: of 4,676 runs holding
  objects and only empty ``hp:t``, 4,675 end in the empty t, 1 in the object);
- ``obj.move_to(..., keep_order=True)`` keeps the object's ``zOrder``;
- ``doc.styles.set_char_property(id, ...)`` changes one character shape in place;
- ``doc.notes.add_memo(..., match=, index=)`` picks which place of *match* the memo goes on.
"""

from __future__ import annotations

import io

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _shape(paragraph) -> list[list[str]]:
    out = []
    for run in paragraph.element.findall(f"{_HP}run"):
        kinds = []
        for child in run:
            name = child.tag.rsplit("}", 1)[-1]
            text = "".join(child.itertext()) if name == "t" else ""
            kinds.append(f"t({text})" if name == "t" and text else name)
        out.append(kinds)
    return out


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    return HwpxDocument.open(buffer.getvalue())


# -- object before the trailing empty hp:t -----------------------------------------------------------


@pytest.mark.parametrize("offset", [0, None])
def test_move_into_empty_paragraph_goes_before_its_empty_t(offset) -> None:
    doc = HwpxDocument.new()
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    target = doc.add_paragraph("")
    assert _shape(target) == [["t"]]

    rect.move_to(target, offset=offset)

    assert _shape(target) == [["rect", "t"]]
    assert rect.paragraph.element is target.element
    reopened = _reopen(doc)
    assert any(_shape(p) == [["rect", "t"]] for p in reopened.paragraphs)


def test_copy_into_empty_paragraph_goes_before_its_empty_t() -> None:
    doc = HwpxDocument.new()
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    target = doc.add_paragraph("")

    rect.copy_to(target)

    assert _shape(target) == [["rect", "t"]]


def test_move_to_end_of_text_paragraph_stays_after_the_text() -> None:
    doc = HwpxDocument.new()
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    target = doc.add_paragraph("글자")

    rect.move_to(target)

    assert _shape(target) == [["t(글자)", "rect"]]
    assert target.text == "글자"


def test_move_to_start_of_text_paragraph_is_unchanged() -> None:
    doc = HwpxDocument.new()
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    target = doc.add_paragraph("글자")

    rect.move_to(target, offset=0)

    assert _shape(target) == [["rect", "t(글자)"]]


# -- keep_order ---------------------------------------------------------------------------------------


def _two_overlapping(doc: HwpxDocument):
    holder = doc.add_paragraph("")
    under = holder.add_rectangle(width=4000, height=4000)
    over = holder.add_rectangle(width=4000, height=4000)
    under.element.set("zOrder", "3")  # as Hancom numbers shapes drawn one over another
    over.element.set("zOrder", "4")
    return under, over


def test_move_puts_the_object_on_top_by_default() -> None:
    doc = HwpxDocument.new()
    under, over = _two_overlapping(doc)
    top = int(over.element.get("zOrder"))
    assert int(under.element.get("zOrder")) < top

    under.move_to(doc.add_paragraph(""))

    assert int(under.element.get("zOrder")) == top + 1


def test_move_keep_order_keeps_z_order() -> None:
    doc = HwpxDocument.new()
    under, over = _two_overlapping(doc)
    orders = (under.element.get("zOrder"), over.element.get("zOrder"))

    target = doc.add_paragraph("")
    under.move_to(target, offset=0, keep_order=True)
    over.move_to(target, keep_order=True)

    assert (under.element.get("zOrder"), over.element.get("zOrder")) == orders
    assert _shape(target) == [["rect", "rect", "t"]]
    reopened = _reopen(doc)
    found = [obj.get("zOrder") for p in reopened.paragraphs for obj in p.element.iter(f"{_HP}rect")]
    assert found == list(orders)


def test_move_keep_order_into_another_document() -> None:
    source, other = HwpxDocument.new(), HwpxDocument.new()
    rect = source.add_paragraph("").add_rectangle(width=2000, height=1000)
    order = rect.element.get("zOrder")
    other.add_paragraph("").add_rectangle(width=2000, height=1000)
    other.add_paragraph("").add_rectangle(width=2000, height=1000)

    rect.move_to(other.add_paragraph(""), keep_order=True)

    assert rect.element.get("zOrder") == order


# -- set_char_property ----------------------------------------------------------------------------------


def _char_pr(doc: HwpxDocument, id_ref: str):
    return doc.oxml.headers[0].element.find(f".//{_HH}charPr[@id='{id_ref}']")


def test_set_char_property_changes_the_definition_in_place() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("가나다")
    second = doc.add_paragraph("라마바")
    third = doc.add_paragraph("사아자")  # keeps the base shape
    run_id = first.runs[0].char_pr_id_ref
    first.runs[0].set_format(bold=True)  # a copy for this run alone
    shared = first.runs[0].char_pr_id_ref
    assert shared != run_id
    second.runs[0].char_pr_id_ref = shared
    count = len(doc.oxml.headers[0].element.findall(f".//{_HH}charPr"))

    doc.styles.set_char_property(shared, letter_spacing=-5, ratio=95)

    assert len(doc.oxml.headers[0].element.findall(f".//{_HH}charPr")) == count  # no copy
    element = _char_pr(doc, str(shared))
    assert {element.find(f"{_HH}spacing").get("hangul"), element.find(f"{_HH}ratio").get("hangul")} == {"-5", "95"}
    assert first.runs[0].char_pr_id_ref == shared and second.runs[0].char_pr_id_ref == shared
    assert third.runs[0].char_pr_id_ref == run_id
    assert _char_pr(doc, str(run_id)).find(f"{_HH}spacing").get("hangul") != "-5"


def test_set_char_property_clears_exactly_the_caches_of_its_users() -> None:
    doc = HwpxDocument.new()
    users = [doc.add_paragraph("가나다"), doc.add_paragraph("라마바")]
    other = doc.add_paragraph("사아자")
    users[0].runs[0].set_format(bold=True)
    shared = users[0].runs[0].char_pr_id_ref
    users[1].runs[0].char_pr_id_ref = shared
    for paragraph in (*users, other):
        paragraph.element.append(paragraph.element.makeelement(f"{_HP}linesegarray", {}))

    cleared = doc.styles.set_char_property(shared, ratio=90)

    assert cleared == 2
    assert all(p.element.find(f"{_HP}linesegarray") is None for p in users)
    assert other.element.find(f"{_HP}linesegarray") is not None
    assert doc.styles.set_char_property(shared, ratio=90) == 0  # the same value: nothing changes


def test_set_char_property_refusals() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxError) as empty:
        doc.styles.set_char_property(0)
    assert empty.value.code == "style-run-format-empty"
    with pytest.raises(HwpxError) as missing:
        doc.styles.set_char_property(9999, bold=True)
    assert missing.value.code == "style-definition-not-found"


# -- add_memo match index ---------------------------------------------------------------------------------


def _anchored_after(paragraph) -> str:
    """The paragraph text in front of the MEMO field's begin."""

    text = []
    for node in paragraph.element.iter(f"{_HP}t", f"{_HP}fieldBegin"):
        if node.tag == f"{_HP}fieldBegin" and node.get("type") == "MEMO":
            return "".join(text)
        if node.tag == f"{_HP}t":
            text.append("".join(node.itertext()))
    raise AssertionError("no memo field")


@pytest.mark.parametrize("index, before", [(0, ""), (1, "답 "), (2, "답 답 ")])
def test_add_memo_index_picks_the_place(index, before) -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("답 답 답")

    memo = doc.notes.add_memo("설명", paragraph=paragraph, match="답", index=index)

    assert memo.paragraph.element is paragraph.element
    assert _anchored_after(paragraph) == before
    assert paragraph.text == "답 답 답"


def test_add_memo_index_refusals() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("답 답")
    with pytest.raises(HwpxError) as missing:
        doc.notes.add_memo("설명", paragraph=paragraph, match="답", index=2)
    assert missing.value.code == "note-match-not-found"
    with pytest.raises(HwpxError) as alone:
        doc.notes.add_memo("설명", paragraph=paragraph, index=1)
    assert alone.value.code == "note-argument-conflict"
    with pytest.raises(HwpxError) as wrong:
        doc.notes.add_memo("설명", paragraph=paragraph, match="답", index="1")  # type: ignore[arg-type]
    assert wrong.value.code
    assert doc.notes.memos == ()  # nothing left behind


def test_attach_index() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가 가")
    memo = doc.notes.add_memo("설명")
    doc.notes.attach(paragraph, memo, match="가", index=1)
    assert _anchored_after(paragraph) == "가 "


def test_memo_with_several_paragraphs_through_insert_after() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("정답 칸")
    memo = doc.notes.add_memo("첫 줄", paragraph=paragraph, match="정답")
    last = memo.paragraphs[0]
    for line in ("둘째 줄", "셋째 줄"):
        last = last.insert_after(line)

    reopened = _reopen(doc)
    (again,) = reopened.notes.memos
    assert [p.text for p in again.paragraphs] == ["첫 줄", "둘째 줄", "셋째 줄"]
