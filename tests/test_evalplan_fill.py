# SPDX-License-Identifier: Apache-2.0
"""Evaluation-plan review-markdown parser + target skeleton.

Unit behaviour is pinned on a synthetic (non-PII) mini review markdown; a gated
test parses the owner-local real review MD when present (skips in CI).
"""
from __future__ import annotations

import os
import re
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
    assert sk == {"achievement": 1, "level": 1, "minlevel": 0,
                  "rubric": 2, "achieve_rate": 1, "ratio": 1}


def test_empty_sections_not_invented():
    c = parse_review_md("# 제목 계획\n\n### 1. 평가의 목적\n가. 목적.\n")
    assert c.schedule == [] and c.rubrics == []
    sk = expected_skeleton(c)
    assert sk["rubric"] == 0 and sk["achievement"] == 0


FIXT = Path(__file__).parent / "fixtures" / "m105_evalplan"
BLANK_3HAK = FIXT / "blank_form_3hak.hwpx"
BLANK_2HAK = FIXT / "blank_form_1-2hak.hwpx"   # 2022-개정 (1·2학년) public form


# A synthetic 2022-개정 (2학년) review markdown: unified A~E 성취기준 table, grade-major
# 학기 단위 성취수준 (A~E), a 5-band 성취율 table, a 3-area 반영비율, and 평가 영역명 rubrics
# -- exercises every 2022-개정 recipe path with no PII.
SYNTHETIC_2022 = """# 2026학년도 2학기 2학년 「합성 과목」 교수학습운영 및 평가계획 (검토용)

> **담당교사: 김철수** · 수행평가 100% · 성취도 5단계

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
**가. 성취기준별 성취수준(A~E)**

| 성취기준 | A | B | C | D | E |
|---|---|---|---|---|---|
| [12합성01-01] 표준 하나 | 상상1 | 상1 | 중1 | 하1 | 최하1 |
| [12합성01-02] 표준 둘 | 상상2 | 상2 | 중2 | 하2 | 최하2 |

**나. 학기 단위 성취수준(A~E)**

| 수준 | 일반적 특성 |
|---|---|
| A | 특성 A. |
| B | 특성 B. |
| C | 특성 C. |
| D | 특성 D. |
| E | 특성 E. |

### 5. 기준 성취율과 성취도
| 성취율(원점수) | 성취도 |
|---|---|
| 90% 이상 | A |
| 80% 이상 ~ 90% 미만 | B |
| 70% 이상 ~ 80% 미만 | C |
| 60% 이상 ~ 70% 미만 | D |
| 60% 미만 | E |

### 6. 평가의 종류와 반영비율 (수행평가 100%)

| 구분 | ① 영역 가 | ② 영역 나 | ③ 영역 다 | 합계 |
|---|---|---|---|---|
| 영역 만점 | 45점(45%) | 30점(30%) | 25점(25%) | 100% |

### 7. 수행평가 세부기준

**① 영역 가 (45점)** · [12합성01-01]

| 평가항목 | 채점 기준(배점) |
|---|---|
| 알파 항목 구현하기 | 완비 **30** / 부분 **20** |
| 베타 항목 완성하기 | 완비 **15** / 부분 **10** |
| 기본점수 **18** · 장기 미인정 결석 **17** | |

**② 영역 나 (30점)** · [12합성01-02]

| 평가항목 | 채점 기준(배점) |
|---|---|
| 감마 식별하기 | 정확 **10** / 부분 **6** |
| 델타 적용하기 | 정확 **10** / 부분 **6** |
| 엡실론 논술하기 | 정확 **10** / 부분 **6** |
| 기본점수 **12** · 장기 미인정 결석 **11** | |

**③ 영역 다 (25점)** · [12합성01-02]

| 평가항목 | 채점 기준(배점) |
|---|---|
| 제타 해석하기 | 근거 **9** / 부분 **5** |
| 에타 판단하기 | 근거 **8** / 부분 **4** |
| 세타 평가하기 | 근거 **8** / 부분 **4** |
| 기본점수 **10** · 장기 미인정 결석 **9** | |

### 8. 정의적 능력 평가
- 요소 하나.

### 9. 수행평가 미응시자
가. 처리.

### 10. 평가 유의사항
- 유의.

### 11. 평가 결과 분석 및 활용
- 활용.
"""


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


def test_prose_drops_section_title_line():
    """The numbered-section prose fields must not carry the '### N. 평가의 목적'
    title the section regex sweeps in -- the D scorer anchors on the first prose
    words, so a leaked title breaks the anchor."""
    c = parse_review_md(SYNTHETIC)
    assert not c.purposes.startswith("평가의 목적")   # title line dropped
    assert "목적 하나" in c.purposes                  # prose kept
    assert not c.policies.startswith("평가 방침")


