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
