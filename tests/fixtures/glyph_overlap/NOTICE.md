# glyph-overlap fixtures — controlled 방송신청서-style 글자겹침 regression

These two `.hwpx` files are **authored by this project** (not vendored, no upstream
source) as the deterministic positive case for the form-fill differential-overlap
detector (`hwpx.form_fit.wordbox.verify_form_fill_differential`, M2 FR-002).

| File | What it is |
|---|---|
| `slot_clean.hwpx` | A 발신명의-style line at normal 자간 (letter-spacing) — renders with no glyph over-print. |
| `slot_overprint.hwpx` | The **same text** with 자간 compressed to **−50%** — the canonical 방송신청서 글자겹침: a value crammed into a slot until consecutive glyphs over-print. |

Both are minimal `HwpxDocument.new()` documents that open clean in real Hancom
(`validate_editor_open_safety` passes); they differ only by the `<hh:spacing>` value
on `charPr` id 0. Measured in Hancom: `slot_clean` renders at ~9.7pt median glyph
advance with 0 over-prints; `slot_overprint` at ~4.8pt (advance halved) with ~23
over-prints (intersection ≥ 30 % of glyph area).

`verify_form_fill_differential(slot_clean, slot_overprint)` must report
`overlap_detected=True` / `ok=False` — a real Hancom-rendered 글자겹침 the overflow
and layout-stability signals do not catch (the compressed text takes *less* width, so
it never escapes a cell). The `…_smoke` test (gated on `HWPX_MAC_ORACLE_SMOKE`)
drives this against real Hancom; the offline synthetic tests cover the geometry.
