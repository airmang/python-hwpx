# #576 bounded internal optimization receipt

Candidate commit: `a43cd790c9be55a57fc4f4ced09db38059e1e9aa`, based on integration `36e68b69`. The field implementation in that integration base is identical to measured main `53f3b1a0`; unrelated integrated layout/encryption-documentation changes do not alter this measured path.

## Change and invariants

Keep the initial full discovery and all selector/ambiguity/failure behavior. After the fill, use the same canonical match builder over only the selected paragraph and accept only the original fieldBegin identity. Refresh its runs, matching end, text nodes, metadata and style snapshot from current XML. A fill removes only content after the selected begin; the begin and everything preceding it remain in place, so its original paragraph location and global field index remain valid. No result data is synthesized or discarded. No cache, persistent index or public API was added.

The refresh deliberately does not reuse stale end-run/child indices: empty-value insertion shifts children, span collapse joins/removes runs, and nested deletion changes controls. The new transient paragraph source reconstructs those details through the canonical existing builder.

## Red/green and compatibility evidence

- Before: six selector/prompt variants failed the payload budget (20 built rather than11). After: all10 new regressions pass, including full field snapshots and save/reopen for actual Hancom spanning/nested fixtures.
- Field/fit/reader suite128 passed; header/footer twins + product-boundary + size suite192 passed.
- mypy121 source files passes; pyright with shared interpreter0 errors; CI-scoped Ruff and public hygiene pass.
- Identical actual Hancom source bytes for six fill cases (four spanning/in-paragraph, nested outer, nested inner): full FieldFillResult including IDs, every public field attribute/location/parameter and every output ZIP member hash are byte-identical between public6.10.0 and candidate. See ../../../scripts/compare_field_fill_outputs.py and the two field-semantics JSONs.
- All four synthetic-size FieldFillResult digests match public and main; dirty marking, cache invalidation and saved/reopened values pass. Public selector/fit/missing-end paths remain unchanged.

## Measurement

Same interpreter, dependency versions, input construction and fill budget as baseline. Probe instrumentation was extended to count the canonical scoped builder if present; older versions retain their original full-scan counting. This adds one Counter update per builder invocation rather than per individual field payload. Full raw result matrices are retained; no downstream aggregate conversion performance is claimed.

| Fields | Main seconds | Candidate1 seconds | Candidate2 seconds | Before payloads | After payloads |
|---:|---:|---:|---:|---:|---:|
| 10 | 0.005788 | 0.003289 | 0.003559 | 200 | 110 |
| 100 | 0.517149 | 0.276477 | 0.441206 | 20,000 | 10,100 |
| 330 | 5.869674 | 3.196099 | 5.857616 | 217,800 | 109,230 |
| 1000 | 54.499750 | 28.091466 | 28.114111 | 2,000,000 | 1,001,000 |

At1000 fields the two candidate runs are about28.1s versus main54.5s (about48.4% less wall time here); both candidate runs build1,001,000 payloads and make1000 full scans, versus2,000,000 payloads and2000 full scans before. Smaller repeat timings are noisy because the host is shared; no small-size/version delta is claimed.

The first full selection scan remains, so N sequential fills still have quadratic work. This bounded change removes the redundant second document-wide rediscovery and makes no claim of a linear-time batch implementation. A separate metadata-only/lazy selection design can use this evidence without adding unsafe name/index caches.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| ../../../scripts/benchmark_ensure_and_fields.py | `559075c5d431293d0d0be8cfb1154f10c19647217939537b7199327451c72a38` |
| ../../../scripts/compare_field_fill_outputs.py | `85884b5320982f0953d82151fe9a053eddf17cda81d3e0c55f187e982dfbc9c4` |
| candidate-576-fields.json | `9ea24e9636267e9ae34b21111e7ec58798a6f5c03d54116fe5bc9e7a10513f1c` |
| candidate-576-fields-repeat.json | `a9cc209b1d704be99fe535eda54b3250e31e5d99e2a8c9cdef07915cfd51db77` |
| public-610-field-semantics.json | `21de6950ff636fd3e20ea7888543c95e0447c9a88ef588524ff9350334ba9c89` |
| candidate-576-field-semantics.json | `21de6950ff636fd3e20ea7888543c95e0447c9a88ef588524ff9350334ba9c89` |