def test_fill_achievement_reshapes_and_fills():
    """fill_achievement drops the 평가준거 column, grows to N clean 상/중/하 blocks,
    fills each standard's code + descriptors, and stays a valid grid -- no
    regeneration (byte formatting carried)."""
    from hwpx.evalplan_fill import fill_achievement, _classify_index, _grid_of
    from hwpx.formfill_quality import score_format_fidelity
    c = parse_review_md(SYNTHETIC)
    blank = BLANK_3HAK.read_bytes()
    data, report = fill_achievement(blank, c)
    assert not report["skipped"], report["skipped"]
    ti = _classify_index(data, "achievement")
    _sp, tb, grid, rep = _grid_of(data, ti)
    assert rep.ok
    assert rep.col_count == 3                          # 평가준거 column dropped
    assert rep.row_count == 1 + 3 * len(c.achievement_std)  # header + 3 rows/std
    # each standard's code landed in its leader cell
    from hwpx.table_patch import _text_of
    for i, std in enumerate(c.achievement_std):
        leader = grid.get((1 + 3 * i, 0))
        assert std[0][:10] in _text_of(tb[leader.start:leader.end])
    # 상/중/하 labels preserved from the clone
    assert _text_of(tb[grid[(1, 1)].start:grid[(1, 1)].end]).strip() == "상"
    # format not regenerated
    assert score_format_fidelity(data, BLANK_3HAK).detail["carry_rate"] > 0.7


# The per-standard §4가 authoring shape: each 성취기준 carries its own `수준 | 성취수준`
# A~E table (levels as rows), rather than one unified table with levels as columns.
# This is how real 평가계획 review MDs are written; the parser must normalise it to the
# same ``[code+진술, A, B, C, D, E]`` rows the unified shape yields.
_PER_STD_GA = """### 4. 성취기준 및 성취수준
**가. 성취기준별 성취수준(A~E)**

**(1) 영역 하나**

**[12합성01-01]** 표준 하나의 진술이다.

| 수준 | 성취수준 |
|---|---|
| A | 하나-A 서술 |
| B | 하나-B 서술 |
| C | 하나-C 서술 |
| D | 하나-D 서술 |
| E | 하나-E 서술 |

**[12합성01-02]** 표준 둘의 진술이다.

| 수준 | 성취수준 |
|---|---|
| A | 둘-A 서술 |
| B | 둘-B 서술 |
| C | 둘-C 서술 |
| D | 둘-D 서술 |
| E | 둘-E 서술 |

"""
# a full 2022-개정 review MD whose §4가 uses the per-standard shape
_UNIFIED_GA_MARKER = "**가. 성취기준별 성취수준(A~E)**"
PER_STD_2022 = (
    SYNTHETIC_2022[: SYNTHETIC_2022.index("### 4.")]
    + _PER_STD_GA
    + SYNTHETIC_2022[SYNTHETIC_2022.index("**나. 학기 단위"):]
)


def test_parse_achievement_std_per_standard_shape():
    """The per-standard §4가 shape (one `수준 | 성취수준` A~E table under each
    `**[code]** 진술` header) normalises to the same ``[code+진술, A, B, C, D, E]``
    rows as the unified single-table shape -- codes preserved, level count read from
    the data (bh=5), no descriptor dropped."""
    from hwpx.evalplan_fill import _parse_achievement_std
    ga = _PER_STD_GA
    rows = _parse_achievement_std(ga)
    assert len(rows) == 2                                   # two standards, one row each
    assert all(len(r) == 6 for r in rows)                  # code + A..E (bh=5)
    assert rows[0][0] == "[12합성01-01] 표준 하나의 진술이다."
    assert rows[0][1:] == ["하나-A 서술", "하나-B 서술", "하나-C 서술", "하나-D 서술", "하나-E 서술"]
    assert rows[1][0].startswith("[12합성01-02]")
    # the unified single-table shape is untouched (regression guard)
    unified = "**가.**\n\n| 성취기준 | 상 | 중 | 하 |\n|---|---|---|---|\n| [12합성09-01] 표준 | 상x | 중x | 하x |\n"
    urows = _parse_achievement_std(unified)
    assert urows == [["[12합성09-01] 표준", "상x", "중x", "하x"]]


