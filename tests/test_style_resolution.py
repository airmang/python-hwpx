# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B1 게이트 — 스타일 이름 해석.

5.x의 실제 동작을 먼저 못박아 둔다(전부 5.8.0 실행으로 측정):

===========================  ==============  ==================================
입력                          호출 시점        저장 시점
===========================  ==============  ==================================
``style_id_ref="개요 1"``     통과            serialize 정규화 → id 2, 성공
``style_id_ref="개요1"``      통과            ``HwpxPackageError: Invalid
                                             integer value: '개요1'``
``style_id_ref=9999``         통과            **무음 성공** — 없는 id 가 그대로
===========================  ==============  ==================================

즉 5.x 의 결함은 하나가 아니라 둘이다. 이름 오타는 **터지긴 하지만 저장
시점이고, 스타일도 가용 목록도 제안도 말하지 않는다**. 없는 숫자 id 는
**아예 조용하다**(기본 저장 정책이 참조 무결성을 요구하지 않는다).

그래서 이 파일이 지키는 것은 "이름을 해석한다"가 아니라 **"언제, 무엇을
말하는가"**다. 6.0 은 두 경우 모두 호출 시점에 `HwpxLookupError` 로 말한다.
"""

from __future__ import annotations

import warnings

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxLookupError, HwpxValueError

#: Skeleton 이 싣는 스타일 수. 하나라도 사라지면 이 파일 전체가 근거를 잃는다.
SKELETON_STYLE_COUNT = 23


@pytest.fixture()
def document() -> HwpxDocument:
    return HwpxDocument.new()


# --------------------------------------------------------------------------
# 게이트 ① 오타는 저장이 아니라 **호출 시점에** 말한다


def test_a_typo_raises_at_the_call_not_at_save(document: HwpxDocument) -> None:
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_paragraph("본문", style="개요1")  # 공백 누락
    error = excinfo.value
    assert error.code == "style-not-found"
    assert "개요 1" in error.context["closest"]
    assert error.context["requested"] == "개요1"
    # names() 는 한글 이름과 영문명을 모두 싣는다(23 + 23).
    assert error.context["availableCount"] == len(error.context["available"])
    assert "doc.styles.names()" in error.suggestion


def test_the_5_x_typo_only_surfaced_at_save_and_named_nothing(tmp_path) -> None:
    """5.x 결함의 정확한 형태(실측): **터지긴 하는데 저장 시점이고 무정보다.**

    ``style_id_ref`` 는 6.x 내내 살아 있는 하위 호환 경로이고 그 동작은 바꾸지
    않았다. 이 테스트가 못박는 것은 **왜 ``style=`` 이 필요한가**다 — 같은
    오타가 여기서는 저장할 때까지 잠자코 있다가 스타일도, 가용 목록도,
    제안도 말하지 않는 `HwpxPackageError` 로 터진다.
    """

    from hwpx.opc.package import HwpxPackageError

    document = HwpxDocument.new()
    document.add_paragraph("본문", style_id_ref="개요1")  # 호출 시점: 무반응
    with pytest.raises(HwpxPackageError) as excinfo:
        document.save_to_path(tmp_path / "late.hwpx")
    message = str(excinfo.value)
    assert "개요1" in message
    # 무엇이 문제인지 말하지 않는다: 스타일이라는 말도, 대안도 없다.
    assert "style" not in message.lower()
    assert "개요 1" not in message


def test_a_dangling_numeric_id_used_to_save_silently(tmp_path) -> None:
    """5.x 의 조용한 절반: 숫자이기만 하면 없는 id 도 그대로 나갔다.

    기본 저장 정책(`QualityPolicy.transparent()`)이 참조 무결성을 요구하지
    않으므로 `styleIDRef="9999"` 가 그대로 기록된다. 6.0 은 이 경우도 호출
    시점에 막는다(아래).
    """

    import re
    import zipfile

    document = HwpxDocument.new()
    document.add_paragraph("본문", style_id_ref=9999)
    target = tmp_path / "dangling.hwpx"
    document.save_to_path(target)  # 5.x 경로: 무음 성공
    xml = zipfile.ZipFile(target).read("Contents/section0.xml").decode("utf-8")
    assert "9999" in re.findall(r'styleIDRef="([^"]*)"', xml)


def test_style_closes_the_dangling_id_hole_at_the_call() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_paragraph("본문", style=9999)
    assert excinfo.value.code == "style-not-found"


def test_style_and_style_id_ref_together_is_refused(document: HwpxDocument) -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_paragraph("본문", style="개요 1", style_id_ref=2)
    assert excinfo.value.code == "style-argument-conflict"


# --------------------------------------------------------------------------
# 게이트 ② Skeleton 23 스타일 name↔id 왕복


def test_every_skeleton_style_round_trips_by_name(document: HwpxDocument) -> None:
    styles = document.oxml.styles
    assert len(styles) == SKELETON_STYLE_COUNT
    resolved = 0
    for style in styles.values():
        assert style.name, "Skeleton 스타일은 전부 한글 이름을 갖는다"
        assert document.styles.resolve(style.name).id == style.id
        resolved += 1
    assert resolved == SKELETON_STYLE_COUNT


def test_every_skeleton_style_round_trips_by_english_name(document: HwpxDocument) -> None:
    for style in document.oxml.styles.values():
        if not style.eng_name:
            continue
        assert document.styles.resolve(style.eng_name).id == style.id


def test_english_names_resolve_case_insensitively(document: HwpxDocument) -> None:
    assert document.styles.resolve("outline 1").name == "개요 1"
    assert document.styles.resolve("OUTLINE 1").name == "개요 1"


def test_numeric_ids_keep_working(document: HwpxDocument) -> None:
    """id 를 쓰던 코드는 한 글자도 안 바뀐다."""

    assert document.styles.resolve(2).name == "개요 1"
    assert document.styles.resolve("2").name == "개요 1"
    assert str(document.add_paragraph("t", style=2).style_id_ref) == "2"


# --------------------------------------------------------------------------
# 게이트 ③ 동명 스타일은 모호하다고 말한다 (5.x 는 조용히 버렸다)


def _duplicate_named_document() -> HwpxDocument:
    """"개요 1" 이라는 이름을 가진 스타일을 하나 더 심는다."""

    import copy

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for node in header.element.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "style" and node.get("name") == "개요 1":
            clone = copy.deepcopy(node)
            clone.set("id", "900")
            clone.set("engName", "Outline 1 Copy")
            node.getparent().append(clone)
            break
    else:  # pragma: no cover - Skeleton 이 바뀌면 이 픽스처가 먼저 깨져야 한다
        pytest.fail("Skeleton 에서 '개요 1' 스타일을 찾지 못했습니다")
    return document


def test_an_ambiguous_name_is_reported_not_silently_dropped() -> None:
    document = _duplicate_named_document()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.styles.resolve("개요 1")
    error = excinfo.value
    assert error.code == "style-ambiguous"
    ids = {candidate["id"] for candidate in error.context["candidates"]}
    assert ids == {"2", "900"}
    assert "숫자 id" in error.suggestion


def test_the_serialize_time_backstop_still_drops_the_ambiguous_alias() -> None:
    """5.x 의 serialize 시점 동작은 그대로 둔다 — 이름을 못 고르면 안 고친다.

    호출 시점 해석이 1차 방어이고, 이건 ``doc.oxml`` 로 직접 만든 문서를 위한
    2차 방어다. 둘의 역할이 다르므로 동작도 다르다.
    """

    document = _duplicate_named_document()
    aliases = document.oxml.style_name_aliases()
    assert aliases["개요 1"] == ("2", "900")          # 모호성이 보존되고
    assert "개요 1" not in document.oxml._style_name_id_map()  # 정규화기는 손대지 않는다


# --------------------------------------------------------------------------
# doc.styles — 5.x 매핑 계약과 조회 표면


def test_styles_namespace_is_still_the_5_x_mapping(document: HwpxDocument) -> None:
    styles = document.styles
    assert styles["0"].name == "바탕글"
    assert len(styles) == SKELETON_STYLE_COUNT
    assert "0" in styles
    assert styles.all == document.oxml.styles
    assert [s.name for s in styles.values()][:2] == ["바탕글", "본문"]


def test_get_follows_the_mapping_contract_and_never_raises(document: HwpxDocument) -> None:
    assert document.styles.get("개요 1").name == "개요 1"
    assert document.styles.get("없는스타일") is None
    sentinel = document.oxml.styles["0"]
    assert document.styles.get("없는스타일", sentinel) is sentinel


def test_names_lists_both_korean_and_english_labels(document: HwpxDocument) -> None:
    names = document.styles.names()
    assert "개요 1" in names and "Outline 1" in names
    assert len(names) == len(set(names)), "중복 없이"


def test_definition_tables_are_reachable_from_the_namespace(document: HwpxDocument) -> None:
    styles = document.styles
    assert styles.char_properties == document.oxml.char_properties
    assert styles.paragraph_properties == document.oxml.paragraph_properties
    assert styles.border_fills == document.oxml.border_fills
    assert styles.bullets == document.oxml.bullets
    assert styles.memo_shapes == document.oxml.memo_shapes
    assert styles.char_property(0) is not None
    assert styles.paragraph_property(0) is not None


def test_ensure_verbs_mint_ids(document: HwpxDocument) -> None:
    bold = document.styles.ensure_run(bold=True)
    assert bold and document.styles.char_property(bold) is not None
    border = document.styles.ensure_border_fill()
    assert border and document.styles.border_fill(border) is not None
    assert document.styles.ensure_numbering(kind="bullet")


def test_apply_verbs_reach_the_layout_owner(document: HwpxDocument) -> None:
    document.add_paragraph("본문")
    result = document.styles.apply_paragraph_format(paragraph_index=0, alignment="CENTER")
    assert result.formatted == 1
    assert result.paragraphs == (0,)
    listed = document.styles.apply_list_format(paragraph_index=0, kind="bullet")
    assert listed.formatted == 1
    assert listed.kind == "bullet"
    # 5.x 의 ``paraPrIDRef`` 카멜 키가 snake_case 속성이 됐다.
    assert listed.para_pr_id_ref


def test_the_moved_root_names_still_answer_with_a_warning(document: HwpxDocument) -> None:
    with pytest.warns(DeprecationWarning):
        assert document.ensure_run_style(bold=True)
    with pytest.warns(DeprecationWarning):
        assert document.style(2).name == "개요 1"


# --------------------------------------------------------------------------
# doc.text / doc.parts


def test_text_namespace_exports_and_searches(document: HwpxDocument) -> None:
    document.add_paragraph("첫 문단")
    assert "첫 문단" in document.text.plain()
    assert "첫 문단" in document.text.markdown()
    assert "첫 문단" in document.text.markdown(rich=True)
    assert "첫 문단" in document.text.html()
    assert sum(1 for _ in document.text.runs()) >= 1
    assert document.text.find_runs(char_pr_id_ref=0)


def test_text_replace_counts_and_refuses_an_empty_needle(document: HwpxDocument) -> None:
    document.add_paragraph("가나다 가나다")
    assert document.text.replace("가나다", "ABC") >= 1
    assert "ABC" in document.text.plain()
    with pytest.raises(HwpxValueError) as excinfo:
        document.text.replace("", "x")
    assert excinfo.value.code == "text-search-empty"


def test_parts_namespace_separates_header_parts_from_page_headers(
    document: HwpxDocument,
) -> None:
    """5.x ``doc.headers`` 는 쪽 머리말이 아니라 header.xml 파트였다."""

    assert document.parts.headers == document.oxml.headers
    assert document.parts.master_pages == document.oxml.master_pages
    assert document.parts.histories == document.oxml.histories
    assert document.parts.version is document.oxml.version

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        document.set_header_text("진짜 쪽 머리말", section=0)
    # 쪽 머리말을 넣어도 header.xml 파트 수는 그대로다 — 서로 다른 것이다.
    assert len(document.parts.headers) == 1
