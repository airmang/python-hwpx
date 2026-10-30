# SPDX-License-Identifier: Apache-2.0
"""Additive core seams preserve warning-free legacy behavior (#565)."""
from __future__ import annotations

import warnings
from importlib import import_module
from io import BytesIO
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools.markdown_export import export_markdown

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


def test_heading_callback_receives_formatted_markdown_and_can_decline() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("Ⅰ. 기본 제목")
    paragraph = document.add_paragraph()
    paragraph.add_run("custom", bold=True)
    seen = []

    def detector(text: str) -> str | None:
        seen.append(text)
        return "### replacement" if "custom" in text else None

    result = export_markdown(document, heading_detector=detector)
    assert "# Ⅰ." not in result and "Ⅰ. 기본 제목" in result
    assert "### replacement" in result and any("**custom**" in text for text in seen)


def test_heading_callback_reaches_one_cell_tables_and_disabled_flag() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "cell heading"
    seen = []

    def detector(text: str) -> str | None:
        seen.append(text)
        return "### cell heading" if "cell heading" in text else None

    assert "### cell heading" in export_markdown(document, heading_detector=detector)
    seen.clear()
    assert "### cell heading" not in export_markdown(document, detect_headings=False, heading_detector=detector)
    assert not seen


def test_omitted_heading_callback_keeps_legacy_default() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("Ⅰ. 기본 제목")
    assert export_markdown(document) == export_markdown(document, heading_detector=None)
    assert "# Ⅰ. 기본 제목" in export_markdown(document)


def test_heading_callback_reaches_namespace_and_ingest_without_extension() -> None:
    from hwpx.ingest import DocumentIngestor

    document = HwpxDocument.new()
    document.add_paragraph("Ⅰ. 기본 제목")
    options = {"heading_detector": lambda text: "### injected" if "기본 제목" in text else None}
    assert "### injected" in document.text.markdown(rich=True, **options)
    result = DocumentIngestor.default().convert(BytesIO(document.to_bytes()), markdown_options=options)
    assert "### injected" in result.markdown and "# Ⅰ." not in result.markdown


@pytest.mark.parametrize("argument", ["heading_detector", "predicate"])
def test_invalid_callbacks_raise_structured_type_errors_before_io(argument) -> None:
    from hwpx.errors import HwpxTypeError
    from hwpx.table_patch import strip_trailing_table_text

    with pytest.raises(HwpxTypeError) as found:
        if argument == "heading_detector":
            export_markdown(b"not a package", heading_detector=42)
        else:
            strip_trailing_table_text(b"not a package", predicate=42)
    assert found.value.code == "hwpx-type-error"
    assert found.value.context == {"argument": argument}
