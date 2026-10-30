# Independent synthetic measurements: styles #607 and fields #576

Observed 2026-10-30 on macOS 26.5.1 arm64, 10 logical CPUs; Python 3.13.13 (Clang 22.1.3), lxml 6.1.3.
Public wheel: `python-hwpx==6.10.0`, installed into a new isolated uv environment. Source comparison: frozen main `53f3b1a0b8c254d54e0254e6294d801bccb72b44`, using the same interpreter/dependencies and only changing PYTHONPATH. The main checkout remained detached and untouched.

## Method and limits

- Privacy-free generated documents; no downstream source was copied or executed.
- These are measurements, not a visual correctness or release gate. No new Hancom observation or whole-conversion speedup is claimed.
- One process/run per matrix and coordinate. The machine was shared with other maintenance work; individual wall times are descriptive, not statistically controlled claims of small version-to-version improvements. Candidate/scan counts are deterministic and establish the scaling independently.
- Style timing is uninstrumented. An independent repeat of the identical requests wraps the actual candidate predicates/comparator to count comparisons, asserts identical returned IDs, and restores originals.
- Field timing includes a wrapper around each full scan (Counter update and len of the native result). Construction and save/reopen validation are excluded from fill timing. Per-field extrema and setup times are retained in raw JSON.
- No persistent cache, index, new API, or production change was introduced.

## Styles

For each of paragraph/run/border ensure, create 10/100/1000 distinct requested shapes over the bundled template. The template contributes existing shapes, so raw JSON records the actual registry sizes (paragraph 30/120/1020, run 16/106/1006, border 12/102/1002). This is not a claim of exactly N total registry records.
Each case makes 100 requests: same early shape, same late shape, distinct existing shapes spread over the entire range, and (for paragraph/run) two distinct bases with the same override. Border ensure has no base argument. Complete matrices appear in both style JSON files.

Late repeated request (100 calls):

| API | Requested shapes | Public 6.10 seconds | Main seconds | Actual candidate comparisons |
|---|---:|---:|---:|---:|
| paragraph | 10 | 0.026937 | 0.027637 | 3,000 |
| paragraph | 100 | 0.158857 | 0.162722 | 12,000 |
| paragraph | 1000 | 1.501157 | 1.539578 | 102,000 |
| run | 10 | 0.006492 | 0.005220 | 1,600 |
| run | 100 | 0.007071 | 0.006819 | 10,600 |
| run | 1000 | 0.022024 | 0.021330 | 100,600 |
| border | 10 | 0.006034 | 0.005992 | 1,200 |
| border | 100 | 0.037203 | 0.037709 | 10,200 |
| border | 1000 | 0.369656 | 0.344235 | 100,200 |

At 1000 requested paragraph shapes, repeating a late shape costs about 15 ms per request on this host, versus about 0.19 ms for an early shape. Both public and main scan the same 1020 candidates for the late match. Border ensure has a similar linear candidate scan; run predicates are cheaper per candidate. These are core ensure costs, independent of any Markdown conversion.

Checks passed at both coordinates: ID reuse; case-normalized paragraph alignment; immutable source base shapes; unknown extension child and hp:switch contents carried into derived shapes and retained after save/reopen; a new document does not inherit extensions. No cache means no cache-invalidation semantics were changed.

**Disposition #607: independently reproduced, keep open for bounded optimization.** Start with reducing repeated full structural-comparison work within an ensure call (or a mutation-aware document-local lookup), benchmark under identical budgets, and retain every preservation case. An app can reuse the returned style IDs within the same document when its base/override inputs are fixed; IDs must not be carried between documents. Do not assume public element escape-hatch edits are observable by a naive cache. The measurement does not justify caching mutable bases without an explicit invalidation contract.

## Native fields

Generate N one-paragraph native CLICKHERE fields using doc.fields.add, each with a name and prompt. Fill each once through doc.fields.fill(name=...), preserving the complete result. No cell lookup, photo handling, downstream monkeypatch, or whole report conversion participates.

