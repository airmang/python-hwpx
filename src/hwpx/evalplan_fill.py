# SPDX-License-Identifier: Apache-2.0
"""Evaluation-plan (평가계획) review-markdown parser + target skeleton.

The GOAL-loop recipe fills a blank province form from a structured review markdown
(Ⅰ 운영계획 + [1]~[11]). This module is the *content* half: it parses that markdown
into a structured :class:`EvalPlanContent` and derives the **target skeleton**
(how many achievement / 성취수준 / rubric / 성취율 tables the content requires) that
the quality scorer's C axis measures against (content-derived counts, not the
1학기 gold's).

Kept deliberately format-tolerant: the review markdown is hand-authored, so the
parser locates sections by their numbered headers and pulls the GitHub-style
tables under each. Prose sections are returned as normalised text. No content is
invented — a missing section yields an empty field, surfaced by the scorer's D
axis rather than silently filled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def _md_table_rows(block: str) -> list[list[str]]:
    """Every data row of the first GitHub-style table in *block* (header +
    separator dropped), each split into trimmed cells."""
    rows: list[list[str]] = []
    seen_sep = False
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if rows:
                break  # table ended
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= {"-", ":", " "} and c for c in cells):
            seen_sep = True
            continue
        rows.append(cells)
    # first row is the header; keep only rows after the separator
    if seen_sep and rows:
        return rows[1:]
    return rows[1:] if len(rows) > 1 else []


def _md_table_header(block: str) -> list[str]:
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("|"):
            return [c.strip() for c in s.strip("|").split("|")]
    return []


@dataclass
class Rubric:
    title: str                       # "문제해결에 탐색 활용하기"
    points: int                      # 35
    standards: str                   # "[12인기02-04][12인기02-05]"
    rows: list[list[str]] = field(default_factory=list)   # [평가항목, 채점 기준]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "points": self.points,
                "standards": self.standards, "rows": self.rows}


@dataclass
class EvalPlanContent:
    title: str = ""
    teacher: str = ""
    schedule: list[list[str]] = field(default_factory=list)     # Ⅰ, 6 cols/row
    purposes: str = ""                                          # §1
    directions: str = ""                                       # §2
    policies: str = ""                                         # §3
    achievement_std: list[list[str]] = field(default_factory=list)  # §4가 [성취기준,상,중,하]
    levels: list[list[str]] = field(default_factory=list)      # §4나 [영역,A,B,C]
    achieve_rate: list[list[str]] = field(default_factory=list)  # §5 [성취율,성취도]
    ratio_header: list[str] = field(default_factory=list)      # §6 header cells
    ratio_rows: list[list[str]] = field(default_factory=list)  # §6 data rows
    rubrics: list[Rubric] = field(default_factory=list)        # §7
    affective: str = ""                                        # §8
    absentee: str = ""                                         # §9
    cautions: str = ""                                         # §10
    analysis: str = ""                                         # §11

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "teacher": self.teacher,
            "schedule_rows": len(self.schedule),
            "achievement_std_rows": len(self.achievement_std),
            "level_rows": len(self.levels),
            "achieve_rate_rows": len(self.achieve_rate),
            "ratio_areas": len([c for c in self.ratio_header if any(ch in c for ch in _CIRCLED)]),
            "rubrics": [r.to_dict() for r in self.rubrics],
        }


def _section(md: str, start_pat: str, end_pats: list[str]) -> str:
    m = re.search(start_pat, md)
    if not m:
        return ""
    rest = md[m.end():]
    ends = [re.search(p, rest) for p in end_pats]
    cut = min((e.start() for e in ends if e), default=len(rest))
    return rest[:cut]


def parse_review_md(md_text: str) -> EvalPlanContent:
    """Parse a 평가계획 review markdown into structured content."""
    c = EvalPlanContent()

    # title + teacher (first heading + 담당교사 mention)
    m = re.search(r"#\s*(\d{4}학년도[^\n]+?계획)", md_text)
    if m:
        c.title = re.sub(r"\s*\(검토용\)\s*$", "", m.group(1)).strip()
    m = re.search(r"담당교사\s*[:：]\s*([^\s·|*]+)", md_text)
    if m:
        c.teacher = m.group(1).strip()

    # Ⅰ schedule table
    sched = _section(md_text, r"##\s*Ⅰ\.\s*교수학습 운영 계획", [r"##\s*Ⅱ\.", r"^##\s"])
    c.schedule = _md_table_rows(sched)

    # numbered sections [1]~[11] (### N. ...)
    def sec(n: int) -> str:
        return _section(md_text, rf"###\s*{n}\.\s", [rf"###\s*{n+1}\.\s", r"^##\s"])

    c.purposes = _prose(sec(1))
    c.directions = _prose(sec(2))
    c.policies = _prose(sec(3))

    s4 = sec(4)
    ga = s4.split("**나.")[0]
    na = ("**나." + s4.split("**나.")[1]) if "**나." in s4 else ""
    c.achievement_std = _md_table_rows(ga)
    c.levels = _md_table_rows(na)

    c.achieve_rate = _md_table_rows(sec(5))

    s6 = sec(6)
    c.ratio_header = _md_table_header(s6)
    c.ratio_rows = _md_table_rows(s6)

    s7 = sec(7)
    c.rubrics = _parse_rubrics(s7)

    c.affective = _prose(sec(8))
    c.absentee = _prose(sec(9))
    c.cautions = _prose(sec(10))
    c.analysis = _prose(sec(11))
    return c


def _prose(text: str) -> str:
    """Normalised prose of a numbered section with its leading **title line**
    dropped -- the ``### N. 평가의 목적`` heading text the section regex sweeps in is
    not prose. Everything up to (and excluding) the first ordinal '가.' marker or
    '-'/'*' bullet on its own is the title; the rest is the actual content."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    # drop a leading title line (no ordinal marker, no bullet) if content follows
    if lines and not re.match(r"^([가-힣]\.\s|[-*·]\s)", lines[0]) and len(lines) > 1:
        lines = lines[1:]
    return _norm(" ".join(lines))


