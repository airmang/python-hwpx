# SPDX-License-Identifier: Apache-2.0
"""Additive core seams preserve warning-free legacy behavior (#565)."""
from __future__ import annotations

import warnings
from importlib import import_module
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

diff_module = import_module("hwpx.tools.doc_diff")


@pytest.mark.parametrize("source,expected", [
    ("A\n\n B ", ["A", " B "]),
    ([" A ", "", {"text": " B "}], ["A", "B"]),
    ({"paragraphs": [" A "], "text": "B", "sections": []}, ["A"]),
    ({"text": " A\n\nB ", "sections": []}, [" A", "B "]),
    ({"text": None}, []),
])
def test_neutral_source_reader_keeps_generic_source_semantics(source, expected) -> None:
    assert diff_module.paragraph_texts(source) == expected


@pytest.mark.parametrize("source", [b"not text", bytearray(b"x"), None, {}, {"sections": []}])
def test_neutral_reader_rejects_plans_and_non_sources(source) -> None:
    with pytest.raises(TypeError):
        diff_module.paragraph_texts(source)


def test_legacy_plan_dispatch_is_unchanged_without_warnings() -> None:
    plan = {"sections": [{"blocks": [{"type": "heading", "text": " A "},
                                    {"type": "table", "rows": [["B", "C"]]}]}]}
    with warnings.catch_warnings(record=True) as found:
        warnings.simplefilter("always")
        report = diff_module.doc_diff(plan, ["A", "B C"])
    assert report["summary"]["counts"] == {"equal": 2, "added": 0, "removed": 0, "changed": 0}
    assert not found


def test_neutral_reader_accepts_documents_and_real_external_paths() -> None:
    path = Path(__file__).parent / "fixtures" / "m2_corpus" / "public_official_table.hwpx"
    with HwpxDocument.open(path) as document:
        expected = [p.text for p in document.paragraphs if p.text.strip()]
        assert expected
        assert diff_module.paragraph_texts(document) == expected
    assert diff_module.paragraph_texts(path) == expected
    assert diff_module.paragraph_texts(str(path)) == expected