def test_fill_achievement_per_standard_2022_fills_ae_blocks():
    """Regression for the real-fill bug: a per-standard §4가 (A~E levels as rows)
    now yields bh=5, so fill_achievement reshapes the 2022 blank's A~E block to N
    per-standard blocks and fills every cell -- previously bh collapsed to 1 and the
    clone raised 'ref_rows out of range', leaving the table unfilled (filled=0)."""
    from hwpx.evalplan_fill import fill_achievement, _classify_index, _grid_of
    from hwpx.table_patch import _text_of, apply_table_ops
    from hwpx.evalplan_fill import plan_structural_ops
    c = parse_review_md(PER_STD_2022)
    assert len(c.achievement_std) == 2 and len(c.achievement_std[0]) == 6
    data = apply_table_ops(str(BLANK_2HAK), plan_structural_ops(str(BLANK_2HAK), c)["ops"]).data
    data, report = fill_achievement(data, c)
    assert not report["skipped"], report["skipped"]
    assert report["filled"] == 2 + 2 * 5                   # 2 leaders + 10 descriptors
    ti = _classify_index(data, "achievement")
    _sp, tb, grid, rep = _grid_of(data, ti)
    assert rep.ok
    assert rep.row_count == 1 + 5 * 2                       # header + 5 rows/std × 2
    # codes landed in the two leader cells (rows 1 and 6)
    assert "[12합성01-01]" in _text_of(tb[grid[(1, 0)].start:grid[(1, 0)].end])
    assert "[12합성01-02]" in _text_of(tb[grid[(6, 0)].start:grid[(6, 0)].end])
    # A~E labels carried from the clone, descriptors down the 서술 column
    assert _text_of(tb[grid[(1, 1)].start:grid[(1, 1)].end]).strip() == "A"
    assert _text_of(tb[grid[(5, 1)].start:grid[(5, 1)].end]).strip() == "E"
    assert "하나-A 서술" in _text_of(tb[grid[(1, 2)].start:grid[(1, 2)].end])
    assert "둘-E 서술" in _text_of(tb[grid[(10, 2)].start:grid[(10, 2)].end])


def test_fill_rubrics_replaces_sample_codes_and_lands_items():
    """fill_rubrics shrinks each rubric's example item block to the review item
    count, replaces the 한국사 sample 성취기준 codes, and lands the 평가항목 labels."""
    from hwpx.evalplan_fill import fill_rubrics, _rubric_indices, _grid_of
    from hwpx.formfill_quality import _all_text, _STD_CODE_RE
    c = parse_review_md(SYNTHETIC)
    blank = BLANK_3HAK.read_bytes()
    data, report = fill_rubrics(blank, c)
    assert not report["skipped"], report["skipped"]
    # the sample 한국사 codes (in the blank, not the review) are replaced
    foreign = set(_STD_CODE_RE.findall(_all_text(blank))) - set(_STD_CODE_RE.findall(SYNTHETIC))
    got = set(_STD_CODE_RE.findall(_all_text(data)))
    hansa = {code for code in foreign if "한사" in code}
    assert not (hansa & got), f"leftover 한국사 codes: {sorted(hansa & got)}"
    # every review 평가항목 label appears in the produced text
    full = _all_text(data).replace(" ", "")
    for r in c.rubrics:
        for item in [row[0] for row in r.rows if not row[0].startswith("기본점수")]:
            assert item.replace(" ", "") in full, f"missing item {item!r}"
    # grids stay valid
    for ti in _rubric_indices(data):
        _sp, _tb, _grid, rep = _grid_of(data, ti)
        assert rep.ok


def test_fill_evalplan_phase_all_is_byte_preserving():
    """phase='all' runs every content fill and still preserves the blank's byte
    formatting (surviving tables carried, edited tables reuse the blank vocab) --
    the anti-regeneration gate."""
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_format_fidelity
    c = parse_review_md(SYNTHETIC)
    res = fill_evalplan(str(BLANK_3HAK), c, phase="all")
    prod = res["_data"]
    assert res["content_report"]["achievement"]["filled"] > 0
    assert res["content_report"]["rubrics"]["filled"] > 0
    b = score_format_fidelity(prod, str(BLANK_3HAK))
    assert b.score >= 20                                # B axis (byte-preserving) gate
    assert b.detail["carry_rate"] > 0.6


def test_fill_ratio_replaces_sample_and_lands_md_numbers():
    """fill_ratio maps the review §6 반영비율 onto the produced 반영비율 table by row
    label: the 영역 만점 numbers, 영역 names, and 성취기준 codes replace the blank's
    통합과학 sample (byte-preserving, no regeneration)."""
    from hwpx.evalplan_fill import fill_ratio, _classify_index, _grid_of
    from hwpx.formfill_quality import score_format_fidelity
    from hwpx.table_patch import _text_of
    c = parse_review_md(SYNTHETIC)
    # start from the structurally-restructured (정기시험 removed) blank
    from hwpx.evalplan_fill import plan_structural_ops
    from hwpx.table_patch import apply_table_ops
    plan = plan_structural_ops(str(BLANK_3HAK), c)
    data = apply_table_ops(str(BLANK_3HAK), plan["ops"]).data
    data, report = fill_ratio(data, c)
    assert not report["skipped"], report["skipped"]
    assert report["rows_filled"] >= 3
    ti = _classify_index(data, "ratio")
    _sp, tb, grid, rep = _grid_of(data, ti)
    rows = {}
    for r in range(rep.row_count):
        c0 = grid.get((r, 0))
        rows[_text_of(tb[c0.start:c0.end]).strip()] = r
    # 영역 만점 numbers landed
    r = rows["영역 만점(반영 비율)"]
    assert "60점(60%)" in _text_of(tb[grid[(r, 1)].start:grid[(r, 1)].end])
    assert "40점(40%)" in _text_of(tb[grid[(r, 2)].start:grid[(r, 2)].end])
    # 영역 names landed in the 시기/영역 row
    r = rows["시기/영역"]
    assert "영역 가" in _text_of(tb[grid[(r, 1)].start:grid[(r, 1)].end])
    # the MD 반영비율 numbers are present in the ratio table (sample % replaced)
    assert "60%" in _text_of(tb) and "40%" in _text_of(tb)
    # byte formatting preserved (not regenerated)
    assert score_format_fidelity(data, str(BLANK_3HAK)).detail["carry_rate"] > 0.6


