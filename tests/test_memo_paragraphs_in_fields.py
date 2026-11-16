"""Memo text kept only in its MEMO field is read as memo paragraphs.

Hangul 2024 saves a memo as a MEMO field holding the memo's text in its ``hp:subList``, with no
``hp:memogroup`` (``tests/fixtures/hancom_saved/hancom2024_memo_fields.hwpx``), and that is what it
makes of a python-hwpx memo when it saves it again: it keeps the field's text and drops the
``hp:memogroup`` copy (out/metrics7 ``created-areas/notes-*``). ``doc.notes.memos`` read such a memo;
``doc.text.iter_paragraphs()`` skipped it, so the memo looked lost after a round trip through Hangul.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"


def _memo_texts(doc: HwpxDocument) -> list[str]:
    return [place.paragraph.text for place in doc.text.iter_paragraphs(where="memo")]


def test_a_memo_hancom_keeps_in_its_field_is_read() -> None:
    doc = HwpxDocument.open(HANCOM / "hancom2024_memo_fields.hwpx")
    [memo] = doc.notes.memos
    assert _memo_texts(doc) == [memo.text]
    assert doc.text.iter_paragraphs(where="body")  # the body is still read as before


def test_a_python_hwpx_memo_is_read_once() -> None:
    doc = HwpxDocument.new()
    doc.notes.add_memo("검토 메모", paragraph=doc.add_paragraph("본문"))
    data = doc.to_bytes()
    assert _memo_texts(HwpxDocument.open(data)) == ["검토 메모"]  # memogroup and field hold it; read once


def test_a_python_hwpx_memo_is_written_as_hancom_writes_it() -> None:
    # 7.0: the memo is in its MEMO field only -- the form Hangul 2024 saves -- so a round trip
    # through Hangul changes nothing the engine reads
    doc = HwpxDocument.new()
    doc.notes.add_memo("검토 메모", paragraph=doc.add_paragraph("본문"))
    again = HwpxDocument.open(doc.to_bytes())
    assert again.oxml.sections[0].element.find(f"{HP}memogroup") is None
    assert [memo.text for memo in again.notes.memos] == ["검토 메모"]
    assert _memo_texts(again) == ["검토 메모"]