def _parse_rubrics(s7: str) -> list[Rubric]:
    rubrics: list[Rubric] = []
    # split on the bolded circled headers "**① title (NN점)** ..."
    parts = re.split(r"\*\*([" + _CIRCLED + r"][^*]*?\(\d+점\)[^*]*)\*\*", s7)
    # parts = [pre, header1, body1, header2, body2, ...]
    for i in range(1, len(parts), 2):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        mt = re.match(r"[" + _CIRCLED + r"]\s*(.*?)\s*\((\d+)점\)", header)
        title = mt.group(1).strip() if mt else header.strip()
        points = int(mt.group(2)) if mt else 0
        ms = re.search(r"\[12[가-힣]*\d\d-\d\d\][^\n·]*", header + body)
        standards = ms.group(0).strip() if ms else ""
        rows = _md_table_rows(body)
        rubrics.append(Rubric(title=title, points=points, standards=standards, rows=rows))
    return rubrics


def _norm(text: str) -> str:
    return " ".join(text.split()).strip()


def expected_skeleton(content: EvalPlanContent) -> dict[str, int]:
    """Content-derived block counts for the quality scorer's C axis.

    A 2학기 fill of this subject family collapses §4가 into a single achievement
    table and §4나 into a single 성취수준 table, keeps one 3단계 성취율 table, and
    has one rubric table per 수행영역."""
    return {
        "achievement": 1 if content.achievement_std else 0,
        "level": 1 if content.levels else 0,
        "rubric": len(content.rubrics),
        "achieve_rate": 1 if content.achieve_rate else 0,
        "ratio": 1 if content.ratio_header else 0,
    }