def test_scorer_ratio_content_penalises_sample():
    """score_content's ratio-content region + '반영비율 carries MD numbers' check
    catch a SAMPLE 반영비율 (50/50/50 → sums to 100 somewhere) that the old sum-only
    check waved through -- an unfilled ratio scores its region low."""
    import hwpx.evalplan_fill as ef
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_content
    c = parse_review_md(SYNTHETIC)
    # disable fill_ratio -> the produced keeps the blank's SAMPLE 반영비율
    orig = ef.fill_ratio
    ef.fill_ratio = lambda data, content: (data, {"skipped": ["disabled for test"]})
    try:
        sample = fill_evalplan(str(BLANK_3HAK), c, phase="all")["_data"]
    finally:
        ef.fill_ratio = orig
    filled = fill_evalplan(str(BLANK_3HAK), c, phase="all")["_data"]
    ds = score_content(sample, content=SYNTHETIC, blank=str(BLANK_3HAK))
    df = score_content(filled, content=SYNTHETIC, blank=str(BLANK_3HAK))
    # the filled ratio scores its region much higher than the sample
    assert df.detail["region_fill"]["ratio_content"] > ds.detail["region_fill"]["ratio_content"]
    assert df.detail["region_fill"]["ratio_content"] >= 0.9
    # the sample trips the explicit "carries MD numbers" finding
    assert any("반영비율 carries" in f for f in ds.findings)


def test_2015_rubric_shrink_survives_repair_repack(tmp_path):
    """The real evalplan path keeps exact merged heights through repair/repack."""
    from hwpx.evalplan_fill import fill_evalplan, _grid_of, _rubric_indices
    from hwpx.table_patch import _direct_cells
    from hwpx.tools.package_validator import validate_editor_open_safety
    from hwpx.tools.repair import repair_repack

    data = fill_evalplan(
        str(BLANK_3HAK), parse_review_md(SYNTHETIC), phase="all",
    )["_data"]
    produced = tmp_path / "evalplan-filled.hwpx"
    repaired = tmp_path / "evalplan-filled-repaired.hwpx"
    produced.write_bytes(data)

    repair = repair_repack(produced, repaired)
    assert repair.open_safety["ok"] is True
    assert validate_editor_open_safety(repaired).ok

    repaired_data = repaired.read_bytes()
    ti = _rubric_indices(repaired_data)[0]
    _sp, table, _grid, report = _grid_of(repaired_data, ti)
    assert report.ok

    heights = {}
    for cell in _direct_cells(table):
        block = table[cell.start:cell.end]
        match = re.search(rb'<hp:cellSz\b[^>]*\bheight="(\d+)"', block)
        assert match is not None
        heights[(cell.row, cell.col, cell.row_span)] = int(match.group(1))

    assert heights[(6, 0, 4)] == 9464
    assert heights[(6, 1, 2)] == 5200
    assert heights[(6, 2, 2)] == 5200


