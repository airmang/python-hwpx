# SPDX-License-Identifier: Apache-2.0
"""변경 추적 수락·거절 — 하나·작성자별·전체, 문단 나눔, 머리의 목록 정리, 작성자 mark."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
CHANGE_TRACK = Path(__file__).parent / "fixtures" / "hwpxlib_corpus" / "reader_writer__ChangeTrack.hwpx"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert list(again.validate().issues) == []
    return again


def _marks(doc: HwpxDocument) -> list[str]:
    names = ("insertBegin", "insertEnd", "deleteBegin", "deleteEnd")
    return [
        element.tag.rsplit("}", 1)[-1]
        for section in doc.oxml.sections
        for element in section.element.iter(*(f"{HP}{name}" for name in names))
    ]


def _two_author_doc() -> tuple[HwpxDocument, object]:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가나다 라마바")
    doc.tracking.insert(paragraph, " 넣음", author="홍길동")
    doc.tracking.delete(paragraph, match="라마바", author="김철수")
    return doc, paragraph


def test_new_authors_are_marked_as_the_schema_allows() -> None:
    doc, _ = _two_author_doc()
    again = _reopen(doc)  # 예전에는 둘째 작성자의 mark="2" 가 스키마 경고를 냈다
    assert len(again.tracking.authors) == 2


def test_accept_all_keeps_insertions_and_removes_deletions() -> None:
    doc, paragraph = _two_author_doc()
    resolved = doc.tracking.accept()
    assert sorted(change.kind for change in resolved) == ["DELETE", "INSERT"]
    assert paragraph.text == "가나다  넣음"
    assert _marks(doc) == []
    assert doc.tracking.changes == {} and doc.tracking.authors == {}
    assert paragraph.element.find(f"{HP}linesegarray") is None
    again = _reopen(doc)
    assert again.paragraphs[-1].text == "가나다  넣음"


def test_reject_all_removes_insertions_and_keeps_deletions() -> None:
    doc, paragraph = _two_author_doc()
    doc.tracking.reject()
    assert paragraph.text == "가나다 라마바"
    assert _marks(doc) == []
    assert doc.tracking.changes == {}
    _reopen(doc)


def test_accept_one_author_leaves_the_other() -> None:
    doc, paragraph = _two_author_doc()
    resolved = doc.tracking.accept(author="김철수")
    assert [change.author for change in resolved] == ["김철수"]
    assert paragraph.text == "가나다  넣음"  # 넣은 글은 아직 표시된 채 남는다
    assert sorted(_marks(doc)) == ["insertBegin", "insertEnd"]
    assert [author.name for author in doc.tracking.authors.values()] == ["홍길동"]
    assert len(doc.tracking.changes) == 1
    _reopen(doc)


def test_reject_one_change_by_id() -> None:
    doc, paragraph = _two_author_doc()
    insert_id = next(key for key, change in doc.tracking.changes.items() if change.change_type == "Insert")
    doc.tracking.reject(insert_id)
    assert paragraph.text == "가나다 라마바"
    assert sorted(_marks(doc)) == ["deleteBegin", "deleteEnd"]
    _reopen(doc)


def test_selector_errors() -> None:
    doc, _ = _two_author_doc()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.tracking.accept(1, author="홍길동")
    assert excinfo.value.code == "track-selector-conflict"
    with pytest.raises(HwpxValueError) as excinfo:
        doc.tracking.accept(99)
    assert excinfo.value.code == "track-change-not-found"


def test_accepting_a_deleted_paragraph_removes_it_with_its_break() -> None:
    doc = HwpxDocument.new()
    keep = doc.add_paragraph("남는 문단")
    gone = doc.add_paragraph("지울 문단")
    after = doc.add_paragraph("뒤 문단")
    doc.tracking.delete(gone)
    count = len(doc.paragraphs)
    doc.tracking.accept()
    assert len(doc.paragraphs) == count - 1
    assert [p.text for p in doc.paragraphs[-2:]] == [keep.text, after.text]
    _reopen(doc)


def test_rejecting_a_deleted_paragraph_keeps_it() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("남는 문단")
    gone = doc.add_paragraph("지울 문단")
    doc.add_paragraph("뒤 문단")
    doc.tracking.delete(gone)
    count = len(doc.paragraphs)
    doc.tracking.reject()
    assert len(doc.paragraphs) == count
    assert gone.text == "지울 문단"
    _reopen(doc)


def test_accept_and_reject_a_hancom_saved_change_track() -> None:
    original = CHANGE_TRACK.read_bytes()
    accepted = HwpxDocument.open(original)
    assert accepted.paragraphs[0].text == "변경 추적 \t인간은"
    accepted.tracking.accept()
    assert accepted.paragraphs[0].text == "변경 \t인간은"
    rejected = HwpxDocument.open(original)
    rejected.tracking.reject()
    assert rejected.paragraphs[0].text == "변경 추적 \t"
    for doc in (accepted, rejected):
        assert _marks(doc) == []
        assert doc.tracking.changes == {} and doc.tracking.authors == {}
        data = doc.to_bytes()
        again = HwpxDocument.open(data)
        assert not [i for i in again.validate().issues if i.severity == "error"]
        with zipfile.ZipFile(io.BytesIO(original)) as a, zipfile.ZipFile(io.BytesIO(data)) as b:
            changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
        assert changed <= {"Contents/header.xml", "Contents/section0.xml"}


def test_accept_one_of_two_hancom_changes() -> None:
    doc = HwpxDocument.open(CHANGE_TRACK.read_bytes())
    doc.tracking.accept(2)  # the deletion of " 추적"
    assert doc.paragraphs[0].text == "변경 \t인간은"
    assert sorted(_marks(doc)) == ["insertBegin", "insertEnd"]
    assert list(doc.tracking.changes) == ["1"]
    assert len(doc.tracking.authors) == 1  # 한/글의 authorID 가 작성자 id 와 달라도 작성자는 남는다
