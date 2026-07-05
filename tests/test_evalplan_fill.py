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


def test_fill_rubrics_replaces_sample_codes_and_lands_items():
    """fill_rubrics shrinks each rubric's example item block to the review item
    count, replaces the 한국사 sample 성취기준 codes, and lands the 평가항목 labels."""
    from hwpx.evalplan_fill import fill_rubrics, _rubric_indices, _grid_of, _cell_text
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


_MD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/검토용_MD/2026_2학기_3학년_인공지능기초_검토용.md"))
_GOLD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/01_참고_기제출본/2026_1학기_3학년_인공지능기초.hwpx"))


@pytest.mark.skipif(not _MD.exists(), reason="owner-local review MD not present (not vendored)")
def test_real_3hak_review_md_skeleton():
    c = parse_review_file(str(_MD))
    assert c.teacher == "고규현"
    assert len(c.schedule) == 21 and len(c.achievement_std) == 8
    assert len(c.levels) == 3
    assert expected_skeleton(c) == {
        "achievement": 1, "level": 1, "minlevel": 0, "rubric": 3, "achieve_rate": 1, "ratio": 1}
    assert [r.points for r in c.rubrics] == [35, 35, 30]


@pytest.mark.skipif(not _MD.exists(), reason="owner-local review MD not present (not vendored)")
def test_real_3hak_content_fill_replaces_all_foreign_samples():
    """The real 3학년 phase='all' fill drops the leftover-sample fraction (음악 +
    한국사 codes) to <=0.10 -- structural proof the achievement + rubric samples
    were actually replaced (no render needed)."""
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_content
    c = parse_review_file(str(_MD))
    res = fill_evalplan(str(BLANK_3HAK), c, phase="all")
    d = score_content(res["_data"], content=str(_MD), blank=str(BLANK_3HAK))
    assert d.detail["leftover_sample_frac"] <= 0.10
    assert d.detail["region_fill"]["achievement_prose"] >= 0.9
    assert d.detail["region_fill"]["rubric_items"] >= 0.8


_MD_2HAK = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/검토용_MD/2026_2학기_2학년_인공지능기초_검토용.md"))


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


@pytest.mark.skipif(not _MD_2HAK.exists(), reason="owner-local 2학년 review MD not present (not vendored)")
def test_real_2hak_content_fill_reaches_target_structure():
    """The real 2학년 phase='all' fill produces the collapsed target skeleton and
    lands its achievement + rubric content (no render needed)."""
    from hwpx.evalplan_fill import fill_evalplan
    from hwpx.formfill_quality import score_content, _skeleton
    c = parse_review_file(str(_MD_2HAK))
    res = fill_evalplan(str(BLANK_2HAK), c, phase="all")
    data = res["_data"]
    k = _skeleton(data)["kinds"]
    assert k.get("achievement") == 1 and k.get("level") == 1 and k.get("rubric") == 3
    assert k.get("minlevel", 0) == 0
    d = score_content(data, content=str(_MD_2HAK), blank=str(BLANK_2HAK))
    assert d.detail["region_fill"]["achievement_prose"] >= 0.9
    assert d.detail["region_fill"]["rubric_items"] >= 0.6
    assert d.detail["leftover_sample_frac"] <= 0.10
