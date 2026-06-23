# lineSegArray Baseline Measurement Harness (P0)

**Purpose.** Before building the "VisualComplete Engine" spec, answer the one
question it never measured: *does retaining a stale `lineSegArray` (layout cache)
actually cause 글자 겹침 in Hancom, and does the current engine's stripping fix
it?* This harness measures that with Hancom itself as the oracle.

It exists because two facts changed the plan:

1. **lineSegArray invalidation already ships.** The engine doesn't just strip on
   edit — `opc/package.py:_sanitize_part_for_write` calls
   `_strip_section_layout_caches` **unconditionally on every section write**
   (`opc/package.py:201-204`). Anything saved through `HwpxPackage` carries **no**
   layout cache. So the spec's P1 ("build scoped dirty-range invalidation") is
   not greenfield — it's *already done, bluntly* (nuke-all-on-save).
2. **The bug was never measured.** Nobody confirmed 글자 겹침 still reproduces.
   So step one is measurement, not engine-building.

The only known path that could still emit a stale cache is the byte-preserving
`patch.py` ZIP-splice path — test it explicitly with `--via-patch` once wired
(not yet implemented; see "Open items").

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

## Verified vs. not (honest status, macOS session 2026-06-23)

**Verified here (ran on macOS):**
- Negative control is real: on a lineseg-injected fixture, ON→0 lineseg,
  OFF→retained, `control_valid=True`, 5 strip symbols neutralized.
- Mutations apply via the public API (`short_to_long`: 9→63 chars).
- `diff_ratio`/`overlap_score` behave on synthetic clean-vs-collapsed pages
  (diff 0.0 vs 0.104; tall_band_ratio 1.0 vs 4.44; overlap signature fires).

**NOT verified (needs your Windows+한컴 box):**
- `hancom_render.ps1` actually exporting PDF (COM not available on macOS).
- End-to-end `rasterize_score.py` on real Hancom PDFs.
- That repo fixtures reproduce the bug — they can't; **supply real Hancom docs**.

## Open items
- `--via-patch` mode for `run_pairs.py` to also exercise the `patch.py`
  byte-splice path (the one save path that could bypass the package strip).
- Form-fill mutation (`fill_form_field`) in the battery, once an anchored
  form fixture is available.
