# SPDX-License-Identifier: Apache-2.0
"""``hp:titleMark`` 저작(``add_title_mark``) -- 사이클 6.15, 박스 COM
InsertFile 이월 트레인의 ③번 항목.

계약 출처: DEV-044(스키마는 hp:t 선택군 자식으로 titleMark를 선언하되
xs:documentation은 없음). 캐럿 문단 타겟팅이 실측 미확정이라 저작을
보류하고 있었으나, 팀장의 Windows 박스 COM ``SetPos``+
``MarkTitle``/``HideTitle`` 3변형이 캐럿 문단 타겟팅을 확정했다(gold를
``tests/fixtures/gui_probes/title_mark_caret_p{1,2}_{mark,hide}.hwpx``로
편입) -- 마크는 항상 캐럿이 있는 문단의 첫 run 첫 ``hp:t`` 맨 앞에,
그 문단 자신의 텍스트 바로 앞에 들어간다. 이전 Mac 프로브의 절 정의
문단(p0) 착지는 캐럿을 못 옮겨서 생긴 퇴화 현상이었음이 이걸로 최종
확인됐다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxStateError

_FIXTURES = Path(__file__).parent / "fixtures" / "gui_probes"


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def test_add_title_mark_matches_the_real_gold_contract_in_toc() -> None:
    """실측(``tm_sp2_mark.hwpx``): <hp:t><hp:titleMark ignore="1"/>제목
    B</hp:t> -- 표시(제목 차례 표시)는 ignore="1"(이름의 직관과 반대)."""

    document = HwpxDocument.new()
    document.add_heading("제목 A", level=1)
    heading_b = document.add_heading("제목 B", level=1)

    heading_b.add_title_mark(in_toc=True)

    xml = _section_xml(document)
    assert "<hp:t><hp:titleMark ignore=\"1\"/>제목 B</hp:t>" in xml


def test_add_title_mark_matches_the_real_gold_contract_hidden() -> None:
    """실측(``tm_sp2_hide.hwpx``): ignore="0" -- 숨김(차례 숨기기)은
    ignore="0"(역시 이름의 직관과 반대)."""

    document = HwpxDocument.new()
    document.add_heading("제목 A", level=1)
    heading_b = document.add_heading("제목 B", level=1)

    heading_b.add_title_mark(in_toc=False)

    xml = _section_xml(document)
    assert "<hp:t><hp:titleMark ignore=\"0\"/>제목 B</hp:t>" in xml


def test_add_title_mark_targets_whichever_heading_paragraph_is_given() -> None:
    """실측(``tm_sp1_mark.hwpx``): 문서의 두 헤딩 중 어느 쪽이든 호출자가
    지정한 문단에 정확히 들어간다 -- 항상 첫 문단(p0)이 아니다."""

    document = HwpxDocument.new()
    heading_a = document.add_heading("제목 A", level=1)
    document.add_heading("제목 B", level=1)

    heading_a.add_title_mark(in_toc=True)

    xml = _section_xml(document)
    assert "<hp:t><hp:titleMark ignore=\"1\"/>제목 A</hp:t>" in xml
    # 제목 B 쪽 run에는 마크가 없어야 한다(대상 오귀속 없음).
    assert "<hp:t>제목 B</hp:t>" in xml


def test_add_title_mark_on_an_empty_paragraph_leaves_no_trailing_text() -> None:
    """빈 문단(구조상 초기 확인된 절 정의 문단류)에 걸면 텍스트 없이
    마크만 남는다 -- tail이 빈 문자열/None으로 조용히 처리."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=True)

    paragraph.add_title_mark(in_toc=False)

    xml = _section_xml(document)
    assert "<hp:t><hp:titleMark ignore=\"0\"/></hp:t>" in xml


def test_add_title_mark_rejects_a_run_less_paragraph() -> None:
    document = HwpxDocument.new()
    paragraph = document._root.sections[0].add_paragraph("", include_run=False)

    with pytest.raises(HwpxStateError) as excinfo:
        paragraph.add_title_mark(in_toc=True)
    assert excinfo.value.code == "paragraph-title-mark-no-text-run"


def test_add_title_mark_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    heading = document.add_heading("제목 A", level=1)
    heading.add_title_mark(in_toc=True)

    reopened = HwpxDocument.open(document.to_bytes())

    xml = _section_xml(reopened)
    assert "<hp:t><hp:titleMark ignore=\"1\"/>제목 A</hp:t>" in xml


@pytest.mark.parametrize(
    ("fixture_name", "expected_paragraph_text", "expected_ignore"),
    [
        ("title_mark_caret_p2_mark.hwpx", "제목 B", "1"),
        ("title_mark_caret_p2_hide.hwpx", "제목 B", "0"),
        ("title_mark_caret_p1_mark.hwpx", "제목 A", "1"),
    ],
)
def test_real_gold_fixtures_open_and_expose_the_titlemark_verbatim(
    fixture_name: str, expected_paragraph_text: str, expected_ignore: str
) -> None:
    """Windows 박스 COM `SetPos`+`MarkTitle`/`HideTitle` 실측 gold를 이
    라이브러리로 직접 열어, GenericElement 불투명 보존 경로가 무손실로
    왕복함을 확인한다(전용 읽기 모델은 여전히 없음 -- 저작만 신규)."""

    fixture = _FIXTURES / fixture_name
    document = HwpxDocument.open(fixture)
    try:
        xml = _section_xml(document)
    finally:
        document.close()

    assert f'<hp:t><hp:titleMark ignore="{expected_ignore}"/>{expected_paragraph_text}</hp:t>' in xml