def plan_structural_ops(blank: str, content: EvalPlanContent | None = None) -> dict[str, Any]:
    """Confident, gold-policy structural edits for a 평가계획 blank (no content
    fills): delete the red/optional tables and the 정기시험 columns, keeping the
    original formatting byte-for-byte. Targets are located by *classification*
    (reusable across the form family), not fixed indices. Returns
    ``{"ops": [...], "transcript": [...]}`` — feed ``ops`` to
    :func:`hwpx.table_patch.apply_table_ops`. Table deletes are emitted in
    descending index order so earlier indices stay valid (column deletes do not
    shift table indices).

    Deferred (needs content mapping into the blank's rich cells, honest-defer):
    achievement / 성취수준 / rubric block restructuring and cell text fills.
    """
    from .formfill_quality import _classify, _tables

    tabs = _tables(blank)
    ops: list[dict[str, Any]] = []
    transcript: list[str] = []
    del_tables: list[int] = []
    exp = expected_skeleton(content) if content else None
    by_kind: dict[str, list[int]] = {}

    for i, t in enumerate(tabs):
        kind = _classify(t)
        by_kind.setdefault(kind, []).append(i)
        if kind in ("seokcha", "submit", "notice_star"):
            del_tables.append(i)
            transcript.append(f"delete_table #{i} ({kind}) — red/optional, gold removes it")
        elif kind == "achieve_rate" and _is_five_grade(t):
            del_tables.append(i)
            transcript.append(f"delete_table #{i} (5단계 성취율) — keep only the 3단계 table")
        elif kind == "ratio":
            cols = _regular_exam_cols(t)
            if cols:
                ops.append({"op": "delete_column", "tableIndex": i, "cols": cols})
                transcript.append(f"delete_column #{i} cols {cols} (정기시험) — 100% 수행 subject")

    # Surplus template-example tables: the blank ships >1 achievement/성취수준
    # example (연주/비평); the content needs `exp[kind]` of them. Delete the extras
    # (keep the first) so the structure matches the content-derived skeleton.
    if exp:
        for kind in ("achievement", "level"):
            idxs = by_kind.get(kind, [])
            want = exp.get(kind, 0)
            for i in idxs[want:]:
                if i not in del_tables:
                    del_tables.append(i)
                    transcript.append(f"delete_table #{i} (surplus {kind} example) — "
                                      f"content needs {want}, blank ships {len(idxs)}")

    for i in sorted(set(del_tables), reverse=True):
        ops.append({"op": "delete_table", "tableIndex": i})
    # INDEX-SAFE ORDER: column deletes FIRST (they modify a table in place and do
    # not shift table indices, so original indices are valid), THEN table deletes
    # in descending index order (so each delete leaves lower indices unchanged).
    # Emitting table deletes first would shift the ratio table under a later
    # delete_column and silently corrupt the wrong table.
    ops.sort(key=lambda o: (o["op"] == "delete_table", -o.get("tableIndex", 0)))
    return {"ops": ops, "transcript": transcript,
            "expected_skeleton": expected_skeleton(content) if content else None}


def _is_five_grade(table) -> bool:
    """A 성취율 table is 5-grade (to delete) when it carries a D or E grade band
    or more than 4 data rows; the 3단계 A~C table is kept."""
    txt = table.text
    return ("D" in txt and "E" in txt) or table.rows > 4


def _regular_exam_cols(table) -> list[int]:
    """Logical column indices of the 정기시험 span in a 반영비율 table header."""
    from .table_patch import build_grid, _direct_cells, _text_of
    tb = table.bytes
    grid, rep = build_grid(tb)
    cols: list[int] = []
    for col in range(rep.col_count):
        c = grid.get((0, col))
        if c and "정기시험" in _text_of(tb[c.start:c.end]):
            cols.append(col)
    return cols


# --------------------------------------------------------------------------- #
# Content fills (phase="all") -- byte-preserving cell/paragraph splices onto the
# restructured form. Every target is located by *classification* / grid geometry
# (reusable across the 평가계획 form family), never by a hard-coded 3학년 index; the
# structural deletions before them shift indices, so each fill re-locates its
# table fresh. All edits go through the byte-preserving primitives in
# :mod:`hwpx.table_patch` / :mod:`hwpx.patch` -- no table is ever regenerated.
# --------------------------------------------------------------------------- #

_STD_CODE = re.compile(r"\[1\d[가-힣A-Za-z]*\d\d-\d\d\]")


def _rubric_indices(data: bytes):
    from .formfill_quality import _classify, _tables
    return [i for i, t in enumerate(_tables(data)) if _classify(t) == "rubric"]


def _classify_index(data: bytes, kind: str) -> int | None:
    """First table index whose scorer classification is *kind* (or None)."""
    from .formfill_quality import _classify, _tables
    for i, t in enumerate(_tables(data)):
        if _classify(t) == kind:
            return i
    return None


def _grid_of(data: bytes, table_index: int):
    """(section_path, table_bytes, grid, report) for a table by document index."""
    from .table_patch import _sections, _iter_table_spans, build_grid
    for sp, section in sorted(_sections(data).items()):
        spans = _iter_table_spans(section)
        if table_index < len(spans):
            ts, te = spans[table_index]
            tb = section[ts:te]
            grid, rep = build_grid(tb)
            return sp, tb, grid, rep
        table_index -= len(spans)
    raise IndexError("table index out of range across sections")


