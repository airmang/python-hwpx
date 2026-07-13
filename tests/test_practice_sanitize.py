from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.practice import sanitize_document_copy
from hwpx.tools.package_validator import validate_editor_open_safety


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_form(path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("홍길동 학생 개인정보 신청서")
    table = document.add_paragraph("").add_table(2, 2)
    table.set_cell_text(0, 0, "성명")
    table.set_cell_text(0, 1, "홍길동")
    table.set_cell_text(1, 0, "비고")
    table.set_cell_text(1, 1, "")
    document.save_to_path(path)


def test_sanitize_masks_body_and_table_text_preserving_structure(tmp_path: Path) -> None:
    source = tmp_path / "private.hwpx"
    destination = tmp_path / "sanitized.hwpx"
    _private_form(source)
    before = _sha(source)

    receipt = sanitize_document_copy(
        source,
        destination,
        derivative_id="DER-0123456789ABCDEFFEDC",
    )

    assert _sha(source) == before
    assert receipt["sourceUnchanged"] is True
    assert receipt["retainedSourceTextSegments"] == 0
    assert receipt["openSafety"]["ok"] is True
    assert receipt["realHancom"]["status"] == "unverified"
    assert "private.hwpx" not in repr(receipt)
    assert validate_editor_open_safety(destination).ok
    reopened = HwpxDocument.open(destination)
    text = "\n".join(paragraph.text for paragraph in reopened.paragraphs)
    tables = [table for paragraph in reopened.paragraphs for table in paragraph.tables]
    assert "홍길동" not in text
    assert len(tables) == 1
    assert len(tables[0].rows) == 2
    assert tables[0].cell(1, 1).text == ""


def test_sanitize_rejects_same_destination_and_nonopaque_id(tmp_path: Path) -> None:
    source = tmp_path / "private.hwpx"
    _private_form(source)
    with pytest.raises(ValueError, match="destination must differ"):
        sanitize_document_copy(
            source,
            source,
            derivative_id="DER-0123456789ABCDEFFEDC",
        )
    with pytest.raises(ValueError, match="opaque DER"):
        sanitize_document_copy(source, tmp_path / "out.hwpx", derivative_id="private-name")
    existing = tmp_path / "existing.hwpx"
    existing.write_bytes(b"do-not-overwrite")
    with pytest.raises(ValueError, match="already exists"):
        sanitize_document_copy(
            source,
            existing,
            derivative_id="DER-0123456789ABCDEFFEDC",
        )
    assert existing.read_bytes() == b"do-not-overwrite"
