# lineSegArray Baseline Measurement Harness (P0)

**Purpose.** Before building the "VisualComplete Engine" spec, answer the one
question it never measured: *does retaining a stale `lineSegArray` (layout cache)
actually cause 글자 겹침 in Hancom, and does the current engine's stripping fix
it?* This harness measures that with Hancom itself as the oracle.

It exists because two facts changed the plan:

1. **lineSegArray invalidation already ships — but per re-serialized section, not
   "unconditionally".** `opc/package.py:_sanitize_part_for_write` →
   `_strip_section_layout_caches` runs **inside `package.write()`**
   (`opc/package.py:201-204`), case-insensitively matching the real lowercase
   `<hp:linesegarray>`. But `package.write()` is only called for sections the
   document model **re-serializes**, i.e. the ones it edited. In a multi-section
   doc, editing one section leaves the *other* sections' caches in place
   (measured: doc with 3 sections, edit section0 → section0 184→0, section1/2
   kept 283/72). That's harmless for content edits — HWPX section breaks are hard
   layout boundaries, so one section's caches can't go stale from another
   section's edit — but the earlier "unconditional on every section write" claim
   was wrong. So P1 ("scoped dirty-range invalidation") is *already done bluntly*
   **for the save path**, not greenfield.
2. **The bug was never measured.** *(Now measured — see "Result" below: it
   reproduces, stripping is load-bearing.)*

The one save path that genuinely emitted a stale cache is the byte-preserving
`patch.py` ZIP-splice path. Confirmed leaking (and now fixed) — see "Result".

---

## What it does

For each input `.hwpx` and each mutation it produces a **control pair**:

| arm | behaviour | how |
|---|---|---|
| **ON**  | engine default — layout cache stripped | normal save |
| **OFF** | layout cache **retained** (pre-fix / counterfactual) | `lineseg_toggle.py` monkeypatches the 5 strip functions to no-ops |

Then Hancom renders both to PDF, and we compare:

- **`diff_ratio` (primary)** — if ON and OFF render identically, Hancom
  re-layouts on open and **stale lineseg is harmless** (blanket strip is just a
  guard). If they differ, the cache changed what Hancom drew.
- **`overlap_score` (corroboration)** — collapsed text bands = overlap signature.

---

## Files

| file | runs on | needs Hancom | role |
|---|---|---|---|
| `lineseg_toggle.py`  | any | no  | context manager: ON/OFF cache stripping |
| `mutate.py`          | any | no  | mutation battery (short→long, long→short, same-length-ko) |
| `run_pairs.py`       | any | no  | driver: emit ON/OFF `.hwpx` pairs + `manifest.json` + control self-check |
| `overlap_detect.py`  | any | no  | `diff_ratio`, `overlap_score` (Pillow+numpy) |
| `hancom_render.ps1`  | **Windows** | **yes** | `.hwpx` → PDF via `HWPFrame.HwpObject` |
| `rasterize_score.py` | any (where PDFs are) | no | PDF → score → `report.{json,md}` |
| `make_injected_fixture.py` | any | no | inject a lineSegArray to smoke-test the toggle (self-test only) |

---

## Run it

### Step 0 — get real input (IMPORTANT precondition)

The repo's 175 bundled `.hwpx` contain **zero** `lineSegArray` (all are
python-hwpx outputs, already stripped). The control needs documents **saved by
Hangul (한글)**, which embed layout caches. Copy a handful of genuine
Hancom-saved `.hwpx` into a folder first.

To smoke-test the harness itself *without* real input (proves the ON/OFF toggle
works, NOT that the bug reproduces), synthesize a fixture with an injected
`lineSegArray`:

```bash
cd python-hwpx
uv run python scripts/visualcomplete-baseline/make_injected_fixture.py \
    <any.hwpx> /tmp/vc-injected.hwpx
uv run python scripts/visualcomplete-baseline/run_pairs.py \
    --out /tmp/vc-smoke /tmp/vc-injected.hwpx
# expect: control_valid 3/3 (ON=0, OFF=1 per mutation)
```

### Step 1 — produce ON/OFF pairs (macOS or anywhere)

```bash
cd python-hwpx
uv run python scripts/visualcomplete-baseline/run_pairs.py \
    --out /tmp/vc-pairs \
    --mutations short_to_long,long_to_short,same_length_ko \
    /path/to/hancom_saved_1.hwpx /path/to/hancom_saved_2.hwpx
```

Check the printed `control_valid` line: it must report OFF retaining more
lineseg than ON for every pair. If it's `0/N`, your inputs had no layout cache
(see Step 0) and the measurement would be meaningless.

### Step 2 — render to PDF (Windows + 한글 only)

Copy `/tmp/vc-pairs/*.hwpx` to the Windows box, then:

```powershell
cd python-hwpx\scripts\visualcomplete-baseline
./hancom_render.ps1 -Path (Get-ChildItem C:\vc-pairs\*.hwpx) `
    -OutDir C:\vc-pdfs -OutJson C:\vc-pdfs\render-manifest.json
```

If a Hangul build rejects `SaveAs(path,"PDF","")`, switch that one line to the
`HAction "FileSaveAsPdf"` path (noted in the script).

### Step 3 — score (anywhere the PDFs + manifest live)

```bash
uv run --with pymupdf --with pillow --with numpy \
    python scripts/visualcomplete-baseline/rasterize_score.py \
    --manifest /tmp/vc-pairs/manifest.json \
    --pdf-dir  /path/to/vc-pdfs \
    --out      /tmp/vc-report
