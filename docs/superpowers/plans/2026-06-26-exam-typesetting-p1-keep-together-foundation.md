# Exam Typesetting — Implementation Plan 1: Keep-Together Engine Foundation + Mechanism Spike

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the python-hwpx engine the two primitives exam typesetting needs to keep each 문항(question) unbroken — a keep-together paragraph-shape authoring primitive and a 문항-split detector over a Hancom render — and then **measure** (Phase 0 spike) which keep mechanism Hancom actually honors in a 2-column flow.

**Architecture:** Spec `specs/003-exam-typesetting/spec.md`, approach A (reuse the school form `.hwpx` as a living container; let Hancom's own layout engine flow the 2 columns; constrain it with keep-together). This plan builds only the **engine foundation + the measurement** that the later composer plans depend on. keep-together is a property of the **paraPr definition** in `header.xml` (referenced by paragraphs via `paraPrIDRef`), not an inline per-paragraph attribute; the inline `columnBreak`/`pageBreak` attributes are the deterministic fallback.

**Tech Stack:** Python 3, `python-hwpx` (lxml-based OWPML model), PyMuPDF (`fitz`) for render geometry, `MacHancomOracle` (AppleScript → PDF) as the verdict source.

## Constitution Check (`.specify/memory/constitution.md` v1.1.0)

- **Dimension/tier (Principle X):** advances `form-fill-integrity` + `document-authoring` (co-top). This plan is *foundation + measurement*; the tier-moving oracle-clean demo `.hwpx` lands in Plan 4 (leap). Foundation alone is not a tier claim — no scorecard change here.
- **Oracle truth (IV) / Measure-first, no silent true (V):** the keep mechanism is decided by a real Hancom render (Phase 0), never asserted. With no oracle the spike degrades to `unverified` and the columnBreak fallback is selected by default.
- **Lossless (VII):** `ensure_paragraph_format` clones a base paraPr and appends a NEW paraPr (new id); it never mutates existing paragraph shapes, so untouched paragraphs round-trip byte-identical.
- **Honest reporting (IX):** the split detector returns an explicit verdict object with `unverified` when no render is available; the spike writes a receipt with `skipped[]` when the oracle is absent.

## Global Constraints

- python-hwpx public API only; no external code copied (Clean-Room VIII).
- New paraPr is appended; existing paraPr definitions are never edited in place (Lossless VII).
- Mac Hancom oracle runs are GUI-automation gated: require `HWPX_MAC_ORACLE_SMOKE=1` and `dangerouslyDisableSandbox` at call time; absence ⇒ `unverified`, never a silent pass (V).
- Tests run green in `python-hwpx` via `.venv/bin/python -m pytest -q` (or `uv run --extra dev pytest -q`).
- Units are human units at the API surface; OWPML attribute values are `"0"`/`"1"` strings.

---

### Task 1: Engine — `ensure_paragraph_format(break_setting=...)` keep-together primitive

**Files:**
- Modify: `python-hwpx/src/hwpx/oxml/_document_impl.py` (`ensure_paragraph_format`, `:5264`; add `_apply_paragraph_break_setting` helper near `_apply_paragraph_border` `:5246`)
- Test: `python-hwpx/tests/test_paragraph_keep_together.py`

**Interfaces:**
- Consumes: existing `ensure_paragraph_format(*, base_para_pr_id, alignment, line_spacing_percent, margins, heading, border) -> str`; helpers `_ensure_direct_para_child(para_pr, local_name, after_local_names)`, `_HH` namespace.
- Produces: `ensure_paragraph_format(..., break_setting: Mapping[str, bool] | None = None) -> str` — accepts keys `keep_with_next`, `keep_lines`, `page_break_before`, `widow_orphan`; writes a `<hh:breakSetting>` child (after `align`/`heading`, before `margin`) with attrs `keepWithNext`/`keepLines`/`pageBreakBefore`/`widowOrphan` = `"1"`/`"0"`; returns the new paraPr id (string).

- [ ] **Step 1: Write the failing test**

```python
# python-hwpx/tests/test_paragraph_keep_together.py
import io
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml import HH

FIXTURE = Path(__file__).parent / "fixtures" / "glyph_overlap" / "slot_clean.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    document.save(buffer)
    return HwpxDocument.open(io.BytesIO(buffer.getvalue()))


def test_ensure_paragraph_format_writes_keep_together_break_setting():
    document = HwpxDocument.open(FIXTURE)
    header = document.oxml.headers[0]

    new_id = header.ensure_paragraph_format(
        break_setting={"keep_with_next": True, "keep_lines": True},
    )
    assert new_id is not None

    # The new paraPr must carry a breakSetting with the keep flags ON.
    para_pr = header.element.find(f".//{HH}paraPr[@id='{new_id}']")
    assert para_pr is not None
    break_setting = para_pr.find(f"{HH}breakSetting")
    assert break_setting is not None
    assert break_setting.get("keepWithNext") == "1"
    assert break_setting.get("keepLines") == "1"

    # Lossless: the flags survive a save/reopen round-trip.
    reopened = _reopen(document)
    rt = reopened.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{new_id}']")
    assert rt.find(f"{HH}breakSetting").get("keepWithNext") == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_paragraph_keep_together.py -q`
Expected: FAIL — `ensure_paragraph_format() got an unexpected keyword argument 'break_setting'`.

- [ ] **Step 3: Write minimal implementation**

Add the helper next to `_apply_paragraph_border`:

```python
    def _apply_paragraph_break_setting(
        self, para_pr: ET.Element, break_setting: Mapping[str, bool]
    ) -> None:
        element = self._ensure_direct_para_child(
            para_pr,
            "breakSetting",
            after_local_names={"align", "heading"},
        )
        attr_map = {
            "keep_with_next": "keepWithNext",
            "keep_lines": "keepLines",
            "page_break_before": "pageBreakBefore",
            "widow_orphan": "widowOrphan",
        }
        for key, attr in attr_map.items():
            if key in break_setting and break_setting[key] is not None:
                element.set(attr, "1" if break_setting[key] else "0")
```

Add the parameter to `ensure_paragraph_format` (signature + body, mirroring the `border` branch):

```python
        border: Mapping[str, str | int] | None = None,
        break_setting: Mapping[str, bool] | None = None,
    ) -> str:
        ...
        if break_setting:
            self._apply_paragraph_break_setting(para_pr, break_setting)
        if border is not None:
            self._apply_paragraph_border(para_pr, border)
```

(Place the `break_setting` branch BEFORE the `border` branch so border's `_insert_child_after` ordering set — which already lists `breakSetting` — stays correct.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_paragraph_keep_together.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd python-hwpx && .venv/bin/python -m pytest -q`
Expected: all green (the pre-existing ~985 suite + 1 new).

- [ ] **Step 6: Commit**

```bash
cd python-hwpx
git add src/hwpx/oxml/_document_impl.py tests/test_paragraph_keep_together.py
git commit -m "feat(oxml): ensure_paragraph_format break_setting (keep-together) for exam typesetting"
```

---

### Task 2: Engine — paragraph carries inline `columnBreak` (deterministic fallback)

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py` (the `add_paragraph` path that already handles `pageBreak="1"`, `:2127`) and/or `python-hwpx/src/hwpx/oxml/body.py` (`:759`, where `columnBreak` is serialized) to confirm a paragraph can be authored with `columnBreak="1"`.
- Test: `python-hwpx/tests/test_paragraph_keep_together.py` (add a test)

**Interfaces:**
- Consumes: existing paragraph authoring that accepts `pageBreak`.
- Produces: an authored paragraph whose `<hp:p>` carries `columnBreak="1"` and round-trips. (If `add_paragraph` already forwards arbitrary break kwargs, this task is a confirming test only; if not, extend it the same way `pageBreak` is forwarded.)

- [ ] **Step 1: Write the failing/confirming test**

```python
def test_paragraph_can_carry_column_break():
    document = HwpxDocument.open(FIXTURE)
    section = document.sections[0]
    para = section.add_paragraph("다음 단으로", columnBreak="1")
    assert para.element.get("columnBreak") == "1"

    reopened = _reopen(document)
    last = reopened.sections[0].paragraphs[-1]
    assert last.element.get("columnBreak") == "1"
```

- [ ] **Step 2: Run it**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_paragraph_keep_together.py::test_paragraph_can_carry_column_break -q`
Expected: PASS if `add_paragraph` already forwards break attrs; otherwise FAIL with a `TypeError`/missing attribute.

- [ ] **Step 3: If it failed, forward `columnBreak` like `pageBreak`**

In `authoring.py` where `add_paragraph("", pageBreak="1", ...)` is built (`:2127` region), allow a `columnBreak` kwarg to flow into the paragraph attributes exactly as `pageBreak` does (search the `pageBreak` attribute write in `oxml/body.py:759` and add the parallel `columnBreak` write if absent).

- [ ] **Step 4: Re-run to PASS, then full suite**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_paragraph_keep_together.py -q && .venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd python-hwpx
git add src/hwpx/authoring.py src/hwpx/oxml/body.py tests/test_paragraph_keep_together.py
git commit -m "feat(authoring): paragraph columnBreak attribute (exam keep-together fallback)"
```

---

### Task 3: Engine — 문항-split detector over render geometry

**Files:**
- Modify: `python-hwpx/src/hwpx/visual/oracle.py` (add `detect_block_splits` + `Block` near the existing `detect_overflow` `:398` and `extract_glyph_boxes` `:230`)
- Test: `python-hwpx/tests/test_question_split_detector.py`

**Interfaces:**
- Consumes: existing `WordBox(x0, y0, x1, y1, text, page, block, line, word_no)` (`oracle.py:230-282`); `fitz.Page.get_drawings()` for column-gutter detection (Plan-4 wiring) is NOT needed here — the detector takes explicit column boundaries so it is pure and unit-testable.
- Produces:
  - `@dataclass Block: id: str; glyphs: list[WordBox]` — one logical 문항/answer unit's glyphs.
  - `detect_block_splits(blocks: list[Block], column_x_bounds: list[tuple[float, float]], page_height: float) -> list[BlockSplit]` where `BlockSplit(block_id: str, kind: Literal["column","page"])`. A block splits when its glyphs fall in **two different columns** (x-center in different `column_x_bounds` ranges) OR on **two different pages**. Returns `[]` when every block is wholly within one column on one page.

- [ ] **Step 1: Write the failing test (synthetic geometry — deterministic, no oracle)**

```python
# python-hwpx/tests/test_question_split_detector.py
from hwpx.visual.oracle import WordBox, Block, detect_block_splits

LEFT = (0.0, 300.0)
RIGHT = (320.0, 620.0)


def _g(x, page=0):
    return WordBox(x0=x, y0=10, x1=x + 8, y1=22, text="가", page=page,
                   block=0, line=0, word_no=0)


def test_block_wholly_in_one_column_is_not_a_split():
    block = Block(id="q1", glyphs=[_g(10), _g(20), _g(30)])
    assert detect_block_splits([block], [LEFT, RIGHT], page_height=800.0) == []


def test_block_straddling_two_columns_is_flagged():
    block = Block(id="q2", glyphs=[_g(10), _g(330)])  # left + right column
    splits = detect_block_splits([block], [LEFT, RIGHT], page_height=800.0)
    assert [s.block_id for s in splits] == ["q2"]
    assert splits[0].kind == "column"


def test_block_straddling_two_pages_is_flagged():
    block = Block(id="q3", glyphs=[_g(10, page=0), _g(20, page=1)])
    splits = detect_block_splits([block], [LEFT, RIGHT], page_height=800.0)
    assert splits[0].kind == "page"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_question_split_detector.py -q`
Expected: FAIL — `cannot import name 'Block'` / `'detect_block_splits'`.

- [ ] **Step 3: Write minimal implementation**

```python
# in visual/oracle.py
from dataclasses import dataclass, field

@dataclass
class Block:
    id: str
    glyphs: list  # list[WordBox]

@dataclass
class BlockSplit:
    block_id: str
    kind: str  # "column" | "page"

def _column_index(x_center: float, column_x_bounds) -> int:
    for i, (x0, x1) in enumerate(column_x_bounds):
        if x0 <= x_center <= x1:
            return i
    return -1  # outside any column (overflow handled elsewhere)

def detect_block_splits(blocks, column_x_bounds, page_height) -> list:
    splits = []
    for block in blocks:
        if not block.glyphs:
            continue
        pages = {g.page for g in block.glyphs}
        if len(pages) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="page"))
            continue
        cols = {
            _column_index((g.x0 + g.x1) / 2.0, column_x_bounds)
            for g in block.glyphs
        }
        cols.discard(-1)
        if len(cols) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="column"))
    return splits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-hwpx && .venv/bin/python -m pytest tests/test_question_split_detector.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Full suite, then commit**