def test_fill_rubrics_2022_normalizes_and_fills_chaejeom_ladder():
    """The 2022-개정 rubric 수행수준 채점기준 ladder is reshaped (delete_row /
    insert_row_by_clone -- byte-preserving, NOT regeneration) to the review MD's level
    count per 평가요소 and filled with the MD descriptors + 배점. When every rubric is
    reconciled, ZERO '채점기준 NEEDS_REVIEW' notes remain (no-silent-true: a rubric that
    CANNOT be reconciled would still emit one)."""
    from hwpx.evalplan_fill import (
        fill_evalplan, _rubric_indices, _grid_of, _pf_bounds, _pf_groups, _pf_desc_col,
    )
    from hwpx.table_patch import _text_of

    c = parse_review_md(SYNTHETIC_2022)
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    d = res["_data"]
    rr = res["content_report"]["rubrics"]

    # (1) the 채점기준 ladder is no longer deferred anywhere.
    assert not [s for s in rr["skipped"] if "NEEDS_REVIEW" in s and "채점기준" in s], rr["skipped"]
    assert rr["filled"] == len(c.rubrics)

    # (2) each rubric's 평가요소 region now has exactly one grid row per MD ladder level,
    #     carrying that level's descriptor + 배점 (the sample rows are gone).
    idxs = _rubric_indices(d)
    for ri, rub in enumerate(c.rubrics):
        items = [row for row in rub.rows if not row[0].startswith("기본점수")]
        _sp, tb, grid, rep = _grid_of(d, idxs[ri])
        ph, base = _pf_bounds(tb, grid, rep)
        groups = _pf_groups(tb, ph, base)
        assert len(groups) == len(items), (ri, len(groups), len(items))
        bat_col = rep.col_count - 1
        desc_col = _pf_desc_col(tb, ph, base, bat_col)
        for gi, (r0, _h) in enumerate(groups):
            ladder = [cl for cl in re.split(r"\s*/\s*", items[gi][1]) if re.search(r"\*\*\d+\*\*", cl)]
            for k, clause in enumerate(ladder):
                score = re.search(r"\*\*(\d+)\*\*", clause).group(1)
                desc = re.sub(r"\s*\*\*\d+\*\*\s*", "", clause).strip()
                dcell = grid.get((r0 + k, desc_col))
                bcell = grid.get((r0 + k, bat_col))
                assert dcell is not None and desc in _text_of(tb[dcell.start:dcell.end]), (ri, gi, k, desc)
                assert bcell is not None and _text_of(tb[bcell.start:bcell.end]).strip() == score, (ri, gi, k, score)

    # (3) byte-preserving: no rubric table was regenerated (structure ops + cell splices
    #     only). The B-fidelity axis flags a regenerated table if any is rebuilt.
    from hwpx.formfill_quality import score_format_fidelity
    b = score_format_fidelity(d, str(BLANK_2HAK))
    assert not (b.detail or {}).get("regenerated_tables"), b.detail


def test_fill_sections_preserves_numbering_and_drops_no_content():
    """fill_sections keeps each item's 가./나./다. ordinal and, when items exceed
    the fixed placeholder slots, appends the surplus (with ordinals) to the last
    slot -- never dropping content. §11 analysis is honestly deferred."""
    from hwpx.evalplan_fill import fill_sections
    from hwpx.patch import _PARAGRAPH_RE
    from hwpx.table_patch import _sections, _text_of
    # content with MORE 목적 items than the blank's 3 placeholders -> forces packing
    md = SYNTHETIC.replace(
        "### 1. 평가의 목적\n가. 목적 하나. 나. 목적 둘.",
        "### 1. 평가의 목적\n가. 알파. 나. 베타. 다. 감마. 라. 델타. 마. 엡실론.")
    c = parse_review_md(md)
    data, report = fill_sections(BLANK_3HAK.read_bytes(), c)
    assert report["filled"] >= 3
    assert any("analysis" in d for d in report["deferred"])   # §11 honest defer
    sx = sorted(_sections(data).items())[0][1]
    paras = [_text_of(m.group(0)).strip() for m in _PARAGRAPH_RE.finditer(sx)]
    i = next(i for i, t in enumerate(paras) if t == "평가의 목적")
    slots = paras[i + 1:i + 4]
    assert slots[0].startswith("가. 알파")                     # numbering preserved
    assert slots[1].startswith("나. 베타")
    joined = " ".join(slots)
    for frag in ("델타", "엡실론"):                            # surplus not dropped
        assert frag in joined


# --------------------------------------------------------------------------- #
# 2022-개정 (2학년) generalization -- exercised on the PUBLIC 1·2학년 fixture with the
# synthetic 2022 review markdown (no PII). These pin the classifier + fills that
# make one recipe cover both 개정.
# --------------------------------------------------------------------------- #


def test_classify_recognizes_2022_signatures():
    """The 2022-개정 blank's per-area 성취기준 (A~E), 학기 단위 성취수준, 영역별 최소 성취
    수준, and 평가 영역명 rubric tables are classified -- and the 최소 성취수준 table is
    NOT miscounted as an achievement block (it would inflate the C-axis count)."""
    from hwpx.formfill_quality import _skeleton
    k = _skeleton(str(BLANK_2HAK))["kinds"]
    assert k.get("achievement", 0) == 6      # 6 per-area 국어 samples
    assert k.get("level", 0) == 1            # 학기 단위 성취수준
    assert k.get("minlevel", 0) == 1         # 영역별 최소 성취수준 (공통과목 전용)
    assert k.get("rubric", 0) == 4           # 평가 영역명 rubrics (incl. 1 surplus)
    assert k.get("achieve_rate", 0) == 4     # 4 성취율 variants


def test_expected_skeleton_2022_is_collapsed():
    c = parse_review_md(SYNTHETIC_2022)
    assert len(c.achievement_std) == 2 and all(len(r) == 6 for r in c.achievement_std)
    assert [r[0] for r in c.levels] == ["A", "B", "C", "D", "E"]   # grade-major
    assert len(c.achieve_rate) == 5                                # 5-band
    assert expected_skeleton(c) == {
        "achievement": 1, "level": 1, "minlevel": 0, "rubric": 3, "achieve_rate": 1, "ratio": 1}