def _cell_text(tb: bytes, grid, row: int, col: int) -> str:
    from .table_patch import _text_of
    c = grid.get((row, col))
    return _text_of(tb[c.start:c.end]) if c else ""


def fill_achievement(data: bytes, content: EvalPlanContent) -> tuple[bytes, dict[str, Any]]:
    """Reshape the 성취기준·평가기준 table to ``len(achievement_std)`` clean 상/중/하
    blocks and fill each from the review MD (byte-preserving).

    The blank ships a 4-column 음악 example with an extra 평가준거 column and an
    irregular first standard (two 평가준거 sub-blocks). We (1) drop the 평가준거
    column, (2) delete every data row except one canonical 3-row 상/중/하 block,
    (3) clone that block to N standards, then (4) splice each standard's code+text
    into the leader cell and its 상/중/하 descriptors into the description column.
    The 상/중/하 label column carries over from the clone. Returns
    ``(new_bytes, report)``; a no-op if the content has no achievement rows."""
    from .table_patch import apply_table_ops, _direct_cells

    stds = content.achievement_std
    report: dict[str, Any] = {"n": len(stds), "filled": 0, "skipped": []}
    if not stds:
        return data, report

    ti = _classify_index(data, "achievement")
    if ti is None:
        report["skipped"].append("no achievement table found")
        return data, report

    _sp, tb, grid, rep = _grid_of(data, ti)
    # locate the 평가준거 column: a data column that some standard's leader does
    # NOT span. In the blank it is logical column 1 (header 교육과정성취기준 cs2 |
    # 평가기준 cs2); the clean standards use a cs2 leader over cols 0-1, the
    # irregular one splits col1 out. Drop col1 when the table is 4 columns wide.
    ops: list[dict[str, Any]] = []
    if rep.col_count == 4:
        ops.append({"op": "delete_column", "table_index": ti, "cols": [1]})
    res = apply_table_ops(data, ops) if ops else None
    data2 = res.data if res is not None else data
    if res is not None and not res.ok:
        report["skipped"].append(f"delete 평가준거 column: {[s.reason for s in res.skipped]}")
        return data, report

    # keep header + one clean 3-row 상/중/하 block, delete the rest
    _sp, tb, grid, rep = _grid_of(data2, ti)
    leaders = sorted((c for c in _direct_cells(tb) if c.col == 0 and c.row_span == 3),
                     key=lambda c: c.row)
    if not leaders:
        report["skipped"].append("no clean 3-row 상/중/하 block to seed from")
        return data, report
    first = leaders[0]
    keep = set(range(first.row, first.row + 3)) | {0}
    delrows = sorted((r for r in range(rep.row_count) if r not in keep), reverse=True)
    if delrows:
        res = apply_table_ops(data2, [{"op": "delete_row", "table_index": ti, "rows": delrows}])
        if not res.ok:
            report["skipped"].append(f"prune to one block: {[s.reason for s in res.skipped]}")
            return data, report
        data2 = res.data

    # grow to N blocks by cloning the single 3-row block (now rows 1..3)
    n = len(stds)
    if n > 1:
        res = apply_table_ops(data2, [{"op": "insert_block_by_clone", "table_index": ti,
                                       "ref_rows": [1, 3], "count": n - 1}])
        if not res.ok:
            report["skipped"].append(f"clone to {n} blocks: {[s.reason for s in res.skipped]}")
            return data, report
        data2 = res.data

    # fill each block: leader (rs3, col0) = code+text; col2 rows = 상/중/하 descriptors
    cells: list[dict[str, Any]] = []
    for i, std in enumerate(stds):
        lr = 1 + 3 * i
        cells.append({"table_index": ti, "row": lr, "col": 0, "text": std[0], "max_lines": 6})
        for k, desc in enumerate(std[1:4]):
            cells.append({"table_index": ti, "row": lr + k, "col": 2, "text": desc, "max_lines": 5})
    from .table_patch import fill_cells
    fr = fill_cells(data2, cells)
    report["filled"] = len(fr.applied)
    report["skipped"].extend(s.reason for s in fr.skipped)
    return fr.data, report


