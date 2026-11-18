"""Document information: the people's names a form brings along can be cleared, and the free-form ``date``
is written in Hangul's own form for the same instant as ``CreatedDate`` (exec7/docinfo)."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxTypeError, HwpxValueError
from hwpx.oxml.document_metadata import hangul_date_text

HANCOM = Path(__file__).resolve().parent / "fixtures" / "hancom_saved"
_DATED = HANCOM / "formfit_ano_teleia_grid.hwpx"


def _hpf(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("Contents/content.hpf")


def _named(data: bytes) -> HwpxDocument:
    document = HwpxDocument.open(data)
    document.package.set_document_metadata(creator="양식 만든 이", lastsaveby="양식 저장한 이")
    return HwpxDocument.open(document.to_bytes())


def test_hangul_date_text_is_the_form_hangul_writes_for_created_date() -> None:
    # Hancom-saved: CreatedDate 2025-09-17T04:32:50Z, date "2025년 9월 17일 수요일 오후 1:32:50".
    metadata = HwpxDocument.open(_DATED).parts.metadata
    assert metadata is not None and metadata.created_date and metadata.date
    created = datetime.strptime(metadata.created_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert hangul_date_text(created) == metadata.date


@pytest.mark.parametrize(
    ("utc", "text"),
    [
        (datetime(2026, 10, 20, 15, 30, 21), "2026년 10월 21일 수요일 오전 12:30:21"),  # 0 o'clock is 오전 12
        (datetime(2025, 9, 4, 1, 23, 8), "2025년 9월 4일 목요일 오전 10:23:08"),
        (datetime(2026, 6, 17, 14, 16, 42), "2026년 6월 17일 수요일 오후 11:16:42"),
        (datetime(2026, 10, 20, 3, 5, 1), "2026년 10월 20일 화요일 오후 12:05:01"),  # noon: inferred
    ],
)
def test_hangul_date_text_clock(utc: datetime, text: str) -> None:
    assert hangul_date_text(utc.replace(tzinfo=timezone.utc)) == text
    seoul = utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9)))
    assert hangul_date_text(seoul) == text


def test_a_naive_or_textual_date_is_refused() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as naive:
        document.parts.set_document_metadata(date=datetime(2026, 1, 1))
    assert naive.value.code == "parts-date-naive"
    with pytest.raises(HwpxTypeError) as text:
        document.parts.set_document_metadata(date="2026년 1월 1일")
    assert text.value.code == "parts-date-invalid-type"


def test_clear_document_authors_empties_the_names_and_keeps_the_rest() -> None:
    document = _named(_DATED.read_bytes())
    before = document.parts.metadata
    assert before is not None
    assert document.parts.clear_document_authors() == ("creator", "lastsaveby")
    after = HwpxDocument.open(document.to_bytes()).parts.metadata
    assert after is not None
    assert (after.creator, after.lastsaveby) == (None, None)
    assert (after.title, after.date, after.created_date, after.modified_date) == (
        before.title, before.date, before.created_date, before.modified_date,
    )
    hpf = _hpf(document.to_bytes())
    assert b'<opf:meta name="creator" content="text"/>' in hpf
    assert b'<opf:meta name="lastsaveby" content="text"/>' in hpf
    assert document.parts.clear_document_authors() == ()  # nothing left to clear


def test_set_document_metadata_writes_and_clears_the_new_fields() -> None:
    document = HwpxDocument.open(_DATED)
    moment = datetime(2026, 11, 18, 6, 7, 8, tzinfo=timezone.utc)
    document.parts.set_document_metadata(
        description="설명", lastsaveby="저장한 이", date=moment, created_date="2026-11-18T06:07:08Z"
    )
    metadata = HwpxDocument.open(document.to_bytes()).parts.metadata
    assert metadata is not None
    assert (metadata.description, metadata.lastsaveby) == ("설명", "저장한 이")
    assert metadata.date == "2026년 11월 18일 수요일 오후 3:07:08"
    document.parts.set_document_metadata(description="", lastsaveby="", date="")
    metadata = HwpxDocument.open(document.to_bytes()).parts.metadata
    assert metadata is not None
    assert (metadata.description, metadata.lastsaveby, metadata.date) == (None, None, None)


def test_rewriting_content_hpf_keeps_its_namespace_declarations() -> None:
    source = _DATED.read_bytes()
    declarations = dict(re.findall(rb'xmlns:(\w+)="([^"]*)"', _hpf(source)))
    assert declarations[b"hp10"] == b"http://www.hancom.co.kr/hwpml/2016/paragraph"
    for change in (
        lambda d: d.parts.set_document_metadata(creator="x"),
        lambda d: d.parts.clear_document_metadata(),
        lambda d: d.parts.clear_document_authors(),
    ):
        document = HwpxDocument.open(source)
        change(document)
        written = dict(re.findall(rb'xmlns:(\w+)="([^"]*)"', _hpf(document.to_bytes())))
        assert written == declarations


def test_writing_document_information_moves_only_the_changed_text() -> None:
    source = _DATED.read_bytes()
    before = _hpf(source)
    document = HwpxDocument.open(source)
    document.parts.set_document_metadata(created_date="2026-11-18T05:06:07Z")
    after = _hpf(document.to_bytes())
    assert after == before.replace(b">2025-09-17T04:32:50Z<", b">2026-11-18T05:06:07Z<")


def test_a_missing_field_is_added_where_hangul_writes_it() -> None:
    source = _DATED.read_bytes()
    before = _hpf(source)
    empty = b'<opf:meta name="lastsaveby" content="text"/>'
    assert before.count(empty) == 1
    trimmed = before.replace(empty, b"")
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as old, zipfile.ZipFile(buffer, "w") as new:
        for info in old.infolist():
            new.writestr(info, trimmed if info.filename == "Contents/content.hpf" else old.read(info))
    document = HwpxDocument.open(buffer.getvalue())
    document.parts.set_document_metadata(lastsaveby="저장한 이")
    filled = '<opf:meta name="lastsaveby" content="text">저장한 이</opf:meta>'.encode()
    assert _hpf(document.to_bytes()) == before.replace(empty, filled)
