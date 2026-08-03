# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.tracking`.

능력 레지스트리의 `redline` 영역. 5.x 는 저작 넷과 조회 넷을 루트에 여덟 칸으로
흩어 두었다.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxLookupError


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("가나다 본문")
    return doc


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def test_insert_registers_a_tracked_change() -> None:
    document = _document()
    change_id = document.tracking.insert(1, "삽입된 글")
    assert str(change_id) in document.tracking.changes

    xml = _section_xml(document)
    assert "삽입된 글" in xml
    assert f'<hp:insertBegin Id="{change_id}"' in xml


def test_tracked_insert_text_is_not_reachable_through_text_extraction() -> None:
    """알려진 읽기 갭 — 5.x 부터 그대로이고 B3 가 만든 것이 아니다.

    삽입된 글은 ``<hp:t>`` 안에서 ``<hp:insertBegin/>`` 의 **tail** 로 놓인다.
    텍스트 추출기는 ``hp:t`` 의 ``.text`` 만 읽으므로 이 글자를 보지 못한다.
    저작(위 테스트)은 정상이고, 읽기 쪽이 못 따라온다.

    이 테스트는 갭을 **고정**한다 — 누군가 읽기를 고치면 여기가 붉어지고,
    그때 이 테스트를 지우면 된다.
    """

    document = _document()
    document.tracking.insert(1, "삽입된 글")
    assert "삽입된 글" in _section_xml(document)
    assert "삽입된 글" not in document.text.plain()
    assert "삽입된 글" not in document.paragraphs[1].text


def test_delete_marks_the_matched_text() -> None:
    document = _document()
    change_id = document.tracking.delete(1, match="본문")
    assert str(change_id) in document.tracking.changes


def test_replace_reports_both_halves() -> None:
    document = _document()
    result = document.tracking.replace(1, "가나다", "라마바")
    # WP-C 조인 전: 5.x 와 같은 2-튜플. 착지 후 .insert / .delete 속성이 된다.
    insert_id, delete_id = result
    assert insert_id != delete_id
    assert str(insert_id) in document.tracking.changes
    assert str(delete_id) in document.tracking.changes


def test_add_change_is_the_low_level_primitive() -> None:
    """본문을 건드리지 않고 변경 항목만 등록한다."""

    document = _document()
    before = document.text.plain()
    change_id = document.tracking.add_change("INSERT")
    assert str(change_id) in document.tracking.changes
    assert document.text.plain() == before


def test_paragraph_accepts_an_index_or_an_object() -> None:
    document = _document()
    assert document.tracking.insert(1, "A")
    assert document.tracking.insert(document.paragraphs[1], "B")


def test_an_out_of_range_paragraph_is_a_typed_error() -> None:
    document = _document()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.tracking.insert(999, "x")
    assert excinfo.value.code == "paragraph-not-found"
    assert "0..1" in excinfo.value.suggestion


def test_lookup_surface_mirrors_the_owner() -> None:
    document = _document()
    document.tracking.insert(1, "삽입")
    assert document.tracking.changes == document.oxml.track_changes
    assert document.tracking.authors == document.oxml.track_change_authors
    first = next(iter(document.tracking.changes))
    assert document.tracking.change(first) is not None
    first_author = next(iter(document.tracking.authors))
    assert document.tracking.author(first_author) is not None


def test_the_moved_root_names_still_answer() -> None:
    document = _document()
    with pytest.warns(DeprecationWarning):
        document.add_tracked_insert(document.paragraphs[1], "삽입")
    with pytest.warns(DeprecationWarning):
        document.add_track_change("INSERT")
    with pytest.warns(DeprecationWarning):
        assert isinstance(document.track_changes, dict)


def test_return_shapes_are_still_the_5_x_ones_pending_wp_c() -> None:
    """WP-C 조인 지점. ``TrackedChange`` 가 착지하면 여기가 먼저 붉어진다."""

    document = _document()
    assert isinstance(document.tracking.insert(1, "A"), int)
    assert isinstance(document.tracking.add_change("INSERT"), int)
    assert isinstance(document.tracking.replace(1, "가나다", "라마바"), tuple)
