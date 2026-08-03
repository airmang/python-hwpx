# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.notes`.

각주·미주·메모는 전부 **본문 흐름 밖에 붙는 주석**이라 한 축이다.
5.x 의 `add_memo` 와 `add_memo_with_anchor` 는 같은 동사의 두 형태였으므로
`anchor=` 파라미터로 접었다.
"""

from __future__ import annotations

import pytest

from hwpx import model
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError, HwpxLookupError, HwpxValueError


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문 문단")
    return doc


# -- 각주 / 미주 -----------------------------------------------------------


def test_footnote_and_endnote_attach_to_the_paragraph(document: HwpxDocument) -> None:
    footnote = document.notes.add_footnote("각주 내용", section=0)
    endnote = document.notes.add_endnote("미주 내용", section=0)
    assert isinstance(footnote, model.Note) and isinstance(endnote, model.Note)
    assert footnote.text == "각주 내용"
    assert endnote.text == "미주 내용"


# -- 메모 -------------------------------------------------------------------


def test_add_memo_without_an_anchor_returns_the_memo(document: HwpxDocument) -> None:
    memo = document.notes.add_memo("메모 내용", section=0)
    assert isinstance(memo, model.Memo)
    assert document.notes.memos == [memo] or len(document.notes.memos) == 1


def test_add_memo_with_an_anchor_folds_the_5_x_second_verb(document: HwpxDocument) -> None:
    """5.x ``add_memo_with_anchor`` 가 ``anchor=`` 파라미터가 됐다."""

    result = document.notes.add_memo("앵커 메모", anchor=1, section=0)
    # WP-C 조인 전: 5.x 와 같은 3-튜플. 착지 후 Memo 하나가 된다.
    memo, paragraph, field_id = result
    assert isinstance(memo, model.Memo)
    assert isinstance(paragraph, model.Paragraph)
    assert isinstance(field_id, str) and field_id


def test_anchor_accepts_an_index_or_an_object(document: HwpxDocument) -> None:
    by_index = document.notes.add_memo("A", anchor=1, section=0)
    by_object = document.notes.add_memo("B", anchor=document.paragraphs[1], section=0)
    assert by_index[1].element is by_object[1].element


def test_an_out_of_range_anchor_is_a_typed_error(document: HwpxDocument) -> None:
    with pytest.raises(HwpxLookupError) as excinfo:
        document.notes.add_memo("메모", anchor=999, section=0)
    assert excinfo.value.code == "paragraph-not-found"


def test_anchor_only_arguments_are_refused_without_an_anchor(
    document: HwpxDocument,
) -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        document.notes.add_memo("메모", author="나", section=0)
    assert excinfo.value.code == "note-argument-conflict"


def test_attach_binds_an_existing_memo_and_remove_undoes_it(
    document: HwpxDocument,
) -> None:
    memo = document.notes.add_memo("메모", section=0)
    field_id = document.notes.attach(1, memo)
    assert isinstance(field_id, str) and field_id
    document.notes.remove_memo(memo)
    assert document.notes.memos == []


# -- section 규약 -----------------------------------------------------------


@pytest.mark.parametrize(
    "name,args",
    [("add_footnote", ("각주",)), ("add_endnote", ("미주",)), ("add_memo", ("메모",))],
)
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_bad_sections_are_typed_errors(name, args, kwargs, code, document) -> None:
    with pytest.raises(HwpxError) as excinfo:
        getattr(document.notes, name)(*args, **kwargs)
    assert excinfo.value.code == code


def test_the_moved_root_names_still_answer(document: HwpxDocument) -> None:
    with pytest.warns(DeprecationWarning):
        document.add_footnote("각주", section_index=0)
    with pytest.warns(DeprecationWarning):
        document.add_memo("메모", section_index=0)
    with pytest.warns(DeprecationWarning):
        assert isinstance(document.memos, list)
