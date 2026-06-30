# M3 Document Authoring — P2: 공문 구조 hard-gate + 각주 + proofing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Checkbox steps.

**Goal:** Turn the 공문 linter into a **structural hard-gate** anchored by the real 시행문 (`seoul_sihaengmun.hwpx`): when a document is a 공문, missing spine elements (수신·발신명의·시행·공개구분·끝.) are ERRORs. Add honest `korean_proofing_status`. Investigate (time-boxed) the 각주 non-render.

**Architecture:** Extend `hwpx.tools.official_lint` to (1) read **table cells** (real 시행문 spine lives in tables), (2) accept an optional `document_type`; when it resolves to 공문, run **structure rules at ERROR severity**; existing 6 text rules stay (warnings). The authoring quality report (`inspect_document_authoring_quality`) surfaces `korean_proofing_status`.

## Global Constraints
- Spec `specs/004-document-authoring/spec.md` FR-004 (hard-gate), FR-005 (proofing), FR-006 (각주). Branch `feat/s057-document-authoring`.
- **Backward-compatible:** with NO `document_type`, `inspect_official_document_style` behaves exactly as today (no new ERRORs) — existing callers unaffected.
- **No silent true (V/IX):** proofing defaults to `unverified`; never assert 맞춤법 pass without an oracle. 각주: if it can't be made to render, report it honestly (not a fake success).
- Anchors: gold `tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx` (real 시행문) MUST pass the structure gate (table-aware); an incomplete 공문 MUST fail.

## Verified (P2 grounding, 2026-06-27)
- `lint(seoul_sihaengmun)` via doc.paragraphs sees spine `['끝.']` only; raw XML has `수신·경유·시행·접수·공개·끝.` → **table-aware reading required**.
- Composed 공문 (full gyeolmun) has spine in body paragraphs `수신·발신·시행·공개·끝.`; current lint fires only `end-marker` (because 끝. is mid-body, 결문 follows) → **end-marker must allow 결문 after 끝. for 공문**.

---

### Task 1: Table-aware paragraph extraction
**Files:** `src/hwpx/tools/official_lint.py`; `tests/test_official_lint_tableaware.py` (new)
- [ ] **Step 1:** Failing test — `inspect_official_document_style("tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx")` summary `paragraph_count` should include table-cell text (assert a paragraph containing "수신" is present in the extracted set via a new `_paragraphs_from_path` that walks table cells). Run → FAIL (currently 2 paras, no 수신).
- [ ] **Step 2:** Implement — in `_paragraphs_from_path`/`_paragraphs_from_source` for `HwpxDocument`, also collect text from table cells (iterate `document` tables → rows → cells → paragraph text), preserving document order as best-effort (append cell texts). Keep existing paragraph collection.
- [ ] **Step 3:** Run → PASS (수신/발신/시행/공개 now visible). Existing lint tests still green (table text is additive). **Step 4: Commit** (`feat(m3-p2): table-aware text extraction in official lint`).

### Task 2: 공문 structure hard-gate (document_type-aware)
**Files:** `src/hwpx/tools/official_lint.py`; `tests/test_official_lint_gongmun_gate.py` (new)
- [ ] **Step 1:** Failing tests:
  - `inspect_official_document_style(gold_path, document_type="공문")` → `pass=True` for the structure rules (수신·발신명의·시행·공개구분·끝. all present; spine satisfied). [Existing text warnings may still list, but no structure ERROR.]
  - A 공문 plan/doc missing 발신명의 + 시행 → structure ERRORs `missing-balsinmyeongui`, `missing-sihaeng`.
  - No `document_type` → no structure rules (backward compat).
- [ ] **Step 2:** Implement — add `document_type: str | None = None` param; resolve via the same 공문 alias set. When 공문, add `_inspect_gongmun_structure(paragraphs)` returning ERROR violations for missing: 수신(두문), 발신명의(결문), 시행/시행일(결문), 공개구분(결문), 끝.(본문 종결). Refine `_inspect_end_marker`: when document_type 공문, 끝. need only be present after 붙임/본문 and BEFORE the 결문 tail (do not require 끝. to be the final non-empty paragraph). Recompute `pass` = (no ERROR-severity violations).
- [ ] **Step 3:** Run → PASS (gold passes structure; incomplete fails). Full lint suite green. **Step 4: Commit** (`feat(m3-p2): 공문 structure hard-gate (수신·발신명의·시행·공개구분·끝.) anchored by 시행문`).

### Task 3: Wire the gate into authoring quality + korean_proofing_status (FR-005)
**Files:** `src/hwpx/authoring.py` (`inspect_document_authoring_quality`); `tests/test_authoring_profile_routing.py` (extend)
- [ ] **Step 1:** Failing test — `inspect_document_authoring_quality(composed_gongmun, plan=plan)` returns `korean_proofing_status == "unverified"` and includes a `gongmun_structure` report when document_type 공문.
- [ ] **Step 2:** Implement — pass plan.document_type into `inspect_official_document_style`; add `korean_proofing_status` field (default `"unverified"`; if an LLM-proof flag is set in the plan/metadata, `"llm_proofed_not_oracle_verified"`). Never `"passed"`.
- [ ] **Step 3:** Run → PASS. **Step 4: Commit** (`feat(m3-p2): authoring quality surfaces 공문 structure + korean_proofing_status`).

### Task 4: 각주 investigation (time-boxed ≤1 spike)
**Files:** scratch spike; outcome → fix in `document.py`/profile OR honest note.
- [ ] **Step 1:** Inspect the footnote XML our `add_footnote` emits vs a real Hancom footnote (compare `<hp:footNote>`/inline `<hp:ctrl>` + the section footNote config). Determine why Hancom drops it (missing section footnote shape / charPr / instId).
- [ ] **Step 2:** If a small fix makes it render (oracle smoke confirms footnote text in PDF) → apply + test. **If not quick** → honest-defer: document the limitation in evidence + report footnote authoring as `unverified` (do NOT claim it works). Commit either the fix (`fix(m3-p2): footnote renders in Hancom`) or the note (`docs(m3-p2): footnote authoring honest-deferred`).

### Task 5: Oracle smoke — gate + gold (gated)
- [ ] Confirm (gated `HWPX_MAC_ORACLE_SMOKE`) the gold 시행문 still opens-clean and our composed 공문 passes the structure gate. Extend the existing oracle smoke if useful. Commit.

## Self-Review
- FR-004 → T1+T2 (table-aware structure hard-gate, 시행문 anchor). FR-005 → T3 (korean_proofing_status, honest). FR-006 → T4 (각주, fix-or-honest-defer). Backward-compat guarded (no document_type → no new ERRORs).
- Types: `inspect_official_document_style(source, *, document_type=None)`; structure rules ERROR severity; `pass = no ERROR`.

## Execution note
TDD per task; oracle steps serial + dangerouslyDisableSandbox. On completion: complete_phase PH-c1423cc07a70 → P3 (oracle wiring into quality gate).