def fill_levels(data: bytes, content: EvalPlanContent) -> tuple[bytes, dict[str, Any]]:
    """Fill the 영역별 성취수준 (A/B/C) table's descriptor column from the first
    review area's levels, replacing the blank's 음악 sample. The table is a small
    ``성취수준 | 일반적 특성`` grid with A/B/C rows; only the descriptor cells are
    touched (byte-preserving), so a mismatch in area count never corrupts it."""
    from .table_patch import fill_cells

    report: dict[str, Any] = {"filled": 0, "skipped": []}
    if not content.levels:
        return data, report
    ti = _classify_index(data, "level")
    if ti is None:
        report["skipped"].append("no level table found")
        return data, report
    _sp, tb, grid, rep = _grid_of(data, ti)
    # first area's A/B/C descriptors (levels rows are [영역, A, B, C])
    abc = content.levels[0][1:4] if len(content.levels[0]) >= 4 else []
    cells = []
    for k, desc in enumerate(abc):
        r = 1 + k  # rows 1,2,3 = A,B,C
        if grid.get((r, 1)):
            cells.append({"table_index": ti, "row": r, "col": 1, "text": desc, "max_lines": 5})
    fr = fill_cells(data, cells)
    report["filled"] = len(fr.applied)
    report["skipped"].extend(s.reason for s in fr.skipped)
    return fr.data, report


def _batjeom_line(item_label: str, criteria: str) -> str:
    """Compose one 채점기준 cell line: 'label: level 15 / level 12 / ...' from the
    MD's bolded-배점 criteria string ('명확히 정의·트리 표현 **15** / ...')."""
    clean = criteria.replace("**", "").strip()
    return f"{item_label}: {clean}" if clean else item_label


def _top_batjeom(criteria: str) -> str:
    m = re.findall(r"\*\*(\d+)\*\*", criteria)
    return m[0] if m else ""


def _base_scores(rows: list[list[str]]) -> tuple[str, str, str, str]:
    """Pull 기본점수 / 장기 미인정 labels+scores from a rubric's trailing summary
    row ('기본점수(백지·미참여) **14** · 장기 미인정 결석 **13**').

    The label itself can contain a middle-dot ('백지·미참여'), so split on the
    score-bearing clause boundary ('**N** ·'), not on every '·'."""
    base_label, base_score, long_label, long_score = "기본점수", "", "장기 미인정 결석", ""
    for row in rows:
        cell = row[0]
        if "기본점수" not in cell:
            continue
        # boundary: the ' · ' that follows the first '**score**'
        m = re.match(r"(.*?\*\*\d+\*\*)\s*·\s*(.*)", cell)
        if m:
            first, second = m.group(1), m.group(2)
        else:
            first, second = cell, ""
        b = re.findall(r"\*\*(\d+)\*\*", first)
        l = re.findall(r"\*\*(\d+)\*\*", second)
        base_label = re.sub(r"\s*\*\*\d+\*\*", "", first).strip() or base_label
        if second:
            long_label = re.sub(r"\s*\*\*\d+\*\*", "", second).strip() or long_label
        if b:
            base_score = b[0]
        if l:
            long_score = l[0]
    return base_label, base_score, long_label, long_score


