# Exam Typesetting — Implementation Plan 4: Skill reference + leap demo

Stage `STG-a47dede4fa57` (S-056) · Wily phase `PH-ebdea8e29481` · spans
`hwpx-skill` (reference + routing) + workspace-root `demo/` (leap demo, git-外).
Branch `feat/s056-exam-typesetting` in hwpx-skill. **Push 금지.**

## Goal

Make the exam-typesetting leap reachable **by prompt alone** through the installed
skill/MCP surface, and check in an oracle-rendered leap demo with honest evidence.
This closes S-056: the skill routes 시험지 조판 requests to `compose_exam`, and
`demo/exam-typesetting/` proves the leap end-to-end.

## Constitution Check

- **I/III** Spec is truth (`specs/003-exam-typesetting/spec.md` §Architecture: "Skill =
  judgment/orchestration"); demo carries concrete oracle-rendered evidence. ✅
- **IV/V Oracle-truth + NO SILENT TRUE**: the real A_form is a Hancom **curve-export**
  form → the text gate cannot measure 문항-split (`splits=null` + `needsReview`). The demo
  therefore proves the leap with **rendered images (visual proof)**, never a fabricated
  text-gate green. Owner pre-approved "honest-unverified + visual proof". ✅
  [[hwpx-curve-export-oracle-finding]]
- **VI fail-closed / VII lossless**: inherited from the composer; demo asserts clean Hancom
  open + 관리박스/footer preserved. ✅

## Global constraints

- **Release coupling (honest)**: `compose_exam` needs `hwpx-mcp-server >= 2.7.0`, which is
  **unreleased**; the skill launchers pin `2.6.0` (`scripts/validate_hwpx_plugin.py:113`,
  `packaging/templates/*`). So Plan 4 **adds skill content + bumps the skill CHANGELOG but
  does NOT bump the launcher pin and does NOT cut a skill release** — that is the downstream
  coordinated release (python-hwpx ships `hwpx.exam` → mcp 2.7.0 → skill pin bump). The
  reference doc states "requires hwpx-mcp-server >= 2.7.0 (release-pending)".
- **Demo drives the real tool**: the connected MCP is the released 2.6.0 (no `compose_exam`),
  so the demo build script calls the **local** `hwpx_mcp_server.server.compose_exam(...)`
  function (faithful tool path, `uv run` in the mcp checkout) — not just the engine.
- **Oracle available** (verified 2026-06-27, `MacHancomOracle.available() == True`) → render
  fresh demo evidence; if it ever degrades, fall back to the Plan-2 receipt PNGs
  (`specs/003-exam-typesetting/evidence/p2-composer-render/`) with attribution.
- `demo/` is at the workspace root, which is **not a git repo** (harness layer like
  `specs/`); demo artifacts are checked into the workspace, not a sub-repo git.

## Verified anchors (read 2026-06-27)

```
hwpx-skill/SKILL.md                         router table + 참조 인덱스 (add 1 row + 1 index line)
hwpx-skill/references/workflows-forms.md    format to mirror for workflows-exam.md
hwpx-skill/scripts/task_eval_harness.py     skill eval harness (grades SKILL.md body)
hwpx-skill/tests/test_task_eval_harness.py  + test_plugin_bundle_validation.py
hwpx-skill/scripts/validate_hwpx_plugin.py  pins hwpx-mcp-server==2.6.0 (DO NOT bump)
demo/M2-form-fill/{README.md,build_leap_demo.py,oracle_verdicts.json,*.png,*.hwpx}  demo template
python-hwpx/tests/fixtures/exam/{A_form.hwpx,sample_exam.md,NOTICE.md}  vendored form + md
hwpx_mcp_server.server.compose_exam(form_filename, output, exam_md=, verify=, ...)  the tool
hwpx.visual.oracle.resolve_oracle().render_pdf(path)  PDF render; fitz → PNG for visual proof
```

## File structure

```
hwpx-skill/
  references/workflows-exam.md     # NEW — the exam-typesetting workflow reference
  SKILL.md                         # +1 routing row, +1 참조 인덱스 line
  CHANGELOG.md                     # skill 0.1.12 entry (content only; pin NOT bumped)
demo/exam-typesetting/             # NEW (workspace root, git-外)
  README.md                        # the leap story + honest curve-export caveat
  transcript.md                    # prompt-only reproduction (skill → compose_exam)
  build_demo.py                    # reproducible: server.compose_exam + oracle render → PNG
  demo_exam.md                     # the authored exam (the "LLM-authored md")
  exam_form.hwpx                   # copy of the school A_form (provenance noted)
  exam_composed.hwpx               # compose_exam output
  exam_composed_p0.png / _p1.png   # Hancom render — visual proof
  oracle_verdicts.json             # honest compose report (renderChecked, needsReview, splits=null)
```

## Tasks

### Phase 0 — author the demo exam + confirm the tool path
- [ ] Author `demo/exam-typesetting/demo_exam.md`: a realistic 중간고사 (~8-12 문항, 1 세트문제
  with 공통지문, varied 배점, ≥1 `[그림N]` placeholder) in the parser's md convention.
- [ ] Smoke `hwpx_mcp_server.server.compose_exam(A_form, out, exam_md=<demo>, verify=False)`
  → confirm it parses + composes (renderChecked=false honest). No commit.

### Task 1 — `references/workflows-exam.md` (hwpx-skill)
**First**: `git -C hwpx-skill switch -c feat/s056-exam-typesetting`.
- [ ] Write the reference mirroring `workflows-forms.md`: when-to-use (출제 md → 학교 양식
  재조판), the contract (form .hwpx + authored md; figures = placeholders), the loop
  (`compose_exam` → read honest report → if `needsReview`/curve-export, `render_preview`
  for visual proof; optional `verify_question_splits`), keep-together explanation,
  the honest curve-export caveat, and "requires hwpx-mcp-server >= 2.7.0 (release-pending)".
- [ ] Commit.

### Task 2 — SKILL.md routing (hwpx-skill)
- [ ] Add one router row: 출제 md를 학교 시험지 양식에 재조판 (문항 keep-together) →
  `compose_exam` · `verify_question_splits` → [workflows-exam].
- [ ] Add one 참조 인덱스 line for `references/workflows-exam.md`.
- [ ] Run the skill suite (`test_task_eval_harness.py`, `test_plugin_bundle_validation.py`)
  — green (routing row well-formed, bundle still valid against the 2.6.0 pin). Commit.

### Task 3 — leap demo `demo/exam-typesetting/` (workspace root)
- [ ] `build_demo.py`: copy A_form → `exam_form.hwpx`; call
  `server.compose_exam(exam_form, exam_composed.hwpx, exam_md=demo_exam.md, verify=True)`;
  render `exam_composed.hwpx` via `resolve_oracle().render_pdf` → fitz rasterize to
  `exam_composed_p{0,1}.png`; write `oracle_verdicts.json` (the honest ComposeResult +
  a `visualProof` note). Deterministic + re-runnable.
- [ ] Run it (oracle live) → produce the composed `.hwpx`, the render PNGs, the verdicts.
- [ ] `README.md`: the leap (prompt → skill → `compose_exam` → finished exam), what the PNGs
  show (관리박스/footer preserved, 문항 keep-together, `[그림N]` placeholders intact), and the
  **honest caveat** (text gate `needsReview` on this curve-export form; the PNG is the proof).
- [ ] `transcript.md`: a realistic prompt-only session (user asks to typeset the exam into the
  school form → skill routes to `compose_exam` → honest report → visual confirmation),
  noting it reproduces against the local/editable mcp 2.7.0 surface now, published after release.

### Task 4 — skill CHANGELOG (no pin bump / no release)
- [ ] hwpx-skill CHANGELOG `[0.1.12]`: route 시험지 조판 (`compose_exam` / `verify_question_splits`
  / keep-together) via `references/workflows-exam.md`; **explicitly note** the launcher pin
  stays `2.6.0` and the exam tools activate when `hwpx-mcp-server>=2.7.0` ships (release-pending).
- [ ] Skill suite green; `git diff --check`. Commit.

### Task 5 — review + close
- [ ] Adversarial review (honesty of the demo's evidence claims + skill routing correctness +
  no false "released/verified" claims). Fix or re-review.
- [ ] **Root** completes Wily phase `PH-ebdea8e29481` with evidence; update SDD ledger + memory.
  This is the **last phase of S-056** — note the stage is ready for `complete_stage` review
  (owner decision) once the downstream release lands.

## Definition of done

- `references/workflows-exam.md` + SKILL.md routing live on `feat/s056-exam-typesetting`
  (hwpx-skill); skill suite green; launcher pin UNCHANGED (2.6.0); release-pending stated.
- `demo/exam-typesetting/` checked into the workspace with an oracle-rendered composed exam,
  visual-proof PNGs, honest `oracle_verdicts.json`, README + transcript.
- Wily phase done with evidence; branches unpushed; no false "verified/released" claim.