def test_plan_structural_ops_2022_keeps_5band_and_drops_minlevel():
    """The 2022-개정 structural plan keeps the single 5단계 성취율 table (content-
    matched, NOT the 3학년 'delete 5단계' rule), deletes the 최소 성취수준 table, prunes
    the surplus achievement / rubric samples, and strips the 정기시험 column."""
    from hwpx.evalplan_fill import plan_structural_ops
    from hwpx.formfill_quality import _skeleton
    from hwpx.table_patch import apply_table_ops
    c = parse_review_md(SYNTHETIC_2022)
    plan = plan_structural_ops(str(BLANK_2HAK), c)
    assert any("최소 성취수준" in t for t in plan["transcript"])       # minlevel deleted
    assert any("5단계" in t for t in plan["transcript"])              # 5-band kept
    res = apply_table_ops(str(BLANK_2HAK), plan["ops"])
    assert res.ok and not res.skipped
    k = _skeleton(res.data)["kinds"]
    assert k.get("achievement", 0) == 1 and k.get("level", 0) == 1
    assert k.get("minlevel", 0) == 0 and k.get("rubric", 0) == 3
    assert k.get("achieve_rate", 0) == 1                             # exactly one kept
    assert _skeleton(res.data)["ratio_has_regular_exam"] is False     # 정기시험 stripped


def test_fill_achievement_2022_five_level_blocks():
    """fill_achievement drives the block height off the MD level count: the 2022-
    개정 unified table becomes N clean 5-row A~E blocks, each filled from the review
    (leader code + A..E descriptors), staying a valid byte-preserving grid."""
    from hwpx.evalplan_fill import (fill_evalplan, _classify_index, _grid_of)
    from hwpx.formfill_quality import score_format_fidelity
    from hwpx.table_patch import _text_of
    c = parse_review_md(SYNTHETIC_2022)
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    assert res["content_report"]["achievement"]["filled"] == 2 * 5 + 2   # descriptors + leaders
    ti = _classify_index(data, "achievement")
    _sp, tb, grid, rep = _grid_of(data, ti)
    assert rep.ok and rep.col_count == 3
    assert rep.row_count == 1 + 5 * len(c.achievement_std)              # header + 5 rows/std
    # each standard's code landed in its leader, and its E descriptor in the last row
    for i, std in enumerate(c.achievement_std):
        lr = 1 + 5 * i
        assert std[0][:10] in _text_of(tb[grid[(lr, 0)].start:grid[(lr, 0)].end])
        assert std[5] in _text_of(tb[grid[(lr + 4, 2)].start:grid[(lr + 4, 2)].end])
    # A/B/C/D/E labels preserved from the clone
    assert [_text_of(tb[grid[(1 + k, 1)].start:grid[(1 + k, 1)].end]).strip() for k in range(5)] \
        == ["A", "B", "C", "D", "E"]
    assert score_format_fidelity(data, str(BLANK_2HAK)).detail["carry_rate"] > 0.6


def test_fill_levels_2022_grade_major():
    """fill_levels maps the grade-major review levels onto the 학기 단위 성취수준 A~E
    rows by grade label (not positional), filling all five descriptor cells."""
    from hwpx.evalplan_fill import fill_evalplan, _classify_index, _grid_of
    from hwpx.table_patch import _text_of
    c = parse_review_md(SYNTHETIC_2022)
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    assert res["content_report"]["levels"]["filled"] == 5
    ti = _classify_index(data, "level")
    _sp, tb, grid, rep = _grid_of(data, ti)
    got = [_text_of(tb[grid[(r, rep.col_count - 1)].start:grid[(r, rep.col_count - 1)].end]).strip()
           for r in range(1, rep.row_count)]
    assert got == ["특성 A.", "특성 B.", "특성 C.", "특성 D.", "특성 E."]


def test_fill_rubrics_2022_lands_item_labels():
    """The 2022-개정 rubric fill lands every 평가항목 label + the 영역 title/points into
    the 평가 영역명 rubric tables (no reshape, byte-preserving), and keeps grids valid."""
    from hwpx.evalplan_fill import fill_evalplan, _rubric_indices, _grid_of
    from hwpx.formfill_quality import _all_text
    c = parse_review_md(SYNTHETIC_2022)
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    full = _all_text(data).replace(" ", "")
    for r in c.rubrics:
        for item in [row[0] for row in r.rows if not row[0].startswith("기본점수")]:
            assert item.replace(" ", "") in full, f"missing rubric item {item!r}"
        assert r.title.replace(" ", "") in full                        # 평가 영역명 filled
    for ti in _rubric_indices(data):
        _sp, _tb, _grid, rep = _grid_of(data, ti)
        assert rep.ok


