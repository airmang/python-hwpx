from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.ingest import DocumentIngestor, UnsupportedDocumentFormat, normalize_markdown


def _sample_hwpx(path: Path) -> Path:
    doc = HwpxDocument.new()
    doc.add_paragraph("2026학년도 운영 계획")
    doc.add_paragraph("1. 추진 목적")
    table = doc.add_table(2, 2)
    table.set_cell_text(0, 0, "항목")
    table.set_cell_text(0, 1, "내용")
    table.set_cell_text(1, 0, "기간")
    table.set_cell_text(1, 1, "2026. 3.")
    doc.save_to_path(path)
    return path


def test_document_ingestor_converts_hwpx_to_rich_markdown(tmp_path: Path) -> None:
    source = _sample_hwpx(tmp_path / "sample.hwpx")

    result = DocumentIngestor.default().convert(source)

    assert result.engine == "python-hwpx"
    assert result.source_format == "hwpx"
    assert result.lossiness == "low"
    assert "2026학년도 운영 계획" in result.markdown
    assert "## 1. 추진 목적" in result.markdown
    assert "| 항목 | 내용 |" in result.markdown
    assert result.metadata["table_count"] == 1
    assert result.tables[0]["data"][1] == ["기간", "2026. 3."]
    assert result.attempts[0].accepted is True


def test_document_ingestor_detects_hwpx_from_stream_without_extension(tmp_path: Path) -> None:
    source = _sample_hwpx(tmp_path / "sample.hwpx")
    stream = BytesIO(source.read_bytes())

    result = DocumentIngestor.default().convert(stream)

    assert result.source_format == "hwpx"
    assert "2026학년도 운영 계획" in result.markdown


def test_document_ingestor_reports_unsupported_format(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("plain text is a later adapter", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentFormat) as exc:
        DocumentIngestor.default().convert(source)

    payload = exc.value.as_dict()
    assert payload["error"] == "UnsupportedDocumentFormat"
    assert payload["attempts"][0]["converter"] == "HwpxMarkdownConverter"
    assert payload["attempts"][0]["accepted"] is False


def test_normalize_markdown_trims_trailing_space_and_extra_blank_lines() -> None:
    assert normalize_markdown("a  \n\n\n\nb\n") == "a\n\nb"
