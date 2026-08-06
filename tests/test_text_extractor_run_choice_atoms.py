# SPDX-License-Identifier: Apache-2.0
"""``hp:t``에 중첩되는 특수 인라인 텍스트 원자(``lineBreak``/``nbSpace``/
``fwSpace``/``hyphen``) 읽기 — 사이클 6.5 트레인 19.

발견한 결함: ``ParaList XML schema.xml``의 ``TextType``(``hp:t``의 내용
모델)은 이 네 원자를 평문 텍스트와 같은 자리(mixed content)에 둔다 —
실코퍼스(``error__20230818__test.hwpx``의 ``hp:lineBreak``,
``error__20251107__test.hwpx``의 ``hp:fwSpace``,
``error__20250808__...hwpx``의 ``hp:nbSpace``)가 이를 확인한다. 그런데
``TextExtractor._render_text_element``는 이 자리를 놓치고 있었다 —
``markpenBegin``/``markpenEnd``가 아닌 자식은 전부 재귀 호출로 넘겼는데,
이 네 원자는 텍스트도 자식도 없는 빈 요소라 재귀가 아무것도 안 만들고,
그 결과 원자 자체가 조용히 사라지면서 앞뒤 텍스트만 아무 구분자 없이
이어 붙었다(예: "표기함<hp:lineBreak/>예)"가 "표기함예)"로 읽힘 — 줄바꿈이
있었다는 사실 자체가 유실).
"""

from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from hwpx.tools.text_extractor import TextExtractor

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "fixtures" / "hwpxlib_corpus"


def _archive_with_paragraph(t_inner_xml: str) -> ZipFile:
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<hs:sec xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'"
        " xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>"
        "  <hp:p>"
        "    <hp:run>"
        f"      <hp:t>{t_inner_xml}</hp:t>"
        "    </hp:run>"
        "  </hp:p>"
        "</hs:sec>"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as builder:
        builder.writestr("Contents/section0.xml", xml)
    buffer.seek(0)
    return ZipFile(buffer)


def _first_paragraph_text(t_inner_xml: str, **kwargs: object) -> str:
    archive = _archive_with_paragraph(t_inner_xml)
    try:
        with TextExtractor(archive) as extractor:
            paragraphs = list(extractor.iter_document_paragraphs(include_nested=False))
        return paragraphs[0].text(**kwargs)
    finally:
        archive.close()


# ============================================================================
# 게이트 ① 결함-부활 — 실코퍼스로 재현
# ============================================================================


def test_line_break_nested_in_t_no_longer_vanishes_on_real_corpus() -> None:
    """error__20230818__test.hwpx: 수리 전에는 "표기함예)"로 붙어 읽혔다
    (줄바꿈 유실). 수리 후에는 "표기함\\n예)"로 갈라져야 한다."""

    with TextExtractor(CORPUS / "error__20230818__test.hwpx") as extractor:
        matches = [
            info.text()
            for info in extractor.iter_document_paragraphs()
            if info.text() and "노선 정거장이 더 많이 포함되는 시도" in info.text()
        ]
    assert len(matches) == 1
    assert "표기함\n예)" in matches[0]
    assert "표기함예)" not in matches[0]


def test_fw_space_nested_in_t_no_longer_vanishes_on_real_corpus() -> None:
    """error__20251107__test.hwpx: hp:t의 첫 자식이 hp:fwSpace다."""

    with TextExtractor(CORPUS / "error__20251107__test.hwpx") as extractor:
        matches = [
            info.text()
            for info in extractor.iter_document_paragraphs()
            if info.text() and "혼합 기체에서 몰 분율을 이해하고" in info.text()
        ]
    assert len(matches) == 1
    assert matches[0].startswith("　[12화학Ⅱ01-03]")


def test_nb_space_nested_in_t_no_longer_vanishes_on_real_corpus() -> None:
    """error__20250808__...hwpx: hp:t의 첫 자식이 hp:nbSpace다."""

    with TextExtractor(
        CORPUS / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
    ) as extractor:
        matches = [
            info.text()
            for info in extractor.iter_document_paragraphs()
            if info.text() and "대륙고기압과 이동성 고기압의 영향을 주기적으로" in info.text()
        ]
    assert len(matches) >= 1
    assert " 대륙고기압" in matches[0]


# ============================================================================
# 게이트 ② 합성 픽스처 — 4원자 전부 + preserve_breaks 플래그
# ============================================================================


def test_line_break_becomes_newline() -> None:
    text = _first_paragraph_text("before<hp:lineBreak/>after")
    assert text == "before\nafter"


def test_line_break_is_dropped_when_breaks_not_preserved() -> None:
    text = _first_paragraph_text("before<hp:lineBreak/>after", preserve_breaks=False)
    assert text == "beforeafter"


def test_nb_space_becomes_no_break_space() -> None:
    text = _first_paragraph_text("before<hp:nbSpace/>after")
    assert text == "before after"


def test_nb_space_flattens_to_plain_space_when_breaks_not_preserved() -> None:
    text = _first_paragraph_text("before<hp:nbSpace/>after", preserve_breaks=False)
    assert text == "before after"


def test_fw_space_becomes_ideographic_space() -> None:
    text = _first_paragraph_text("before<hp:fwSpace/>after")
    assert text == "before　after"


def test_fw_space_flattens_to_plain_space_when_breaks_not_preserved() -> None:
    text = _first_paragraph_text("before<hp:fwSpace/>after", preserve_breaks=False)
    assert text == "before after"


def test_hyphen_becomes_soft_hyphen() -> None:
    text = _first_paragraph_text("before<hp:hyphen/>after")
    assert text == "before­after"


def test_hyphen_is_dropped_entirely_when_breaks_not_preserved() -> None:
    """소프트 하이픈은 서식 정보라 preserve_breaks=False에서 "-"로 뭉개지지
    않고 아예 없어진다(tab이 "\\t"→" "로 뭉개지는 것과는 다른 취급 — 하이픈은
    평문화 시 어떤 문자로도 대체할 근거가 없는 순수 서식 힌트)."""

    text = _first_paragraph_text("before<hp:hyphen/>after", preserve_breaks=False)
    assert text == "beforeafter"


def test_all_four_atoms_together_preserve_order() -> None:
    text = _first_paragraph_text(
        "a<hp:lineBreak/>b<hp:nbSpace/>c<hp:fwSpace/>d<hp:hyphen/>e"
    )
    assert text == "a\nb c　d­e"