```bash
cd python-hwpx && .venv/bin/python -m pytest -q
git add src/hwpx/visual/oracle.py tests/test_question_split_detector.py
git commit -m "feat(visual): 문항-split detector (column/page boundary) for exam typesetting"
```

---

### Task 4: Phase 0 spike — does Hancom honor keepWithNext in a 2-column flow? (measure-first)

**Files:**
- Create: `python-hwpx/scripts/exam_spike_keep_together.py` (a spike harness, not shipped surface)
- Create (output): `specs/003-exam-typesetting/evidence/phase0-keep-together-decision.json` + a one-paragraph verdict appended to the spec's Phase-0 section.

**Interfaces:**
- Consumes: Task 1 (`ensure_paragraph_format(break_setting=...)`), Task 2 (`columnBreak`), Task 3 (`detect_block_splits`), the form copy `scratchpad/exam/A_form.hwpx` (re-copy from NAS `/Volumes/airbot/OpenClaw/incoming/시험지/` if the scratchpad is gone), `MacHancomOracle` / `render_form_geometry` (`visual/oracle.py`).
- Produces: a decision receipt `{ "mechanism": "keepWithNext" | "columnBreak", "keepWithNext_honored": bool|null, "splits_keepwithnext": int, "splits_columnbreak": int, "render_checked": bool, "skipped": [...] }`.