def fill_rubrics(data: bytes, content: EvalPlanContent) -> tuple[bytes, dict[str, Any]]:
    """Fill each 수행평가 세부기준 rubric table from the matching review rubric
    (byte-preserving). Replaces the 한국사 sample 성취기준 codes (the dominant
    leftover-sample source) and lands every 평가항목 label.

    Per rubric: shrink the single 7-배점-row example block to the review rubric's
    평가항목 count, then splice 성취기준 (r0), 상/중/하 평가기준 (r1-3 from levels),
    학생 유의사항 (r4), 영역(만점), the 평가항목 labels (into the merged 평가항목
    cell's paragraphs), each item's 채점기준 breakdown + top 배점, and the
    기본점수 / 장기 미인정 rows. Item blocks are shrunk with ``delete_row`` (the
    merges collapse cleanly); nothing is regenerated."""
    from .table_patch import apply_table_ops, fill_cells, _text_of, _all_paragraph_spans

    report: dict[str, Any] = {"rubrics": len(content.rubrics), "filled": 0, "skipped": []}
    levels = content.levels

    # STEP 1 (structure): shrink each rubric's item block to its review item count.
    for i, rub in enumerate(content.rubrics):
        items = [row for row in rub.rows if not row[0].startswith("기본점수")]
        n = max(1, len(items))
        idxs = _rubric_indices(data)
        if i >= len(idxs):
            report["skipped"].append(f"rubric {i}: no matching blank table")
            continue
        ti = idxs[i]
        hdr, base, _nrows = _rubric_bounds(data, ti)
        if hdr is None or base is None:
            report["skipped"].append(f"rubric {i}: could not bound item block")
            continue
        item_rows = base - (hdr + 1)          # blank example block height (7)
        first_item = hdr + 1
        todel = list(range(first_item + n, base))   # keep n, drop the surplus
        if todel:
            res = apply_table_ops(data, [{"op": "delete_row", "table_index": ti, "rows": todel}])
            if not res.ok:
                report["skipped"].append(f"rubric {i} shrink: {[s.reason for s in res.skipped]}")
                continue
            data = res.data

    # STEP 2 (content): fill each rubric's cells.
    for i, rub in enumerate(content.rubrics):
        idxs = _rubric_indices(data)
        if i >= len(idxs):
            continue
        ti = idxs[i]
        hdr, base, _nrows = _rubric_bounds(data, ti)
        if hdr is None or base is None:
            continue
        first_item = hdr + 1
        items = [row for row in rub.rows if not row[0].startswith("기본점수")]
        n = len(items)
        _sp, tb, grid, rep = _grid_of(data, ti)

        cells: list[dict[str, Any]] = []
        # r0 성취기준 (replaces 한국사 sample codes)
        std_text = rub.standards or (content.achievement_std and "")
        if std_text:
            cells.append({"table_index": ti, "row": 0, "col": 1, "text": std_text, "max_lines": 3})
        # r1-3 상/중/하 평가기준 from the matching area's A/B/C descriptors
        if i < len(levels) and len(levels[i]) >= 4:
            for k, desc in enumerate(levels[i][1:4]):
                rr = 1 + k
                if grid.get((rr, 2)):
                    cells.append({"table_index": ti, "row": rr, "col": 2, "text": desc, "max_lines": 4})
        # 영역(만점) leader
        area_cell = grid.get((first_item, 0))
        if area_cell is not None:
            cells.append({"table_index": ti, "row": first_item, "col": 0,
                          "text": f"{rub.title}({rub.points}점)", "max_lines": 3})
        # 평가항목 labels -> the merged 평가항목 cell's paragraphs (one line per item)
        item_cell = grid.get((first_item, 1))
        if item_cell is not None:
            n_para = len(_all_paragraph_spans(tb[item_cell.start:item_cell.end]))
            labels = [it[0] for it in items]
            if n_para >= 1:
                # pack labels across available paragraphs; extras merged into the last
                if len(labels) <= n_para:
                    packed = labels
                else:
                    packed = labels[:n_para - 1] + [" · ".join(labels[n_para - 1:])]
                cells.append({"table_index": ti, "row": first_item, "col": 1,
                              "text": "\n".join(packed), "max_lines": 2})
        # per-item 채점기준 rows (col3) + top 배점 (col4)
        for k, it in enumerate(items):
            rr = first_item + k
            if rr >= base:
                break
            if grid.get((rr, 3)):
                cells.append({"table_index": ti, "row": rr, "col": 3,
                              "text": _batjeom_line(it[0], it[1]), "max_lines": 3})
            top = _top_batjeom(it[1])
            if top and grid.get((rr, 4)):
                cells.append({"table_index": ti, "row": rr, "col": 4, "text": top, "max_lines": 1})
        # 기본점수 / 장기 미인정 rows
        base_label, base_score, long_label, long_score = _base_scores(rub.rows)
        if grid.get((base, 1)):
            cells.append({"table_index": ti, "row": base, "col": 1, "text": base_label, "max_lines": 2})
        if base_score and grid.get((base, 4)):
            cells.append({"table_index": ti, "row": base, "col": 4, "text": base_score, "max_lines": 1})
        if grid.get((base + 1, 1)):
            cells.append({"table_index": ti, "row": base + 1, "col": 1, "text": long_label, "max_lines": 2})
        if long_score and grid.get((base + 1, 4)):
            cells.append({"table_index": ti, "row": base + 1, "col": 4, "text": long_score, "max_lines": 1})

        fr = fill_cells(data, cells)
        data = fr.data
        report["filled"] += len(fr.applied)
        report["skipped"].extend(f"rubric {i}: {s.reason}" for s in fr.skipped)
    return data, report


