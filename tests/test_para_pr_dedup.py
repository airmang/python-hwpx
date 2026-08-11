# SPDX-License-Identifier: Apache-2.0
"""``ensure_paragraph_format``의 paraPr 중복 생성 결함 수리 -- cycle 6.14
트레인㊾-2.

발견 경위: 6.13 트레인㊼ titleMark 재프로브에서 팀장이 두 개의 "제목
하나"류 헤딩을 만들었더니 실한컴이 저장 시점에 두 번째 헤딩의
``paraPrIDRef``를 (다른 값으로 새로 만들었던 것을) 첫 번째 것과 같은
값으로 **되돌렸다**(21→20) -- 우리 쪽 `HwpxDocument.add_heading` →
`_headings.bind_outline_level` → `_document/layout.py`의
`set_paragraph_format(outline_level=)` → `header_part.py`의
`ensure_paragraph_format`이 동일한 내용의 paraPr을 매번 새 id로
다시 만들던 습성이 원인이었다(dedupe 조회 없음) -- 실한컴 자신은 저장
시점에 중복을 병합하지만 우리는 안 했다.

수리: `ensure_paragraph_format`이 새 paraPr을 append하기 전, 이미 존재하는
paraPr 중 (id를 제외하고) 구조적으로 동일한 것이 있으면 그 id를 재사용한다
(``ensure_tab_definition``/``ensure_style``의 dedupe 선례와 같은 원칙,
새 헬퍼 ``_elements_structurally_equal``).
"""
from __future__ import annotations

from hwpx.document import HwpxDocument


def _para_properties_count(document: HwpxDocument) -> int:
    header = document._root.headers[0]
    para_properties = header.element.find(
        ".//{http://www.hancom.co.kr/hwpml/2011/head}paraProperties"
    )
    assert para_properties is not None
    return len(
        para_properties.findall("{http://www.hancom.co.kr/hwpml/2011/head}paraPr")
    )


def test_two_identical_headings_share_one_para_pr() -> None:
    """결함-부활 증명: 수리 전엔 h1/h2가 서로 다른 paraPrIDRef를 받았다
    (팀장의 titleMark 재프로브에서 관측된 21→20 현상의 근본 원인)."""

    document = HwpxDocument.new()

    h1 = document.add_heading("제목 하나", level=1)
    h2 = document.add_heading("제목 둘", level=1)

    assert h1.para_pr_id_ref == h2.para_pr_id_ref


def test_different_heading_levels_stay_distinct() -> None:
    """dedupe가 과하게 공격적이지 않은지 확인 -- 실제로 다른 내용이면
    합치지 않는다."""

    document = HwpxDocument.new()

    h1 = document.add_heading("제목 하나", level=1)
    h2 = document.add_heading("제목 둘", level=2)

    assert h1.para_pr_id_ref != h2.para_pr_id_ref


def test_repeated_add_heading_does_not_grow_para_properties_unboundedly() -> None:
    document = HwpxDocument.new()
    before = _para_properties_count(document)

    for i in range(5):
        document.add_heading(f"제목 {i}", level=3)

    after = _para_properties_count(document)
    # exactly one new paraPr for the shared level-3 heading format, not five.
    assert after == before + 1


def test_same_paragraph_format_call_on_two_fresh_paragraphs_dedupes() -> None:
    document = HwpxDocument.new()
    p1 = document.add_paragraph("문단 A")
    p2 = document.add_paragraph("문단 B")

    document.styles.apply_paragraph_format(
        paragraph_index=document.paragraphs.index(p1), alignment="CENTER"
    )
    document.styles.apply_paragraph_format(
        paragraph_index=document.paragraphs.index(p2), alignment="CENTER"
    )

    assert p1.para_pr_id_ref == p2.para_pr_id_ref


def test_paragraph_format_dedupe_does_not_disturb_unrelated_paragraphs() -> None:
    """실 코퍼스 문서에서 한 문단만 편집해도 다른 문단들의 paraPrIDRef는
    그대로다(회귀 방지 -- dedupe 조회가 잘못된 후보를 매치시키지 않음)."""
    import zipfile

    fixture = (
        "tests/fixtures/hwpxlib_corpus/"
        "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
    )
    with zipfile.ZipFile(fixture):
        pass  # sanity: fixture exists and is a valid zip

    document = HwpxDocument.open(fixture)
    try:
        before = [p.para_pr_id_ref for p in document.paragraphs]
        document.styles.apply_paragraph_format(paragraph_index=5, alignment="CENTER")
        after = [p.para_pr_id_ref for p in document.paragraphs]
    finally:
        document.close()

    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    assert changed == [5]


def test_plain_round_trip_stays_byte_identical() -> None:
    """dedupe 조회는 ``ensure_paragraph_format``이 실제로 호출될 때만
    실행된다 -- 편집 없는 단순 열기/재저장은 이 경로를 아예 안 타므로
    바이트 단위로 그대로다."""

    fixture = (
        "tests/fixtures/hwpxlib_corpus/"
        "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
    )
    document = HwpxDocument.open(fixture)
    try:
        first = document.to_bytes()
    finally:
        document.close()

    reopened = HwpxDocument.open(first)
    try:
        second = reopened.to_bytes()
    finally:
        reopened.close()

    assert first == second
