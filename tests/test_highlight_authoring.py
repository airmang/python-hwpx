# SPDX-License-Identifier: Apache-2.0
"""``doc.text.highlight``/``doc.text.highlights`` — 형광펜 저작·읽기 계약 테스트.

실코퍼스 리버스(``hwpxlib_corpus/error__20251107__test*.hwpx``, 감사 갭 #5의
유일한 실 fixture)와 OWPML 스키마(``ParaList XML schema.xml``)가 합의하는 형태를
고정한다: ``markpenBegin``/``markpenEnd``는 단일 ``hp:t`` 안에서 위치로 짝짓는다
(id 없음, LIFO). 저작은 ``doc.tracking.delete``와 같은 단일-run 매치 제약을 쓴다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxLookupError, HwpxValueError
from hwpx.objects import Highlight

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
REPO = Path(__file__).resolve().parent.parent
REAL_CORPUS_FILE = (
    REPO / "tests" / "fixtures" / "hwpxlib_corpus" / "error__20251107__test.hwpx"
)


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("Hello World")
    return doc


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if name.endswith("section0.xml")
        )


# --------------------------------------------------------------------------
# 저작 — 신규 형광펜


def _element_xml(paragraph) -> str:
    import xml.etree.ElementTree as ET

    return ET.tostring(paragraph.element, encoding="unicode")


def test_highlight_wraps_the_first_match_and_returns_it() -> None:
    document = _document()
    result = document.text.highlight(1, "World", color="#00CCFF")

    assert isinstance(result, Highlight)
    assert result.text == "World"
    assert result.color == "#00CCFF"
    assert result.paragraph.element is document.paragraphs[1].element

    element_xml = _element_xml(document.paragraphs[1])
    assert "<hp:markpenBegin color=\"#00CCFF\"" in element_xml
    assert "World" in element_xml
    assert "<hp:markpenEnd" in element_xml
    # markpenBegin/End precede/follow exactly the matched text, not the run.
    assert element_xml.index("Hello ") < element_xml.index("markpenBegin")
    assert element_xml.index("markpenBegin") < element_xml.index("World")
    assert element_xml.index("World") < element_xml.index("markpenEnd")


def test_highlight_default_color_is_yellow() -> None:
    document = _document()
    result = document.text.highlight(1, "Hello")
    assert result.color == "#FFFF00"


def test_highlights_enumerates_in_document_order() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("alpha beta")
    document.add_paragraph("gamma delta")
    document.text.highlight(1, "beta", color="#FFFF00")
    document.text.highlight(2, "gamma", color="#00FF00")

    found = document.text.highlights()
    assert [(h.text, h.color) for h in found] == [
        ("beta", "#FFFF00"),
        ("gamma", "#00FF00"),
    ]
    assert found[0].paragraph.element is document.paragraphs[1].element
    assert found[1].paragraph.element is document.paragraphs[2].element


def test_highlight_paragraph_accepts_an_index_or_an_object() -> None:
    document = _document()
    assert (
        document.text.highlight(1, "Hello").paragraph.element
        is document.paragraphs[1].element
    )
    document.add_paragraph("Second paragraph")
    assert (
        document.text.highlight(document.paragraphs[2], "Second").paragraph.element
        is document.paragraphs[2].element
    )


def test_nested_highlights_pair_positionally_like_the_reader() -> None:
    """``markpenEnd`` carries no id — the innermost open begin closes first,
    the same LIFO rule ``text_extractor``'s ``highlight_stack`` already
    applies when *reading*. Highlighting a substring of an already-highlighted
    run nests rather than erroring."""

    document = _document()
    document.text.highlight(1, "World", color="#FFFF00")
    document.text.highlight(1, "orl", color="#00FF00")

    found = document.text.highlights()
    assert [(h.text, h.color) for h in found] == [
        ("orl", "#00FF00"),
        ("Wd", "#FFFF00"),
    ]


def test_highlight_round_trips_through_save_and_reopen(tmp_path) -> None:
    document = _document()
    document.text.highlight(1, "World", color="#123ABC")
    path = tmp_path / "highlight.hwpx"
    document.save_to_path(path)
    document.close()

    xml = _section_xml(path)
    assert '<hp:markpenBegin color="#123ABC"' in xml
    assert "<hp:markpenEnd" in xml

    reopened = HwpxDocument.open(path)
    found = reopened.text.highlights()
    assert [(h.text, h.color) for h in found] == [("World", "#123ABC")]
    reopened.close()


def test_authored_highlight_passes_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    document = _document()
    document.text.highlight(1, "World")
    path = tmp_path / "safe.hwpx"
    document.save_to_path(path)
    document.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# --------------------------------------------------------------------------
# typed error — 색·매치·범위


def test_highlight_empty_match_is_a_typed_error() -> None:
    document = _document()
    with pytest.raises(HwpxValueError) as excinfo:
        document.text.highlight(1, "")
    assert excinfo.value.code == "text-highlight-match-empty"
    assert excinfo.value.suggestion


def test_highlight_missing_match_is_a_typed_error() -> None:
    document = _document()
    with pytest.raises(HwpxValueError) as excinfo:
        document.text.highlight(1, "존재하지않음")
    assert excinfo.value.code == "text-highlight-match-not-found"
    assert excinfo.value.context["match"] == "존재하지않음"


@pytest.mark.parametrize(
    "color", ["yellow", "#FFF", "#GGGGGG", "FFFF00", "#FFFF0000", ""]
)
def test_highlight_invalid_color_is_a_typed_error(color: str) -> None:
    document = _document()
    with pytest.raises(HwpxValueError) as excinfo:
        document.text.highlight(1, "Hello", color=color)
    assert excinfo.value.code == "text-highlight-color-invalid"
    assert excinfo.value.context["color"] == color


def test_highlight_crossing_existing_markup_is_a_typed_error() -> None:
    document = _document()
    document.text.highlight(1, "World", color="#FFFF00")
    # "lo Wo" straddles the leading_text / markpenBegin-trailing_text boundary.
    with pytest.raises(HwpxValueError) as excinfo:
        document.text.highlight(1, "lo Wo")
    assert excinfo.value.code == "text-highlight-match-crosses-markup"


def test_highlight_out_of_range_paragraph_is_a_typed_error() -> None:
    document = _document()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.text.highlight(999, "Hello")
    assert excinfo.value.code == "paragraph-not-found"


def test_highlight_errors_are_still_catchable_as_plain_value_error() -> None:
    """5.x 스타일 ``except ValueError`` 호환 — house 컨벤션."""

    document = _document()
    with pytest.raises(ValueError):
        document.text.highlight(1, "")
    with pytest.raises(ValueError):
        document.text.highlight(1, "Hello", color="not-a-color")


def test_highlight_is_a_registered_error_code() -> None:
    from hwpx.errors import ERROR_CODES

    for code in (
        "text-highlight-match-empty",
        "text-highlight-match-not-found",
        "text-highlight-match-crosses-markup",
        "text-highlight-color-invalid",
    ):
        assert code in ERROR_CODES


# --------------------------------------------------------------------------
# 실코퍼스 — hwpxlib_corpus/error__20251107__test*.hwpx


@pytest.mark.skipif(not REAL_CORPUS_FILE.exists(), reason="real corpus fixture missing")
def test_real_corpus_malformed_pair_reads_as_empty_not_fabricated() -> None:
    """알려진 갭 — ``markpenBegin``이 ``hp:t`` 밖(``hp:run`` 직속)에 있는 유일한
    실 fixture. 스키마 위반 배치라 span 모델이 못 찾는다 — 만들어내지 않고
    정직하게 0을 보고한다(이 파일 자체가 hwpxlib "error" 회귀 fixture다:
    재저장본(``_test_re.hwpx``)에서 한컴 자신도 ``color`` 속성을 잃는다).

    이 테스트는 갭을 **고정**한다 — 형광펜 읽기가 이 배치까지 잡도록
    확장되면 여기가 붉어지고, 그때 이 테스트를 갱신하면 된다.
    """

    document = HwpxDocument.open(REAL_CORPUS_FILE)
    try:
        assert document.text.highlights() == ()
    finally:
        document.close()


@pytest.mark.skipif(not REAL_CORPUS_FILE.exists(), reason="real corpus fixture missing")
def test_real_corpus_new_highlight_coexists_with_the_original_malformed_pair(
    tmp_path,
) -> None:
    """실파일에 신규 형광펜을 더해도 기존(스키마 위반) 마크는 바이트 그대로다."""

    document = HwpxDocument.open(REAL_CORPUS_FILE)
    target = None
    for paragraph in document.paragraphs:
        text = paragraph.text
        if len(text.strip()) < 10:
            continue
        if any(span.marks for run in paragraph.runs for span in run.to_model().text_spans):
            continue
        target = paragraph
        break
    assert target is not None, "no plain paragraph found to highlight"

    word = target.text.split()[0]
    created = document.text.highlight(target, word, color="#00CCFF")
    assert created.text == word

    out = tmp_path / "roundtrip.hwpx"
    document.save_to_path(out)
    document.close()

    # The original malformed markpenBegin (color #CBFF99, sibling of hp:ctrl
    # rather than nested in hp:t) survives byte-identical.
    with zipfile.ZipFile(REAL_CORPUS_FILE) as archive:
        original_section = archive.read("Contents/section1.xml")
    with zipfile.ZipFile(out) as archive:
        new_section = archive.read("Contents/section1.xml")
    original_text = original_section.decode("utf-8")
    new_text = new_section.decode("utf-8")
    marker = '<hp:markpenBegin color="#CBFF99"/><hp:ctrl><hp:fieldBegin id="1770492296"'
    assert marker in original_text
    assert marker in new_text

    reopened = HwpxDocument.open(out)
    try:
        found = [h for h in reopened.text.highlights() if h.text == word]
        assert len(found) == 1
        assert found[0].color == "#00CCFF"
    finally:
        reopened.close()
