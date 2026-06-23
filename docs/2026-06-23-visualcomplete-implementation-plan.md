# HWPX VisualComplete — Implementation Plan v0.3 (re-baselined by measurement)

**Audience:** the engineer/agent continuing this on the Windows + 한컴(COM) machine.
**Read this first; it is self-contained.** It supersedes the v0.1 "VisualComplete
Engine Spec" — every place the two disagree, this plan wins, because it is grounded
in an actual Hancom-oracle measurement that v0.1 never ran.

> **v0.3 change:** added §0.0 "The verification ceiling" — makes the
> oracle-portability limit an explicit docx-grade constraint, and defines tiered
> assurance for environments without Hancom. (Still deferred, to fill on arrival:
> font-metric FormFit + mail-merge-at-scale, field/dynamic-content recalculation.)

North star: **DOCX-grade stability for HWPX.** A write succeeds only when the
result is `visualComplete=true` — opens clean in Hancom, content correct, edits
preserve original style/tables, form values fit their slots, nothing overlaps,
new docs look human-made.

---

## 0.0 The verification ceiling (read before believing "docx-grade")

**docx-grade stability is reachable, but its proof is not portable — and that is a
structural constraint, not an implementation detail.**

Why docx tooling is stable: it leans on **LibreOffice** — a faithful,
Word-compatible renderer that is free, headless, and runs on any CI/OS. So "does
this docx render correctly" is verifiable *everywhere, cheaply*.

HWPX has **no such renderer.** The only faithful oracle is **Hancom (한글)
itself** — Windows-only, GUI-rooted, licensed, driven via COM. There is no free
headless HWPX renderer that matches Hancom's line-breaking/layout. Therefore:

- `visualComplete=true` is a **render-backed guarantee only where Hancom runs.**
  Everywhere else it necessarily degrades to *structural plausibility*
  (integrity + XML + OPC/ID + layout lint + open-safety + FormFit measurement) —
  which is "probably fine," **not** "verified."
- This is the single biggest gap between HWPX and docx, and **no amount of code in
  this plan removes it.** It can only be *managed honestly*.

### Assurance tiers (the engine MUST distinguish these, never blur them)

| tier | environment | what runs | what `visualComplete` may claim |
|---|---|---|---|
| **Oracle-verified** | Windows + 한컴 (COM) | full structural + **Hancom render diff/overlap/overflow** | `visual_complete=true`, `render_checked=true` — true docx-grade |
| **Structural** | no Hancom (Linux/cloud/macOS) | integrity, XML, OPC/ID, layout lint, open-safety, FormFit measurement | `render_checked=false`; **`visual_complete` MUST be `unverified`, never `true`** — surfaced as "open-safe + structural," not docx-grade |

**Engine contract (binding on Phase A/B):**
- `visual_complete=true` **requires** `render_checked=true`. Off-oracle, the top
  achievable result is an explicitly-labeled *structural* pass — `ok` may be
  `true`, but `visual_complete` is reported `unverified`, never silently `true`.
- An explicit `allow_unverified_visual_complete` escape hatch may exist for
  expert/batch use, but it must be opt-in and recorded in the report.

**Product implication:** to deliver docx-grade in production, a **Hancom render
worker (Windows/COM) must be part of the topology** — as a CI gate and/or a
batch verification stage. Plan the deployment around the oracle's location, not
the other way around. (For high-volume mail-merge this becomes a throughput
problem — see the deferred "template-once-measure" note in Phase C.)

---

## 0. Ground truth — what is already TRUE (do not redo)

This was measured on 2026-06-23 with the Hancom COM oracle, 6 genuine
Hancom-saved docs × 3 mutations (17 valid pairs). See
`scripts/visualcomplete-baseline/README.md` → "Result".

