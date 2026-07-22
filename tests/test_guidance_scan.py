"""guidance_scan Stage-1 정찰 엔진 — 실양식(평가계획) 그라운드 트루스 테스트.

그라운드 트루스 출처(이중 검증):
1) 2026-07-06 오너/root의 produced_3hak.pdf 시각 전수 감사에서 확인된 결함 위치들
   (빨간 지시문·placeholder·조건부 블록·타과목 샘플)이 blank에서 후보로 잡혀야 한다.
2) root의 ElementTree 부모-체인 독립 계수: blank_form_3hak 빨강(#FF0000) 37 t-span ·
   파랑(#0000FF) 189 t-span. 스캐너는 이 전수를 커버해야 한다(4% 셀-블라인드 재발 방지).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from hwpx.guidance_scan import scan_form_guidance

FIXTURES = Path(__file__).parent / "fixtures" / "m105_evalplan"
BLANK_3HAK = FIXTURES / "blank_form_3hak.hwpx"
BLANK_12HAK = FIXTURES / "blank_form_1-2hak.hwpx"


@pytest.fixture(scope="module")
def report_3hak():
    return scan_form_guidance(BLANK_3HAK)


def _independent_color_spans(path: Path, hex_color: str) -> int:
    """스캐너와 독립인 계수 오라클: 부모-체인 기반 색 t-span 수."""

    def local(el) -> str:
        return el.tag.split("}")[-1]

    with zipfile.ZipFile(path) as z:
        header = ET.fromstring(z.read("Contents/header.xml"))
        colors = {
            cp.get("id"): (cp.get("textColor") or "#000000").upper()
            for cp in header.iter()
            if local(cp) == "charPr"
        }
        total = 0
        for part in z.namelist():
            if not part.startswith("Contents/section"):
                continue
            root = ET.fromstring(z.read(part))
            parent = {c: p for p in root.iter() for c in p}
            for t in root.iter():
                if local(t) != "t" or not "".join(t.itertext()).strip():
                    continue
                run = parent.get(t)
                while run is not None and local(run) != "run":
                    run = parent.get(run)
                if run is None:
                    continue
                if colors.get(run.get("charPrIDRef", "0"), "#000000") == hex_color:
                    total += 1
        return total


def _scanner_color_spans(report, hex_color: str) -> int:
    return report.color_inventory.get(hex_color, {}).get("runs", 0)


class TestColorCoverage:
    """셀 내부·캡션 포함 100% 색 커버리지 — find_runs_by_style의 4% 블라인드 재발 방지."""

    def test_red_spans_match_independent_count(self, report_3hak):
        independent = _independent_color_spans(BLANK_3HAK, "#FF0000")
        assert independent >= 30  # 양식에 빨간 지시문이 실재
        assert _scanner_color_spans(report_3hak, "#FF0000") == independent

    def test_blue_spans_match_independent_count(self, report_3hak):
        independent = _independent_color_spans(BLANK_3HAK, "#0000FF")
        assert independent >= 150
        assert _scanner_color_spans(report_3hak, "#0000FF") == independent


class TestLegend:
    def test_three_way_legend_parsed(self, report_3hak):
        actions = {b.family: b.action for b in report_3hak.legend}
        assert actions.get("black") == "keep"
        assert actions.get("blue") == "modify"
        assert actions.get("red") == "delete"

    def test_red_binding_recovers_exact_hex_from_legend_ink(self, report_3hak):
        red = next(b for b in report_3hak.legend if b.family == "red")
        assert red.exact_hex == "#FF0000"


class TestDeleteCandidates:
    """오너 시각 감사에서 '산출물에 남아 있던' 빨간 지시문들이 후보로 잡히는가."""

    @pytest.mark.parametrize(
        "needle",
        [
            "빨간색 글씨는 모두 삭제합니다",  # p1 색 범례 유의문
            "맞추어 작성해주세요",  # §Ⅱ 유의문
            "해당하는 것만 남기고 나머지는 삭제",  # ***유의 조건부
            "빨간 글씨 삭제!!",  # 분할점수 캡션
            "교과별로 수정 및 추가",  # 반복 red 꼬리 항목
            "모두 삭제 바랍니다",  # 마지막 페이지 통째 삭제 지시
        ],
    )
    def test_known_red_instruction_is_candidate(self, report_3hak, needle):
        assert any(
            needle in c.text_preview and c.confidence == "high"
            for c in report_3hak.delete_candidates
        ), f"미탐지: {needle}"

    def test_red_instructions_inside_table_cells_are_found(self, report_3hak):
        # 학생 유의사항 셀 안 빨간 지시(산출물에 3회 반복 잔존했던 그 텍스트)
        in_cell = [
            c
            for c in report_3hak.delete_candidates
            if c.cell is not None and "삭제" in c.text_preview
        ]
        assert in_cell, "셀 내부 빨간 지시문을 하나도 못 찾음(셀 블라인드 재발)"


class TestPlaceholders:
    def test_title_double_star_placeholder(self, report_3hak):
        assert any(
            "**과목" in c.text_preview and "placeholder:double_star" in c.signals
            for c in report_3hak.placeholder_candidates
        )

    def test_teacher_circle_blank(self, report_3hak):
        assert any(
            "담당교사" in c.text_preview and "placeholder:circle_blank" in c.signals
            for c in report_3hak.placeholder_candidates
        )


class TestConditionalAndQuestions:
    def test_split_score_conditional_block_detected(self, report_3hak):
        assert any(
            "남기고 나머지는 삭제" in c.text_preview for c in report_3hak.conditional_choices
        )

    def test_questions_include_circle_blank_value(self, report_3hak):
        assert any("◯◯◯" in q for q in report_3hak.questions)


class TestModifyTargets:
    def test_blue_sample_music_content_flagged_as_modify(self, report_3hak):
        # 산출물에 잔존했던 음악 샘플("연주/비평" 등 파랑)이 수정 대상으로 집계되는가
        assert report_3hak.modify_candidates_by_table, "파랑 수정 대상 집계가 비어 있음"
        total = sum(v["paragraphs"] for v in report_3hak.modify_candidates_by_table.values())
        assert total >= 50  # 파랑 문단이 광범위하게 존재하는 양식임


class TestGeneralizationSmoke:
    def test_scans_sibling_form_without_domain_knowledge(self):
        report = scan_form_guidance(BLANK_12HAK)
        assert report.stats["paragraphs"] > 100
        assert report.legend, "1-2학년 양식에서 범례 미발견"
        assert report.delete_candidates
        assert report.to_markdown()


class TestIsFormInstruction:
    """is_form_instruction — 색 없이 텍스트만으로 지시-문구 문단을 판정하는 렉시콘.

    검정(무색) 안내 문단까지 걸러야 하는 evalplan finalize용. 모호한 마커(※·유의))는
    정상 유의사항 본문 오삭제를 막으려 일부러 제외한다."""

    def test_instruction_phrases_true(self):
        from hwpx.guidance_scan import is_form_instruction
        for s in [
            "이 부분은 삭제 바랍니다.",
            "교과별로 수정하세요",
            "교과별 특성이 드러나게 작성",
            "재구성하여 작성",
            "빨간 글씨는 안내입니다",
            "파란색 글씨를 과목에 맞게",
            "추정분할점수 표",
            "궁금하면 문의 주세요",
            "여기에 작성해 주세요",
            "해당하는 것만 남기고",
        ]:
            assert is_form_instruction(s), s

    def test_legit_content_false(self):
        from hwpx.guidance_scan import is_form_instruction
        for s in [
            "가급적 동점자가 없도록 배점을 설계한다.",
            "문제해결에 탐색을 활용하기",
            "성취기준 [12합성01-01]을 평가한다",
            "※ 재시험은 실시하지 않는다.",   # 모호 마커 — 정상 유의사항, 삭제 금지
            "(유의) 제출 기한을 지킬 것",       # 모호 마커 — 오삭제 금지
            "",
        ]:
            assert not is_form_instruction(s), s
