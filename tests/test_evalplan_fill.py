# SPDX-License-Identifier: Apache-2.0
"""Evaluation-plan review-markdown parser + target skeleton.

Unit behaviour is pinned on a synthetic (non-PII) mini review markdown; a gated
test parses the owner-local real review MD when present (skips in CI).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hwpx.evalplan_fill import expected_skeleton, parse_review_file, parse_review_md

SYNTHETIC = """# 2026학년도 2학기 3학년 「합성 과목」 교수학습운영 및 평가계획 (검토용)

> **담당교사: 홍길동** · 수행평가 100% · 성취도 3단계

## Ⅰ. 교수학습 운영 계획

| 월 | 주 | 단원 | 성취기준 | 수업방법 | 주안점 |
|---|---|---|---|---|---|
| 8 | 3 | 단원1 | [12합성01-01] | 강의 | 주안점1 |
| 8 | 4 | 단원2 | [12합성01-02] | 실습 | 주안점2 |

## Ⅱ. 평가 세부 계획

### 1. 평가의 목적
가. 목적 하나. 나. 목적 둘.

### 2. 평가의 기본 방향
가. 방향.

### 3. 평가 방침
가. 방침.

### 4. 성취기준 및 성취수준
**가. 교육과정 성취기준·평가기준(상/중/하)**

| 성취기준 | 상 | 중 | 하 |
|---|---|---|---|
| [12합성01-01] 표준 하나 | 상1 | 중1 | 하1 |
| [12합성01-02] 표준 둘 | 상2 | 중2 | 하2 |
| [12합성01-03] 표준 셋 | 상3 | 중3 | 하3 |

**나. 영역별 성취수준(A/B/C)**

| 영역 | A | B | C |
|---|---|---|---|
| 영역 가 | A1 | B1 | C1 |
| 영역 나 | A2 | B2 | C2 |

### 5. 기준 성취율과 성취도
| 성취율(원점수) | 성취도 |
|---|---|
| 80% 이상 | A |
| 60% 이상 ~ 80% 미만 | B |
| 60% 미만 | C |

### 6. 평가의 종류와 반영비율 (수행평가 100%)

| 구분 | ① 영역 가 | ② 영역 나 | 합계 |
|---|---|---|---|
| 영역 만점 | 60점(60%) | 40점(40%) | 100% |

### 7. 수행평가 세부기준

**① 영역 가 (60점)** · [12합성01-01]

| 평가항목 | 채점 기준(배점) |
|---|---|
| 항목1 | 기준 **30** / **20** |
| 항목2 | 기준 **30** / **20** |

**② 영역 나 (40점)** · [12합성01-02]

| 평가항목 | 채점 기준(배점) |
|---|---|
| 항목1 | 기준 **40** / **20** |

### 8. 정의적 능력 평가
- 요소 하나.

### 9. 수행평가 미응시자
가. 처리.

### 10. 평가 유의사항
- 유의.

### 11. 평가 결과 분석 및 활용
- 활용.
"""


def test_parse_synthetic_structure():
    c = parse_review_md(SYNTHETIC)
    assert c.teacher == "홍길동"                       # markdown bold stripped
    assert "합성 과목" in c.title
    assert len(c.schedule) == 2 and len(c.schedule[0]) == 6
    assert len(c.achievement_std) == 3 and len(c.achievement_std[0]) == 4
    assert [r[0] for r in c.levels] == ["영역 가", "영역 나"]
    assert c.achieve_rate == [["80% 이상", "A"], ["60% 이상 ~ 80% 미만", "B"], ["60% 미만", "C"]]
    assert any("①" in h for h in c.ratio_header)
    assert [(r.title, r.points) for r in c.rubrics] == [("영역 가", 60), ("영역 나", 40)]
    assert len(c.rubrics[0].rows) == 2 and len(c.rubrics[1].rows) == 1
    assert c.purposes and c.cautions and c.analysis


def test_expected_skeleton_synthetic():
    c = parse_review_md(SYNTHETIC)
    sk = expected_skeleton(c)
    assert sk == {"achievement": 1, "level": 1, "rubric": 2, "achieve_rate": 1, "ratio": 1}


def test_empty_sections_not_invented():
    c = parse_review_md("# 제목 계획\n\n### 1. 평가의 목적\n가. 목적.\n")
    assert c.schedule == [] and c.rubrics == []
    sk = expected_skeleton(c)
    assert sk["rubric"] == 0 and sk["achievement"] == 0


FIXT = Path(__file__).parent / "fixtures" / "m105_evalplan"
BLANK_3HAK = FIXT / "blank_form_3hak.hwpx"


def _content_2area():
    return parse_review_md(SYNTHETIC)


def test_plan_structural_ops_index_safe_order():
    """Column deletes must precede table deletes (they don't shift table indices),
    and table deletes must be in descending index order -- otherwise a later
    delete_column lands on a shifted table and silently corrupts it."""
    from hwpx.evalplan_fill import plan_structural_ops
    plan = plan_structural_ops(str(BLANK_3HAK), _content_2area())
    ops = plan["ops"]
    kinds = [o["op"] for o in ops]
    # every delete_column comes before every delete_table
    if "delete_column" in kinds and "delete_table" in kinds:
        assert kinds.index("delete_column") < kinds.index("delete_table")
    # table deletes are strictly descending by index
    tdel = [o["tableIndex"] for o in ops if o["op"] == "delete_table"]
    assert tdel == sorted(tdel, reverse=True)
    # the red tables + 정기시험 column are targeted
    assert any(o["op"] == "delete_column" for o in ops)  # 정기시험
    assert len(tdel) >= 3                                 # seokcha/submit/notice + 5단계/surplus


def test_fill_evalplan_structural_is_byte_preserving_and_removes_red():
    """The structural transform applies cleanly, removes the red/정기시험 material,
    and keeps every surviving table's formatting (no regeneration)."""
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import _skeleton, score_format_fidelity
    res = fill_evalplan(str(BLANK_3HAK), _content_2area())
    assert res["ok"] and not res["skipped"]
    prod = res["_data"]
    sk = _skeleton(prod)
    assert sk["ratio_has_regular_exam"] is False          # 정기시험 removed
    assert sk["kinds"].get("seokcha", 0) == 0             # red table gone
    # surviving tables carried verbatim -> high B (not a rebuild)
    b = score_format_fidelity(prod, str(BLANK_3HAK))
    assert b.detail["carry_rate"] > 0.8


def test_content_fidelity_axis_flags_unfilled(tmp_path):
    """D content-fidelity: a produced file lacking the review's standard codes
    scores low (not a silent pass)."""
    from hwpx.formfill_quality import score_content
    md = tmp_path / "c.md"
    md.write_text("[12합성01-01] [12합성01-02] [12합성01-03]", encoding="utf-8")
    a = score_content(str(BLANK_3HAK), content=str(md))   # blank has no 합성 codes
    assert a.detail["content_match"] == 0.0
    assert any("content matches review MD" in f for f in a.findings)


_MD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/검토용_MD/2026_2학기_3학년_인공지능기초_검토용.md"))


@pytest.mark.skipif(not _MD.exists(), reason="owner-local review MD not present (not vendored)")
def test_real_3hak_review_md_skeleton():
    c = parse_review_file(str(_MD))
    assert c.teacher == "고규현"
    assert len(c.schedule) == 21 and len(c.achievement_std) == 8
    assert len(c.levels) == 3
    assert expected_skeleton(c) == {
        "achievement": 1, "level": 1, "rubric": 3, "achieve_rate": 1, "ratio": 1}
    assert [r.points for r in c.rubrics] == [35, 35, 30]
