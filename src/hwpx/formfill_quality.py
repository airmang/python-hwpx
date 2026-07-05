# SPDX-License-Identifier: Apache-2.0
"""Form-fill quality scorer -- the fitness function of the evalplan GOAL loop.

Given ``(produced, gold, blank)`` this scores a filled evaluation-plan form on
five axes against the gold reference (a correctly submitted form of the same
family), returning a weighted 0-100 total plus a per-axis *gap report* pinning
concrete defects and their locations.

    A. render cleanliness (30) -- real-Hancom render: text overflowing a cell
       border, collapsed/overlapping lines, page-count sanity. **Requires an
       oracle**; with none the axis is ``unverified`` (contributes 0, never a
       silent pass -- Constitution IV/V).
    B. format fidelity (25) -- byte preservation vs *blank*: untouched tables
       carried verbatim, edited tables reusing the blank's formatting vocabulary
       (borderFill / column-width integers). A regenerated form scores ~0. This
       axis measures OUR byte-discipline, so *gold* (re-serialised by Hancom)
       legitimately scores low here -- gold is the reference for A/C/D, not B.
    C. structure conformance (20) -- vs the *gold* skeleton: the same delete/keep
       policy (정기시험 column, 석차등급 / 제출 / ★유의 red tables, 5단계 성취율),
       achievement-standard block count, rubric-area count.
    D. content completeness (15) -- sections [1]~[11] present, score sum == 100,
       반영비율 non-increasing.
    E. compliance (10) -- 평가계획 lint; manual-only rules are ``needs_review``,
       never a silent pass.

Design rails: measure-first, no-silent-true, honest-defer. Every axis reports a
``status`` so a partial/undetectable measurement is visible, not disguised as a
pass. Reuses the byte parsers in :mod:`hwpx.table_patch` and the render oracle in
:mod:`hwpx.visual.oracle`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .table_patch import (
    _direct_cells,
    _iter_table_spans,
    _read_source_bytes,
    _sections,
    _text_of,
    build_grid,
)

# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

# status vocabulary for an axis (no-silent-true: an undetectable axis says so)
MEASURED = "measured"
UNVERIFIED = "unverified"      # could not run the required oracle -> not a pass
NEEDS_REVIEW = "needs_review"  # measured what we can; some rules are manual-only

AXES = (
    ("A", "render_cleanliness", 30),
    ("B", "format_fidelity", 25),
    ("C", "structure_conformance", 20),
    ("D", "content_completeness", 15),
    ("E", "compliance", 10),
)


@dataclass
class AxisScore:
    key: str
    name: str
    weight: int
    score: float            # 0..weight
    status: str             # MEASURED | UNVERIFIED | NEEDS_REVIEW
    findings: list[str] = field(default_factory=list)   # gap report (with locations)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "weight": self.weight,
            "score": round(self.score, 2),
            "status": self.status,
            "findings": self.findings,
            "detail": self.detail,
        }


@dataclass
class ScoreCard:
    total: float
    render_checked: bool
    axes: list[AxisScore]

    def axis(self, key: str) -> AxisScore:
        for a in self.axes:
            if a.key == key:
                return a
        raise KeyError(key)

    def lowest_axis(self) -> AxisScore:
        """Weakest axis by weight-normalised score, tie-broken A>B>C>D>E.

        An ``unverified`` axis is not "lowest" for diagnosis (you fix the oracle,
        not the content), so it is excluded unless every axis is unverified.
        """
        order = {k: i for i, (k, _n, _w) in enumerate(AXES)}
        candidates = [a for a in self.axes if a.status != UNVERIFIED] or list(self.axes)
        return min(candidates, key=lambda a: (a.score / a.weight, order[a.key]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 2),
            "render_checked": self.render_checked,
            "axes": [a.to_dict() for a in self.axes],
            "lowest_axis": self.lowest_axis().key,
        }


# --------------------------------------------------------------------------- #
# Shared table extraction
# --------------------------------------------------------------------------- #

@dataclass
class _Table:
    section: str
    index: int
    bytes: bytes
    rows: int
    cols: int
    first_row: list[str]
    heading: str
    text: str


def _tables(source: str | Path | bytes) -> list[_Table]:
    data = _read_source_bytes(source)
    out: list[_Table] = []
    for sp, section in sorted(_sections(data).items()):
        spans = _iter_table_spans(section)
        for ti, (s, e) in enumerate(spans):
            tb = section[s:e]
            _grid, rep = build_grid(tb)
            first: list[str] = []
            for col in range(rep.col_count):
                c = _grid.get((0, col))
                first.append(" ".join(_text_of(tb[c.start:c.end]).split()) if c else "")
            # de-dup horizontally-merged repeats in the preview
            dedup: list[str] = []
            for cell in first:
                if not dedup or dedup[-1] != cell:
                    dedup.append(cell)
            w_start = max(0, s - 8000)
            heading = " ".join(_text_of(section[w_start:s]).split())[-80:]
            out.append(_Table(
                section=sp, index=ti, bytes=tb,
                rows=rep.row_count, cols=rep.col_count,
                first_row=dedup, heading=heading,
                text=" ".join(_text_of(tb).split()),
            ))
    return out


_BORDERFILL_RE = re.compile(rb'borderFillIDRef="(\d+)"')
_WIDTH_RE = re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?cellSz\b[^>]*\bwidth="(\d+)"')


def _borderfill_vocab(tables: Sequence[_Table]) -> set[str]:
    v: set[str] = set()
    for t in tables:
        v.update(m.group(1).decode() for m in _BORDERFILL_RE.finditer(t.bytes))
    return v


def _width_vocab(tables: Sequence[_Table]) -> set[int]:
    v: set[int] = set()
    for t in tables:
        v.update(int(m.group(1)) for m in _WIDTH_RE.finditer(t.bytes))
    return v


# --------------------------------------------------------------------------- #
# A. render cleanliness  (oracle)
# --------------------------------------------------------------------------- #

def detect_overflow_crossings(pdf_path: str | Path, *, eps: float = 1.5) -> list[dict[str, Any]]:
    """Words whose bbox interior is crossed by a vertical cell border -- i.e. text
    spilling right across a cell boundary, the signature form-fill overflow mode.

    Calibrated so a clean gold render reports 0. Only stroke line segments count
    (cell separators); ``re`` rectangle fills / underlines are excluded. Requires
    PyMuPDF; raises ``RuntimeError`` if unavailable (caller degrades to unverified).
    """
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - env probe
        raise RuntimeError(f"PyMuPDF unavailable: {exc}") from exc

    incidents: list[dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))
    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            vsegs: list[tuple[float, float, float]] = []
            for path in page.get_drawings():
                for it in path["items"]:
                    if it[0] == "l":
                        a, b = it[1], it[2]
                        if abs(a.x - b.x) < 0.6 and abs(a.y - b.y) > 3:
                            vsegs.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            if not vsegs:
                continue
            for w in page.get_text("words"):
                x0, y0, x1, y1, txt = w[0], w[1], w[2], w[3], w[4]
                mid = (y0 + y1) / 2
                for vx, vy0, vy1 in vsegs:
                    if x0 + eps < vx < x1 - eps and vy0 <= mid <= vy1:
                        incidents.append({"page": pno, "x": round(x0), "y": round(y0), "text": txt})
                        break
    finally:
        doc.close()
    return incidents


def score_render(
    produced: str | Path,
    *,
    oracle: Any | None = None,
    produced_pdf: str | Path | None = None,
    expected_pages: int | None = None,
    work_dir: str | Path | None = None,
) -> AxisScore:
    """A axis. Renders *produced* (or uses a pre-rendered ``produced_pdf``) and
    penalises overflow crossings + page-count anomaly. Oracle-truthful: with no
    oracle and no pdf the axis is ``unverified`` (score 0, flagged)."""
    key, name, weight = "A", "render_cleanliness", 30
    pdf = str(produced_pdf) if produced_pdf else None
    if pdf is None:
        if oracle is None:
            from .visual.oracle import resolve_oracle
            oracle = resolve_oracle()
        if oracle is None or not oracle.available():
            return AxisScore(key, name, weight, 0.0, UNVERIFIED,
                             ["no Hancom render oracle reachable -- A is unverified, not a pass"])
        out = None
        if work_dir:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
            out = str(Path(work_dir) / "produced_render.pdf")
        pdf = oracle.render_pdf(str(produced), out)
        if not pdf:
            return AxisScore(key, name, weight, 0.0, MEASURED,
                             ["Hancom failed to render produced document (hard render failure)"])
    try:
        crossings = detect_overflow_crossings(pdf)
    except RuntimeError as exc:
        return AxisScore(key, name, weight, 0.0, UNVERIFIED,
                         [f"render imaging deps unavailable: {exc}"])

    import fitz  # already importable if we got here
    doc = fitz.open(pdf)
    pages = doc.page_count
    doc.close()

    findings: list[str] = []
    penalty = 0.0
    if crossings:
        by_page: dict[int, int] = {}
        for c in crossings:
            by_page[c["page"]] = by_page.get(c["page"], 0) + 1
        penalty += min(20.0, len(crossings) * 3.0)
        for c in crossings[:8]:
            findings.append(f"overflow: '{c['text']}' crosses a cell border at p{c['page']} ({c['x']},{c['y']})")
        findings.append(f"overflow crossings total: {len(crossings)} across pages {sorted(by_page)}")

    if expected_pages is not None and pages > expected_pages:
        over = pages - expected_pages
        penalty += min(6.0, over * 2.0)
        findings.append(f"page-count {pages} exceeds expected {expected_pages} (+{over}) -- possible overflow/pagination")

    score = max(0.0, weight - penalty)
    detail = {"pages": pages, "expected_pages": expected_pages,
              "overflow_crossings": len(crossings), "pdf": pdf}
    status = MEASURED
    if not findings:
        findings.append(f"render clean: 0 overflow crossings over {pages} pages")
    return AxisScore(key, name, weight, score, status, findings, detail)


# --------------------------------------------------------------------------- #
# B. format fidelity  (byte preservation vs blank)
# --------------------------------------------------------------------------- #

def score_format_fidelity(produced: str | Path, blank: str | Path) -> AxisScore:
    """B axis. Untouched tables must be carried byte-verbatim from *blank*; edited
    tables must reuse the blank's formatting vocabulary (borderFill IDs + width
    integers) rather than regenerate generic formatting."""
    key, name, weight = "B", "format_fidelity", 25
    ptabs = _tables(produced)
    btabs = _tables(blank)
    if not ptabs:
        return AxisScore(key, name, weight, 0.0, MEASURED, ["produced has no tables"])

    blank_blobs = {t.bytes for t in btabs}
    bf_vocab = _borderfill_vocab(btabs)
    w_vocab = _width_vocab(btabs)

    carried = 0
    preserved_credit = 0.0
    regenerated: list[int] = []
    for i, t in enumerate(ptabs):
        if t.bytes in blank_blobs:
            carried += 1
            continue
        # edited / new: does it reuse the blank's formatting vocabulary?
        bf = {m.group(1).decode() for m in _BORDERFILL_RE.finditer(t.bytes)}
        ws = {int(m.group(1)) for m in _WIDTH_RE.finditer(t.bytes)}
        bf_match = (len(bf & bf_vocab) / len(bf)) if bf else 0.0
        w_match = (len(ws & w_vocab) / len(ws)) if ws else 0.0
        cred = 0.5 * bf_match + 0.5 * w_match
        preserved_credit += cred
        if cred < 0.5:
            regenerated.append(i)

    n = len(ptabs)
    carry_rate = carried / n
    edited = n - carried
    fmt_pres_rate = (preserved_credit / edited) if edited else 1.0
    raw = 0.5 * carry_rate + 0.5 * fmt_pres_rate
    score = weight * raw

    findings: list[str] = []
    findings.append(f"carried verbatim: {carried}/{n} tables ({carry_rate:.0%}); "
                    f"edited-format-preservation: {fmt_pres_rate:.0%} over {edited} edited tables")
    if carried == 0 and n >= 5:
        findings.append("REGENERATION: no blank table survives byte-verbatim -- "
                        "document was rebuilt, not edited (Constitution VII violation)")
    for i in regenerated[:8]:
        t = ptabs[i]
        findings.append(f"regenerated formatting: table #{i} '{t.first_row[:3]}' "
                        f"does not reuse blank borderFill/width vocabulary")
    detail = {"carried": carried, "n_produced": n, "carry_rate": round(carry_rate, 3),
              "fmt_preservation": round(fmt_pres_rate, 3), "regenerated_tables": regenerated}
    return AxisScore(key, name, weight, score, MEASURED, findings, detail)


# --------------------------------------------------------------------------- #
# C. structure conformance  (vs gold skeleton)
# --------------------------------------------------------------------------- #

def _classify(t: _Table) -> str:
    """Coarse table type from its first-row / heading signature."""
    fr = " | ".join(t.first_row)
    txt = t.text
    if "석차등급" in fr and "원점수" in fr:
        return "seokcha"                         # red table -> should be deleted
    if "제출" in fr and ("모아찍기" in txt or "인쇄물" in txt):
        return "submit"                          # red submit table -> deleted
    if t.rows == 1 and t.cols == 1 and t.text.startswith("★유의"):
        return "notice_star"                     # red ★유의 table -> deleted
    if fr.startswith("교육과정 성취기준") and "평가기준" in fr:
        return "achievement"                     # 성취기준·평가기준
    if fr.startswith("성취수준") and "일반적 특성" in fr:
        return "level"                           # 영역별 성취수준
    if fr.startswith("교육과정성취기준"):
        return "rubric"                          # 수행평가 세부기준 rubric
    if "평가 종류" in fr or ("수행평가" in fr and "합계" in fr):
        return "ratio"                           # 평가의 종류와 반영비율
    if "성취율" in fr and "성취도" in fr:
        return "achieve_rate"                    # 기준 성취율과 성취도
    return "other"


def _skeleton(source: str | Path) -> dict[str, Any]:
    tabs = _tables(source)
    kinds: dict[str, int] = {}
    ratio_has_regular = False
    for t in tabs:
        k = _classify(t)
        kinds[k] = kinds.get(k, 0) + 1
        if k == "ratio" and "정기시험" in " | ".join(t.first_row):
            ratio_has_regular = True
    return {"kinds": kinds, "ratio_has_regular_exam": ratio_has_regular, "n_tables": len(tabs)}


def score_structure(produced: str | Path, gold: str | Path) -> AxisScore:
    """C axis. Match the gold skeleton's delete/keep policy and block counts."""
    key, name, weight = "C", "structure_conformance", 20
    ps = _skeleton(produced)
    gs = _skeleton(gold)
    pk, gk = ps["kinds"], gs["kinds"]

    checks: list[tuple[str, bool, str]] = []
    # deletion policy: red / optional tables gold removed, produced must too
    for kind, label in [("seokcha", "석차등급 red table"),
                        ("submit", "제출 안내 red table"),
                        ("notice_star", "★유의 red table")]:
        gone_in_gold = gk.get(kind, 0) == 0
        gone_in_prod = pk.get(kind, 0) == 0
        ok = (gone_in_prod == gone_in_gold)
        checks.append((f"delete:{label}", ok,
                       "" if ok else f"gold has {gk.get(kind,0)} / produced {pk.get(kind,0)} -- deletion policy mismatch"))
    # 정기시험 column removed from 반영비율 (this subject: 100% 수행)
    ok = (ps["ratio_has_regular_exam"] == gs["ratio_has_regular_exam"])
    checks.append(("ratio:정기시험 column policy", ok,
                   "" if ok else f"gold 정기시험={gs['ratio_has_regular_exam']} / produced={ps['ratio_has_regular_exam']}"))
    # block counts vs gold
    for kind, label in [("achievement", "성취기준·평가기준 blocks"),
                        ("level", "영역별 성취수준 blocks"),
                        ("rubric", "수행평가 세부기준 blocks"),
                        ("achieve_rate", "기준 성취율/성취도 tables")]:
        g, p = gk.get(kind, 0), pk.get(kind, 0)
        ok = (g == p)
        checks.append((f"count:{label}", ok,
                       "" if ok else f"gold {g} vs produced {p}"))

    passed = sum(1 for _l, ok, _m in checks if ok)
    total = len(checks)
    score = weight * (passed / total) if total else 0.0
    findings = [f"structure checks {passed}/{total} match gold skeleton"]
    for label, ok, msg in checks:
        if not ok:
            findings.append(f"MISMATCH {label}: {msg}")
    detail = {"produced_kinds": pk, "gold_kinds": gk, "passed": passed, "total": total}
    return AxisScore(key, name, weight, score, MEASURED, findings, detail)