- [ ] **Step 1: Build the controlled stress document**

In `exam_spike_keep_together.py`: open `A_form.hwpx`; into its body region insert ONE synthetic 문항 long enough that, placed near the bottom of column 1, it would naturally straddle into column 2 (e.g. a 발문 + 5 답항, ~18 lines). Emit it as a `Block` (group its paragraph ids). Save two variants:
  - **V1 (keepWithNext):** every paragraph of the 문항 uses a paraPr from `ensure_paragraph_format(base=<문항 style>, break_setting={"keep_with_next": True, "keep_lines": True})`.
  - **V2 (columnBreak):** same content, but the 문항's first paragraph carries `columnBreak="1"`.

- [ ] **Step 2: Render both via the Hancom oracle and measure**

```python
# pseudocode of the spike's core
geo_v1 = render_form_geometry(v1_path)   # MacHancomOracle → fitz boxes
geo_v2 = render_form_geometry(v2_path)
col_bounds = column_x_bounds_from(geo_v1)        # two ranges from page/column setup
splits_v1 = detect_block_splits([block], col_bounds, geo_v1.page_height)
splits_v2 = detect_block_splits([block], col_bounds, geo_v2.page_height)
```

- [ ] **Step 3: Write the decision receipt (no silent true)**

Rules: if the oracle is unavailable (`HWPX_MAC_ORACLE_SMOKE` unset / render not checked) → `render_checked=false`, `keepWithNext_honored=null`, `mechanism="columnBreak"` (safe default), `skipped=["mac-hancom-oracle"]`. If rendered: `keepWithNext_honored = (len(splits_v1) == 0)`; pick `mechanism="keepWithNext"` iff honored, else `"columnBreak"`.