1. **lineSegArray invalidation is CLOSED.** Verdict: `lineseg_matters` (stale
   cache → 글자 겹침 on text growth; reproduced visually in Hancom). The fix was
   already shipped for the save path and the one leaking path is now fixed:
   - Save path: `opc/package._strip_section_layout_caches` runs inside
     `package.write()`, for **re-serialized (edited) sections**. (NOT "every
     section unconditionally" — that earlier claim was wrong. Untouched sections
     keep their caches; harmless, because HWPX section breaks are hard layout
     boundaries.) Correct as-is — **do not touch.**
   - Byte path: `patch.py` ZIP-splice was leaking; fixed in commit `00ba546`
     (`_strip_paragraph_layout_cache`, targeted to the patched paragraph only).
     Regression: `tests/test_kordoc_absorption.py::
     test_byte_preserving_patch_strips_only_patched_paragraph_layout_cache`.
   - Full suite green (757 passed). **Do not reopen lineseg work** unless a new
     oracle measurement shows a regression.

2. **A working render oracle EXISTS** as a one-off measurement harness:
   `scripts/visualcomplete-baseline/` — `hancom_render.ps1` (.hwpx→PDF via COM),
   `rasterize_score.py` (PDF→diff/overlap→verdict), `overlap_detect.py`
   (`diff_ratio`, `overlap_score`), `lineseg_toggle.py` (ON/OFF control),
   `run_pairs.py`, `make_injected_fixture.py`. It is NOT yet a reusable gate —
   promoting it is Phase A.