# --------------------------------------------------------------------------- #
# D. content completeness
# --------------------------------------------------------------------------- #

_SECTION_RE = re.compile(r"(\d+)\s*(평가의 목적|평가의 기본 방향|평가 방침|성취기준|"
                         r"평가의 종류와 반영비율|기준 성취율|수행평가 세부기준|정의적|"
                         r"수행평가 미응시|평가 유의사항|평가 결과)")


def score_content(produced: str | Path, *, content: str | Path | None = None) -> AxisScore:
    """D axis. Sections present, ratio row sums to 100 and is non-increasing."""
    key, name, weight = "D", "content_completeness", 15
    tabs = _tables(produced)
    full_text = "\n".join(t.text for t in tabs)

    checks: list[tuple[str, bool, str]] = []
    # sections [1]~[11] -- look for the numbered section labels in the section tables
    labels = ["평가의 목적", "평가의 기본 방향", "평가 방침", "성취기준 및 성취수준",
              "평가의 종류와 반영비율", "기준 성취율과 성취도", "수행평가 세부기준",
              "정의적 능력 평가", "수행평가 미응시자", "평가 유의사항", "평가 결과 분석"]
    missing = [lab for lab in labels if lab.replace(" ", "") not in full_text.replace(" ", "")]
    checks.append(("sections [1]~[11] present", not missing,
                   "" if not missing else f"missing sections: {missing}"))

    # 반영비율: parse percentages in the ratio table, sum ~100, non-increasing
    ratio_tabs = [t for t in tabs if _classify(t) == "ratio"]
    ratio_ok = None
    ratio_msg = ""
    if ratio_tabs:
        rt = ratio_tabs[0].text
        pcts = [int(m) for m in re.findall(r"(\d+)\s*%", rt)]
        area_pcts = [p for p in pcts if p not in (100,)]
        if area_pcts:
            total_p = None
            # find a contiguous set that sums to 100
            for k in range(2, min(len(area_pcts), 5) + 1):
                if sum(area_pcts[:k]) == 100:
                    total_p = 100
                    seg = area_pcts[:k]
                    break
            else:
                seg = area_pcts
            # "왼쪽 우선": the first (left-most) area carries the largest weight.
            # gold uses 30/20/20/30 -- NOT strictly monotone -- so require only
            # that the first area ties the maximum, which gold satisfies.
            left_first = bool(seg) and seg[0] == max(seg)
            ratio_ok = (total_p == 100) and left_first
            ratio_msg = f"ratio segment {seg} sum={sum(seg)} left-first-largest={left_first}"
        else:
            ratio_ok = False
            ratio_msg = "no percentages found in ratio table"
    if ratio_ok is not None:
        checks.append(("반영비율 sum=100 & non-increasing", ratio_ok, "" if ratio_ok else ratio_msg))

    passed = sum(1 for _l, ok, _m in checks if ok)
    total = len(checks)
    score = weight * (passed / total) if total else 0.0
    status = MEASURED
    findings = [f"content checks {passed}/{total}"]
    for label, ok, msg in checks:
        if not ok:
            findings.append(f"INCOMPLETE {label}: {msg}")
    # note the limits honestly
    findings.append("note: empty-required-cell detection is coarse (text-presence only)")
    return AxisScore(key, name, weight, score, status, findings,
                     {"missing_sections": missing, "passed": passed, "total": total})


