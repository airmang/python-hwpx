# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))

# Samples that python-hwpx cannot yet read. Each entry MUST have a reason and a
# tracking note. Empty list is the goal; failures are classified here, never silently skipped.
KNOWN_READ_FAILURES: dict[str, str] = {
    # "reader_writer__SimpleEquation.hwpx": "equation part not modeled yet (builder backlog)",
}


def _sample_ids() -> list[str]:
    return [s["file"] for s in MANIFEST["samples"]]


def test_manifest_count_matches_files() -> None:
    files = {p.name for p in CORPUS.glob("*.hwpx")}
    assert files == {s["file"] for s in MANIFEST["samples"]}
    assert MANIFEST["count"] == len(files)


@pytest.mark.parametrize("sample", _sample_ids())
def test_corpus_sample_opens(sample: str) -> None:
    if sample in KNOWN_READ_FAILURES:
        pytest.xfail(KNOWN_READ_FAILURES[sample])
    doc = HwpxDocument.open(CORPUS / sample)
    # Minimal liveness: sections iterate and text export does not raise.
    assert doc.sections is not None
    doc.export_text()
