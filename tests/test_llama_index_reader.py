from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core import SimpleDirectoryReader  # noqa: E402
from llama_index.core.readers.base import BaseReader  # noqa: E402
from llama_index.core.schema import Document  # noqa: E402

from hwpx import HwpxDocument  # noqa: E402
from hwpx.ingest import UnsupportedDocumentFormat  # noqa: E402
from hwpx.integrations.llama_index import HwpxReader  # noqa: E402

_HWP_FIXTURES = Path(__file__).parent / "fixtures" / "hwp5"


def _sample(path: Path) -> Path:
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


def test_reader_returns_one_markdown_document_with_flat_metadata(tmp_path: Path) -> None:
    source = _sample(tmp_path / "계획.hwpx")

    reader = HwpxReader()
    docs = reader.load_data(source)

    assert isinstance(reader, BaseReader)
    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert "| 항목 | 내용 |" in docs[0].text
    assert "## 1. 추진 목적" in docs[0].text
    metadata = docs[0].metadata
    assert metadata["source"] == str(source.resolve())
    assert metadata["source_format"] == "hwpx"
    assert metadata["lossiness"] == "low"
    assert metadata["table_count"] == 1
    assert all(isinstance(value, (str, int)) for value in metadata.values())


def test_reader_takes_a_string_path_reads_hwp_and_keeps_extra_info() -> None:
    docs = HwpxReader().load_data(
        str(_HWP_FIXTURES / "border_3d.hwp"),
        extra_info={"file_name": "border_3d.hwp", "source": "given"},
    )

    assert docs[0].metadata["source_format"] == "hwp"
    assert docs[0].metadata["file_name"] == "border_3d.hwp"
    assert docs[0].metadata["source"] == "given"
    assert docs[0].text.strip()


def test_reader_passes_markdown_options(tmp_path: Path) -> None:
    source = _sample(tmp_path / "plan.hwpx")

    plain = HwpxReader(markdown_options={"detect_headings": False}).load_data(source)

    assert "## 1. 추진 목적" not in plain[0].text
    assert "1. 추진 목적" in plain[0].text


def test_reader_works_as_a_directory_file_extractor(tmp_path: Path) -> None:
    _sample(tmp_path / "plan.hwpx")
    (tmp_path / "old.hwp").write_bytes((_HWP_FIXTURES / "border_3d.hwp").read_bytes())
    reader = HwpxReader()

    try:
        docs = SimpleDirectoryReader(
            str(tmp_path), file_extractor={".hwpx": reader, ".hwp": reader}
        ).load_data()
    except ImportError as exc:
        # Older llama-index-core loads its default extractors whatever file_extractor says, and
        # wants llama-index-readers-file for them.
        pytest.skip(f"SimpleDirectoryReader of this llama-index-core is not usable alone: {exc}")

    assert sorted(doc.metadata["source_format"] for doc in docs) == ["hwp", "hwpx"]
    assert sorted(doc.metadata["file_name"] for doc in docs) == ["old.hwp", "plan.hwpx"]


def test_reader_says_why_a_file_cannot_be_read(tmp_path: Path) -> None:
    source = tmp_path / "old.hwp"
    source.write_bytes(b"HWP Document File V3.00 \x1a\x01\x02\x03\x04\x05" + b"\x00" * 64)

    with pytest.raises(UnsupportedDocumentFormat, match="HWP 3.x"):
        HwpxReader().load_data(source)


def test_importing_hwpx_does_not_load_llama_index() -> None:
    code = (
        "import sys, hwpx, hwpx.ingest\n"
        "assert not any(name.split('.')[0] == 'llama_index' for name in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
