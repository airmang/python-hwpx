# M3 Document Authoring — P0: Measure-First Spike + 공문 Gold Corpus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De-risk M3 by **measuring** (via the real Mac Hancom oracle) that the authoring building blocks open clean, harvest the missing **가정통신문** profile, and curate a **regulation-clean 공문 gold corpus** — producing receipts that shape the P1–P5 task design.

**Architecture:** New documents are composed from **verified Hancom-saved profiles + harvested fragments** (`hwpx.design.compose` lowering a `DocumentPlan` onto a `Profile`), never imagined XML. P0 only *measures and curates* — no product behavior change yet. The Mac Hancom oracle (`resolve_oracle` → `MacHancomOracle.render_pdf`) is the opens-clean truth.

**Tech Stack:** python-hwpx (`hwpx.design`, `hwpx.visual.oracle`, `hwpx.tools.official_lint`, `hwpx.document`), Mac Hancom GUI via osascript, `uv run python -m pytest`, fitz (PyMuPDF) for render verification.

## Global Constraints

- **Spec:** `specs/004-document-authoring/spec.md` (M3 / Wily S-057). This plan implements **P0** only.
- **Branch:** all code/commits on `feat/s057-document-authoring` (never `main` — harness rule). python-hwpx is clean at `9237454`.
- **Oracle truth (Constitution IV/V):** `opens-clean` is asserted ONLY when `MacHancomOracle.render_pdf` returns a PDF and fitz can open it. No oracle available → `unverified`, never silent true. Oracle runs need `dangerouslyDisableSandbox` (GUI/Accessibility).
- **Clean-room (VIII):** vendored corpus files carry a `NOTICE.md` with upstream attribution; no code copied.
- **No product behavior change in P0** — measurement scripts live under `scratch/` or `docs/.../evidence/`; the only committed artifacts are the gold corpus (+NOTICE), the harvested `home_notice` profile, and the P0 decision receipt.
- **Measure-first:** P1–P5 detailed plans are authored only AFTER this P0 receipt lands (do not pre-plan on unmeasured premises).

---

### Task 1: Branch + profile render baseline (official_notice, report)

**Files:**
- Create: `specs/004-document-authoring/evidence/p0-profile-render-verdicts.json`
- Scratch (uncommitted): `scratchpad/p0/render_baseline.py`

**Interfaces:**
- Consumes: `hwpx.design.load_profile(id)`, `hwpx.design.compose(plan, profile=...)` / `compose_bytes`, `hwpx.design.available_profiles()`, `hwpx.visual.oracle.resolve_oracle()`, `MacHancomOracle.render_pdf(hwpx_path, out_pdf)`.
- Produces: a verdict JSON `{profile_id: {composed_ok, render_pdf_path|null, fitz_open_ok, text_chars, verdict: opens_clean|unverified}}` consumed by Task 5.

- [ ] **Step 1: Create branch**

Run: `git -C /Users/wilycastle/Code/projects/hwpx/python-hwpx checkout -b feat/s057-document-authoring`
Expected: `Switched to a new branch 'feat/s057-document-authoring'`

- [ ] **Step 2: Confirm the compose/profile API signatures (no assumptions)**

Run: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -c "import inspect, hwpx.design as d; print(inspect.signature(d.compose)); print(inspect.signature(d.load_profile)); print(d.available_profiles())"`
Expected: prints `compose(...)` + `load_profile(profile_id)` signatures and `['application_form', 'official_notice', 'report']`.

- [ ] **Step 3: Write the render-baseline measurement script**

`scratchpad/p0/render_baseline.py`: for each of `official_notice`, `report` — `load_profile(id)`, build a minimal `DocumentPlan` (title + 2–3 body paragraphs + one heading), `compose(...)` to a temp `.hwpx`, then `resolve_oracle()` → `render_pdf` to a temp PDF, open the PDF with fitz and count text chars. Record results into the verdict dict. Treat any oracle-unavailable / render-None as `verdict="unverified"` (never crash, never silent true).

- [ ] **Step 4: Run the baseline against the real Mac Hancom oracle**

Run (needs `dangerouslyDisableSandbox`): `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python scratchpad/p0/render_baseline.py`
Expected: for each profile, `composed_ok=true`; `render_pdf_path` non-null and `fitz_open_ok=true` (opens-clean) OR a clearly-logged `unverified` if the oracle is unavailable.

- [ ] **Step 5: Write the verdict receipt + commit (evidence only)**

Write the verdict dict to `specs/004-document-authoring/evidence/p0-profile-render-verdicts.json`.
Run: `git add specs/004-document-authoring/evidence/p0-profile-render-verdicts.json && git commit -m "spike(m3-p0): profile render baseline (official_notice, report) oracle verdicts"`
(specs/ is git-外 Harness layer in the workspace root; if python-hwpx does not track specs/, store the receipt under `python-hwpx/docs/superpowers/evidence/` instead and commit there.)

---

### Task 2: 결문 메타 + 각주 opens-clean spike

**Files:**
- Scratch: `scratchpad/p0/gyeolmun_footnote_spike.py`
- Append to: `specs/004-document-authoring/evidence/p0-profile-render-verdicts.json` (new key `gyeolmun_footnote`)

**Interfaces:**
- Consumes: `hwpx.design.compose`, `hwpx.document.HwpxDocument` + paragraph `.add_footnote(...)` (`src/hwpx/document.py:1644`), oracle as Task 1.
- Produces: verdict `{gyeolmun_footnote: {render_pdf_path, fitz_open_ok, footnote_rendered_hint, verdict}}` for Task 5.

- [ ] **Step 1: Confirm add_footnote signature**

Run: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -c "import inspect; from hwpx.document import HwpxDocument; import hwpx.oxml._document_impl as m; print([n for n in dir(m) if 'footnote' in n.lower()])"`
Expected: prints footnote-related names (confirm `add_footnote` exists and its params).

