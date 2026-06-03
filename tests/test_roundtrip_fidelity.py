# SPDX-License-Identifier: Apache-2.0
"""Roundtrip fidelity diagnostics for the hwpxlib corpus.

Task 1 SPIKE observations:
- `reader_writer__SimpleTable.hwpx`, `reader_writer__SimpleEquation.hwpx`,
  and `reader_writer__SimplePicture.hwpx` all reopen after `open -> to_bytes`
  and preserve identical local-name element counts.
- A corpus-wide probe of 47 samples found no reopen failures and no local-name
  losses. This locks the diagnostic meaning: namespace prefix spelling, ID
  renumbering, and element order changes are outside this loss metric; only a
  before-count greater than the after-count for the same element local-name is
  reported as structural loss.
"""


import json
from collections import Counter
from pathlib import Path

import pytest

from hwpx.tools.roundtrip_diff import roundtrip_report


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
SAMPLES = [
    s["file"]
    for s in json.loads((CORPUS / "manifest.json").read_text("utf-8"))["samples"]
]

# 재오픈 자체가 실패하는 샘플(현재). 사유 명기, silent skip 금지.
KNOWN_REOPEN_FAILURES: dict[str, str] = {}


def test_roundtrip_report_shape(tmp_path):
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    p = tmp_path / "d.hwpx"
    doc.save_to_path(p)

    rep = roundtrip_report(p)

    assert rep["reopened"] is True
    assert isinstance(rep["lost_elements"], dict)
    assert isinstance(rep["added_elements"], dict)
    assert "p" in rep["before_counts"]


def test_hwpxlib_manifest_contains_expected_47_samples():
    assert len(SAMPLES) == 47


@pytest.mark.parametrize("sample", SAMPLES)
def test_corpus_sample_roundtrips(sample):
    if sample in KNOWN_REOPEN_FAILURES:
        pytest.xfail(KNOWN_REOPEN_FAILURES[sample])

    rep = roundtrip_report(CORPUS / sample)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}


def test_emit_loss_inventory():
    agg: Counter[str] = Counter()
    per_sample = {}
    for sample in SAMPLES:
        if sample in KNOWN_REOPEN_FAILURES:
            continue
        rep = roundtrip_report(CORPUS / sample)
        if rep["lost_elements"]:
            per_sample[sample] = rep["lost_elements"]
            agg.update(rep["lost_elements"])

    out = Path("work/s021-roundtrip")
    out.mkdir(parents=True, exist_ok=True)
    (out / "roundtrip_inventory.json").write_text(
        json.dumps(
            {
                "aggregate_lost_by_local_name": dict(agg.most_common()),
                "per_sample": per_sample,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print("LOSS INVENTORY:", dict(agg.most_common(20)))

    assert (out / "roundtrip_inventory.json").exists()
