# SPDX-License-Identifier: Apache-2.0
"""``doc.styles.ensure_memo_shape`` — 메모(코멘트) 모양 정의 저작.

실코퍼스(hwpxlib_corpus, memoPr 6파일)와 OWPML 스키마(Header XML
schema.xml:1705-1753) 리버스: ``hh:memoPr``는 ``hh:refList/hh:memoProperties``
안에 사는 id 1부터 시작하는 컬렉션(``hh:borderFill``과 달리 0을 쓰지 않는다).
관측 전량 width=15591·lineType=SOLID·memoType="NOMAL"(스키마 원문 철자, 오타
아님) — 그 중 lineWidth=1인 절반이 lineColor=#000000/fillColor=#CCFF99/
activeColor=#FFFF99 조합을 공유해 이걸 기본값으로 쓴다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

REPO = Path(__file__).resolve().parent.parent
REAL_CORPUS_SINGLE = (
    REPO / "tests" / "fixtures" / "hwpxlib_corpus" / "error__20241104__mot.hwpx"
)
REAL_CORPUS_DOUBLE = (
    REPO / "tests" / "fixtures" / "hwpxlib_corpus" / "error__20251107__test.hwpx"
)


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if name.endswith("header.xml")
        )


# --------------------------------------------------------------------------
# 저작 — 신규 메모 모양


def test_ensure_memo_shape_emits_the_measured_hancom_shape() -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape()

    assert shape_id == "1"
    shape = doc.styles.memo_shapes[shape_id]
    assert shape.width == 15591
    assert shape.line_width == "1"
    assert shape.line_type == "SOLID"
    assert shape.line_color == "#000000"
    assert shape.fill_color == "#CCFF99"
    assert shape.active_color == "#FFFF99"
    assert shape.memo_type == "NOMAL"


def test_ensure_memo_shape_ids_start_at_one_not_zero() -> None:
    """hh:borderFill과 달리 실코퍼스 6파일 전량 id=1부터 — 0은 미관측."""

    doc = HwpxDocument.new()
    first = doc.styles.ensure_memo_shape()
    second = doc.styles.ensure_memo_shape(fill_color="#F0FFE9")
    assert first == "1"
    assert second == "2"


def test_ensure_memo_shape_dedupes_on_repeat() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_memo_shape(fill_color="#F0FFE9", line_color="#B6D7AE")
    second = doc.styles.ensure_memo_shape(fill_color="#F0FFE9", line_color="#B6D7AE")
    assert first == second
    assert len(doc.styles.memo_shapes) == 1


def test_ensure_memo_shape_distinct_colors_create_distinct_shapes() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_memo_shape(fill_color="#CCFF99")
    second = doc.styles.ensure_memo_shape(fill_color="#F0FFE9")
    assert first != second
    assert len(doc.styles.memo_shapes) == 2


def test_memo_shapes_reflects_a_new_definition_immediately() -> None:
    """조회(memo_shapes)가 저작 직후 캐시 없이 바로 반영되는지."""

    doc = HwpxDocument.new()
    assert doc.styles.memo_shapes == {}
    shape_id = doc.styles.ensure_memo_shape(line_width=3, fill_color="#CBFF99")
    shapes = doc.styles.memo_shapes
    assert shape_id in shapes
    assert shapes[shape_id].line_width == "3"


# --------------------------------------------------------------------------
# 왕복 — save/reopen


def test_memo_shape_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape()
    path = tmp_path / "shape.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert (
        '<hh:memoPr id="1" width="15591" lineWidth="1" lineType="SOLID" '
        'lineColor="#000000" fillColor="#CCFF99" activeColor="#FFFF99" '
        'memoType="NOMAL"/>' in xml
    )

    reopened = HwpxDocument.open(path)
    assert shape_id in reopened.styles.memo_shapes
    reopened.close()


# --------------------------------------------------------------------------
# 실 소비 경로 — add_memo(memo_shape_id_ref=...)


def test_add_memo_consumes_a_newly_created_shape() -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape(fill_color="#F0FFE9", line_color="#B6D7AE")
    paragraph = doc.add_paragraph("본문")
    memo = doc.notes.add_memo("코멘트", anchor=paragraph, memo_shape_id_ref=shape_id)
    assert memo.memo_shape_id_ref == shape_id


def test_add_memo_with_new_shape_round_trips(tmp_path) -> None:
    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape(fill_color="#F0FFE9", line_color="#B6D7AE")
    paragraph = doc.add_paragraph("본문")
    doc.notes.add_memo("코멘트", anchor=paragraph, memo_shape_id_ref=shape_id)
    path = tmp_path / "memo.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    memos = [m for section in reopened.oxml.sections for m in section.memos]
    assert len(memos) == 1
    assert memos[0].memo_shape_id_ref == shape_id
    assert memos[0].memo_shape_id_ref in reopened.styles.memo_shapes
    reopened.close()


def test_authored_memo_shape_passes_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    shape_id = doc.styles.ensure_memo_shape()
    paragraph = doc.add_paragraph("본문")
    doc.notes.add_memo("코멘트", anchor=paragraph, memo_shape_id_ref=shape_id)
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# --------------------------------------------------------------------------
# typed error


def test_memo_shape_invalid_line_type_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_memo_shape(line_type="DIAGONAL")
    assert excinfo.value.code == "style-memo-shape-line-type-invalid"
    assert "SOLID" in excinfo.value.context["allowed"]


def test_memo_shape_invalid_memo_type_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_memo_shape(memo_type="USER_REVERT")
    assert excinfo.value.code == "style-memo-shape-memo-type-invalid"


def test_memo_shape_errors_are_still_catchable_as_plain_value_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(ValueError):
        doc.styles.ensure_memo_shape(line_type="DIAGONAL")


def test_memo_shape_error_codes_are_registered() -> None:
    from hwpx.errors import ERROR_CODES

    for code in (
        "style-memo-shape-line-type-invalid",
        "style-memo-shape-memo-type-invalid",
    ):
        assert code in ERROR_CODES


# --------------------------------------------------------------------------
# 실코퍼스


@pytest.mark.skipif(not REAL_CORPUS_SINGLE.exists(), reason="real corpus fixture missing")
def test_real_corpus_single_memo_shape_reads_correctly() -> None:
    document = HwpxDocument.open(REAL_CORPUS_SINGLE)
    try:
        shapes = document.styles.memo_shapes
        assert set(shapes) == {"1"}
        shape = shapes["1"]
        assert shape.width == 15591
        assert shape.line_width == "1"
        assert shape.fill_color == "#CCFF99"
        assert shape.memo_type == "NOMAL"
    finally:
        document.close()


@pytest.mark.skipif(not REAL_CORPUS_DOUBLE.exists(), reason="real corpus fixture missing")
def test_real_corpus_new_shape_coexists_with_existing_shapes_after_roundtrip(
    tmp_path,
) -> None:
    document = HwpxDocument.open(REAL_CORPUS_DOUBLE)
    before = set(document.styles.memo_shapes)
    assert before == {"1", "2"}

    new_id = document.styles.ensure_memo_shape(
        fill_color="#FFCCCC", line_color="#990000", active_color="#FFEEEE",
    )
    assert new_id == "3"

    out = tmp_path / "roundtrip.hwpx"
    document.save_to_path(out)
    document.close()

    with zipfile.ZipFile(REAL_CORPUS_DOUBLE) as archive:
        original_header = archive.read("Contents/header.xml").decode("utf-8")
    assert (
        '<hh:memoPr id="1" width="15591" lineWidth="3" lineType="SOLID" '
        'lineColor="#A9A9A9" fillColor="#CBFF99" activeColor="#FDBCDD" '
        'memoType="NOMAL"/>' in original_header
    )

    reopened = HwpxDocument.open(out)
    try:
        shapes = reopened.styles.memo_shapes
        assert set(shapes) == {"1", "2", "3"}
        assert shapes["1"].fill_color == "#CBFF99"  # original, untouched
        assert shapes["3"].fill_color == "#FFCCCC"  # newly authored
    finally:
        reopened.close()