- [ ] **Step 4: Run the spike (oracle smoke)**

Run: `cd python-hwpx && HWPX_MAC_ORACLE_SMOKE=1 .venv/bin/python scripts/exam_spike_keep_together.py` (this is a `dangerouslyDisableSandbox` GUI-automation run).
Expected: a receipt JSON is written and the chosen `mechanism` is printed. If no oracle: receipt records `unverified` + `columnBreak` default (still a successful, honest run).

- [ ] **Step 5: Record the verdict and commit the evidence**

Append the verdict (mechanism + render_checked + split counts) to `specs/003-exam-typesetting/spec.md` §"keep-together — Phase 0 spike", and commit the script.

```bash
cd python-hwpx
git add scripts/exam_spike_keep_together.py
git commit -m "feat(spike): Phase-0 keep-together mechanism measurement (keepWithNext vs columnBreak)"
```

(The receipt under `specs/003-exam-typesetting/evidence/` lives in the harness layer, not git — reference it from the spec.)

---

## Self-Review

**Spec coverage (this plan = foundation + spike only):** spec §"keep-together — grounded mechanism + Phase 0 spike" → Tasks 1, 2, 4. spec §"Oracle gate … 문항-split detector (new)" → Task 3. spec §"Engine/MCP work items" items 1–2 → Tasks 1–3 (item 3 MCP + the composer are **Plans 2–4**, see below). No spec requirement in *this plan's scope* is unmapped.

