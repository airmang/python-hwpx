"""Writing document information and changing the manifest (sections, pictures, master pages) in any order
keeps both; fields added to opf:metadata go in Hangul's order (exec7/docinfo2)."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest

from hwpx import HwpxDocument

HANCOM = Path(__file__).resolve().parent / "fixtures" / "hancom_saved"
_SOURCE = (HANCOM / "formfit_auto_spacing_letter_spacing.hwpx").read_bytes()
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f01f0005000201a5f6c2d40000000049454e44ae426082"
)


def _two_sections() -> bytes:
    document = HwpxDocument.open(_SOURCE)
    document.add_section().add_paragraph("둘째 구역")
    return document.to_bytes()


def _count(document: HwpxDocument) -> tuple[int, int, int]:
    pictures = sum(len(p.pictures) for p in document.paragraphs)
    return len(document.sections), pictures, len(document.oxml.master_pages)


_CHANGES: dict[str, tuple[bytes, Callable[[HwpxDocument], None], tuple[int, int, int]]] = {
    "add_section": (_SOURCE, lambda d: d.add_section().add_paragraph("새 구역"), (2, 0, 0)),
    "remove_section": (_two_sections(), lambda d: d.remove_section(1), (1, 0, 0)),
    "add_picture": (_SOURCE, lambda d: d.paragraphs[-1].add_picture(_PNG, width=1000, height=1000), (1, 1, 0)),
    "add_master_page": (_SOURCE, lambda d: d.parts.add_master_page(text="바탕", page_type="BOTH", section=0), (1, 0, 1)),
}
_METADATA = {
    "set_document_metadata": lambda d: d.parts.set_document_metadata(
        creator="만든 이", date=datetime(2026, 11, 18, 5, 6, 7, tzinfo=timezone.utc)
    ),
    "clear_document_authors": lambda d: d.parts.clear_document_authors(),
}


@pytest.mark.parametrize("metadata_first", [True, False], ids=["metadata-first", "metadata-last"])
@pytest.mark.parametrize("metadata", sorted(_METADATA))
@pytest.mark.parametrize("change", sorted(_CHANGES))
def test_document_information_and_a_manifest_change_both_survive(
    change: str, metadata: str, metadata_first: bool
) -> None:
    source, apply_change, expected = _CHANGES[change]
    document = HwpxDocument.open(source)
    steps = [_METADATA[metadata], apply_change]
    for step in steps if metadata_first else reversed(steps):
        step(document)
    again = HwpxDocument.open(document.to_bytes())
    assert _count(again) == expected
    info = again.parts.metadata
    assert info is not None
    if metadata == "set_document_metadata":
        assert (info.creator, info.date) == ("만든 이", "2026년 11월 18일 수요일 오후 2:06:07")
    else:
        assert (info.creator, info.lastsaveby) == (None, None)


def _without_dates(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as old, zipfile.ZipFile(buffer, "w") as new:
        for info in old.infolist():
            payload = old.read(info)
            if info.filename == "Contents/content.hpf":
                payload = re.sub(
                    rb'<opf:meta name="(CreatedDate|ModifiedDate|date)" content="text">[^<]*</opf:meta>', b"", payload
                )
            new.writestr(info, payload)
    return buffer.getvalue()


def _meta_order(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        hpf = archive.read("Contents/content.hpf").decode("utf-8")
    return re.findall(r'<opf:meta name="(\w+)"', hpf)


_HANGUL = ["creator", "subject", "description", "lastsaveby", "CreatedDate", "ModifiedDate", "date", "keyword"]


@pytest.mark.parametrize("then_add_section", [False, True], ids=["splice", "whole-part"])
def test_added_date_fields_go_in_hangul_order(then_add_section: bool) -> None:
    source = _without_dates(_SOURCE)
    assert _meta_order(source) == [k for k in _HANGUL if k not in ("CreatedDate", "ModifiedDate", "date")]
    document = HwpxDocument.open(source)
    moment = datetime(2026, 11, 18, 5, 6, 7, tzinfo=timezone.utc)
    document.parts.set_document_metadata(
        date=moment, modified_date="2026-11-18T05:06:07Z", created_date="2026-11-18T05:06:07Z"
    )
    if then_add_section:
        document.add_section()
    assert _meta_order(document.to_bytes()) == _HANGUL