3. **Current engine state (what's missing):**
   - Multiple independent save paths (`document.py` save, `patch.py`,
     `template_formfit.py`, `builder/`) — **no single SavePipeline**. The
     patch.py leak above is exactly what a bypass looks like.
   - **No FormFit / text-measurement** — form fill is raw insertion.
   - Builder generates **from-scratch XML** — no template/fragment reuse.
   - Validation exists (`tools/package_validator.py`, `tools/validator.py` XSD,
     `tools/id_integrity.py`) but is **called ad-hoc, not a mandatory gate**.

---

## 1. Guardrails (non-negotiable, apply to every phase)

- **Measure-first.** Hancom is the only authoritative arbiter. Validate with
  REAL Hancom-saved docs through the oracle, not synthetic fixtures or
  structural lint alone. (This is the discipline that already corrected one
  wrong assumption — keep it.)
- **No raw-XML editing surface for the model.** Operations only (§Appendix B).
  Never expose `raw_xml_replace` / `arbitrary_xpath_mutation` in the user-facing
  MCP namespace.
- **No SavePipeline bypass.** Every write path must funnel through the one gate
  (Phase B). The patch.py leak proves bypasses cause real visual bugs.
- **Layout cache ≠ content.** Byte-preserve unmodified parts/paragraphs; a
  modified paragraph's stale `<hp:linesegarray>` is NOT preserved.
- **XSD is soft lint, not a hard gate.** Hancom acceptance + OPC/ID integrity +
  visualComplete take priority. Promote XSD to hard fail only in an explicit
  `strict` mode.
- **HTML/CSS is optional design/preview only** (Phase H), never the HWPX
  writer. Final HWPX is always produced by `python-hwpx` native code.
- **Do not rewrite the engine** into JS/Rust. Upgrade `python-hwpx` in place.
- **Scope discipline.** Touch only what a phase requires; don't "clean up"
  adjacent code.

---

## 2. Phases, in priority order

Each phase: **Goal · Why now · Tasks · File targets · Acceptance (oracle-gated)**.
Do them in order; each builds on the previous. Commit + push after each; keep the
full test suite green.

### Phase A — Promote the oracle into a reusable VisualComplete gate  ⭐ START HERE

**Goal.** Turn the one-off harness into a reusable verifier: given a before/after
`.hwpx` pair (or a single new doc), render through Hancom and return a
`VisualReport` (JSON) judging overlap / overflow / out-of-mask change.

**Why now.** This is the linchpin that makes "docx-grade" *verifiable*. Every
later phase (FormFit overflow decisions, new-doc aesthetics, conformance) is
judged by it. It is ~80% built already.

**Tasks.**
1. Extract the COM render + rasterize + detect logic from
   `scripts/visualcomplete-baseline/` into a small reusable module, e.g.
   `src/hwpx/visual/oracle.py` with a clean API:
   ```python
   class RenderOracle:                 # adapter; Hancom COM on Windows
       def available(self) -> bool: ...
       def render_pdf(self, hwpx_path: str) -> str | None: ...   # -> pdf path

   def visual_check(
       before_hwpx: str | None,        # None for new-doc generation
       after_hwpx: str,
       *, oracle: RenderOracle,
       edit_mask: "EditMask | None" = None,
       diff_eps: float = 0.005,
   ) -> "VisualReport": ...
   ```
2. Define `VisualReport` (§Appendix A) and `EditMask` (regions the edit was
   allowed to change; everything outside must stay pixel-stable).
3. Keep the COM call isolated and swappable (a `RenderOracle` that returns
   `available()==False` off-Windows, so the engine degrades to structural-only
   with a warning rather than crashing).
4. CLI: `python -m hwpx.visual.oracle --before a.hwpx --after b.hwpx --out report/`.

**File targets.** `src/hwpx/visual/{__init__,oracle,diff,masks,detectors,report}.py`;
reuse `overlap_detect.py` logic. Keep `hancom_render.ps1` as the COM backend the
Python adapter shells out to (or port to `pywin32`/`comtypes` if you prefer a
pure-Python adapter — your call on the Windows box).

**Acceptance (oracle-gated).**
- On the existing measurement corpus, `visual_check` reproduces the harness's
  verdicts (lineseg_matters cases flagged, hancom_relayouts cases pass).
- A deliberately-overflowed form fill is judged `ok=false` with
  `overflow_detected=true`; a clean edit is `ok=true`.
- Off-Windows: `oracle.available()==False`, `visual_check` returns
  `render_checked=false` + warning, never raises.
- A regression test exercises the structural path (no Hancom) end-to-end.

---

### Phase B — SavePipeline + QualityPolicy + VisualCompleteReport (one gate, no bypass)

**Goal.** Every write/save funnels through one `SavePipeline` that runs
validation → (optional) visual gate → composes a `VisualCompleteReport`, and
returns `ok=false` (rolling back / saving only as debug artifact) when
`require_visual_complete` and the result isn't visualComplete.

**Why now.** The patch.py leak proved independent save paths drift. Centralizing
is how lineseg-style bugs stop recurring and how every later phase reports
uniformly.

**Tasks.**
1. Add `QualityPolicy` and `VisualCompleteReport` (§Appendix A).
2. Add `SavePipeline.run(package, ledger, assertions, output_path, quality)`:
   integrity → XML well-formedness → OPC/ref/ID → semantic/form assertions →
   layout lint (Phase D) → open-safety → visual oracle (Phase A, if
   available/required) → aesthetic (Phase E, if profiled) → compose → atomic
   save or rollback.
3. Route the existing paths through it: `document.py` save, `patch.py`,
   `template_formfit.py`, `builder/`. **Goal: zero bypassing write paths.**
4. `DirtyLayoutLedger` (§Appendix A) — note its purpose is now *the edit mask
   for the visual gate* (what changed → where to look), NOT driving lineseg
   invalidation (already handled at save). Keep it lightweight.

**File targets.** `src/hwpx/quality/{__init__,save_pipeline,policy,report}.py`;
edits to the four save paths.

**Acceptance.**
- Every public write returns a `VisualCompleteReport`; `requireVisualComplete`
  works; an inventory test asserts **0 write paths bypass SavePipeline**.
- All existing tests still green (the gate is transparent when policy is lenient).

---

### Phase C — FormFit engine (values fit their slots)  ⭐ highest user-visible value

**Goal.** Form fill stops being raw insertion. A value is measured against its
cell/field box and wrapped / shrunk / failed per `FitPolicy`. Success =
"value sits inside the slot and looks right," not "text was inserted."

**Why now.** The measurement's headline failure (방송신청서 title overflowing its
slot) is a FormFit problem. With Phase A you can finally *validate* overflow
decisions against Hancom instead of guessing.

**Tasks.**
1. `FitPolicy` / `FitResult` (§Appendix A).
2. Conservative text measurement (`form_fit/measure.py`): per-script average
   advance widths (Hangul / Latin upper-lower / digit / space / punctuation) ×
   font size, vs. cell width − margins − indent, accounting for line spacing and
   `maxLines`. Start conservative; **when uncertain, defer to the oracle or fail
   when `overflow=fail`.**
3. Modes: `keep / wrap / shrink / wrap_then_shrink / expand_row /
   truncate_with_report / fail_on_overflow`.
4. Wire into `fill_form_field` / `setTableCell`; record a `DirtyLayoutRange`
   when fit changes style; emit a `FormReport`.

