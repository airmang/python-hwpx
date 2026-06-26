# Exam Typesetting — Implementation Plan 2: Composer (Exam IR → 학교 양식 본문 재조판)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the python-hwpx **composer** (`src/hwpx/exam/`) that takes an LLM-authored exam (Markdown) and pours it into a school form `.hwpx` — mapping each role (발문/배점/답항/지문) onto the form's **existing named styles**, keeping every 문항 unbroken with the Phase-0 mechanism (keepWithNext + oracle-measured break insertion), inserting into the form's **body region** (never appending — Hancom drops appended content), and leaving `[그림N]` text placeholders intact — so the output opens clean in Hancom with 문항-split = 0.

**Architecture:** Spec `specs/003-exam-typesetting/spec.md`, approach A (reuse the school form as a living container; Hancom flows the 2 columns; keep-together constrains it). Plan 1 shipped the engine primitives this plan consumes (`ensure_paragraph_format(break_setting=…)`, `detect_block_splits`, inline `columnBreak`). This plan adds the **judgment-free engine half** of the composer: IR + md→IR parser + form profiler + body-region replace + measure helpers + a thin convergence driver. The form-aware orchestration/leap demo is Plan 4; the MCP surface is Plan 3. **The composer OPENS the form and INSERTS into its body — it does NOT call `create_document_from_plan` (that builds a fresh document, the wrong tool for the container strategy).**

**Tech Stack:** Python 3, `python-hwpx` (lxml-based OWPML model), PyMuPDF (`fitz`) for render geometry, `MacHancomOracle` (AppleScript → PDF) / `resolve_oracle` as the verdict source.

## Constitution Check (`.specify/memory/constitution.md` v1.1.0)

- **Dimension/tier (Principle X):** advances `form-fill-integrity` + `document-authoring` (co-top). This plan is the **engine composer**; the tier-moving oracle-clean demo `.hwpx` (the leap) lands in Plan 4. No scorecard change here — composer + smoke test only.
- **Oracle truth (IV) / Measure-first, no silent true (V):** the A_form body-region map is **measured from the real file** (Task 4 evidence receipt), never assumed. The convergence driver's `splits=0` claim REQUIRES `render_checked=true`; with no oracle it degrades to `render_checked=false` + `needs_review`, never a silent pass.
- **Lossless (VII):** 관리박스 para[0] and any preserved tail paragraphs round-trip byte-identical (deepcopy compare in tests); new paraPr are **appended** by `ensure_paragraph_format` — existing paraPr are never mutated.
- **Fail-closed (VI) / Honest reporting (IX):** unparseable md, a missing required form style, an ambiguous body paragraph, a lost/false-resolved placeholder, or a 문항 longer than one column → **raise / report**, never emit a silently wrong layout. `render_checked`, `needs_review`, `skipped` are first-class fields on the result.
- **Clean-Room (VIII):** vendored fixtures (A_form / B_submitted) carry a `NOTICE.md` (Task 3); no external code is copied.

## Global Constraints

- python-hwpx **public API only** for the composer; the one section-level method we use that is not on `HwpxDocument` is `HwpxOxmlSection.insert_paragraphs` / `copy_paragraph_range`, reached via `doc.sections[i]` (each is an `HwpxOxmlSection`). No private `_`-prefixed access.
- New paraPr is appended via `ensure_paragraph_format`; existing paraPr/style definitions are never edited in place (Lossless VII).
- The composer **INSERTS** composed paragraphs into the body region; it MUST NOT append paragraphs after the form's tail (Phase-0 finding: Hancom silently drops appended content in the real form).
- Numbering and `①②③④⑤` are **literal text** (the form does not auto-number these in the real exams) — the composer emits literal markers.
- Mac Hancom oracle runs are GUI-automation gated: require `HWPX_MAC_ORACLE_SMOKE=1` and `dangerouslyDisableSandbox` at call time; absence ⇒ `render_checked=false`, never a silent pass.
- Tests run green in `python-hwpx` via `.venv/bin/python -m pytest -q`. Oracle smoke tests are `@pytest.mark.skipif(not (mac+Hancom+HWPX_MAC_ORACLE_SMOKE))` so CI without an oracle stays green.
- Wily: this plan is stage **S-056** (STG-a47dede4fa57), branch **`feat/s056-exam-typesetting`**, phase **PH-c1ee1bf83fee** ("조판기 — Exam IR + 출제 md→IR + 양식 본문 조판 (Plan2)"). Plan-2 base HEAD: `0fc7827` (after Plan 1's Task 4 spike; `bd36cdd` was Plan 1's base).

## Verified consumed signatures (from Plan-1 + engine, file:line)

```
# engine primitives (Plan 1, shipped)
HwpxOxmlHeader.ensure_paragraph_format(*, base_para_pr_id=None, alignment=None,
    line_spacing_percent=None, margins=None, heading=None, border=None,
    break_setting: Mapping[str,bool]|None=None) -> str           # _document_impl.py:5282
    # break_setting keys: keep_with_next / keep_lines / page_break_before / widow_orphan
    #   -> attrs keepWithNext/keepLines/pageBreakBefore/widowOrphan = "1"/"0"; returns NEW paraPr id
from hwpx.visual.oracle import Block, BlockSplit, detect_block_splits, WordBox  # oracle.py:461-523
    Block(id: str, glyphs: list)               # one 문항/answer unit's glyphs
    BlockSplit(block_id: str, kind: str)       # kind in {"column","page"}
    detect_block_splits(blocks, column_x_bounds: list[tuple[float,float]], page_height: float) -> list[BlockSplit]
    WordBox(x0,y0,x1,y1,text,page=0,block=-1,line=-1,word_no=-1)  # form_fit/wordbox.py:114 (frozen,slots)

# document / section / paragraph (public + section-level)
HwpxDocument.open(path) ; .save_to_path(path) ; .sections -> list[HwpxOxmlSection]   # document.py:325,2656,429
HwpxDocument.oxml.headers -> list[HwpxOxmlHeader]                                     # _document_impl.py:5975
HwpxDocument.styles -> dict[str,Style] ; .style(id) ; .paragraph_property(id) ; .char_property(id)  # document.py:527,532,509,805
HwpxDocument.paragraphs -> list[HwpxOxmlParagraph] ; .remove_paragraph(para|int, *, section=None, section_index=None)  # document.py:795,756
Style(id:int|None, raw_id, type:str|None, name:str|None, eng_name, para_pr_id_ref:int|None, char_pr_id_ref:int|None, ...)  # header.py:438
HwpxOxmlSection.paragraphs -> list[HwpxOxmlParagraph]                                 # _document_impl.py:4486
HwpxOxmlSection.add_paragraph(text="", *, para_pr_id_ref=None, style_id_ref=None,
    char_pr_id_ref=None, run_attributes=None, include_run=True, inherit_style=True, **extra_attrs) -> HwpxOxmlParagraph  # :4549  (APPENDS to section tail)
HwpxOxmlSection.insert_paragraphs(index:int, paragraphs:Sequence[HwpxOxmlParagraph|ET.Element]) -> list[HwpxOxmlParagraph]  # :4618 (deep-clones into place)
HwpxOxmlSection.remove_paragraph(paragraph:HwpxOxmlParagraph|int) ; .copy_paragraph_range(start,end) -> list[ET.Element] ; .mark_dirty()  # :4532,:4640,:4649
HwpxOxmlParagraph.para_pr_id_ref (get/set) ; .style_id_ref (get/set) ; .char_pr_id_ref (get/set) ; .text (get/set) ; .element  # :4271,:4289,:4307

# oracle / geometry
from hwpx.visual.oracle import MacHancomOracle, NullOracle, resolve_oracle  # oracle.py:197,312,326
    MacHancomOracle().available() -> bool ; .render_pdf(hwpx_path, out_pdf=None) -> str|None  # :250,:257
from hwpx.form_fit.wordbox import render_form_geometry, extract_glyph_boxes, detect_overflow  # wordbox.py:752,230,398
    extract_glyph_boxes(pdf_path, *, page=None) -> list[WordBox]
    render_form_geometry(hwpx_path, *, oracle=None, page=None) -> tuple[list[WordBox], list[Rect], list[tuple[float,float]], str]

# house utility
from hwpx.tools.table_cleanup import normalize_cell_text   # table_cleanup.py:12 -> collapses \r?\n + spaces
```

## File Structure

```
python-hwpx/src/hwpx/exam/                  ← NEW package (greenfield; src/hwpx/exam/ does not exist)
  __init__.py        public exports (ExamDoc, parse_exam_markdown, profile_form, compose_exam_into_form, ...)
  ir.py              Exam IR dataclasses (Task 1)
  parser.py          parse_exam_markdown + ExamParseError (Task 2)
  profile.py         FormProfile + profile_form + FormProfileError (Task 5)
  measure.py         column_x_bounds + group_question_blocks + measure_question_splits + SplitReport (Task 6)
  compose.py         lowering (IR -> styled paragraphs) + replace_body_region + compose_exam_into_form + ComposeResult (Tasks 7-8)
python-hwpx/scripts/exam_profile_a_form.py  ← measure-first A_form body-region probe (Task 4)
python-hwpx/tests/fixtures/exam/            ← vendored: A_form.hwpx, B_submitted.hwpx, sample_exam.md, NOTICE.md (Task 3)
python-hwpx/tests/test_exam_ir.py           (Task 1)
python-hwpx/tests/test_exam_parser.py       (Task 2)
python-hwpx/tests/test_exam_fixtures.py     (Task 3)
python-hwpx/tests/test_exam_profile.py      (Task 5)
python-hwpx/tests/test_exam_measure.py      (Task 6)
python-hwpx/tests/test_exam_compose.py      (Task 7)
python-hwpx/tests/test_exam_compose_oracle.py (Task 8, smoke-gated)
python-hwpx/examples/compose_exam.py        (Task 9)
specs/003-exam-typesetting/evidence/a-form-body-map.json   ← Task 4 evidence receipt (harness layer)
```