def _rubric_bounds(data: bytes, ti: int) -> tuple[int | None, int | None, int]:
    """(header_row, 기본점수_row, row_count) of a rubric table -- the item block is
    the physical rows between them."""
    from .table_patch import _text_of
    _sp, tb, grid, rep = _grid_of(data, ti)
    hdr = base = None
    for r in range(rep.row_count):
        c0 = grid.get((r, 0))
        if c0 is not None:
            t0 = _text_of(tb[c0.start:c0.end])
            if "영역" in t0 and "만점" in t0:
                hdr = r
        c1 = grid.get((r, 1))
        if c1 is not None and base is None and "기본점수" in _text_of(tb[c1.start:c1.end]):
            base = r
    return hdr, base, rep.row_count


def _prose_items(raw: str, header_words: Sequence[str] = ()) -> list[str]:
    """Split a ``_norm``'d prose section ('가. ... 나. ... 다. ...') into 가/나/다
    items, dropping any leading section-title words the parser swept in."""
    s = raw.strip()
    for hw in header_words:
        if s.startswith(hw):
            s = s[len(hw):].strip()
    # split before each Korean-letter ordinal marker '가.'..'하.'
    parts = re.split(r"(?<!\S)(?=[가-힣]\.\s)", s)
    items = [re.sub(r"^[가-힣]\.\s*", "", p).strip() for p in parts if p.strip()]
    # drop residual '- ' bullet / title fragments with no ordinal
    return [it for it in items if it and not it.startswith("평가")]


def fill_sections(data: bytes, content: EvalPlanContent) -> tuple[bytes, dict[str, Any]]:
    """Fill the 가./나./다. prose placeholders of §1 목적 / §2 기본방향 / §3 방침 /
    §11 결과분석 with the review MD's items (byte-preserving paragraph splices).

    The blank ships three empty '가.'/'나.'/'다.' placeholder paragraphs per prose
    section; the review has more items, so items are distributed across the three
    slots (surplus items merged into the last slot) -- content preserved, honest
    about the slot limit. Uses :func:`hwpx.patch.paragraph_patch`, which only
    *replaces* existing paragraphs (never inserts), so the document geometry is
    untouched. Sections whose placeholders can't be located are reported, not
    faked."""
    from .patch import paragraph_patch, _PARAGRAPH_RE
    from .table_patch import _sections, _text_of

    report: dict[str, Any] = {"filled": 0, "skipped": []}
    sections = _sections(data)
    if not sections:
        return data, report
    sp = sorted(sections)[0]
    section = sections[sp]
    paras = list(_PARAGRAPH_RE.finditer(section))
    texts = [_text_of(m.group(0)).strip() for m in paras]

    # locate each prose section's placeholder run: the first index of a section's
    # numbered header paragraph (bare '평가의 목적' etc.), then the '가.'/'나.'/'다.'
    # paragraphs that follow it before the next section header.
    def slots_after(header_kw: str, next_kws: Sequence[str]) -> list[int]:
        try:
            hi = next(i for i, t in enumerate(texts) if t == header_kw)
        except StopIteration:
            return []
        # boundary = next section header
        end = len(texts)
        for nk in next_kws:
            for j in range(hi + 1, len(texts)):
                if texts[j] == nk:
                    end = min(end, j)
                    break
        slots = [j for j in range(hi + 1, end) if re.match(r"^[가-힣]\.\s*$", texts[j]) or texts[j] in ("가.", "나.", "다.")]
        return slots

    plan = [
        ("purposes", "평가의 목적", ("평가의 기본 방향",), ("평가의 목적",)),
        ("directions", "평가의 기본 방향", ("평가 방침",), ("평가의 기본 방향",)),
    ]
    patches: list[dict[str, Any]] = []
    for attr, header, nexts, titlewords in plan:
        raw = getattr(content, attr, "")
        items = _prose_items(raw, titlewords)
        slots = slots_after(header, nexts)
        if not slots or not items:
            if items:
                report["skipped"].append(f"{attr}: no empty 가/나/다 placeholder to fill")
            continue
        # distribute items across slots (surplus merged into last)
        k = len(slots)
        if len(items) <= k:
            packed = items
        else:
            packed = items[:k - 1] + [" ".join(items[k - 1:])]
        for slot_idx, text in zip(slots, packed):
            patches.append({"section_path": sp, "paragraph_index": slot_idx, "text": text})

    if not patches:
        report["skipped"].append("no fillable prose placeholders located")
        return data, report
    pres = paragraph_patch(data, patches)
    report["filled"] = len(pres.applied)
    report["skipped"].extend(s.reason for s in pres.skipped)
    return pres.data, report