**File targets.** `src/hwpx/form_fit/{__init__,policy,engine,measure,report}.py`;
edits to `document.py` form-fill, `form_fill.py`.

**Acceptance (oracle-gated).**
- Long address wraps or shrinks; with `overflow=fail` and a genuinely-too-long
  value → `ok=false` + `FIELD_OVERFLOW` + `suggestedRetry`.
- **Oracle confirms:** filled cells show no overflow/overlap in the Hancom
  render for the pass cases; the fail cases really did overflow.
- Until the oracle backs a `fail`, default `overflow=warn` for any field whose
  measurement confidence is low (measurement honesty over false precision).

**Deferred (v0.3 backlog, fill on arrival):** (a) promote measurement to real font
metrics (HarfBuzz + bundled 한컴 fonts) so `fail` is trustworthy without rendering
every fill; (b) **template-once-measure** for mail-merge — measure the slot on the
template a single time, then trust it for N batch fills (the per-doc oracle is too
slow at volume; see §0.0). Both are out of scope for the first FormFit pass.

---

### Phase D — LayoutLint / structural visual smoke (renderer-less guard)

**Goal.** Catch likely visual problems WITHOUT a renderer, so non-Windows CI and
fast pre-checks still have teeth.

**Tasks.** dirty-range ↔ (already-stripped) lineseg consistency; stale-cache
detection (`textpos > text length`, already a validator hard error — wire it in);
overflow-risk heuristic for un-fitted long cell values; table structural sanity.
Hard-fail in SavePipeline on: layout mutation with no ledger entry; required form
field empty; `overflow=fail` with detected overflow; XML not well-formed.

**File targets.** `src/hwpx/layout/lint.py` (+ `ledger.py`, `report.py`).

**Acceptance.** The lint catches the seeded overflow/stale cases without a
renderer; clean docs pass; it never contradicts the Phase-A oracle on the shared
corpus (lint may be stricter, never wronger).

---

### Phase E — Template/Profile builder (new docs look human-made)

**Goal.** New documents are composed from **verified Hancom-saved templates +
fragments**, not imagined XML. Production mode forbids the minimal from-scratch
builder.

**Tasks.** profile loader + fragment library; profiles `official_notice`,
`report`, `application_form` (each = a real Hancom-saved `template.hwpx` +
`profile.json` + fragment XML snippets harvested from Hancom-saved docs);
`DocumentPlan` (§Appendix B) → native lowering; `styleCoverage` check; forbid
minimal-XML fallback in production mode (allow in debug with a warning).

**File targets.** `src/hwpx/design/{__init__,profile,fragments,composer,validator}.py`;
`src/hwpx/design/profiles/<id>/{template.hwpx,profile.json,fragments/*.xml}`.

**Acceptance (oracle-gated).** 공문/보고서/신청서 fixtures generate; open-safe;
`styleCoverage ≥ threshold`; **the Hancom render looks like a human document**
(margins/title/table padding sane per Phase-A new-doc checks).

---

### Phase F — MCP / plugin quality contract

**Goal.** No model can bypass the gate. Every write MCP tool takes a `quality`
block and returns a `VisualCompleteReport`; `visualComplete=false ⇒ ok=false`
with a structured `suggestedRetry`. Add capability/version handshake
(`core/mcp/plugin` versions + hash) that fails closed on skew. Update
`hwpx_doctor`. Document "no raw XML" in the plugin.

**File targets.** `hwpx-mcp-server` write tools; plugin docs.

**Acceptance.** MCP write tools use SavePipeline; skew fails closed; a model sees
`FIELD_OVERFLOW`/`STALE_LINESEG_DETECTED`/… and can retry from the structured
error.

---

### Phase G — Conformance corpus + badges (make "docx-grade" measurable)

**Goal.** Turn "docx-grade" into numbers. Public + private corpora, golden
reports, a conformance runner, and badge tiers with **explicit thresholds**:
- **Open-Safe** — opens in Hancom.
- **Semantic-Safe** — content assertions pass.
- **Form-Safe** — form fields filled + fit, oracle-confirmed.
- **VisualComplete** — open + semantic + form + layout + visual all pass on
  ≥ X% of corpus, overflow rate 0 on the form set.