# --------------------------------------------------------------------------- #
# E. compliance lint
# --------------------------------------------------------------------------- #

def score_compliance(produced: str | Path) -> AxisScore:
    """E axis. Computable 평가계획 lint rules; manual-only rules -> needs_review.

    Rules are *gold-calibrated*: gold (the accepted submission) passes every one.
    (Notably gold uses ``~`` in the 성취율 band notation, so a blanket 물결표 ban
    is a false positive and is deferred to manual review, not scored.)
    """
    key, name, weight = "E", "compliance", 10
    tabs = _tables(produced)
    checks: list[tuple[str, bool, str]] = []

    # (1) 정기시험 column removed (100% 수행 for this subject family)
    ratio_tabs = [t for t in tabs if _classify(t) == "ratio"]
    has_regular = any("정기시험" in " | ".join(t.first_row) for t in ratio_tabs)
    checks.append(("정기시험 열 부재", not has_regular,
                   "" if not has_regular else "반영비율 table still has 정기시험 column"))

    # (2) 반영비율 왼쪽 우선(첫 영역이 최대) -- gold 30/20/20/30 passes
    left_ok = None
    if ratio_tabs:
        pcts = [int(m) for m in re.findall(r"(\d+)\s*%", ratio_tabs[0].text) if int(m) != 100]
        seg = None
        for k in range(2, min(len(pcts), 5) + 1):
            if sum(pcts[:k]) == 100:
                seg = pcts[:k]
                break
        seg = seg or pcts
        left_ok = bool(seg) and seg[0] == max(seg)
        checks.append(("반영비율 왼쪽 우선(첫 영역 최대)", left_ok,
                       "" if left_ok else f"first area {seg[:1]} is not the max of {seg}"))

    # (3) 성취도 3단계(A~C) present in a 성취율 table (진로선택 절대평가)
    rate_tabs = [t for t in tabs if _classify(t) == "achieve_rate"]
    three_grade = any(all(g in t.text for g in ("A", "B", "C")) for t in rate_tabs) if rate_tabs else None
    if three_grade is not None:
        checks.append(("성취도 3단계(A~C)", three_grade,
                       "" if three_grade else "성취율 table missing A/B/C grade bands"))

    passed = sum(1 for _l, ok, _m in checks if ok)
    total = len(checks)
    score = weight * (passed / total) if total else 0.0
    findings = [f"lint {passed}/{total} computable rules pass; "
                "manual-only 유의사항 rules (수행 30%↑, 기본점수 20~40%, 급간 동일, "
                "물결표 문맥) require human review -> needs_review"]
    for label, ok, msg in checks:
        if not ok:
            findings.append(f"LINT {label}: {msg}")
    return AxisScore(key, name, weight, score, NEEDS_REVIEW, findings,
                     {"passed": passed, "total": total})