- [ ] **Step 2: Write the spike script**

`scratchpad/p0/gyeolmun_footnote_spike.py`: compose an `official_notice` doc whose body carries 결문-style lines (발신명의 / `생산등록번호: …` / `시행일: 2026. 6. 27.` / `공개구분: 공개`) and add ONE footnote to a body paragraph via `add_footnote`. Save `.hwpx`, render via Mac Hancom, fitz-open, and check the PDF text contains the 결문 tokens + footnote marker.

- [ ] **Step 3: Run the spike (oracle)**

Run (with `dangerouslyDisableSandbox`): `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python scratchpad/p0/gyeolmun_footnote_spike.py`
Expected: `fitz_open_ok=true` and 결문 tokens present in extracted text (opens-clean with 결문+각주). Otherwise log `unverified` + the failure mode.

- [ ] **Step 4: Append verdict + commit**

Run: `git add specs/004-document-authoring/evidence/p0-profile-render-verdicts.json && git commit -m "spike(m3-p0): 결문 메타 + 각주 opens-clean verdict"`

---

### Task 3: 가정통신문 (home_notice) profile harvest

**Files:**
- Create: `src/hwpx/design/profiles/home_notice/{profile.json,template.hwpx,fragments/*.xml}` (via harvester)
- Source (input): a genuine 가정통신문 `.hwpx` (owner-provided or sourced; recorded in NOTICE)

**Interfaces:**
- Consumes: `hwpx.design.harvest` (`src/hwpx/design/harvest.py` — writes `profiles/<id>/` from a genuine `.hwpx`), `load_profile`, oracle.
- Produces: a loadable `home_notice` profile + a render verdict for Task 5; `available_profiles()` now includes `home_notice`.

- [ ] **Step 1: Confirm the harvester entrypoint + obtain a real source**

Run: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -c "import hwpx.design.harvest as h; print([n for n in dir(h) if not n.startswith('_')])"`
Expected: prints the harvest function name + signature. **BLOCKER CHECK:** a genuine 가정통신문 `.hwpx` must exist. Look under `/Volumes/airbot/OpenClaw/incoming/` and ask the owner if none is found. Do NOT synthesize one (Constitution VIII — harvest from a real doc only).

- [ ] **Step 2: Harvest the profile**

Run: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -m hwpx.design.harvest <source.hwpx> home_notice` (use the confirmed entrypoint).
Expected: `src/hwpx/design/profiles/home_notice/` created with `profile.json` (incl. `source_basename`), `template.hwpx`, fragments.

- [ ] **Step 3: Load + render the harvested profile (oracle)**

Run (oracle): `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -c "import hwpx.design as d; d.load_profile('home_notice')"` then compose+render via the Task 1 baseline script extended to `home_notice`.
Expected: `load_profile('home_notice')` succeeds; composed doc `opens-clean` in Hancom (or logged `unverified`).

- [ ] **Step 4: Commit the harvested profile + NOTICE**

Add a `NOTICE` entry (source provenance) for the 가정통신문 source.
Run: `git add src/hwpx/design/profiles/home_notice tests/fixtures/m3_gongmun_gold/NOTICE.md && git commit -m "feat(m3-p0): harvest 가정통신문 (home_notice) design profile"`

---

### Task 4: 공문 gold corpus triage + curation