**Acceptance.** `conformance run` produces per-tier pass rates; a CI job tracks
them over time; regressions are visible as a number, not a vibe.

---

### Phase H — (OPTIONAL, deferred) HTML/CSS design layer

Authoring/preview only: `DocumentPlan` → semantic HTML → print.css → reference
PNG/PDF → DOM-box `DesignIR`. **Not** an HWPX converter, **not** a fit oracle
(CSS px ≠ Hancom line-breaking). Build only after A–E land, and only if a real
authoring need appears. Keep it out of the stability path.

---

## 3. Definition of Done (re-baselined, measurable)

1. Zero write paths bypass SavePipeline (asserted by test).
2. Every public write returns a `VisualCompleteReport`.
3. lineseg: save path + byte path both strip on the modified paragraph;
   regression tests guard both. *(already true — keep green.)*
4. Form fill performs fit, not raw insertion; `overflow=fail` is oracle-backed.
5. New docs are template/fragment-based in production mode.
6. XSD is soft lint unless `strict`.
7. MCP write tools never report `visualComplete=false` as success.
8. The Phase-A oracle gates the above on a real Hancom-saved corpus, with badge
   thresholds met.
9. **Assurance is tiered, never blurred (§0.0):** `visual_complete=true` requires
   `render_checked=true`; without the Hancom oracle the engine reports an
   explicitly-labeled *structural* pass (`visual_complete=unverified`), never a
   silent `true`. docx-grade is claimed only on the oracle-verified tier.

---

## Appendix A — Core data models (condensed; carry forward, corrected)

```python
@dataclass
class QualityPolicy:
    require_open_safety: bool = True
    require_visual_complete: bool = True
    # NOTE: lineseg invalidation is already handled at save; this knob now mainly
    # scopes the edit mask for the visual gate, not the strip itself.
    layout_invalidation: Literal["none","paragraph","following","story","document"] = "story"
    render_check: Literal["off","auto","required"] = "auto"   # auto = use oracle if available
    xsd_mode: Literal["off","lint"] = "lint"                  # soft by default
    overflow_policy: Literal["fail","warn","truncate"] = "fail"
    preserve_unmodified_parts: bool = True
    allow_expert_unsafe: bool = False

@dataclass
class VisualCompleteReport:
    ok: bool
    output_path: str | None
    visual_complete: bool
    open_safety: "OpenSafetyReport"
    semantic: "SemanticReport"
    form: "FormReport"
    layout: "LayoutReport"
    visual: "VisualReport"
    aesthetic: "AestheticReport"
    warnings: list[str]
    errors: list["QualityError"]

@dataclass
class VisualReport:                 # produced by Phase A
    ok: bool
    render_checked: bool            # False off-Windows -> degrade + warn, never crash
    original_render: str | None
    output_render: str | None
    diff_image: str | None
    unexpected_diff_outside_mask: bool
    overlap_detected: bool
    overflow_detected: bool
    table_break_detected: bool
    page_count_changed: bool | None
    warnings: list[str]
    errors: list[str]

@dataclass
class DirtyLayoutRange:             # now = "what changed" for the edit mask
    part: str; story_id: str
    story_type: Literal["body","header","footer","footnote","endnote","table_cell","textbox","unknown"]
    start_paragraph: int | None; end_paragraph: int | None
    table_path: list[int] | None; cell_path: list[tuple[int,int]] | None
    reason: Literal["text_replaced","text_inserted","text_deleted","style_changed",
                    "paragraph_style_changed","table_cell_changed","table_structure_changed",
                    "image_changed","section_changed","form_filled","builder_generated"]
    policy: Literal["none","paragraph","following","story","document"]

@dataclass
class FitPolicy:
    mode: Literal["keep","wrap","shrink","wrap_then_shrink","expand_row",
                  "truncate_with_report","fail_on_overflow"] = "wrap_then_shrink"
    max_lines: int | None = None
    min_font_pt: float = 8.0
    max_font_pt: float | None = None
    allow_row_expand: bool = False
    overflow: Literal["fail","warn","truncate"] = "fail"

@dataclass
class FitResult:
    ok: bool; value: str; applied_value: str; applied_style_changes: dict
    lines: int | None; font_pt: float | None
    overflow_detected: bool; truncated: bool
    warnings: list[str]; errors: list[str]
```

