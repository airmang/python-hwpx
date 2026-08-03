# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B1 게이트 — `add_heading`.

`add_heading` 은 python-docx 이주자가 가장 먼저 찾는 이름이지만, 이 파일이
지키는 것은 편의가 아니라 **결함 수리**다.

5.x 에서 개요 **스타일**과 개요 **수준**은 분리돼 있었다:

- `set_paragraph_format(outline_level=1)` → `<hh:heading type="OUTLINE">` 은
  쓰지만 `styleIDRef` 는 그대로(바탕글 0). "번호는 붙는데 스타일은 본문."
- `add_paragraph(style_id_ref="개요 1")` → 스타일은 붙지만 문단이 자기 개요
  수준을 선언하지 않는다.

`add_heading` 은 둘을 한 번에 묶는 유일한 경로다. 아래 첫 테스트가 그 결합을
XML 로 직접 확인한다.
"""

from __future__ import annotations

import copy

import pytest

from hwpx._document import headings
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxLookupError, HwpxValueError

OUTLINE_LEVELS = list(range(headings.MIN_HEADING_LEVEL, headings.MAX_HEADING_LEVEL + 1))


def _heading_of(document: HwpxDocument, paragraph):
    para_pr = document.oxml.paragraph_property(paragraph.para_pr_id_ref)
    assert para_pr is not None, "문단이 자기 paraPr 을 가져야 한다"
    return para_pr.heading


# --------------------------------------------------------------------------
# 게이트 ④ 스타일과 개요 수준이 **함께** 나간다


@pytest.mark.parametrize("level", OUTLINE_LEVELS)
def test_style_and_outline_level_are_emitted_together(level: int) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_heading(f"제목 {level}", level=level)

    style = document.styles[str(paragraph.style_id_ref)]
    assert style.name == f"개요 {level}"

    heading = _heading_of(document, paragraph)
    assert heading is not None, "개요 수준이 문단에 선언돼야 한다"
    assert heading.type == "OUTLINE"
    assert str(heading.level) == str(level - 1)


@pytest.mark.parametrize("level", OUTLINE_LEVELS)
def test_the_binding_survives_a_save_round_trip(level: int, tmp_path) -> None:
    """XML 로 나가고 다시 읽어도 둘 다 남아 있는가."""

    document = HwpxDocument.new()
    document.add_heading(f"제목 {level}", level=level)
    target = tmp_path / f"heading-{level}.hwpx"
    document.save_to_path(target)

    with HwpxDocument.open(target) as reopened:
        paragraph = reopened.paragraphs[-1]
        assert reopened.styles[str(paragraph.style_id_ref)].name == f"개요 {level}"
        heading = _heading_of(reopened, paragraph)
        assert heading is not None and heading.type == "OUTLINE"
        assert str(heading.level) == str(level - 1)


def test_the_5_x_halves_really_were_separate() -> None:
    """수리 전 상태의 증거 — 두 옛 경로는 각각 절반만 한다.

    각 절반을 **새 문서**에서 잰다. 같은 문서에서 이어 재면 두 번째 문단이
    ``inherit_style`` 로 첫 문단의 ``paraPrIDRef`` 를 물려받아, 스타일만 준
    문단에 개요 수준이 딸려오는 것처럼 보인다(이 테스트를 처음 그렇게 썼다가
    잡혔다).
    """

    # 절반 A: 개요 수준만. 스타일은 바탕글(0) 그대로.
    document = HwpxDocument.new()
    document.add_paragraph("수준만")
    only_level = document.paragraphs[-1]
    document.styles.apply_paragraph_format(
        paragraph_index=len(document.paragraphs) - 1, outline_level=1
    )
    assert _heading_of(document, only_level).type == "OUTLINE"
    assert str(only_level.style_id_ref) == "0", "스타일은 여전히 바탕글이다"

    # 절반 B: 스타일만. 문단은 자기 개요 수준을 선언하지 않는다.
    document = HwpxDocument.new()
    only_style = document.add_paragraph("스타일만", style="개요 1")
    assert str(only_style.style_id_ref) == "2"
    assert _heading_of(document, only_style).type == "NONE"


# --------------------------------------------------------------------------
# 게이트 ⑥ level 경계


@pytest.mark.parametrize("level", [0, 11, -1, 100])
def test_levels_outside_the_hwpx_outline_are_refused(level: int) -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_heading("t", level=level)
    error = excinfo.value
    assert error.code == "heading-level-out-of-range"
    assert error.context == {"requested": level, "min": 1, "max": 10}
    assert "style=" in error.suggestion


def test_level_zero_is_refused_on_purpose_not_by_accident() -> None:
    """``python-docx`` 의 ``level=0``(Title)을 흉내내지 않는다.

    Skeleton 에 "제목" 스타일이 없고, 없는 스타일을 만들어 넣으면 한컴의 개요
    번호 매기기가 그 문단을 세지 않아 **번호가 어긋난 문서**가 나온다.
    벤치마크는 복사 대상이 아니다.
    """

    document = HwpxDocument.new()
    assert "제목" not in document.styles.names()
    with pytest.raises(HwpxValueError):
        document.add_heading("문서 제목", level=0)


def test_a_non_integer_level_is_a_typed_error() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_heading("t", level="1")  # type: ignore[arg-type]
    assert excinfo.value.code == "heading-level-invalid"


def test_bool_is_not_an_outline_level() -> None:
    """``True`` 는 int 의 서브클래스다 — 수준 1 로 조용히 읽히면 안 된다."""

    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_heading("t", level=True)  # type: ignore[arg-type]
    assert excinfo.value.code == "heading-level-invalid"


# --------------------------------------------------------------------------
# 게이트 ⑤ 개요 스타일이 없는 야생 문서


def _document_without_outline_styles() -> HwpxDocument:
    """개요 스타일을 전부 걷어낸 문서 — 야생 HWPX 를 흉내낸다."""

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for node in list(header.element.iter()):
        if node.tag.rsplit("}", 1)[-1] != "style":
            continue
        name = (node.get("name") or "").strip()
        eng = (node.get("engName") or "").strip()
        if name.startswith("개요") or eng.lower().startswith("outline"):
            node.getparent().remove(node)
    return document


def test_a_document_without_outline_styles_fails_closed() -> None:
    document = _document_without_outline_styles()
    assert not any(n.startswith("개요") for n in document.styles.names())

    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_heading("제목", level=1)
    error = excinfo.value
    assert error.code == "heading-style-missing"
    assert error.context["level"] == 1
    assert error.context["tried"] == ["개요 1", "Outline 1", "paraPr heading level 0"]
    assert error.context["available"], "무엇이 있는지는 말해줘야 한다"
    assert "style=" in error.suggestion


def test_we_do_not_invent_outline_styles_in_someone_elses_document() -> None:
    """fail-closed 이지 자동 생성이 아니다 — 무손실 편집이 우리 계약이다."""

    document = _document_without_outline_styles()
    before = dict(document.oxml.styles)
    with pytest.raises(HwpxLookupError):
        document.add_heading("제목", level=1)
    assert dict(document.oxml.styles) == before


def test_an_explicit_style_still_works_without_outline_styles() -> None:
    document = _document_without_outline_styles()
    paragraph = document.add_heading("제목", level=1, style="본문")
    assert document.styles[str(paragraph.style_id_ref)].name == "본문"
    # 명시 스타일이어도 개요 수준은 붙는다 — 그게 add_heading 의 일이다.
    assert _heading_of(document, paragraph).type == "OUTLINE"


# --------------------------------------------------------------------------
# 폴백 4단계: 이름이 바뀐 야생 문서는 **구조**로 찾는다


def test_a_renamed_outline_style_is_found_by_its_paragraph_property() -> None:
    """이름을 바꿔도 `paraPr` 의 `hh:heading` 이 그 수준을 선언하면 찾는다."""

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for node in header.element.iter():
        if node.tag.rsplit("}", 1)[-1] == "style" and node.get("name") == "개요 1":
            node.set("name", "장 제목")
            node.set("engName", "Chapter Title")
            break
    else:  # pragma: no cover
        pytest.fail("Skeleton 에서 '개요 1' 을 찾지 못했습니다")

    assert "개요 1" not in document.styles.names()
    paragraph = document.add_heading("제1장", level=1)
    assert document.styles[str(paragraph.style_id_ref)].name == "장 제목"
    assert _heading_of(document, paragraph).type == "OUTLINE"


# --------------------------------------------------------------------------
# 명시 style= 은 스타일 해석기의 오류를 그대로 물려받는다


def test_an_explicit_style_typo_reports_the_closest_name() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_heading("제목", level=1, style="개요1")
    error = excinfo.value
    assert error.code == "style-not-found"
    assert "개요 1" in error.context["closest"]


def test_an_ambiguous_explicit_style_is_reported() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    for node in header.element.iter():
        if node.tag.rsplit("}", 1)[-1] == "style" and node.get("name") == "개요 1":
            clone = copy.deepcopy(node)
            clone.set("id", "901")
            node.getparent().append(clone)
            break
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_heading("제목", level=1, style="개요 1")
    assert excinfo.value.code == "style-ambiguous"


# --------------------------------------------------------------------------
# 섹션 인자는 §5 규약을 그대로 따른다


def test_add_heading_accepts_a_section_index() -> None:
    document = HwpxDocument.new()
    document.add_section()
    paragraph = document.add_heading("첫 섹션 제목", level=1, section=0)
    assert paragraph in document.sections[0].paragraphs


def test_add_heading_returns_a_model_paragraph() -> None:
    from hwpx import model

    document = HwpxDocument.new()
    assert isinstance(document.add_heading("t", level=1), model.Paragraph)


# --------------------------------------------------------------------------
# 게이트 ⑦ 3줄 데모 — 오라클 없이 시각 주장을 하지 않는다


def test_the_three_line_demo_runs_and_its_render_claim_stays_unverified(tmp_path) -> None:
    """설계서 §4.6 데모. 구조는 여기서 증명하고, **렌더는 주장하지 않는다.**

    실한컴 오라클은 이 스위트가 부를 수 있는 것이 아니다(헌법 V). 구조 계약만
    확인하고, 시각 판정은 `unverified` 로 남긴다 — 배치 경계에서 박스가 실한컴
    으로 판정한다.
    """

    document = HwpxDocument.new()
    document.add_heading("2026 학년도 운영계획", level=1)
    document.add_paragraph("가. 추진 배경", style="개요 2")
    target = tmp_path / "plan.hwpx"
    document.save_to_path(target)

    with HwpxDocument.open(target) as reopened:
        names = [
            reopened.styles[str(p.style_id_ref)].name
            for p in reopened.paragraphs
            if p.text.strip()
        ]
        assert names == ["개요 1", "개요 2"]

    render_verdict = "unverified"  # 오라클 미가용 — 이 스위트는 한컴을 부르지 않는다
    assert render_verdict == "unverified"