**Files:**
- Create: `tests/fixtures/m3_gongmun_gold/{NOTICE.md, <2-3 selected 공문>.hwpx}`
- Scratch: `scratchpad/p0/corpus_triage.py`

**Interfaces:**
- Consumes: `python-hwpx/work/public-document-corpus/` (24 docs + `manifest.json`), `hwpx.tools.official_lint.inspect_official_document_style`, oracle.
- Produces: a small committed 공문 gold set (genuine 시행문 with 두문/결문, regulation-clean + Hancom-clean) + a triage note for Task 5 (what real 공문 결문 structure looks like → feeds P2 lint rules).

- [ ] **Step 1: Triage the 24-doc corpus**

`scratchpad/p0/corpus_triage.py`: for each doc in `work/public-document-corpus/downloads/`, extract paragraphs and classify as `gongmun_sihaengmun` (has 두문 기관명 + 수신 + 결문 발신명의/시행일) vs `press_release` vs `form`. Print a table. (manifest `kind` is a hint: press-release/notice/form/legislation.)

- [ ] **Step 2: Select 2–3 genuine 공문 + run the regulation linter**

Run: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run python -c "from hwpx.tools.official_lint import inspect_official_document_style as f; print(f('<selected.hwpx>'))"` for each candidate.
Expected: capture the violation list (this measures how the *current* linter scores real 공문 — directly informs which structural rules P2 must add).

- [ ] **Step 3: Oracle-confirm each selected doc opens clean**

Run (oracle): render each selected `.hwpx` via `MacHancomOracle.render_pdf`; require fitz-open success (entry bar for a gold member — same rule as m2_corpus NOTICE).

- [ ] **Step 4: Commit the gold set with NOTICE**

Write `tests/fixtures/m3_gongmun_gold/NOTICE.md` (upstream URL/agency/sha256 per file, Constitution VIII wording mirroring `tests/fixtures/m2_corpus/NOTICE.md`).
Run: `git add tests/fixtures/m3_gongmun_gold && git commit -m "test(m3-p0): vendor 공문 gold corpus (regulation+Hancom clean) with NOTICE"`

---

### Task 5: P0 decision receipt (go/no-go + P1–P5 design inputs)

**Files:**
- Create: `specs/004-document-authoring/evidence/p0-decision.json` + `specs/004-document-authoring/evidence/p0-decision.md`

**Interfaces:**
- Consumes: all Task 1–4 verdicts + triage notes.
- Produces: the receipt that gates P1 and records design adjustments (e.g., exact 결문 slots observed in real 공문, which lint structural rules are needed, whether 가정통신문 harvest succeeded).

- [ ] **Step 1: Synthesize verdicts**

Aggregate: profile render verdicts (official_notice/report/home_notice), 결문+각주 verdict, gold-corpus linter findings + real 결문 structure observed.

- [ ] **Step 2: Write go/no-go + design deltas**

`p0-decision.md`: per sub-bar — does the building block open clean? what real-공문 structure must P2's lint enforce? any blocker (e.g., 가정통신문 source). Explicit `unverified` where the oracle was unavailable (Constitution V/IX).

- [ ] **Step 3: Commit + Wily phase complete**

Run: `git add specs/004-document-authoring/evidence/p0-decision.* && git commit -m "spike(m3-p0): P0 decision receipt (go/no-go + P1-P5 design inputs)"`
Then (root session): `complete_phase` for the P0 Wily phase with this receipt as verification; author P1–P5 detailed plans next.

---

## Self-Review

- **Spec coverage (P0 portion):** FR-009 (가정통신문 harvest) → Task 3; FR-012 (공문 gold corpus) → Task 4; measure-first premise for FR-001/002/003/004/008 → Tasks 1,2,5. FR-005/006/007/010/011 are P1–P5 (deferred by design — measure-first).
- **Placeholder scan:** the only deliberate unknown is the 가정통신문 source file (Task 3 Step 1) and the exact harvest CLI form — both have explicit "confirm signature / ask owner" steps, not silent placeholders.
- **Type consistency:** uses the verified public API (`compose`, `load_profile`, `available_profiles`, `resolve_oracle`, `render_pdf`, `inspect_official_document_style`); verdict JSON shape is consistent across Tasks 1–5.

## Execution note

Per the workspace harness rhythm (owner approved autonomous drive) + ultracode, P0 executes subagent/workflow-driven from the root session, with the Mac Hancom oracle steps run serially (GUI, non-parallel) and `dangerouslyDisableSandbox`. Root owns Wily lifecycle + verification. P1–P5 plans are authored after this P0 receipt.
