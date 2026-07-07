"""fill_residue — 잔존물 zero-체크 게이트 (Stage 3 P1).

그라운드 트루스: 2026-07-06 평가계획 거짓 수렴에서 사람 눈이 잡았던 결함 유형
(빨간 지시문·미수정 샘플·placeholder)이, "blank를 그대로 낸 채움본"에서 전부
ERROR로 떠야 한다. 반대로 해당 텍스트를 제거/수정하면 그 finding이 사라져야 한다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hwpx.body_patch import apply_body_ops
from hwpx.fill_residue import inspect_fill_residue

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


@pytest.fixture(scope="module")
def unfilled_report():
    # 최악의 채움본 = blank 그대로 제출
    return inspect_fill_residue(BLANK, blank=BLANK)


class TestWorstCaseAllFlagged:
    def test_red_instructions_flagged(self, unfilled_report):
        reds = [f for f in unfilled_report.errors if f.kind == "delete_color_residue"]
        assert len(reds) >= 15  # 빨간 지시문 사이트들
        assert any("모두 삭제합니다" in f.text_preview for f in reds)

    def test_unmodified_samples_flagged(self, unfilled_report):
        samples = [f for f in unfilled_report.errors if f.kind == "unmodified_sample"]
        assert len(samples) >= 30  # 파란(수정) 샘플 다수
        assert any("음악" in f.text_preview or "노래" in f.text_preview for f in samples)

    def test_placeholders_flagged(self, unfilled_report):
        ph = [f for f in unfilled_report.errors if f.kind == "placeholder"]
        assert any("◯◯◯" in f.text_preview for f in ph)
        # ``**``는 각주 표식과 중의적 → needs_review로 강등(신청서 실측)
        amb = [f for f in unfilled_report.needs_review if f.kind == "placeholder_ambiguous"]
        assert any("**과목" in f.text_preview for f in amb)

    def test_verdict_fails(self, unfilled_report):
        assert unfilled_report.ok is False
        assert unfilled_report.to_dict()["ok"] is False


class TestFindingClearsAfterFix:
    def test_deleting_red_text_clears_that_finding(self, tmp_path):
        work = tmp_path / "w.hwpx"
        shutil.copy(BLANK, work)
        fixed = tmp_path / "fixed.hwpx"
        res = apply_body_ops(
            work,
            [{"op": "replace_text", "find": "빨간 글씨 삭제!! (환경)", "replace": ""}],
            output_path=fixed,
        )
        assert res.ok
        report = inspect_fill_residue(fixed, blank=BLANK)
        assert not any("(환경)" in f.text_preview for f in report.errors)
        # 다른 잔존물은 여전히 잡힘(게이트가 느슨해진 게 아님)
        assert report.ok is False


class TestWithoutBlank:
    def test_placeholder_only_mode(self):
        report = inspect_fill_residue(BLANK)  # blank 미제공 → 범례 신호 없음
        assert report.stats["blankDeleteTexts"] == 0
        assert any(f.kind == "placeholder" for f in report.errors)