def fill_schedule(data: bytes, content: EvalPlanContent) -> tuple[bytes, dict[str, Any]]:
    """Fill the Ⅰ 교수학습 운영 계획 schedule table from ``content.schedule`` (one
    logical row per review row, 6 columns), shrink-to-fit at 4 lines. Located by
    the widest multi-row data table under the Ⅰ heading. Merged-cell skips (the
    month/week span carry-overs) are expected and reported, not errors."""
    from .table_patch import fill_cells

    report: dict[str, Any] = {"rows": len(content.schedule), "filled": 0, "skipped": []}
    if not content.schedule:
        return data, report
    ti = _schedule_index(data)
    if ti is None:
        report["skipped"].append("no schedule table found")
        return data, report
    cells = []
    for i, row in enumerate(content.schedule):
        r = i + 1  # row 0 is the header
        for col in range(min(6, len(row))):
            cells.append({"table_index": ti, "row": r, "col": col, "text": row[col], "max_lines": 4})
    fr = fill_cells(data, cells)
    report["filled"] = len(fr.applied)
    report["skipped"].extend(s.reason for s in fr.skipped)
    return fr.data, report


def _schedule_index(data: bytes) -> int | None:
    """Table index of the Ⅰ schedule grid: the first multi-row table whose header
    row carries the 월/주/성취기준 signature."""
    from .table_patch import _sections, _iter_table_spans, build_grid, _text_of
    base = 0
    for sp, section in sorted(_sections(data).items()):
        spans = _iter_table_spans(section)
        for ti, (s, e) in enumerate(spans):
            tb = section[s:e]
            grid, rep = build_grid(tb)
            if rep.row_count < 3:
                continue
            hdr = " ".join(_text_of(tb[grid[(0, c)].start:grid[(0, c)].end])
                           for c in range(rep.col_count) if grid.get((0, c)))
            if "월" in hdr and "주" in hdr and "성취기준" in hdr:
                return base + ti
        base += len(spans)
    return None


def fill_evalplan(
    blank: str,
    content: EvalPlanContent,
    *,
    output: str | None = None,
    phase: str = "structural",
) -> dict[str, Any]:
    """Apply the recipe to a blank form.

    ``phase="structural"`` runs the confident deletions only (red/optional tables,
    정기시험 column, surplus example tables). ``phase="all"`` additionally runs the
    content fills -- schedule, achievement, levels, rubrics, section prose -- each
    byte-preserving and located by classification/geometry (index-safe against the
    prior structural deletes). Returns the apply result dict plus the op-plan
    transcript and, for ``phase="all"``, a ``content_report`` per region."""
    from .table_patch import apply_table_ops

    plan = plan_structural_ops(blank, content)
    result = apply_table_ops(blank, plan["ops"])
    data = result.data
    payload = result.to_dict()

    content_report: dict[str, Any] = {}
    if phase == "all":
        data, content_report["schedule"] = fill_schedule(data, content)
        data, content_report["achievement"] = fill_achievement(data, content)
        data, content_report["levels"] = fill_levels(data, content)
        data, content_report["rubrics"] = fill_rubrics(data, content)
        data, content_report["sections"] = fill_sections(data, content)

    if output is not None:
        from pathlib import Path as _P
        _P(output).write_bytes(data)
        payload["outputPath"] = output
    payload["transcript"] = plan["transcript"]
    payload["expected_skeleton"] = plan["expected_skeleton"]
    payload["content_report"] = content_report
    payload["_data"] = data
    return payload


def parse_review_file(path: str) -> EvalPlanContent:
    import pathlib
    return parse_review_md(pathlib.Path(path).read_text(encoding="utf-8"))


__all__ = [
    "EvalPlanContent", "Rubric", "parse_review_md", "parse_review_file",
    "expected_skeleton", "plan_structural_ops", "fill_evalplan",
    "fill_schedule", "fill_achievement", "fill_levels", "fill_rubrics", "fill_sections",
]