def test_fill_evalplan_2022_phase_all_byte_preserving():
    """phase='all' on the 2022-개정 fixture preserves the blank's byte formatting
    (surviving tables carried, edited tables reuse the blank vocab) -- the anti-
    regeneration gate -- while producing the collapsed target skeleton."""
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_format_fidelity, _skeleton
    c = parse_review_md(SYNTHETIC_2022)
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    assert _skeleton(data)["kinds"].get("achievement") == 1
    b = score_format_fidelity(data, str(BLANK_2HAK))
    assert b.score >= 20                                               # B axis gate
    assert b.detail["carry_rate"] > 0.6


def test_fill_rubric_2022_ae_descriptors_replace_sample_prose():
    """The 2022-개정 rubric 성취기준별 성취수준 A~E block ships the blank's foreign sample
    descriptors (통합사회/미술 프로젝트 prose). ``_fill_rubric_2022`` now splices each A~E
    block's 서술 cells from the review MD's per-standard 성취수준 (block *i* ← the *i*-th
    referenced standard), byte-preserving. Assert on the PUBLIC fixture + synthetic MD
    that the primary block descriptors are the MD's (A→상상, …, E→최하), the blank's
    sample prose (사회적 소수자/인권 문제/조형 요소) is gone from every FILLED 서술 cell,
    and an A~E block with no referenced standard is left as-is and REPORTED (fail-
    closed -- no fabricated standard mapping, no corruption)."""
    from hwpx.evalplan_fill import (
        fill_evalplan, _rubric_indices, _grid_of, _std_level_map,
    )
    from hwpx.table_patch import _text_of, _direct_cells
    from hwpx.formfill_quality import score_format_fidelity

    c = parse_review_md(SYNTHETIC_2022)
    # synthetic §4가 gives [12합성01-01] -> 상상1/상1/중1/하1/최하1 (5 descriptors)
    std_levels = _std_level_map(c.achievement_std)
    assert std_levels["[12합성01-01]"] == ["상상1", "상1", "중1", "하1", "최하1"]

    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    idxs = _rubric_indices(data)
    assert len(idxs) == len(c.rubrics)

    SAMPLE = ("사회적 소수자", "인권 문제", "인포그래픽", "조형 요소", "삼투현상")

    def ae_desc_by_grade(ti):
        """{grade: [서술 text, ...]} for every A~E grade row of rubric table ``ti``."""
        _sp, tb, grid, _rep = _grid_of(data, ti)
        out: dict[str, list[str]] = {}
        for cell in sorted(_direct_cells(tb), key=lambda x: x.row):
            g = _text_of(tb[cell.start:cell.end]).strip()
            if g in ("A", "B", "C", "D", "E") and cell.col_span == 1:
                d = grid.get((cell.row, cell.col + 1))
                if d is not None and d.col > cell.col:
                    out.setdefault(g, []).append(_text_of(tb[d.start:d.end]).strip())
        return out

    # rubric[0] '영역 가' references [12합성01-01]: its single A~E block is the MD's.
    r0 = ae_desc_by_grade(idxs[0])
    assert r0["A"] == ["상상1"] and r0["E"] == ["최하1"]
    assert r0["B"] == ["상1"] and r0["C"] == ["중1"] and r0["D"] == ["하1"]

    # rubric[2] '영역 다' references [12합성01-02]: A→상상2 … E→최하2.
    r2 = ae_desc_by_grade(idxs[2])
    assert r2["A"] == ["상상2"] and r2["E"] == ["최하2"]

    # rubric[1] '영역 나' references ONE standard ([12합성01-02]) but the blank ships TWO
    # A~E blocks: block 0 is filled from that standard; block 1 (no 2nd referenced
    # standard) is left as-is and reported -- fail-closed, never fabricated.
    r1 = ae_desc_by_grade(idxs[1])
    assert r1["A"][0] == "상상2"                        # first block filled from the std
    assert any("block 1" in s and "no 1-th referenced standard" in s
               for s in res["content_report"]["rubrics"]["skipped"])

    # every FILLED 서술 cell (blocks driven by a real standard) is free of sample prose.
    filled_texts = r0["A"] + r0["B"] + r0["C"] + r0["D"] + r0["E"] + r2["A"] + [r1["A"][0]]
    for t in filled_texts:
        assert not any(s in t for s in SAMPLE), f"sample prose survived in filled A~E cell: {t!r}"

    # anti-regeneration: the fill is a byte-preserving cell splice, not a rebuild.
    b = score_format_fidelity(data, str(BLANK_2HAK))
    assert b.detail["carry_rate"] > 0.6


_MD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/검토용_MD/2026_2학기_3학년_인공지능기초_검토용.md"))
_GOLD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/01_참고_기제출본/2026_1학기_3학년_인공지능기초.hwpx"))


