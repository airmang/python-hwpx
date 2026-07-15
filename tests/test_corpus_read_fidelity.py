# SPDX-License-Identifier: Apache-2.0
"""M6 / S-060 P3: corpus-scale run-format round-trip fidelity gate.

Content-level guard (charPr-resolved run spans survive open->save->reopen) across
the real-Korean hwpxlib conformance corpus. Structural — no Hancom oracle.
"""
from __future__ import annotations

from pathlib import Path


from hwpx.tools.read_fidelity import corpus_fidelity

CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hwpxlib_corpus"


def _corpus_paths() -> list[Path]:
    return sorted(CORPUS.glob("*.hwpx"))


def test_corpus_present():
    assert len(_corpus_paths()) >= 40, "hwpxlib conformance corpus missing"


def test_corpus_run_format_roundtrip_fidelity_ge_95():
    report = corpus_fidelity(_corpus_paths())
    assert report["total_runs"] > 1000, report
    assert report["run_format_fidelity"] >= 0.95, {
        "fidelity": report["run_format_fidelity"],
        "below": report["files_below_100pct"][:10],
        "errors": report["errors"],
    }


def test_corpus_no_run_loss():
    report = corpus_fidelity(_corpus_paths())
    # every file must round-trip its run count (no silent run drops)
    assert report["files_below_100pct"] == [], report["files_below_100pct"][:10]
