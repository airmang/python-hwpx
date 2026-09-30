"""Memos kept in MEMO fields: Hancom saves a memo as a ``hp:fieldBegin type="MEMO"`` holding the memo's text in
its own ``hp:subList``, with no ``hp:memogroup`` entry (an HWP file read as HWPX holds them the same way)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.oxml.memo import HwpxOxmlFieldMemo

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
# Hancom saved the repository's examples/note_example.hwpx as .hwp, then that .hwp as .hwpx: five memos.
SAVED = ["memos_in_fields.hwpx", "memos_in_fields.hwp"]


def _memo_fields(data: bytes) -> tuple[int, int]:
    """(MEMO field begins, field ends) in the first section of *data*."""

    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml"))
    begins = [field for field in root.iter(f"{HP}fieldBegin") if field.get("type") == "MEMO"]
    return len(begins), len(list(root.iter(f"{HP}fieldEnd")))


@pytest.mark.parametrize("name", SAVED)
def test_memos_hancom_keeps_in_fields_are_read(name: str) -> None:
    document = HwpxDocument.open(FIXTURES / name)

    memos = document.notes.memos

    assert [memo.id for memo in memos] == ["memo1", "memo2", "memo3", "memo4", "memo5"]
    assert all(isinstance(memo, HwpxOxmlFieldMemo) for memo in memos)
    assert all(memo.text for memo in memos)
    assert all(memo.field_id and memo.paragraph is not None for memo in memos)
    assert memos[0].attributes["Number"] == "1"


@pytest.mark.parametrize("name", SAVED)
def test_removing_a_memo_kept_in_a_field_keeps_the_text_it_spans(name: str) -> None:
    document = HwpxDocument.open(FIXTURES / name)
    memo = document.notes.memos[0]
    paragraph = memo.paragraph
    assert paragraph is not None
    text = paragraph.text

    document.notes.remove_memo(memo)

    assert [memo.id for memo in document.notes.memos] == ["memo2", "memo3", "memo4", "memo5"]
    assert paragraph.text == text
    data = document.to_bytes()
    assert _memo_fields(data) == (4, 4)
    assert len(HwpxDocument.open(data).notes.memos) == 4


def test_a_memo_kept_in_a_field_takes_new_text() -> None:
    document = HwpxDocument.open(FIXTURES / "memos_in_fields.hwpx")
    memo = document.notes.memos[1]

    memo.text = "고친 메모"

    reopened = HwpxDocument.open(document.to_bytes())
    assert reopened.notes.memos[1].text == "고친 메모"


def test_a_memo_kept_in_a_field_takes_a_new_id_in_its_field() -> None:
    document = HwpxDocument.open(FIXTURES / "memos_in_fields.hwpx")
    memo = document.notes.memos[0]

    memo.id = "memo9"

    reopened = HwpxDocument.open(document.to_bytes())
    assert [kept.id for kept in reopened.notes.memos] == ["memo9", "memo2", "memo3", "memo4", "memo5"]


def test_a_memo_anchored_by_python_hwpx_counts_once_and_goes_with_its_field() -> None:
    # python-hwpx keeps an anchored memo in the memo group and in its MEMO field (which carries the memo's
    # id): it is one memo, and removing it removes the field too, so Hancom no longer shows it.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앵커 글")
    memo = document.notes.add_memo("메모 글", anchor=paragraph)

    assert [kept.id for kept in document.notes.memos] == [memo.id]

    document.notes.remove_memo(memo)

    assert document.notes.memos == []
    assert _memo_fields(document.to_bytes()) == (0, 0)
    assert paragraph.text == "앵커 글"
