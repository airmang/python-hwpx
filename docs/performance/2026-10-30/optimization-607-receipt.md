# #607 per-call paragraph matcher optimization receipt

Candidate: `dee5d782485f4ef85901f77a94ee1aef02b591a6`, based on `36e68b69`, branch `perf/paragraph-ensure-comparison`. The baseline paragraph comparator/ensure path is identical to measured main `53f3b1a0`. Python3.13.13/lxml6.1.3/macOS26.5.1 arm64; same interpreter, dependencies and fixed input budgets at both coordinates.

## Scope

Prepare only the built paragraph shape side once per ensure lookup: its tag, filtered attributes and per-child predicates. Existing candidates are compared lazily against that ephemeral structure. Nothing persists across calls or documents. Candidate order, first usable ID, id-ignoring at every depth and text/tail-ignoring behavior stay exactly as before. Unknown extension elements and switch children keep their existing structural meaning.
The existing private comparison callable keeps its signature and delegates to the same per-call matcher, so production has one comparison implementation. Tests keep a frozen pre-optimization recursive reference and compare both production entry points with it across3150 mutations. No index, invalidation mechanism or public API was introduced.

## Five-repeat measurements

Each sample makes100 ensure calls. Each repeat opens the same fresh input bytes; repeated, existing distinct, new distinct and two-base+override cases are separated. Setup and instrumentation are outside the timed region. Deterministic instrumentation subsequently counts actual candidate comparisons, target compilation calls and prepared nodes. The old comparator remains the baseline counting fallback; no zero-candidate score is reported for the new path.

| Requested shapes | Case | Baseline median s | Candidate median s | Reduction | Candidate comparisons |
|---:|---|---:|---:|---:|---:|
| 10 | same_late | 0.025534 | 0.016874 | 33.9% | 3,000 |
| 10 | distinct_existing | 0.018761 | 0.012877 | 31.4% | 2,505 |
| 10 | new_distinct | 0.097508 | 0.056915 | 41.6% | 7,950 |
| 10 | two_bases_override | 0.013698 | 0.009860 | 28.0% | 3,150 |
| 100 | same_late | 0.160206 | 0.087059 | 45.7% | 12,000 |
| 100 | distinct_existing | 0.085992 | 0.049143 | 42.9% | 7,050 |
| 100 | new_distinct | 0.235828 | 0.132640 | 43.8% | 16,950 |
| 100 | two_bases_override | 0.047112 | 0.028605 | 39.3% | 12,150 |
| 1000 | same_late | 1.451861 | 0.786618 | 45.8% | 102,000 |
| 1000 | distinct_existing | 0.734846 | 0.436978 | 40.5% | 52,005 |
| 1000 | new_distinct | 1.578878 | 0.865434 | 45.2% | 106,950 |
| 1000 | two_bases_override | 0.364739 | 0.199761 | 45.2% | 102,150 |

Every measured matrix case improves28–46% by median, substantially more than its within-run variation. At1000 shapes the late repeated request falls1.4519→0.7866s per100 calls; comparisons remain102,000 while the target is prepared100 times (2300 nodes total). The scan remains linear; this optimizes repeated structural-comparison work rather than claiming an index.

A first-candidate-exact-match control (1000 calls, five repeats) measured baseline median0.044716s and candidate0.046696s, about2microseconds additional work per call. No gain is claimed for this no-scan path. Small version-to-version differences and total Markdown conversion speedups are not inferred from these ensure-only measurements.

## Correctness and externality

-113 focused paragraph-dedup/style-definition/document-formatting tests pass. New matcher tests cover3150 deterministic old/new comparisons across nested trees and changed tags/attributes/child order/text/tail, ignored nested IDs and names, comments/processing instructions, first usable IDs, direct public XML mutation and unknown extensions/switch save/reopen.
-A real external public corpus document, error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx, is read from the same frozen fixture directory at both coordinates. Applying CENTER alignment to paragraph5 yields identical returned paragraph style IDs and identical SHA-256 maps for every output ZIP member. Both raw JSONs retain the input hash and complete output-member maps. This supplies the independently authored input for the preservation gate; no fresh visual Hancom claim is made.
-mypy121 files, pyright0 errors, CI-scoped Ruff and public hygiene pass.
-In-memory inversion of the new matching condition is caught by the first-usable-ID regression. No source file was changed for that mutation run.

## Experiment ledger

| Idea | Observation | Decision |
|---|---|---|
| Child-list-only change | Owner root measured1.523→1.425s median (~6%, noise) | Reverted; no claimed gain |
| dict copy + pop | Owner root measured1.681s | Reverted; worse than baseline |
| Per-call target matcher | Full matrix above;28–46% median lower, same results/counts/preservation | Keep as separate candidate after independent root review |

## Reproduce / public copy

../../../scripts/benchmark_paragraph_matcher.py is standalone, uses only the Python standard library plus python-hwpx and its lxml dependency, and accepts --label, --output and --fixtures. Run it with each coordinate imported through a matching environment/PYTHONPATH and the same --fixtures directory. The shared ../../../scripts/benchmark_ensure_and_fields.py was also updated to count the new matcher correctly; it remains an internal broad styles/fields probe and need not be copied into the public repository.

Example:

```sh
PYTHONPATH="$PWD/./src" .bench-610/bin/python scripts/benchmark_paragraph_matcher.py --label candidate-dee5d782 --output candidate.json --fixtures ./tests/fixtures
```

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| ../../../scripts/benchmark_paragraph_matcher.py | `e7672bbe11611035b3211d7e7c555955053a5712d8c39d7c1674b5134ac114fb` |
| ../../../scripts/benchmark_ensure_and_fields.py | `a21b3f04e36d0902cfbb75ded8156ae09ff1fd140ae952847320c6450f1cb642` |
| baseline-607-five.json | `b3f312ac00367da5b6458c8491772eb71185d80d829639c9d8f564fb3bb40181` |
| candidate-607-five.json | `95f32268fff7e2d8e7b0b6da0b78a468eb54b3304beed05964da5033072dc17a` |

Published script copies include an added license header. Original executed-probe hashes above identify the pre-header files.

Source-size follow-up: the existing1600-line architecture gate initially rejected1602 lines. Removing the duplicate production algorithm in favor of the compatibility wrapper reduces the module to1587 lines; the original recursive implementation is frozen only in tests. The focused semantic/style/architecture suite passes120 tests, with mypy121 files and pyright still clean. The timed ensure lookup path is unchanged, so the performance matrix above remains applicable.