_MD_DRIFT = pytest.mark.xfail(
    strict=False,
    reason="오너 검토용 MD가 iter5 이후 편집됨(2026-07-06 실측 mtime) — 계약 재고정은 "
    "범용 form-fill goal Stage 3의 evalplan 재통과에서 수행. 무음 green 금지용 표식.",
)


@_MD_DRIFT
@pytest.mark.skipif(not _MD.exists(), reason="owner-local review MD not present (not vendored)")
def test_real_3hak_review_md_skeleton():
    c = parse_review_file(str(_MD))
    assert c.teacher == "고규현"
    assert len(c.schedule) == 21 and len(c.achievement_std) == 8
    assert len(c.levels) == 3
    assert expected_skeleton(c) == {
        "achievement": 1, "level": 1, "minlevel": 0, "rubric": 3, "achieve_rate": 1, "ratio": 1}
    assert [r.points for r in c.rubrics] == [35, 35, 30]


@_MD_DRIFT
@pytest.mark.skipif(not _MD.exists(), reason="owner-local review MD not present (not vendored)")
def test_real_3hak_content_fill_replaces_all_foreign_samples():
    """The real 3학년 phase='all' fill drops the leftover-sample fraction (음악 +
    한국사 + 통합과학 codes) to 0 -- structural proof the achievement + rubric + ratio
    samples were actually replaced (no render needed)."""
    import re
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_content, _document_text
    c = parse_review_file(str(_MD))
    res = fill_evalplan(str(BLANK_3HAK), c, phase="all")
    data = res["_data"]
    d = score_content(data, content=str(_MD), blank=str(BLANK_3HAK))
    assert d.detail["leftover_sample_frac"] <= 0.10
    assert d.detail["leftover_sample_frac"] <= 0.03
    assert d.detail["region_fill"]["achievement_prose"] >= 0.9
    assert d.detail["region_fill"]["rubric_items"] >= 0.8
    assert d.detail["region_fill"]["ratio_content"] >= 0.9    # 반영비율 table filled
    # ZERO foreign standard codes survive (통과/통사/음/한사 all gone; only 인기 remain)
    txt = _document_text(data)
    foreign = [x for x in set(re.findall(r"\[\d?\d?[가-힣A-Za-z]+\d[\d\-]*\]", txt))
               if not x.startswith("[12인기")]
    assert foreign == [], f"foreign sample codes survived: {foreign}"


_MD_2HAK = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/검토용_MD/2026_2학기_2학년_인공지능기초_검토용.md"))


@_MD_DRIFT
@pytest.mark.skipif(not _MD_2HAK.exists(), reason="owner-local 2학년 review MD not present (not vendored)")
def test_real_2hak_review_md_skeleton():
    c = parse_review_file(str(_MD_2HAK))
    assert c.teacher == "고규현"
    assert len(c.schedule) == 21 and len(c.achievement_std) == 8
    assert [r[0] for r in c.levels] == ["A", "B", "C", "D", "E"]      # grade-major
    assert len(c.achieve_rate) == 5                                    # 5-band
    assert expected_skeleton(c) == {
        "achievement": 1, "level": 1, "minlevel": 0, "rubric": 3, "achieve_rate": 1, "ratio": 1}
    assert [r.points for r in c.rubrics] == [45, 30, 25]


@_MD_DRIFT
@pytest.mark.skipif(not _MD_2HAK.exists(), reason="owner-local 2학년 review MD not present (not vendored)")
def test_real_2hak_content_fill_reaches_target_structure():
    """The real 2학년 phase='all' fill produces the collapsed target skeleton, lands
    its achievement + rubric + ratio content, and leaves NO foreign sample code
    (통사/통과/공국/미술 all replaced) (no render needed)."""
    import re
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_content, _skeleton, _document_text
    c = parse_review_file(str(_MD_2HAK))
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    k = _skeleton(data)["kinds"]
    assert k.get("achievement") == 1 and k.get("level") == 1 and k.get("rubric") == 3
    assert k.get("minlevel", 0) == 0
    d = score_content(data, content=str(_MD_2HAK), blank=str(BLANK_2HAK))
    assert d.detail["region_fill"]["achievement_prose"] >= 0.9
    assert d.detail["region_fill"]["rubric_items"] >= 0.6
    assert d.detail["region_fill"]["ratio_content"] >= 0.9    # 반영비율 table filled
    assert d.detail["leftover_sample_frac"] <= 0.10
    assert d.detail["leftover_sample_frac"] <= 0.03
    # ZERO foreign standard codes survive (including the 2-part [10통사2-01-03] rubric
    # sample and the single-digit-prefix [9미…] second-block sample)
    txt = _document_text(data)
    foreign = [x for x in set(re.findall(r"\[\d?\d?[가-힣A-Za-z]+\d[\d\-]*\]", txt))
               if not x.startswith("[12인기")]
    assert foreign == [], f"foreign sample codes survived: {foreign}"