```

Read `/tmp/vc-report/report.md`.

---

## How to read the verdict

| verdict | meaning | consequence for the spec |
|---|---|---|
| **all `hancom_relayouts`** | ON≈OFF; Hancom always re-layouts | stale lineseg is **harmless**; P1 scoped-invalidation is unnecessary — keep the blanket strip as a cheap guard and **redirect effort to FormFit / template / oracle** |
| **any `lineseg_matters`** | OFF differs / overlaps | stripping is **load-bearing** → the blanket strip is correct, and the `patch.py` byte path **must** strip too; add a regression that proves it |
| **`inconclusive`** | render missing | fix Hancom export first |

Either outcome **re-baselines P1–P5** with evidence instead of assumption — which
was the whole point.

---

## Result (Windows + 한글 Office 2022 v12, COM oracle, 2026-06-23)

**Verdict: `lineseg_matters` — stripping the stale cache is load-bearing.**

Measured over 6 genuine Hancom-saved docs × 3 mutations (17 valid pairs):
`lineseg_matters` 8 · `hancom_relayouts` 9 · `inconclusive` 1.

- **Text growth (`short_to_long`) reproduces 글자 겹침.** A 방송신청서 form title
  overflowed its stale single-line slot — glyphs piled on top of each other and
  2 pages collapsed to 1. Confirmed visually in the Hancom PDF.
- **Text shrink / same-length → ON==OFF (diff 0.0).** Hancom re-layouts; the
  retained cache is harmless. The open-safety validator additionally *rejects*
  the worst shrink case (`textpos > text length`), which is why one pair is
  `inconclusive` (OFF refused to save).
- `doc06`'s marginal 0.0086 diff (identical across all 3 mutations, no overlap
  signature) is cached-vs-fresh rounding noise, not 글자 겹침.

**Consequences acted on:**
- The save-path (blanket-ish) strip is correct — kept.
- **`patch.py` byte path was leaking** (no strip; its only guard,
  `validate_editor_open_safety`, can't detect text-*growth* staleness without
  doing layout). **Fixed**: the splice now drops the patched paragraph's
  `<hp:linesegarray>` (`patch.py:_strip_paragraph_layout_cache`). Regression:
  `tests/test_kordoc_absorption.py::test_byte_preserving_patch_strips_only_patched_paragraph_layout_cache`.
  Re-rendered through Hancom: the prior overlap smear is gone.
- Validator left as-is (textpos>length is its clean invariant; growth staleness
  isn't robustly detectable without layout — strip on patch is the right fix).

---

## macOS cross-validation (Mac 한컴 oracle, v12.30.0, 2026-06-24)

**The Windows verdict reproduces on the Mac oracle.** The same harness was run on
macOS with the new `MacHancomOracle` (`Hancom Office HWP.app` driven via
computer-use GUI → PDF; see `src/hwpx/visual/_render_hwpx_mac.applescript`)
substituting for `hancom_render.ps1`. Input: one genuine Hancom-saved `.hwpx`
(synthetic doc re-saved through Hancom's `다른 이름으로 저장하기` → 6 `linesegarray`
in section0; `control_valid 3/3`).

| mutation | verdict | max_diff | signal |
|---|---|---|---|
| `short_to_long` | **`lineseg_matters`** | 0.0066 (≥ eps 0.005) | stale single-line cache crammed the grown title onto one line; ON re-laid it to two |
| `long_to_short` | `hancom_relayouts` | 0.0000 | clean edit; ON==OFF |
| `same_length_ko` | `hancom_relayouts` | 0.0000 | clean edit; ON==OFF |

The text-growth defect is the same one Windows saw — the stale `lineSegArray`
(describing the *original short* `방송 신청서`) forces the lengthened paragraph into
the cached single line instead of wrapping; the cache-stripped (ON) render wraps
correctly. So the Mac backend confirms: **stripping is load-bearing on text
growth, harmless on clean edits.** Render fidelity matches COM; the Mac transport
is dev/spot-check grade (slower, GUI-serialized) — COM stays canonical for
CI/scale. (Evidence PNGs are reproducible out-of-tree; genuine Hancom docs and
renders aren't committed, same as the Windows run.)

---

## Verified vs. not (honest status, macOS session 2026-06-23)

**Verified here (ran on macOS):**
- Negative control is real: on a lineseg-injected fixture, ON→0 lineseg,
  OFF→retained, `control_valid=True`, 5 strip symbols neutralized.
- Mutations apply via the public API (`short_to_long`: 9→63 chars).
- `diff_ratio`/`overlap_score` behave on synthetic clean-vs-collapsed pages
  (diff 0.0 vs 0.104; tall_band_ratio 1.0 vs 4.44; overlap signature fires).

**Now verified on Windows + 한글 Office 2022 v12 (2026-06-23):**
- `hancom_render.ps1` exports PDF via COM — needed two build fixes: `Open` takes
  the full `(path, "", "")` signature on this build (1-arg fails to bind);
  `SaveAs(...,"PDF","")` works as-is.
- End-to-end `rasterize_score.py` on real Hancom PDFs (see "Result").
- Repo fixtures can't reproduce the bug (all stripped). Real Hancom-saved docs
  were sourced from local Downloads/Documents and processed out-of-tree.
- **Harness counter bug found + fixed**: `run_pairs.py`/`make_injected_fixture.py`
  counted only camelCase `lineSegArray`, but real Hangul writes lowercase
  `linesegarray`, so `control_valid` was a false 0 on every real doc. Now
  `re.IGNORECASE` (matches the engine's own case-insensitive strip).

## Open items
- ~~`--via-patch` mode~~ — the `patch.py` byte path was exercised directly
  (out-of-tree) and **fixed** with a unit regression. An in-tree `--via-patch`
  flag for `run_pairs.py` would still be a convenience.
- Form-fill mutation (`fill_form_field`) in the battery, once an anchored
  form fixture is available.
