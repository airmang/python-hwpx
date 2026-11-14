from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from langchain_core.document_loaders import BaseLoader  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from hwpx import HwpxDocument  # noqa: E402
from hwpx.ingest import UnsupportedDocumentFormat  # noqa: E402
from hwpx.integrations.langchain import HwpxLoader  # noqa: E402

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


def test_loader_returns_one_markdown_document_with_flat_metadata(tmp_path: Path) -> None:
    source = _sample(tmp_path / "계획.hwpx")

    loader = HwpxLoader(source)
    docs = loader.load()

    assert isinstance(loader, BaseLoader)
    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert "| 항목 | 내용 |" in docs[0].page_content
    assert "## 1. 추진 목적" in docs[0].page_content
    metadata = docs[0].metadata
    assert metadata["source"] == str(source.resolve())
    assert metadata["source_format"] == "hwpx"
    assert metadata["lossiness"] == "low"
    assert metadata["table_count"] == 1
    assert all(isinstance(value, (str, int)) for value in metadata.values())


def test_loader_takes_a_string_path_and_loads_lazily(tmp_path: Path) -> None:
    source = _sample(tmp_path / "plan.hwpx")

    loader = HwpxLoader(str(source))
    source.unlink()  # nothing was read when the loader was made

    with pytest.raises(FileNotFoundError):
        next(iter(loader.lazy_load()))


def test_loader_reads_hwp() -> None:
    docs = HwpxLoader(_HWP_FIXTURES / "border_3d.hwp").load()

    assert docs[0].metadata["source_format"] == "hwp"
    assert docs[0].page_content.strip()


def test_loader_passes_markdown_options(tmp_path: Path) -> None:
    source = _sample(tmp_path / "plan.hwpx")

    plain = HwpxLoader(source, markdown_options={"detect_headings": False}).load()

    assert "## 1. 추진 목적" not in plain[0].page_content
    assert "1. 추진 목적" in plain[0].page_content


def test_loader_says_why_a_file_cannot_be_read(tmp_path: Path) -> None:
    source = tmp_path / "old.hwp"
    source.write_bytes(b"HWP Document File V3.00 \x1a\x01\x02\x03\x04\x05" + b"\x00" * 64)

    with pytest.raises(UnsupportedDocumentFormat, match="HWP 3.x"):
        HwpxLoader(source).load()


def test_importing_hwpx_does_not_load_langchain() -> None:
    code = (
        "import sys, hwpx, hwpx.ingest\n"
        "assert not any(name.split('.')[0] == 'langchain_core' for name in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
