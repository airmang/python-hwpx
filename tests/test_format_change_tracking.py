# SPDX-License-Identifier: Apache-2.0
"""Tracked character and paragraph shape changes are read, but not written or rejected yet.

OWPML names them (``hh:trackChange type="CharShape"|"ParaShape"`` with ``charShapeID``/
``paraShapeID``; ``hp:run@charTcId``, ``hp:p@paraTcId``), but none of the 1,304 public HWPX
documents tracks a format change (one tracks insertions and deletions). The only public trace is
an HWP 5.0 sample whose 62 format changes (34 character, 28 paragraph) python-hwpx cannot turn into
HWPX as Hancom would. Until a Hangul-saved document shows Hancom's form, python-hwpx refuses to
write them, refuses to reject them, and accepts one only when no text points at it.
"""

from __future__ import annotations

import io

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _with_format_change(*, linked: bool, kind: str = "CharShape", spelling: str = "charShapeID") -> HwpxDocument:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("바뀐 모양의 글")
    doc.tracking.insert(paragraph, " 넣은 글")
    header = doc.oxml.headers[0]
    changes = header._track_changes_element()
    entry = etree.SubElement(
        changes,
        f"{HH}trackChange",
        {"type": kind, "date": "2026-11-16T00:00:00Z", "authorID": "1", spelling: "0", "hide": "0", "id": "9"},
    )
    changes.set("itemCnt", str(len(changes)))
    header.mark_dirty()
    if linked:
        run = paragraph.runs[0].element
        if kind == "CharShape":
            run.set("charTcId", entry.get("id"))
        else:
            paragraph.element.set("paraTcId", entry.get("id"))
        doc.sections[0].mark_dirty()
    return HwpxDocument.open(io.BytesIO(doc.to_bytes()))


def test_a_format_change_is_read_from_the_header() -> None:
    doc = _with_format_change(linked=True)
    change = doc.tracking.changes["9"]
    assert change.change_type == "CharShape" and change.char_shape_id == 0


def test_the_hwp_converted_spelling_is_read_and_kept() -> None:
    doc = _with_format_change(linked=False, kind="ParaShape", spelling="parashapeID")
    assert doc.tracking.changes["9"].para_shape_id == 0
    doc.tracking.insert(doc.paragraphs[-1], " 하나 더")  # rewrites the header's change list
    head = etree.fromstring(__import__("zipfile").ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/header.xml"))
    entry = next(e for e in head.iter(f"{HH}trackChange") if e.get("id") == "9")
    assert entry.get("parashapeID") == "0" and entry.get("paraShapeID") is None


@pytest.mark.parametrize("change_type", ["CharShape", "charshape", "char_shape", "ParaShape"])
def test_writing_a_format_change_is_refused(change_type: str) -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as caught:
        doc.tracking.add_change(change_type)
    assert caught.value.code == "track-format-change-unconfirmed"
    assert doc.tracking.changes == {}


def test_insertions_and_deletions_are_still_written() -> None:
    doc = HwpxDocument.new()
    assert doc.tracking.add_change("Insert").kind == "INSERT"


@pytest.mark.parametrize("accept", [True, False])
def test_a_format_change_the_text_points_at_is_neither_accepted_nor_rejected(accept: bool) -> None:
    doc = _with_format_change(linked=True)
    before = doc.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        (doc.tracking.accept if accept else doc.tracking.reject)()

    assert caught.value.code == "track-format-change-unconfirmed"
    assert caught.value.context["changes"] == ["9"]
    assert doc.to_bytes() == before


def test_the_insertion_beside_it_resolves_on_its_own() -> None:
    doc = _with_format_change(linked=True)
    insert_id = next(key for key, change in doc.tracking.changes.items() if change.change_type == "Insert")

    resolved = doc.tracking.reject(change=insert_id)

    assert [change.kind for change in resolved] == ["INSERT"]
    assert set(doc.tracking.changes) == {"9"}
    assert HwpxDocument.open(doc.to_bytes()).validate().ok


@pytest.mark.parametrize("kind", ["CharShape", "ParaShape"])
def test_a_format_change_nothing_points_at_is_accepted_by_dropping_its_entry(kind: str) -> None:
    doc = _with_format_change(linked=False, kind=kind)

    resolved = doc.tracking.accept()

    assert sorted(change.kind for change in resolved) == sorted(["INSERT", kind.upper()])
    assert doc.tracking.changes == {}
    with pytest.raises(HwpxValueError):
        _with_format_change(linked=False, kind=kind).tracking.reject()