# --------------------------------------------------------------------------- #
# Top-level scorer
# --------------------------------------------------------------------------- #

def score_form_fill(
    produced: str | Path,
    gold: str | Path,
    blank: str | Path,
    *,
    oracle: Any | None = None,
    produced_pdf: str | Path | None = None,
    content: str | Path | None = None,
    expected_pages: int | None = None,
    work_dir: str | Path | None = None,
    run_render: bool = True,
) -> ScoreCard:
    """Score ``produced`` against ``gold`` (structure) and ``blank`` (byte
    fidelity), on 5 axes -> weighted 0-100 + gap report. The loop's fitness fn.

    ``run_render=False`` skips the A oracle render (fast structural-only pass;
    A becomes ``unverified``). Provide ``produced_pdf`` to reuse a prior render.
    """
    if run_render or produced_pdf is not None:
        a = score_render(produced, oracle=oracle, produced_pdf=produced_pdf,
                         expected_pages=expected_pages, work_dir=work_dir)
    else:
        a = AxisScore("A", "render_cleanliness", 30, 0.0, UNVERIFIED,
                      ["render skipped (run_render=False) -- A unverified"])
    b = score_format_fidelity(produced, blank)
    c = score_structure(produced, gold)
    d = score_content(produced, content=content)
    e = score_compliance(produced)
    axes = [a, b, c, d, e]
    total = sum(ax.score for ax in axes)
    render_checked = a.status == MEASURED
    return ScoreCard(total=total, render_checked=render_checked, axes=axes)


__all__ = [
    "AxisScore", "ScoreCard", "score_form_fill",
    "score_render", "score_format_fidelity", "score_structure",
    "score_content", "score_compliance", "detect_overflow_crossings",
    "MEASURED", "UNVERIFIED", "NEEDS_REVIEW",
]
