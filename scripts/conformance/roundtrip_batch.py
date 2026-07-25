# SPDX-License-Identifier: Apache-2.0
"""Ranked roundtrip batch harness over an HWPX corpus.

Runs each sample through ``open -> serialize (round1) -> reopen -> serialize
(round2)`` and classifies it into a single ranked status:

    PARSE_FAIL  -> SERIALIZE_FAIL -> REPARSE_FAIL -> ROUND2_DIFF -> PASS

Hard failures (parse/serialize/reparse) are structural and fail CI (non-zero
exit). ``ROUND2_DIFF`` (the serializer is not a fixed point from its own output)
is *gradable* — reported but non-blocking — so a corpus can carry a known-
imperfect sample without masking a true structural regression. A separate
informational ``source_semantic_drift`` flag records whether the content
sequence changed from the ORIGINAL on first roundtrip (legitimate normalization
or a genuine loss; not a pass/fail by itself).

This gives a cheap, continuous, Hancom-free content-fidelity signal between the
expensive ComputerUse visual checks.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.idempotence import check_idempotent_pair
from hwpx.tools.ir_equality import compare_documents_semantic

__all__ = ["SampleResult", "BatchReport", "classify_sample", "run_corpus", "main"]

_STATUS_RANK = {
    "PARSE_FAIL": 0,
    "SERIALIZE_FAIL": 1,
    "REPARSE_FAIL": 2,
    "ROUND2_DIFF": 3,
    "PASS": 4,
}
_HARD_FAILS = {"PARSE_FAIL", "SERIALIZE_FAIL", "REPARSE_FAIL"}


@dataclass(frozen=True)
class SampleResult:
    sample: str
    status: str
    detail: str = ""
    source_semantic_drift: bool = False

    @property
    def is_hard_fail(self) -> bool:
        return self.status in _HARD_FAILS

    def to_dict(self) -> dict[str, object]:
        return {
            "sample": self.sample,
            "status": self.status,
            "detail": self.detail,
            "source_semantic_drift": self.source_semantic_drift,
        }


@dataclass
class BatchReport:
    results: list[SampleResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(r.status for r in self.results))

    @property
    def hard_fail_count(self) -> int:
        return sum(1 for r in self.results if r.is_hard_fail)

    @property
    def drift_count(self) -> int:
        return sum(1 for r in self.results if r.source_semantic_drift)

    @property
    def ok(self) -> bool:
        return self.hard_fail_count == 0

    def to_tsv(self) -> str:
        lines = ["sample\tstatus\tsource_drift\tdetail"]
        for r in self.results:
            lines.append(f"{r.sample}\t{r.status}\t{int(r.source_semantic_drift)}\t{r.detail}")
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "total": len(self.results),
            "counts": self.counts,
            "hardFailCount": self.hard_fail_count,
            "sourceDriftCount": self.drift_count,
            "results": [r.to_dict() for r in self.results],
        }


def classify_sample(path: str | Path) -> SampleResult:
    name = Path(path).name
    try:
        source = Path(path).read_bytes()
        doc1 = HwpxDocument.open(source)
    except Exception as exc:
        return SampleResult(name, "PARSE_FAIL", f"{type(exc).__name__}: {exc}")
    try:
        round1 = doc1.to_bytes()
    except Exception as exc:
        return SampleResult(name, "SERIALIZE_FAIL", f"{type(exc).__name__}: {exc}")
    try:
        round2 = HwpxDocument.open(round1).to_bytes()
    except Exception as exc:
        return SampleResult(name, "REPARSE_FAIL", f"{type(exc).__name__}: {exc}")

    # Informational: did the content sequence change from the original?
    drift = not compare_documents_semantic(source, round1).ok

    idem = check_idempotent_pair(round1, round2)
    if not idem.ok:
        return SampleResult(name, "ROUND2_DIFF", idem.summary(), drift)
    return SampleResult(name, "PASS", "", drift)


def run_corpus(
    corpus_dir: str | Path, samples: list[str] | None = None
) -> BatchReport:
    corpus = Path(corpus_dir)
    if samples is None:
        manifest = corpus / "manifest.json"
        if manifest.exists():
            samples = [s["file"] for s in json.loads(manifest.read_text("utf-8"))["samples"]]
        else:
            samples = sorted(p.name for p in corpus.glob("*.hwpx"))
    report = BatchReport()
    for sample in samples:
        report.results.append(classify_sample(corpus / sample))
    # Worst-first ordering for readability.
    report.results.sort(key=lambda r: (_STATUS_RANK.get(r.status, 99), r.sample))
    return report


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: roundtrip_batch <corpus_dir> [--tsv out.tsv] [--json out.json]", file=sys.stderr)
        return 2
    corpus_dir = argv[0]
    tsv_out = json_out = None
    if "--tsv" in argv:
        tsv_out = argv[argv.index("--tsv") + 1]
    if "--json" in argv:
        json_out = argv[argv.index("--json") + 1]

    report = run_corpus(corpus_dir)
    if tsv_out:
        Path(tsv_out).write_text(report.to_tsv(), "utf-8")
    if json_out:
        Path(json_out).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), "utf-8")

    print(
        f"corpus={len(report.results)} counts={report.counts} "
        f"hardFails={report.hard_fail_count} sourceDrift={report.drift_count}"
    )
    return 1 if report.hard_fail_count else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