| Fields | Public fill seconds | Main fill seconds | Main ms/field | Full scans | Field payloads built |
|---:|---:|---:|---:|---:|---:|
| 10 | 0.005866 | 0.005788 | 0.579 | 20 | 200 |
| 100 | 0.518218 | 0.517149 | 5.171 | 200 | 20,000 |
| 330 | 5.986656 | 5.869674 | 17.787 | 660 | 217,800 |
| 1000 | 55.037071 | 54.499750 | 54.500 | 2,000 | 2,000,000 |

1000 sequential native fills take about 55 seconds and build 2,000,000 field payloads: two full scans per fill, quadratic in N. The current main does not remove this cost. This establishes a core bottleneck without interpreting the downstream aggregate timings as a core speedup.

For every N at both coordinates, the full FieldFillResult payloads (excluding randomly generated field IDs) hash identically across versions. before is the prompt, after is the requested value, fit is None, and the before/after style snapshots are retained. stylePreserved is false for these first fills because the screen prompt uses style 7 and the inserted value intentionally uses begin-run style 0; the benchmark records the actual contract rather than falsely asserting all prompts keep their display style. Every field is dirty=1; modified field paragraphs have no line caches; saved documents reopen with exactly N names and the requested values.

**Disposition #576: independently reproduced, keep open for bounded optimization.** Prototype metadata-only selection/lazy payload construction before considering a persistent index. Avoid the second whole-document payload rebuild when the selected field can be rediscovered locally, but prove stable public indices and result objects after nested-field deletion, span collapse, and header/footer twins. Preserve missing-end failures, duplicate/empty name and id/index selection, multiline/spanning/nested fields, fit before-mutation refusal, dirty marking, line-cache invalidation, and round trips. A shortcut that returns less result data or assumes names never change does not meet the contract.

## Reproduction

```sh
uv venv .bench-610 --python python3
uv pip install --python .bench-610/bin/python 'python-hwpx==6.10.0'
.bench-610/bin/python scripts/benchmark_ensure_and_fields.py --label public-wheel-6.10.0 --mode all --output public.json
PYTHONPATH="$PWD//tmp/hwpx-benchmark-main/src" .bench-610/bin/python scripts/benchmark_ensure_and_fields.py --label main-53f3b1a0 --mode all --output main.json
```

Prepare the exact source checkout first with `git worktree add --detach /tmp/hwpx-benchmark-main 53f3b1a0b8c254d54e0254e6294d801bccb72b44`.

The referenced frozen checkout must resolve to the full main SHA above. The source label is authoritative for the imported implementation; package metadata remains the isolated public wheel metadata.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| ../../../scripts/benchmark_ensure_and_fields.py | `559075c5d431293d0d0be8cfb1154f10c19647217939537b7199327451c72a38` |
| public-610-styles.json | `ca71d85b9e2794c1c6a2d706a12f54ef6e122004a12976c9a09a5979f6a95c03` |
| main-53f3-styles.json | `edc7f97dea00ec3232da10c459129cabb7d2e920e1faec6eba0db3b7bb7ea49d` |
| public-610-fields.json | `91007e24cc2fe70f4ebef0ca0a94ec36504129f7238ad6e6317b63aca3ebefb9` |
| main-53f3-fields.json | `3ae14d97ec09e2a26133143934ff5d3d88765ec2297f4973b02a6fdccef6b5d9` |


Follow-up: the bounded redundant-scan optimization is recorded in [optimization-576-receipt.md](optimization-576-receipt.md). The baseline tables above remain historical measurements; current candidate disposition is described in that receipt.

## Discarded comparison experiments

A five-repeat 100-request/1000-shape probe measured a 1.523s baseline median. Removing temporary child lists gave 1.425s (6.4%); attribute dict-copy/pop plus that change gave 1.681s (10.4% slower). The first delta was not sufficient to establish a useful improvement under concurrent host load, and the second was worse. Both production experiments were reverted. No new style cache or invalidation contract ships. The remaining linear candidate-scan cost is tracked by #607.

The published script copies include an added license header; the receipt hashes above identify the original executed probes, rather than the header-adjusted copies.
