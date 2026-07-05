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

    c.purposes = _norm(sec(1))
    c.directions = _norm(sec(2))
    c.policies = _norm(sec(3))

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

    c.affective = _norm(sec(8))
    c.absentee = _norm(sec(9))
    c.cautions = _norm(sec(10))
    c.analysis = _norm(sec(11))
    return c


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


def parse_review_file(path: str) -> EvalPlanContent:
    import pathlib
    return parse_review_md(pathlib.Path(path).read_text(encoding="utf-8"))


__all__ = [
    "EvalPlanContent", "Rubric", "parse_review_md", "parse_review_file",
    "expected_skeleton",
]