**Placeholder scan:** Task 4 is a measure-first spike whose deliverable is an evidence receipt + recorded verdict (not a unit-test pass) — this is intentional per Constitution V, not a placeholder. All code tasks (1–3) carry complete, runnable code and exact commands.

**Type consistency:** `break_setting` keys (`keep_with_next`/`keep_lines`/`page_break_before`/`widow_orphan`) and OWPML attrs (`keepWithNext`/`keepLines`/`pageBreakBefore`/`widowOrphan`) are used identically in Task 1 and Task 4. `Block`/`detect_block_splits`/`BlockSplit` signatures match between Task 3's definition and Task 4's consumption.

## Subsequent Plans (roadmap — authored after Phase 0 fixes the mechanism)

- **Plan 2 — Composer (`python-hwpx/src/hwpx/exam/`):** Exam IR + recommended exam-md → IR normalizer + compose-into-container (map IR roles → the form's existing styles: `문항자동번호넣기`/`1~5행답항`/`(보기)박스안내용`; attach the Phase-0-chosen keep mechanism; preserve 관리박스 para[0] + footer; leave `[그림N]` text placeholders). Golden test: reverse `B_submitted` body → IR → recompose → layout matches B.
- **Plan 3 — MCP surface (`hwpx-mcp-server`):** expose keep-together on `set_paragraph_format` (or a focused new tool) + a 문항-split verification tool wrapping Task 3; dry-run + revision-guard + openSafety like existing tools.
- **Plan 4 — Skill reference + leap demo:** `hwpx-skill/references/workflows-exam.md` + one routing row in `SKILL.md`; the **anti-nibble leap** = a real authored exam composed into the A form, rendered clean in Hancom (split 0, overflow 0, placeholders intact), checked in as `demo/exam-typesetting/`. Tier move on `form-fill-integrity`/`document-authoring` claimed here with the render receipt.

## Execution Handoff

**Plan complete and saved to `python-hwpx/docs/superpowers/plans/2026-06-26-exam-typesetting-p1-keep-together-foundation.md`.** This is Plan 1 of 4 (foundation + spike); it produces working, tested engine primitives and the mechanism decision that gates Plans 2–4.