Error codes (structured, retry-able): `VISUAL_COMPLETE_FAILED`,
`STALE_LINESEG_DETECTED`, `LAYOUT_MUTATION_WITHOUT_LEDGER`, `FIELD_OVERFLOW`,
`REQUIRED_FIELD_MISSING`, `OPEN_SAFETY_FAILED`, `REFERENCE_INTEGRITY_FAILED`,
`CAPABILITY_SKEW`, `RENDER_ORACLE_UNAVAILABLE`, `PROFILE_REQUIRED`,
`STYLE_COVERAGE_TOO_LOW`.

## Appendix B — Operation API & schemas (model-facing; raw XML forbidden)

The LLM emits **operations** and **plans**, never XML.

```jsonc
// hwpx.operations.v1 — edit an existing doc
{ "ops": [
  { "op": "replacePlaceholder", "placeholder": "{{성명}}", "value": "홍길동" },
  { "op": "fillField", "field": "주소", "value": "...",
    "fitPolicy": { "mode": "wrap_then_shrink", "maxLines": 2, "minFontPt": 8.5, "overflow": "fail" } },
  { "op": "setTableCell", "selector": { "nearText": "신청인" }, "row": 1, "col": 2, "value": "홍길동" },
  { "op": "replaceText", "find": "2025년", "replace": "2026년" },
  { "op": "replaceImage", "selector": { "altText": "서명" }, "imagePath": "sig.png" },
  { "op": "cloneTableRow", "selector": { "nearText": "참석자" }, "templateRow": 2,
    "values": [["홍길동","팀장"],["김철수","대리"]] }
] }
```
Per-op dirty/fit policy: `fillField`→form_filled + **FitEngine required**;
`setTableCell`→table_cell + FitEngine/overflow policy; `cloneTableRow`→
table_structure_changed + table layout lint; `replace*`→text_replaced;
section/page change→document.

```jsonc
// hwpx.document_plan.v1 — generate a new doc (Phase E lowers this natively)
{ "profile": "official_notice", "title": "2026학년도 운영 계획",
  "blocks": [
    { "type": "paragraph", "role": "body", "text": "다음과 같이 운영 계획을 수립합니다." },
    { "type": "table", "role": "info", "columns": ["구분","내용","비고"],
      "rows": [["일시","2026. 6. 23.",""],["장소","본교 회의실",""]] }
  ] }
```

```jsonc
// hwpx.form_schema.v1 — field detection order: 누름틀/필드/북마크 > {{placeholder}} >
// 표 라벨-값 패턴 > 주변텍스트 anchor > (최후) 시각좌표 추정
{ "fields": [ { "id": "applicant_name", "label": "성명", "kind": "text", "required": true,
  "anchor": { "part": "Contents/section0.xml", "story": "body", "tablePath": [2], "cell": [1,1], "paragraph": 0 },
  "stylePolicy": "inherit",
  "fitPolicy": { "mode": "wrap_then_shrink", "maxLines": 1, "minFontPt": 9.0, "overflow": "fail" } } ] }
```

## Appendix C — Validation policy

**Hard:** ZIP/package integrity · XML well-formedness · required entries ·
OPC/content-types/relationships · ID/reference ledger · BinData/image/style/
numbering/header-footer/section refs · table structural sanity · editor-open
safety · layout lint · semantic & form assertions · visualComplete checks.
**Soft (warn):** XSD/schema · OWPML/DVC compat · namespace version mismatch ·
spec drift. Promote XSD to hard only in `strict` mode.

## Appendix D — Existing assets to build on

- `scripts/visualcomplete-baseline/` — the oracle harness + its README "Result".
- `src/hwpx/opc/package.py` — save-path lineseg strip (correct; don't touch).
- `src/hwpx/patch.py` — byte-path strip fix (`_strip_paragraph_layout_cache`).
- `src/hwpx/tools/package_validator.py`, `tools/validator.py` (XSD),
  `tools/id_integrity.py` — validators to wire into SavePipeline.
- `scripts/hancom_com_open_verify.ps1` — original COM open/text-extract pattern.

---

### Suggested commit cadence
One phase = one (or few) commits, suite green each time, push to `main` so it can
be reviewed from any machine. Phase A first.