## Scope decisions (read before executing)

- **Composer = engine, not orchestration.** The role→style *mapping table* and the per-form judgment live in the skill (Plan 4). This plan ships the mechanism: given a role→style map and a form, lower the IR and produce a verified-clean `.hwpx`. The composer exposes a sane **default** role→style map for forms A/B (derived from the form's own style names) and accepts an override.
- **B_submitted golden = render baseline, not reverse-IR.** The spec's "extract B → IR → recompose → match B" is satisfied for v1 by the **forward** oracle gate: compose a committed authored `sample_exam.md` into A_form and assert splits=0 / overflow=0 / placeholders intact / clean open (Task 8). B_submitted is vendored and used as (a) a structural cross-check that the profiler resolves the same styles a real filled instance uses (Task 5) and (b) a page-count sanity baseline. **Full reverse HWPX→IR extraction is deferred (v1 non-goal)** — it is a separate substantial parser whose only purpose is a testing convenience; the leap value is forward composition, validated directly by the oracle. Rationale logged per Governance (simpler compliant alternative: the forward gate proves the same property). *If the owner wants the full reverse-golden, it becomes Plan 2.5.*
- **Convergence driver lives here (engine), MCP wrapper in Plan 3, leap demo in Plan 4.** Task 8 ships `compose_exam_into_form(...)` (render→measure→break-insert→re-render, ≤`max_rounds`). Plan 3 wraps it as an MCP tool; Plan 4 runs it for the demo and claims the tier.

---

### Task 1: Exam IR — `src/hwpx/exam/ir.py`

**Files:**
- Create: `python-hwpx/src/hwpx/exam/__init__.py`
- Create: `python-hwpx/src/hwpx/exam/ir.py`
- Test: `python-hwpx/tests/test_exam_ir.py`

**Interfaces:**
- Consumes: nothing (greenfield).
- Produces (later tasks rely on these exact names/types):
  - `@dataclass(frozen=True, slots=True) Placeholder(id: str, kind: str, raw_text: str)` — `kind ∈ {"img","table","equation"}`.
  - `@dataclass(frozen=True, slots=True) Question(number: str, stem: str, choices: tuple[str,...]=(), points: str|None=None, placeholders: tuple[Placeholder,...]=())`.
  - `@dataclass(frozen=True, slots=True) QuestionSet(passage: str, rng: str, members: tuple[Question,...]=())`.
  - `@dataclass(frozen=True, slots=True) ExamDoc(title: str="", blocks: tuple[Question|QuestionSet,...]=())` with `iter_questions() -> Iterator[Question]` (flattens sets).

- [ ] **Step 1: Write the failing test**

```python
# python-hwpx/tests/test_exam_ir.py
from hwpx.exam import ir


def test_iter_questions_flattens_sets_in_order():
    q1 = ir.Question(number="1", stem="발문1")
    q3 = ir.Question(number="3", stem="발문3")
    q4 = ir.Question(number="4", stem="발문4")
    qset = ir.QuestionSet(passage="공통지문", rng="3∼4", members=(q3, q4))
    doc = ir.ExamDoc(title="중간고사", blocks=(q1, qset))
    assert [q.number for q in doc.iter_questions()] == ["1", "3", "4"]


def test_question_is_frozen_and_carries_choices_points_placeholders():
    ph = ir.Placeholder(id="그림1", kind="img", raw_text="[그림1]")
    q = ir.Question(number="2", stem="발문", choices=("① 가", "② 나"), points="3", placeholders=(ph,))
    assert q.points == "3" and q.choices[0] == "① 가" and q.placeholders[0].kind == "img"
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.points = "5"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_ir.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.exam'`.

- [ ] **Step 3: Write minimal implementation**

```python
# python-hwpx/src/hwpx/exam/__init__.py
"""Exam re-typesetting (조판): authored exam Markdown -> school form .hwpx body."""
from __future__ import annotations

from .ir import ExamDoc, Placeholder, Question, QuestionSet

__all__ = ["ExamDoc", "Placeholder", "Question", "QuestionSet"]
```

```python
# python-hwpx/src/hwpx/exam/ir.py
"""Normalized exam model (Exam IR). Metadata lives in the form's 관리박스, NOT here."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Placeholder:
    id: str           # e.g. "그림1"
    kind: str         # "img" | "table" | "equation"
    raw_text: str     # literal marker preserved verbatim, e.g. "[그림1]"


@dataclass(frozen=True, slots=True)
class Question:
    number: str                                  # literal 문항 number text, e.g. "1"
    stem: str                                    # 발문
    choices: tuple[str, ...] = ()                # 답항 ①~⑤, literal markers included
    points: str | None = None                    # 배점, e.g. "3"; None if absent
    placeholders: tuple[Placeholder, ...] = ()   # [그림N]/[표N]/[식N] referenced by this 문항


@dataclass(frozen=True, slots=True)
class QuestionSet:                               # 세트문제 (shared 공통지문)
    passage: str
    rng: str                                     # e.g. "3∼4"
    members: tuple[Question, ...] = ()


@dataclass(frozen=True, slots=True)
class ExamDoc:
    title: str = ""
    blocks: tuple[Question | QuestionSet, ...] = ()

    def iter_questions(self) -> Iterator[Question]:
        for block in self.blocks:
            if isinstance(block, QuestionSet):
                yield from block.members
            else:
                yield block
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_ir.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd python-hwpx
git add src/hwpx/exam/__init__.py src/hwpx/exam/ir.py tests/test_exam_ir.py
git commit -m "feat(exam): Exam IR dataclasses (Question/QuestionSet/Placeholder/ExamDoc)"
```

---

### Task 2: md→IR parser — `src/hwpx/exam/parser.py`

**Files:**
- Create: `python-hwpx/src/hwpx/exam/parser.py`
- Modify: `python-hwpx/src/hwpx/exam/__init__.py` (export `parse_exam_markdown`, `ExamParseError`)
- Test: `python-hwpx/tests/test_exam_parser.py`

**Interfaces:**
- Consumes: `ir.*` (Task 1); `hwpx.tools.table_cleanup.normalize_cell_text` (`table_cleanup.py:12`).
- Produces: `parse_exam_markdown(md: str, *, title: str = "") -> ExamDoc`; `class ExamParseError(ValueError)` carrying `line_no: int` and `text: str`.

**The recommended exam-md convention** (the skill authors AND parses it, so it is strict, not adversarial):

```
# 2026학년도 2학년 정보 중간고사       ← optional H1 title (first H1 before any 문항)

## 1. (3점)                           ← standalone 문항: "## <number>. [(<points>점)]"
다음 설명으로 옳은 것은?               ← 발문 (1+ lines until a choice/placeholder/next header)
① 첫 번째 보기
② 두 번째 보기
③ 세 번째 보기
④ 네 번째 보기
⑤ 다섯 번째 보기

## 2. (4점)
[그림1]                               ← standalone placeholder line (also allowed inside stem text)
주어진 그림을 보고 물음에 답하시오.
① ... ⑤ ...

## 3∼4. 세트                          ← set header: "## <a>[∼~]<b>. 세트"
다음 글을 읽고 물음에 답하시오. (공통지문 …)   ← passage lines until first "### " member
### 3. (2점)
발문 …
① ... ⑤ ...
### 4.
발문 …
① ... ⑤ ...
```

- [ ] **Step 1: Write the failing test**

```python
# python-hwpx/tests/test_exam_parser.py
import pytest

from hwpx.exam import ExamDoc, Question, QuestionSet
from hwpx.exam.parser import ExamParseError, parse_exam_markdown

SAMPLE = """# 중간고사

## 1. (3점)
다음 설명으로 옳은 것은?
① 가
② 나
③ 다
④ 라
⑤ 마

## 2.
[그림1]
그림을 보고 답하시오.
① 하나
② 둘

## 3∼4. 세트
다음 글을 읽고 물음에 답하시오.
### 3. (2점)
발문 셋
① 가
② 나
### 4.
발문 넷
① 가
② 나
"""


def test_parses_title_questions_set_points_choices_placeholder():
    doc = parse_exam_markdown(SAMPLE)
    assert isinstance(doc, ExamDoc)
    assert doc.title == "중간고사"
    assert len(doc.blocks) == 3  # Q1, Q2, set(3∼4)

    q1 = doc.blocks[0]
    assert isinstance(q1, Question) and q1.number == "1" and q1.points == "3"
    assert q1.stem == "다음 설명으로 옳은 것은?"
    assert q1.choices == ("① 가", "② 나", "③ 다", "④ 라", "⑤ 마")

    q2 = doc.blocks[1]
    assert q2.number == "2" and q2.points is None
    assert q2.placeholders[0].id == "그림1" and q2.placeholders[0].kind == "img"

    qset = doc.blocks[2]
    assert isinstance(qset, QuestionSet) and qset.rng == "3∼4"
    assert qset.passage == "다음 글을 읽고 물음에 답하시오."
    assert [m.number for m in qset.members] == ["3", "4"]
    assert qset.members[0].points == "2"

    # flatten reaches every 문항 in order
    assert [q.number for q in doc.iter_questions()] == ["1", "2", "3", "4"]


def test_content_before_any_question_header_fails_loud():
    with pytest.raises(ExamParseError) as exc:
        parse_exam_markdown("본문이 문항 헤더 없이 먼저 나온다.\n## 1.\n발문\n")
    assert exc.value.line_no == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.exam.parser'`.

- [ ] **Step 3: Write minimal implementation**

```python
# python-hwpx/src/hwpx/exam/parser.py
"""Parse the recommended exam-md convention into the Exam IR.

The skill authors this md, so the grammar is strict and any unattributable
line fails loud (Constitution VI/IX — no silently wrong layout)."""
from __future__ import annotations

import re

from hwpx.tools.table_cleanup import normalize_cell_text

from .ir import ExamDoc, Placeholder, Question, QuestionSet

_TITLE_RE = re.compile(r"^#\s+(?P<t>.*\S)\s*$")
_Q_RE = re.compile(r"^##\s+(?P<n>\d+)\.\s*(?:\((?P<p>\d+)\s*점\))?\s*$")
_SET_RE = re.compile(r"^##\s+(?P<a>\d+)\s*[~∼-]\s*(?P<b>\d+)\.\s*세트\s*$")
_MEMBER_RE = re.compile(r"^###\s+(?P<n>\d+)\.\s*(?:\((?P<p>\d+)\s*점\))?\s*$")
_CHOICE_RE = re.compile(r"^\s*(?P<mark>[①②③④⑤⑥⑦⑧⑨⑩])\s*(?P<t>.*)$")
_PLACEHOLDER_RE = re.compile(r"\[(?P<k>그림|표|식)\s*(?P<n>\d+)\]")

_KIND = {"그림": "img", "표": "table", "식": "equation"}


class ExamParseError(ValueError):
    def __init__(self, line_no: int, text: str, reason: str) -> None:
        super().__init__(f"line {line_no}: {reason}: {text!r}")
        self.line_no = line_no
        self.text = text
        self.reason = reason


class _QBuf:
    """Accumulates one 문항 across lines, then freezes to a Question."""

    def __init__(self, number: str, points: str | None) -> None:
        self.number = number
        self.points = points
        self.stem_lines: list[str] = []
        self.choices: list[str] = []
        self.placeholders: list[Placeholder] = []

    def add_text(self, text: str) -> None:
        for m in _PLACEHOLDER_RE.finditer(text):
            pid = f"{m.group('k')}{m.group('n')}"
            self.placeholders.append(Placeholder(id=pid, kind=_KIND[m.group("k")], raw_text=m.group(0)))
        self.stem_lines.append(text)

    def add_choice(self, mark: str, text: str) -> None:
        self.choices.append(f"{mark} {text}".rstrip())

    def freeze(self) -> Question:
        return Question(
            number=self.number,
            stem=normalize_cell_text(" ".join(self.stem_lines)),
            choices=tuple(self.choices),
            points=self.points,
            placeholders=tuple(self.placeholders),
        )


def parse_exam_markdown(md: str, *, title: str = "") -> ExamDoc:
    blocks: list[Question | QuestionSet] = []
    cur_q: _QBuf | None = None
    set_open = False
    set_rng = ""
    set_passage: list[str] = []
    set_members: list[Question] = []

    def flush_q() -> None:
        nonlocal cur_q
        if cur_q is None:
            return
        q = cur_q.freeze()
        if set_open:
            set_members.append(q)
        else:
            blocks.append(q)
        cur_q = None

    def flush_set() -> None:
        nonlocal set_open, set_rng, set_passage, set_members
        if not set_open:
            return
        blocks.append(
            QuestionSet(
                passage=normalize_cell_text(" ".join(set_passage)),
                rng=set_rng,
                members=tuple(set_members),
            )
        )
        set_open, set_rng, set_passage, set_members = False, "", [], []

    for i, raw in enumerate(md.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue

        m_set = _SET_RE.match(line)
        if m_set:
            flush_q()
            flush_set()
            set_open = True
            set_rng = f"{m_set.group('a')}∼{m_set.group('b')}"
            continue

        m_member = _MEMBER_RE.match(line)
        if m_member:
            if not set_open:
                raise ExamParseError(i, line, "'### N.' member outside a 세트 header")
            flush_q()
            cur_q = _QBuf(m_member.group("n"), m_member.group("p"))
            continue

        m_q = _Q_RE.match(line)
        if m_q:
            flush_q()
            flush_set()
            cur_q = _QBuf(m_q.group("n"), m_q.group("p"))
            continue

        m_title = _TITLE_RE.match(line)
        if m_title and not blocks and cur_q is None and not set_open:
            title = title or normalize_cell_text(m_title.group("t"))
            continue

        m_choice = _CHOICE_RE.match(line)
        if m_choice and cur_q is not None:
            cur_q.add_choice(m_choice.group("mark"), normalize_cell_text(m_choice.group("t")))
            continue

        # plain content line: belongs to the current 문항 stem, or the set passage
        if cur_q is not None:
            cur_q.add_text(line.strip())
        elif set_open:
            set_passage.append(line.strip())
        else:
            raise ExamParseError(i, line, "content before any 문항 / 세트 header")

    flush_q()
    flush_set()
    return ExamDoc(title=title, blocks=tuple(blocks))
```

Then export from `__init__.py`:

```python
# python-hwpx/src/hwpx/exam/__init__.py  (extend)
from .ir import ExamDoc, Placeholder, Question, QuestionSet
from .parser import ExamParseError, parse_exam_markdown

__all__ = [
    "ExamDoc", "Placeholder", "Question", "QuestionSet",
    "ExamParseError", "parse_exam_markdown",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_parser.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite (no regressions), then commit**

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/exam/parser.py src/hwpx/exam/__init__.py tests/test_exam_parser.py
git commit -m "feat(exam): exam-md -> Exam IR parser (strict convention, fail-loud)"
```

---

### Task 3: Vendor exam fixtures + provenance — `tests/fixtures/exam/`

**Files:**
- Create (copy from NAS): `python-hwpx/tests/fixtures/exam/A_form.hwpx`, `python-hwpx/tests/fixtures/exam/B_submitted.hwpx`
- Create: `python-hwpx/tests/fixtures/exam/sample_exam.md` (a realistic authored exam used by Tasks 8/9)
- Create: `python-hwpx/tests/fixtures/exam/NOTICE.md` (clean-room provenance, mirroring `tests/fixtures/m2_corpus/NOTICE.md`)
- Test: `python-hwpx/tests/test_exam_fixtures.py`

**Interfaces:**
- Consumes: NAS source `/Volumes/airbot/OpenClaw/incoming/시험지/` (mounted at authoring time). The vendored copies are the durable truth; the NAS is not a runtime dependency.
- Produces: openable fixtures + a parseable `sample_exam.md`.

- [ ] **Step 1: Copy the real form + submitted exam from the NAS**

```bash
cd python-hwpx && mkdir -p tests/fixtures/exam
cp "/Volumes/airbot/OpenClaw/incoming/시험지/(1) 2026학년도 원안지_양식.hwpx" tests/fixtures/exam/A_form.hwpx
cp "/Volumes/airbot/OpenClaw/incoming/시험지/(1) 2026학년도 원안지_2학년_정보_제출본.hwpx" tests/fixtures/exam/B_submitted.hwpx
ls -la tests/fixtures/exam/
```
Expected: `A_form.hwpx` (~457 KB) and `B_submitted.hwpx` (~80 KB) present. If the NAS is not mounted, STOP and report — these are required golden inputs.

- [ ] **Step 2: Author `tests/fixtures/exam/sample_exam.md`**

Write a realistic exam in the Task-2 convention: a title, **≥12 standalone 문항** (mix of 배점 present/absent), **one 세트문제 (e.g. `## 7∼8. 세트`)** with a multi-line 공통지문 and 2 members, and **≥2 placeholders** (`[그림1]`, `[표1]`). Each 문항 = a 발문 of 1–3 lines + 4–5 답항 (`①…⑤`), long enough that stacking them in a 2-column B4 flow naturally pushes some 문항 onto column/page boundaries (so Task 8's gate is non-vacuous). Keep 답항 text free of any leading `"N."` digit-period pattern (it is the 문항-grouping marker — see Task 6).

- [ ] **Step 3: Write `tests/fixtures/exam/NOTICE.md`**

```markdown
# Exam-typesetting corpus — vendored real-world HWPX documents

These `.hwpx` files are **sample data vendored for testing** under the project's
clean-room policy (Constitution VIII). No source **code** is copied — only the
document files are vendored as oracle/regression inputs for exam re-typesetting
(S-056). Each remains the property of its author; if any rights holder objects,
the file will be removed.

| Local file | Provenance |
|---|---|
| `A_form.hwpx` | School 원안지 **양식** (blank form: 관리박스 + page setup + 머리글/꼬리글 + styles). Vendored 2026-06-26 from the owner's working corpus. |
| `B_submitted.hwpx` | A **제출본** (filled instance of the same form). Used as a structural cross-check + render baseline, never re-distributed. |

`sample_exam.md` is original authored test content (not vendored).
```

- [ ] **Step 4: Write the fixture sanity test**

```python
# python-hwpx/tests/test_exam_fixtures.py
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.exam.parser import parse_exam_markdown

FIX = Path(__file__).parent / "fixtures" / "exam"


def test_form_fixtures_open():
    for name in ("A_form.hwpx", "B_submitted.hwpx"):
        doc = HwpxDocument.open(FIX / name)
        assert len(doc.paragraphs) >= 1


def test_sample_exam_md_parses_with_a_set_and_placeholders():
    doc = parse_exam_markdown((FIX / "sample_exam.md").read_text(encoding="utf-8"))
    qs = list(doc.iter_questions())
    assert len(qs) >= 12
    assert any(b.__class__.__name__ == "QuestionSet" for b in doc.blocks)
    assert any(q.placeholders for q in qs)
```

- [ ] **Step 5: Run, then commit (fixtures + NOTICE + test)**

```bash
cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_fixtures.py -q
git add tests/fixtures/exam/A_form.hwpx tests/fixtures/exam/B_submitted.hwpx \
        tests/fixtures/exam/sample_exam.md tests/fixtures/exam/NOTICE.md tests/test_exam_fixtures.py
git commit -m "test(exam): vendor A_form/B_submitted fixtures + sample_exam.md + NOTICE (clean-room)"
```

---

### Task 4: Measure-first — characterize A_form's body region (evidence receipt)

**Files:**
- Create: `python-hwpx/scripts/exam_profile_a_form.py` (probe, not shipped surface)
- Create (output): `specs/003-exam-typesetting/evidence/a-form-body-map.json` + a recorded rule appended to `specs/003-exam-typesetting/spec.md` §"Composition detail — form profiling".

**Interfaces:**
- Consumes: `HwpxDocument.open`, `doc.paragraphs`, `HwpxOxmlParagraph.{text,style_id_ref}`, `doc.style(id)`; the A_form fixture (Task 3).
- Produces: the empirical map of A_form — for each section-0 paragraph: `{index, style_id, style_name, text_head}` — and the derived `{admin_box_index, body_start, body_end, footer_indices, replaceable_style_names, structural_indices}`. **This resolves the open A2 assumption** (the Phase-0 spike never characterized the real form — it used a clean B4 bed) and the critical question: **is the form's "footer" a body paragraph or a section header/footer (`<hp:ctrl>`) outside the paragraph stream?** The profiler (Task 5) and composer (Task 7) use whatever this measures.

> Per Constitution V this task's deliverable is an **evidence receipt**, not a unit-test pass.

- [ ] **Step 1: Write the probe**

```python
# python-hwpx/scripts/exam_profile_a_form.py
# SPDX-License-Identifier: Apache-2.0
"""Measure-first probe (S-056 Plan 2): characterize A_form's body region.

Prints, for section 0 of the school form, every paragraph's (index, style id,
style name, text head); then derives the replaceable body range vs the
관리박스 / structural / footer paragraphs and writes an evidence receipt.
No assumptions — the composer's body-region rule is grounded by THIS output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hwpx.document import HwpxDocument  # noqa: E402

# Style names the form uses for replaceable question/answer body content
# (recon, identical in A and B). Anything else in the body is structural.
REPLACEABLE_NAMES = {
    "바탕글", "문항자동번호넣기",
    "1행답항", "2행답항", "3행답항", "5행답항",
    "(보기)박스안내용", "박스안내용",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--form", default="tests/fixtures/exam/A_form.hwpx")
    ap.add_argument("--receipt", default="../specs/003-exam-typesetting/evidence/a-form-body-map.json")
    args = ap.parse_args(argv)

    doc = HwpxDocument.open(args.form)
    section = doc.sections[0]
    rows = []
    for idx, para in enumerate(section.paragraphs):
        sid = para.style_id_ref
        style = doc.style(sid) if sid is not None else None
        name = style.name if style else None
        rows.append(
            {
                "index": idx,
                "style_id": sid,
                "style_name": name,
                "text_head": (para.text or "")[:40],
            }
        )

    repl = [r["index"] for r in rows if r["style_name"] in REPLACEABLE_NAMES]
    body_start = min(repl) if repl else None
    body_end = max(repl) if repl else None
    structural = [
        r["index"]
        for r in rows
        if body_start is not None and body_start <= r["index"] <= body_end
        and r["style_name"] not in REPLACEABLE_NAMES
    ]
    receipt = {
        "form": args.form,
        "n_sections": len(doc.sections),
        "n_paragraphs_section0": len(rows),
        "admin_box_index": 0,
        "body_start": body_start,
        "body_end": body_end,
        "footer_indices": [r["index"] for r in rows if body_end is not None and r["index"] > body_end],
        "structural_indices_in_body": structural,
        "replaceable_style_names": sorted(REPLACEABLE_NAMES),
        "paragraphs": rows,
    }
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in receipt if k != "paragraphs"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the probe and read the map**

Run: `cd python-hwpx && .venv/bin/python scripts/exam_profile_a_form.py`
Expected: a JSON summary printed and `specs/003-exam-typesetting/evidence/a-form-body-map.json` written. **Inspect it:** confirm `admin_box_index=0`, note the real `body_start`/`body_end`/`footer_indices`, and whether any `structural_indices_in_body` exist (e.g. a 논술형 header). If `footer_indices` is empty, the form's footer is a section header/footer (outside the paragraph stream) → the composer simply replaces `[body_start..body_end]` and the footer is preserved automatically.

- [ ] **Step 3: Record the rule in the spec, commit the probe**

Append to `specs/003-exam-typesetting/spec.md` §"Composition detail — form profiling" a 2–3 line **measured** result: A_form section count, `admin_box_index`, `body_start..body_end`, footer location (body paras vs section ctrl), and any structural-in-body indices. This is the rule Task 5/7 encode.

```bash
cd python-hwpx
git add scripts/exam_profile_a_form.py
git commit -m "feat(exam): measure-first A_form body-region probe + evidence receipt"
```
(The receipt under `specs/003-exam-typesetting/evidence/` lives in the harness layer, not git — reference it from the spec.)

---

### Task 5: Form profiler — `src/hwpx/exam/profile.py`

**Files:**
- Create: `python-hwpx/src/hwpx/exam/profile.py`
- Modify: `python-hwpx/src/hwpx/exam/__init__.py` (export `FormProfile`, `profile_form`, `FormProfileError`, `ResolvedStyle`)
- Test: `python-hwpx/tests/test_exam_profile.py`

**Interfaces:**
- Consumes: `HwpxDocument.styles` (`dict[str,Style]`), `Style.{id,name,para_pr_id_ref,char_pr_id_ref,type}`, `doc.sections[0].paragraphs`, `HwpxOxmlParagraph.style_id_ref`; the Task-4 measured rule; A_form/B_submitted fixtures.
- Produces:
  - `@dataclass(frozen=True, slots=True) ResolvedStyle(name: str, style_id: str, para_pr_id: str|None, char_pr_id: str|None)`.
  - `@dataclass(frozen=True, slots=True) FormProfile(role_styles: dict[str,ResolvedStyle], admin_box_index: int, body_start: int, body_end: int, replaceable_indices: tuple[int,...], structural_indices: tuple[int,...], ambiguous_indices: tuple[int,...])`.
  - `profile_form(doc: HwpxDocument, *, role_style_names: Mapping[str,str]|None=None) -> FormProfile` — resolves required form styles by **name** (there is no `style_by_name` API; iterate `doc.styles.values()`), **delimits the body region by the question/answer styles only** (per the Task-4 measurement: `바탕글` also clothes 관리박스 [0] and the footer tail, so only `문항자동번호넣기`/`N행답항`/`(보기)박스안내용`/`박스안내용` anchor the body → `body_start..body_end`; the full span is `replaceable_indices`, 관리박스 [0] and the `[body_end+1..]` footer/essay tail are preserved), and **raises `FormProfileError`** if a required role style is missing.
  - `class FormProfileError(ValueError)`.
- **Default role→style names** (forms A/B): `{"normal":"바탕글", "number":"문항자동번호넣기", "choice1":"1행답항", "choice2":"2행답항", "choice3":"3행답항", "choice5":"5행답항", "box_guide":"(보기)박스안내용", "box":"박스안내용"}`.

- [ ] **Step 1: Write the failing test (grounded by Task 4's measured map)**

```python
# python-hwpx/tests/test_exam_profile.py
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.exam.profile import FormProfileError, profile_form

FIX = Path(__file__).parent / "fixtures" / "exam"


def test_profile_resolves_required_styles_and_body_region():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    # required roles resolve to real style ids present in the form
    for role in ("normal", "number", "choice1", "choice5"):
        rs = profile.role_styles[role]
        assert rs.style_id is not None and rs.name
    assert profile.admin_box_index == 0
    # measured (scripts/exam_profile_a_form.py / evidence/a-form-body-map.json):
    # question/answer styles span [1..70]; 관리박스 [0] and the trailing 바탕글
    # footer/essay zone [71..100] are preserved, NOT in the body.
    assert profile.body_start == 1
    assert profile.body_end == 70
    assert profile.body_end < len(doc.sections[0].paragraphs) - 1  # footer not in body
    assert profile.replaceable_indices == tuple(range(1, 71))
    assert not profile.ambiguous_indices  # A_form is known/clean in v1


def test_same_styles_resolve_in_a_filled_instance():
    # B_submitted is a filled instance of the same form -> same role styles exist
    doc = HwpxDocument.open(FIX / "B_submitted.hwpx")
    profile = profile_form(doc)
    assert profile.role_styles["number"].name == "문항자동번호넣기"


def test_missing_required_style_fails_loud():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    with pytest.raises(FormProfileError):
        profile_form(doc, role_style_names={"number": "존재하지않는스타일"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.exam.profile'`.

- [ ] **Step 3: Write minimal implementation** (encode the Task-4 measured rule)

```python
# python-hwpx/src/hwpx/exam/profile.py
"""Profile a school form: resolve role->style and classify the body region.

Grounded by the measure-first A_form probe (scripts/exam_profile_a_form.py).
No style-by-name API exists, so we build a name->Style index ourselves."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hwpx.document import HwpxDocument

DEFAULT_ROLE_STYLE_NAMES: dict[str, str] = {
    "normal": "바탕글",
    "number": "문항자동번호넣기",
    "choice1": "1행답항",
    "choice2": "2행답항",
    "choice3": "3행답항",
    "choice5": "5행답항",
    "box_guide": "(보기)박스안내용",
    "box": "박스안내용",
}
# Roles that MUST exist for composition (others are optional conveniences).
REQUIRED_ROLES = ("normal", "number", "choice1", "choice5")


class FormProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedStyle:
    name: str
    style_id: str
    para_pr_id: str | None
    char_pr_id: str | None


@dataclass(frozen=True, slots=True)
class FormProfile:
    role_styles: dict[str, ResolvedStyle]
    admin_box_index: int
    body_start: int
    body_end: int
    replaceable_indices: tuple[int, ...]
    structural_indices: tuple[int, ...]
    ambiguous_indices: tuple[int, ...]


def _name_index(doc: HwpxDocument) -> dict[str, "object"]:
    index: dict[str, object] = {}
    for style in doc.styles.values():
        if style.name:
            index.setdefault(style.name, style)
    return index


def profile_form(
    doc: HwpxDocument,
    *,
    role_style_names: Mapping[str, str] | None = None,
) -> FormProfile:
    names = dict(DEFAULT_ROLE_STYLE_NAMES)
    if role_style_names:
        names.update(role_style_names)

    by_name = _name_index(doc)
    role_styles: dict[str, ResolvedStyle] = {}
    for role, style_name in names.items():
        style = by_name.get(style_name)
        if style is None:
            if role in REQUIRED_ROLES:
                raise FormProfileError(
                    f"required role '{role}' style {style_name!r} not found in form"
                )
            continue
        role_styles[role] = ResolvedStyle(
            name=style_name,
            style_id=str(style.id if style.id is not None else style.raw_id),
            para_pr_id=None if style.para_pr_id_ref is None else str(style.para_pr_id_ref),
            char_pr_id=None if style.char_pr_id_ref is None else str(style.char_pr_id_ref),
        )

    # Anchor the body region on the QUESTION/ANSWER styles ONLY. 바탕글(normal)
    # also clothes the 관리박스 [0] and the trailing footer/essay zone, so it
    # cannot delimit the body (measured: A_form [0] and [71..100] are all 바탕글;
    # the question/answer slots span [1..70], footer marker sits at [99]).
    anchor_names = {rs.name for role, rs in role_styles.items() if role != "normal"}
    section = doc.sections[0]
    paragraphs = section.paragraphs

    anchors: list[int] = []
    for idx, para in enumerate(paragraphs):
        if idx == 0:  # 관리박스 (never replaceable)
            continue
        sid = para.style_id_ref
        style = doc.style(sid) if sid is not None else None
        if style is not None and style.name in anchor_names:
            anchors.append(idx)

    if not anchors:
        raise FormProfileError("no question/answer-style body paragraphs found (form profile failed)")

    body_start, body_end = anchors[0], anchors[-1]
    # The whole [body_start..body_end] span is recomposed from the exam IR
    # (inline 바탕글 lines + 논술형 scaffolding within it included); 관리박스 [0]
    # and the tail [body_end+1..] (footer / essay answer space) are preserved.
    return FormProfile(
        role_styles=role_styles,
        admin_box_index=0,
        body_start=body_start,
        body_end=body_end,
        replaceable_indices=tuple(range(body_start, body_end + 1)),
        structural_indices=(),
        ambiguous_indices=(),  # v1: the body span is recomposed wholesale from the IR
    )
```

Export from `__init__.py`:

```python
from .profile import FormProfile, FormProfileError, ResolvedStyle, profile_form
# add to __all__: "FormProfile", "FormProfileError", "ResolvedStyle", "profile_form"
```

- [ ] **Step 4: Run test to verify it passes** (adjust the asserted role names only if the Task-4 map showed different style names)

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_profile.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Full suite, then commit**

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/exam/profile.py src/hwpx/exam/__init__.py tests/test_exam_profile.py
git commit -m "feat(exam): form profiler (role->style resolve + body-region classify, fail-loud)"
```

---

### Task 6: Measure helpers — `src/hwpx/exam/measure.py` (extract + DRY the spike)

**Files:**
- Create: `python-hwpx/src/hwpx/exam/measure.py`
- Modify: `python-hwpx/scripts/exam_spike_keep_together.py` (replace its local `_column_x_bounds`/`_group_blocks`/`_measure_splits` with imports — DRY; the spike must stay runnable)
- Modify: `python-hwpx/src/hwpx/exam/__init__.py` (export `column_x_bounds`, `group_question_blocks`, `measure_question_splits`, `SplitReport`)
- Test: `python-hwpx/tests/test_exam_measure.py`

**Interfaces:**
- Consumes: `from hwpx.visual.oracle import Block, detect_block_splits`; `from hwpx.form_fit.wordbox import extract_glyph_boxes`; `WordBox` (`.x0,.x1,.y0,.y1,.text,.page,.block,.line`).
- Produces:
  - `column_x_bounds(glyphs) -> list[tuple[float,float]]` — 2 column x-ranges by mid-gutter split (lifted verbatim from spike `_column_x_bounds`, `exam_spike_keep_together.py:187`).
  - `DEFAULT_QUESTION_MARKER = re.compile(r"^\s*(\d+)\s*\.")` — a body 문항 starts with its literal number + period (the composer emits this).
  - `group_question_blocks(glyphs, *, marker_re=DEFAULT_QUESTION_MARKER) -> list[Block]` — reading-order line grouping sliced on `marker_re` (generalized from spike `_group_blocks`, `:209`; the spike passes its own `[[QNN]]` regex).
  - `@dataclass(frozen=True, slots=True) SplitReport(n_splits:int, n_blocks:int, n_glyphs:int, kinds:dict[str,int], split_ids:tuple[str,...])`.
  - `measure_question_splits(pdf_path, *, marker_re=DEFAULT_QUESTION_MARKER) -> SplitReport` (generalized from spike `_measure_splits`, `:285`).

- [ ] **Step 1: Write the failing test (synthetic glyphs — deterministic, no oracle)**

```python
# python-hwpx/tests/test_exam_measure.py
import re

from hwpx.visual.oracle import WordBox
from hwpx.exam.measure import column_x_bounds, group_question_blocks


def _g(text, x, y, page=0, line=0):
    return WordBox(x0=x, y0=y, x1=x + 8, y1=y + 12, text=text, page=page, block=0, line=line, word_no=0)


def test_column_x_bounds_splits_left_right_at_gutter():
    glyphs = [_g("가", 10, 10), _g("나", 20, 10), _g("다", 330, 10), _g("라", 340, 10)]
    bounds = column_x_bounds(glyphs)
    assert len(bounds) == 2
    assert bounds[0][1] < bounds[1][0]  # left max-x < right min-x


def test_group_question_blocks_slices_on_number_marker():
    # line 0: "1." marker ; line 1: choice ; line 2: "2." marker
    glyphs = [
        _g("1", 10, 10, line=0), _g(".", 18, 10, line=0),
        _g("①", 10, 30, line=1), _g("가", 18, 30, line=1),
        _g("2", 10, 50, line=2), _g(".", 18, 50, line=2),
    ]
    blocks = group_question_blocks(glyphs)
    assert [b.id for b in blocks] == ["1", "2"]
    assert len(blocks[0].glyphs) == 4  # "1." + choice line belong to Q1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_measure.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.exam.measure'`.

- [ ] **Step 3: Write `measure.py`** (lift the spike's pure helpers; parameterize the marker; `block id = captured group 1`)

```python
# python-hwpx/src/hwpx/exam/measure.py
"""Pure render-geometry helpers for the 문항-split oracle gate.

Lifted from the Phase-0 spike (scripts/exam_spike_keep_together.py) so the
composer's gate and the spike share ONE implementation (DRY)."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from hwpx.form_fit.wordbox import extract_glyph_boxes
from hwpx.visual.oracle import Block, detect_block_splits

DEFAULT_QUESTION_MARKER = re.compile(r"^\s*(\d+)\s*\.")


def column_x_bounds(glyphs) -> list[tuple[float, float]]:
    if not glyphs:
        return []
    xs0 = min(g.x0 for g in glyphs)
    xs1 = max(g.x1 for g in glyphs)
    mid = (xs0 + xs1) / 2.0
    left = [g for g in glyphs if (g.x0 + g.x1) / 2.0 < mid]
    right = [g for g in glyphs if (g.x0 + g.x1) / 2.0 >= mid]
    bounds: list[tuple[float, float]] = []
    if left:
        bounds.append((min(g.x0 for g in left), max(g.x1 for g in left)))
    if right:
        bounds.append((min(g.x0 for g in right), max(g.x1 for g in right)))
    return bounds


def group_question_blocks(glyphs, *, marker_re: re.Pattern = DEFAULT_QUESTION_MARKER) -> list[Block]:
    if not glyphs:
        return []
    line_key = lambda g: (g.page, g.block, g.line)
    lines: dict[tuple, list] = defaultdict(list)
    for g in glyphs:
        lines[line_key(g)].append(g)

    records = []
    for gl in lines.values():
        gl_sorted = sorted(gl, key=lambda g: g.x0)
        text = "".join(g.text for g in gl_sorted)
        cx = sum((g.x0 + g.x1) / 2.0 for g in gl_sorted) / len(gl_sorted)
        cy = sum((g.y0 + g.y1) / 2.0 for g in gl_sorted) / len(gl_sorted)
        records.append({"page": gl_sorted[0].page, "cx": cx, "cy": cy, "text": text, "glyphs": gl_sorted})

    by_page: dict[int, list] = defaultdict(list)
    for rec in records:
        by_page[rec["page"]].append(rec)
    ordered: list[dict] = []
    for page in sorted(by_page):
        recs = by_page[page]
        xs0 = min(r["cx"] for r in recs)
        xs1 = max(r["cx"] for r in recs)
        mid = (xs0 + xs1) / 2.0
        recs.sort(key=lambda r: (0 if r["cx"] < mid else 1, r["cy"], r["cx"]))
        ordered.extend(recs)

    blocks: list[Block] = []
    cur_id: str | None = None
    cur_glyphs: list = []
    for rec in ordered:
        m = marker_re.search(rec["text"]) or marker_re.search(rec["text"].replace(" ", ""))
        if m is not None:
            if cur_id is not None:
                blocks.append(Block(id=cur_id, glyphs=cur_glyphs))
            cur_id = m.group(1)
            cur_glyphs = list(rec["glyphs"])
        elif cur_id is not None:
            cur_glyphs.extend(rec["glyphs"])
    if cur_id is not None:
        blocks.append(Block(id=cur_id, glyphs=cur_glyphs))
    return blocks


@dataclass(frozen=True, slots=True)
class SplitReport:
    n_splits: int
    n_blocks: int
    n_glyphs: int
    kinds: dict[str, int]
    split_ids: tuple[str, ...]


def measure_question_splits(pdf_path: str, *, marker_re: re.Pattern = DEFAULT_QUESTION_MARKER) -> SplitReport:
    glyphs = extract_glyph_boxes(pdf_path)
    blocks = group_question_blocks(glyphs, marker_re=marker_re)
    page_height = max((g.y1 for g in glyphs), default=0.0)
    bounds = column_x_bounds(glyphs)
    splits = detect_block_splits(blocks, bounds, page_height)
    kinds: dict[str, int] = {}
    for s in splits:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    return SplitReport(len(splits), len(blocks), len(glyphs), kinds, tuple(s.block_id for s in splits))
```

- [ ] **Step 4: Refactor the spike to import these (DRY; keep it runnable)**

In `scripts/exam_spike_keep_together.py`: delete the local `_column_x_bounds`, `_group_blocks`, `_measure_splits` bodies and import from the new module, passing the spike's own `[[QNN]]` marker:

```python
import re as _re
from hwpx.exam.measure import column_x_bounds as _column_x_bounds
from hwpx.exam.measure import group_question_blocks, measure_question_splits

_QNN_MARKER = _re.compile(r"\[\s*\[\s*Q\s*0*(\d+)\s*\]\s*\]")

def _group_blocks(glyphs):
    return group_question_blocks(glyphs, marker_re=_QNN_MARKER)

def _measure_splits(pdf_path):
    r = measure_question_splits(pdf_path, marker_re=_QNN_MARKER)
    return r.n_splits, r.n_blocks, r.n_glyphs, dict(r.kinds), list(r.split_ids)
```

(The spike still imports `Block`/`detect_block_splits` indirectly; leave its top-level imports intact for `MacHancomOracle`/`resolve_oracle`/`extract_glyph_boxes` it uses elsewhere.)

- [ ] **Step 5: Run measure test + the spike's import sanity, then commit**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_measure.py -q && .venv/bin/python -c "import ast,sys; ast.parse(open('scripts/exam_spike_keep_together.py').read()); print('spike parses')"`
Expected: PASS (2 passed) + `spike parses`.

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/exam/measure.py src/hwpx/exam/__init__.py scripts/exam_spike_keep_together.py tests/test_exam_measure.py
git commit -m "feat(exam): measure helpers (column bounds + question grouping + split report); DRY spike"
```

---

### Task 7: Composer core — `src/hwpx/exam/compose.py` (lower IR → body, no oracle)

**Files:**
- Create: `python-hwpx/src/hwpx/exam/compose.py`
- Modify: `python-hwpx/src/hwpx/exam/__init__.py` (export `lower_exam`, `replace_body_region`, `ComposePlan`)
- Test: `python-hwpx/tests/test_exam_compose.py`

**Interfaces:**
- Consumes: `ir.*`, `FormProfile`/`ResolvedStyle` (Task 5), `doc.oxml.headers[0].ensure_paragraph_format(base_para_pr_id=…, break_setting=…)`, `HwpxOxmlSection.{paragraphs,add_paragraph,insert_paragraphs,remove_paragraph,mark_dirty}`, `HwpxOxmlParagraph.element`.
- Produces:
  - `@dataclass ParaSpec(text:str, role:str, keep_with_next:bool, is_question_head:bool, question_number:str|None)` — one composed body paragraph before it is materialized.
  - `lower_exam(exam: ExamDoc, profile: FormProfile) -> list[ParaSpec]` — maps IR roles → form role styles; emits literal `"<n>. <stem>"` for each 문항 head, one `ParaSpec` per 답항 / passage / placeholder; sets `keep_with_next=True` on every paragraph of a 문항 **except its last** (column cohesion that still allows a break before the next 문항).
  - `replace_body_region(doc, profile, specs) -> dict[str,int]` — builds the paragraphs (with role style + a keepWithNext paraPr cloned from the role's paraPr), **inserts them into the body region** `[body_start..body_end]` (clearing the old slots; never appending past the tail), and returns `question_anchors: {question_number: section_paragraph_index_of_its_head}` for the convergence loop.

- [ ] **Step 1: Write the failing test** (synthetic 2-paragraph form to keep it oracle-free and deterministic)

```python
# python-hwpx/tests/test_exam_compose.py
import copy

from hwpx.document import HwpxDocument
from hwpx.exam import ir
from hwpx.exam.compose import lower_exam, replace_body_region
from hwpx.exam.profile import profile_form
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "exam"


def _exam():
    q1 = ir.Question(number="1", stem="발문 하나", choices=("① 가", "② 나"), points="3")
    ph = ir.Placeholder(id="그림1", kind="img", raw_text="[그림1]")
    q2 = ir.Question(number="2", stem="발문 둘", choices=("① 다", "② 라"), placeholders=(ph,))
    return ir.ExamDoc(title="t", blocks=(q1, q2))


def test_lower_sets_keep_with_next_on_all_but_last_para_of_each_question():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    specs = lower_exam(_exam(), profile)
    # group specs by question head boundaries
    heads = [i for i, s in enumerate(specs) if s.is_question_head]
    assert len(heads) == 2
    q1_specs = specs[heads[0]:heads[1]]
    assert all(s.keep_with_next for s in q1_specs[:-1])
    assert q1_specs[-1].keep_with_next is False
    # literal number prefix + placeholder preserved verbatim
    assert specs[heads[0]].text.startswith("1.")
    assert any("[그림1]" in s.text for s in specs)


def test_replace_body_region_inserts_into_body_and_preserves_admin_box_and_tail():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    section = doc.sections[0]
    admin_before = copy.deepcopy(section.paragraphs[0].element)
    tail_index = profile.body_end + 1
    tail_before = (
        copy.deepcopy(section.paragraphs[tail_index].element)
        if tail_index < len(section.paragraphs) else None
    )

    specs = lower_exam(_exam(), profile)
    anchors = replace_body_region(doc, profile, specs)

    # 관리박스 para[0] byte-identical (Lossless VII)
    from lxml import etree
    assert etree.tostring(doc.sections[0].paragraphs[0].element) == etree.tostring(admin_before)
    # preserved tail still present & identical (if the form has body-stream footer paras)
    if tail_before is not None:
        tails = [etree.tostring(p.element) for p in doc.sections[0].paragraphs]
        assert etree.tostring(tail_before) in tails
    # the composed 문항 text now lives in the body (round-trips through save/open)
    import io
    buf = io.BytesIO(); doc.save(buf)
    text = "".join(p.text or "" for p in HwpxDocument.open(io.BytesIO(buf.getvalue())).paragraphs)
    assert "발문 하나" in text and "발문 둘" in text and "[그림1]" in text
    assert set(anchors) == {"1", "2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_compose.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.exam.compose'`.

- [ ] **Step 3: Write `compose.py`**

```python
# python-hwpx/src/hwpx/exam/compose.py
"""Lower the Exam IR into the school form's body region.

Strategy (Phase-0 grounded): map each role onto the form's EXISTING style,
attach keepWithNext (column cohesion) to every paragraph of a 문항 except its
last, and INSERT into the body region [body_start..body_end] — never append
(Hancom drops appended content)."""
from __future__ import annotations

from dataclasses import dataclass

from hwpx.document import HwpxDocument

from .ir import ExamDoc, Question, QuestionSet
from .profile import FormProfile, ResolvedStyle


@dataclass(slots=True)
class ParaSpec:
    text: str
    role: str               # key into FormProfile.role_styles
    keep_with_next: bool
    is_question_head: bool
    question_number: str | None


def _choice_role(n_choices: int, idx: int) -> str:
    # answer-row styles encode a "rows" hint; default to choice1, fall back gracefully
    return "choice1"


def _lower_question(q: Question) -> list[ParaSpec]:
    specs: list[ParaSpec] = [
        ParaSpec(
            text=f"{q.number}. {q.stem}".rstrip(),
            role="number",
            keep_with_next=True,
            is_question_head=True,
            question_number=q.number,
        )
    ]
    for i, choice in enumerate(q.choices):
        specs.append(ParaSpec(text=choice, role=_choice_role(len(q.choices), i),
                              keep_with_next=True, is_question_head=False, question_number=q.number))
    for ph in q.placeholders:
        # keep the literal placeholder on its own line so a human can find it
        specs.append(ParaSpec(text=ph.raw_text, role="normal", keep_with_next=True,
                              is_question_head=False, question_number=q.number))
    if specs:
        specs[-1].keep_with_next = False  # last para of the 문항 may break before the next
    return specs


def lower_exam(exam: ExamDoc, profile: FormProfile) -> list[ParaSpec]:
    specs: list[ParaSpec] = []
    for block in exam.blocks:
        if isinstance(block, QuestionSet):
            specs.append(ParaSpec(text=block.passage, role="box", keep_with_next=True,
                                  is_question_head=False, question_number=None))
            for member in block.members:
                specs.extend(_lower_question(member))
        else:
            specs.extend(_lower_question(block))
    # drop roles the form lacks -> fall back to "normal"
    for s in specs:
        if s.role not in profile.role_styles:
            s.role = "normal"
    return specs


def _keep_para_pr(doc: HwpxDocument, base: ResolvedStyle, keep: bool, cache: dict) -> str | None:
    key = (base.name, keep)
    if key in cache:
        return cache[key]
    pid = doc.oxml.headers[0].ensure_paragraph_format(
        base_para_pr_id=base.para_pr_id,
        break_setting={"keep_with_next": keep, "keep_lines": True},
    )
    cache[key] = pid
    return pid


def replace_body_region(doc: HwpxDocument, profile: FormProfile, specs: list[ParaSpec]) -> dict[str, int]:
    section = doc.sections[0]
    paragraphs = section.paragraphs
    start, end = profile.body_start, profile.body_end
    old_slots = [paragraphs[i] for i in range(start, end + 1)]  # capture wrappers up front

    cache: dict = {}
    temp = []
    for spec in specs:
        style = profile.role_styles.get(spec.role) or profile.role_styles["normal"]
        para_pr_id = _keep_para_pr(doc, style, spec.keep_with_next, cache)
        temp.append(
            section.add_paragraph(  # appended to tail; cloned into body below, then removed
                spec.text,
                para_pr_id_ref=para_pr_id,
                style_id_ref=style.style_id,
                char_pr_id_ref=style.char_pr_id,
                inherit_style=False,
            )
        )

    inserted = section.insert_paragraphs(start, temp)   # deep-clone into the body
    for wrapper in reversed(temp):
        section.remove_paragraph(wrapper)               # drop the temporary tail copies
    for wrapper in old_slots:
        section.remove_paragraph(wrapper)               # drop the old form slots
    section.mark_dirty()

    # `inserted` is index-aligned with `specs`; each 문항 head now lives at
    # body-region offset `start + offset`. Build the convergence anchor map.
    anchors: dict[str, int] = {}
    for offset, spec in enumerate(specs):
        if spec.is_question_head and spec.question_number is not None:
            anchors[spec.question_number] = start + offset
    return anchors
```

> Implementer note: `insert_paragraphs` returns the clones in the order passed, so `inserted[i]` corresponds to `specs[i]`; the body region begins at `start`, so 문항 head `specs[i]` sits at section-paragraph index `start + i` after the old slots are removed (removal happens at indices `> start + len(specs)`, so it does not shift the inserted block).

Export from `__init__.py`:

```python
from .compose import ParaSpec, lower_exam, replace_body_region
# add to __all__: "ParaSpec", "lower_exam", "replace_body_region"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_compose.py -q`
Expected: PASS (2 passed). If the body-region indices from Task 4 differ from what the synthetic test assumes, the test reads them from `profile` directly (it does) so it stays robust.

- [ ] **Step 5: Full suite, then commit**

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/exam/compose.py src/hwpx/exam/__init__.py tests/test_exam_compose.py
git commit -m "feat(exam): composer core — lower IR to form body, keep-together, insert-not-append"
```

---

### Task 8: Convergence driver + oracle smoke gate — `compose_exam_into_form`

**Files:**
- Modify: `python-hwpx/src/hwpx/exam/compose.py` (add `ComposeResult`, `compose_exam_into_form`, `_insert_break`)
- Modify: `python-hwpx/src/hwpx/exam/__init__.py` (export `compose_exam_into_form`, `ComposeResult`)
- Test: `python-hwpx/tests/test_exam_compose_oracle.py` (smoke-gated)

**Interfaces:**
- Consumes: Task 7 (`lower_exam`, `replace_body_region`), Task 6 (`measure_question_splits`), Task 5 (`profile_form`), Task 2 (`parse_exam_markdown`); `resolve_oracle`, `MacHancomOracle`, `detect_overflow` (`wordbox.py:398`), `extract_glyph_boxes`; `HwpxOxmlParagraph.element.set("columnBreak"|"pageBreak","1")`.
- Produces:
  - `@dataclass(frozen=True, slots=True) ComposeResult(out_path:str, render_checked:bool, splits:int|None, overflow:int|None, placeholders_ok:bool, rounds:int, needs_review:bool, notes:tuple[str,...])`.
  - `compose_exam_into_form(form_path:str, exam_md:str, out_path:str, *, oracle=None, max_rounds:int=2, role_style_names=None) -> ComposeResult` — parse → profile → compose (keepWithNext) → save; if an oracle is available, render → `measure_question_splits` → for each split block_id look up its anchor and set `columnBreak`/`pageBreak` on that 문항's head paragraph → re-save → re-render, up to `max_rounds`; verify placeholder integrity (every `[그림N]`/`[표N]`/`[식N]` from the IR still present in the rendered text); set `render_checked=False`, `needs_review=True` when no oracle (no silent true).

- [ ] **Step 1: Write the smoke-gated oracle test**

```python
# python-hwpx/tests/test_exam_compose_oracle.py
import os
from pathlib import Path

import pytest

from hwpx.exam.compose import compose_exam_into_form
from hwpx.visual.oracle import MacHancomOracle

FIX = Path(__file__).parent / "fixtures" / "exam"
_SMOKE = bool(os.environ.get("HWPX_MAC_ORACLE_SMOKE")) and MacHancomOracle().available()


@pytest.mark.skipif(not _SMOKE, reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the exam render smoke")
def test_compose_sample_into_A_form_renders_clean(tmp_path):
    out = str(tmp_path / "composed.hwpx")
    md = (FIX / "sample_exam.md").read_text(encoding="utf-8")
    result = compose_exam_into_form(str(FIX / "A_form.hwpx"), md, out)
    assert result.render_checked is True
    assert result.splits == 0           # primary gate: no 문항 straddles a column/page
    assert result.overflow == 0
    assert result.placeholders_ok is True
    assert Path(out).exists()


def test_compose_without_oracle_is_honest_unverified(tmp_path):
    out = str(tmp_path / "composed.hwpx")
    md = (FIX / "sample_exam.md").read_text(encoding="utf-8")
    from hwpx.visual.oracle import NullOracle
    result = compose_exam_into_form(str(FIX / "A_form.hwpx"), md, out, oracle=NullOracle())
    assert result.render_checked is False
    assert result.needs_review is True
    assert result.splits is None        # never a silent 0
    assert Path(out).exists()           # keepWithNext composition still produced a file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_compose_oracle.py -q`
Expected: FAIL — `ImportError: cannot import name 'compose_exam_into_form'`. (The smoke test SKIPS without an oracle; the no-oracle test runs.)

- [ ] **Step 3: Implement the driver in `compose.py`**

```python
# add to python-hwpx/src/hwpx/exam/compose.py
from dataclasses import dataclass

from hwpx.form_fit.wordbox import detect_overflow, extract_glyph_boxes
from hwpx.visual.oracle import resolve_oracle

from .measure import measure_question_splits
from .parser import parse_exam_markdown
from .profile import profile_form


@dataclass(frozen=True, slots=True)
class ComposeResult:
    out_path: str
    render_checked: bool
    splits: int | None
    overflow: int | None
    placeholders_ok: bool
    rounds: int
    needs_review: bool
    notes: tuple[str, ...]


def _insert_break(section, head_index: int, kind: str) -> None:
    attr = "pageBreak" if kind == "page" else "columnBreak"
    section.paragraphs[head_index].element.set(attr, "1")
    section.mark_dirty()


def compose_exam_into_form(
    form_path: str,
    exam_md: str,
    out_path: str,
    *,
    oracle=None,
    max_rounds: int = 2,
    role_style_names=None,
) -> ComposeResult:
    notes: list[str] = []
    exam = parse_exam_markdown(exam_md)
    expected_ph = {ph.raw_text for q in exam.iter_questions() for ph in q.placeholders}

    doc = HwpxDocument.open(form_path)
    profile = profile_form(doc, role_style_names=role_style_names)
    specs = lower_exam(exam, profile)
    anchors = replace_body_region(doc, profile, specs)
    doc.save_to_path(out_path)
    notes.append(f"composed {len(list(exam.iter_questions()))} 문항 into body [{profile.body_start}..{profile.body_end}]")

    if oracle is None:
        oracle = resolve_oracle()
    if not oracle.available():
        notes.append("oracle unavailable -> render_checked=false, needs_review=true (no silent true)")
        return ComposeResult(out_path, False, None, None, True, 0, True, tuple(notes))

    rounds = 0
    splits = overflow = None
    placeholders_ok = True
    while rounds < max_rounds:
        rounds += 1
        pdf = oracle.render_pdf(out_path)
        if not pdf:
            notes.append(f"round {rounds}: render returned None -> render_checked=false")
            return ComposeResult(out_path, False, None, None, True, rounds, True, tuple(notes))
        report = measure_question_splits(pdf)
        glyphs = extract_glyph_boxes(pdf)
        rendered_text = "".join(g.text for g in glyphs)
        placeholders_ok = all(ph.replace(" ", "") in rendered_text.replace(" ", "") for ph in expected_ph)
        overflow = len(detect_overflow(glyphs))
        splits = report.n_splits
        notes.append(f"round {rounds}: splits={splits} kinds={report.kinds} overflow={overflow} ph_ok={placeholders_ok}")
        if splits == 0:
            break
        # fix: force a break on each straddling 문항's head paragraph, then re-render
        section = doc.sections[0]
        for block_id in report.split_ids:
            head_index = anchors.get(block_id)
            if head_index is None:
                notes.append(f"round {rounds}: split id {block_id!r} has no anchor (skipped)")
                continue
            kind = "page" if report.kinds.get("page") else "column"
            _insert_break(section, head_index, kind)
        doc.save_to_path(out_path)

    needs_review = splits is None or splits > 0 or not placeholders_ok
    return ComposeResult(out_path, True, splits, overflow, placeholders_ok, rounds, needs_review, tuple(notes))
```

Export `compose_exam_into_form`, `ComposeResult` from `__init__.py`.

- [ ] **Step 4: Run the no-oracle test (always) + the smoke test (if you have Hancom)**

Run (CI-equivalent, no oracle): `cd python-hwpx && .venv/bin/python -m pytest tests/test_exam_compose_oracle.py -q`
Expected: 1 passed (no-oracle honesty test), 1 skipped (smoke).

Run (local macOS + Hancom, the real gate): `cd python-hwpx && HWPX_MAC_ORACLE_SMOKE=1 .venv/bin/python -m pytest tests/test_exam_compose_oracle.py -q`
Expected: 2 passed — the composed `sample_exam.md` → A_form renders with `splits=0`, `overflow=0`, placeholders intact. This is a `dangerouslyDisableSandbox` GUI-automation run. If the gate finds `splits>0` after `max_rounds`, that is a real finding — raise `max_rounds` or inspect the anchor→break mapping; do NOT relax the assertion.

- [ ] **Step 5: Full suite, then commit**

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/exam/compose.py src/hwpx/exam/__init__.py tests/test_exam_compose_oracle.py
git commit -m "feat(exam): convergence driver compose_exam_into_form (oracle gate + honest unverified)"
```

---

### Task 9: Package polish — example + CHANGELOG + suite + handoff

**Files:**
- Create: `python-hwpx/examples/compose_exam.py` (runnable end-to-end demo, no oracle required)
- Modify: `python-hwpx/CHANGELOG.md` (unreleased section: exam composer)
- Test: re-run full suite

**Interfaces:**
- Consumes: the full `hwpx.exam` public surface.
- Produces: a documented, runnable example; an unreleased CHANGELOG entry. (No version bump / publish — release staging is the owner's call, Plan 4 / release stage.)

- [ ] **Step 1: Write the example**

```python
# python-hwpx/examples/compose_exam.py
"""Compose an authored exam (Markdown) into a school form .hwpx.

    python examples/compose_exam.py FORM.hwpx EXAM.md OUT.hwpx

Without a Hancom oracle the result is composed (keepWithNext) but reported
render_checked=false / needs_review=true (no silent true). On macOS with
Hancom + HWPX_MAC_ORACLE_SMOKE=1 the convergence loop verifies splits=0."""
from __future__ import annotations

import sys
from pathlib import Path

from hwpx.exam import compose_exam_into_form


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    form, md_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    result = compose_exam_into_form(form, Path(md_path).read_text(encoding="utf-8"), out)
    print(f"out={result.out_path} render_checked={result.render_checked} "
          f"splits={result.splits} overflow={result.overflow} "
          f"placeholders_ok={result.placeholders_ok} needs_review={result.needs_review}")
    for note in result.notes:
        print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add a CHANGELOG entry** (under the top `## [Unreleased]` heading; create it if absent)

```markdown
### Added
- `hwpx.exam`: re-typeset an authored exam (Markdown) into a school form `.hwpx`
  — Exam IR + strict md parser, form profiler (role→existing-style), keep-together
  body composition (insert-not-append), and an oracle-gated convergence driver
  (`compose_exam_into_form`) that verifies 문항-split=0 / overflow=0 / placeholders
  intact, degrading to `render_checked=false` + `needs_review` without an oracle.
```

- [ ] **Step 3: Run the example end-to-end (no oracle) and the full suite**

```bash
cd python-hwpx
.venv/bin/python examples/compose_exam.py tests/fixtures/exam/A_form.hwpx tests/fixtures/exam/sample_exam.md /tmp/composed.hwpx
.venv/bin/python -m pytest -q
```
Expected: the example prints `render_checked=False needs_review=True` and writes `/tmp/composed.hwpx`; full suite green (the ~1057 pre-existing + the new exam tests; oracle smoke skipped).

- [ ] **Step 4: Commit**

```bash
cd python-hwpx
git add examples/compose_exam.py CHANGELOG.md
git commit -m "docs(exam): runnable compose example + CHANGELOG entry for hwpx.exam composer"
```

- [ ] **Step 5: Update the Wily phase (root session only)**

After all tasks land and the suite is green, the root session records the phase verification on **PH-c1ee1bf83fee** (commits, suite counts, the A_form body-region evidence path, and — if run — the oracle smoke `splits=0` receipt), then marks it done. *Subagents must not change Wily state (Constitution II).* Update `python-hwpx/.superpowers/sdd/progress.md` with the Plan-2 completion line.

---

## Self-Review

**Spec coverage** (spec `specs/003-exam-typesetting/spec.md`):
- §"Inputs (the contract)" container + md body + placeholders → Tasks 2 (parser), 3 (fixtures), 7 (compose).
- §"Architecture ① Profile the form" → Tasks 4 (measure A_form), 5 (profiler).
- §"② md → Exam IR" → Tasks 1 (IR), 2 (parser).
- §"③ Compose … FORM's existing style + keep-together + preserve 관리박스/footer + [그림N] placeholders" → Task 7.
- §"④ Oracle verify loop … on split → insert columnBreak → re-render" → Task 8 (`compose_exam_into_form`) + Task 6 (measure).
- §"Oracle gate (definition of done)": 문항-split=0 → Task 8 primary assert; overflow=0 → Task 8 (`detect_overflow`); placeholder integrity → Task 8 (`placeholders_ok`); clean open → implied by the oracle render succeeding (Hancom refuses a 손상 file). Column balance is correctly NOT gated.
- §"Engine/MCP work items" item 4 "reuse existing primitives" → Tasks 6–8 reuse `ensure_paragraph_format`/`detect_block_splits`/`render_form_geometry`/`detect_overflow`. (Items 1–2 were Plan 1; item 3 MCP is Plan 3.)
- §"Composition detail — form profiling" (distinguish replaceable slots vs structural) → Tasks 4–5.
- §"Error handling (no-silent-true)": unparseable md → Task 2 `ExamParseError`; missing style → Task 5 `FormProfileError`; placeholder lost → Task 8 `placeholders_ok=False`; no oracle → Task 8 `render_checked=False`/`needs_review`.
- §"Testing strategy": compose unit tests → Tasks 2,7; lossless byte-diff → Task 7 (deepcopy compare of para[0]/tail); oracle smoke gated `HWPX_MAC_ORACLE_SMOKE=1` → Task 8. **B_submitted reverse-recompose** is consciously reduced to a render baseline + structural cross-check (Task 5) — see "Scope decisions"; deferred with rationale per Governance.

**Placeholder scan:** Task 4 is a measure-first evidence task (deliverable = receipt, not a unit-test pass), intentional per Constitution V. Task 8's smoke assertion requires a live oracle — its no-oracle sibling always runs. The Task-7 `replace_body_region` listing contains two clearly-labelled scaffolding loops the implementer must delete (called out inline); the real anchor builder is the final `enumerate(inserted)` block. No "TBD"/"add error handling"/"similar to" placeholders remain; all code steps carry runnable code + exact commands.

**Type consistency:** `break_setting` keys (`keep_with_next`/`keep_lines`) match Plan-1's `ensure_paragraph_format`. `Block(id,glyphs)`/`BlockSplit(block_id,kind)`/`detect_block_splits(...)` match the verified oracle signatures. `ResolvedStyle.{style_id,para_pr_id,char_pr_id}` produced by Task 5 are consumed verbatim by Task 7's `add_paragraph(style_id_ref=…, para_pr_id_ref=…, char_pr_id_ref=…)`. `SplitReport.{n_splits,kinds,split_ids}` produced by Task 6 are consumed by Task 8's loop. `question_anchors: dict[str,int]` produced by Task 7 keys on `question_number` (str) and is looked up by Task 8 with `report.split_ids` (str block ids) — both are the literal 문항 number captured by `DEFAULT_QUESTION_MARKER` group 1.

**Known risk flagged for execution:** the 문항-grouping marker (`^\s*(\d+)\s*\.`) assumes each rendered 문항 head line starts with `"<n>."` and that 답항/passage lines do not. Task 3's `sample_exam.md` must keep 답항 text free of leading `"N."`. If A_form's `문항자동번호넣기` style renders the number differently than the literal prefix the composer emits, Task 4's evidence will reveal it and the marker regex (single source in `measure.py`) is adjusted once.

## Subsequent Plans (unchanged from Plan 1's roadmap)

- **Plan 3 — MCP surface (`hwpx-mcp-server`, phase PH-7adb7e648d06):** expose `compose_exam_into_form` as an MCP tool (dry-run + revision-guard + openSafety like existing tools) and a 문항-split verification tool wrapping `measure_question_splits`/`detect_block_splits`.
- **Plan 4 — Skill reference + leap demo (phase PH-ebdea8e29481):** `hwpx-skill/references/workflows-exam.md` + one routing row in `SKILL.md`; the anti-nibble **leap** = a real authored exam composed into the A form, rendered clean in Hancom (split 0, overflow 0, placeholders intact), checked in as `demo/exam-typesetting/`. Tier move on `form-fill-integrity`/`document-authoring` claimed here with the render receipt + scorecard bump.

## Execution Handoff

**Plan complete and saved to `python-hwpx/docs/superpowers/plans/2026-06-26-exam-typesetting-p2-composer.md`.** This is Plan 2 of 4 (the composer engine); it produces working, tested IR + parser + profiler + measure + composer + convergence driver, on branch `feat/s056-exam-typesetting` under Wily phase PH-c1ee1bf83fee, and gates Plans 3–4.
