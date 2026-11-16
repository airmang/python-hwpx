"""Memos are written as Hangul 2024 saves them: in the MEMO field's ``hp:subList``, no ``hp:memogroup``.

Evidence: the six Hangul-saved documents with memos among the public and test HWPX
(``tests/fixtures/hancom_saved/hancom2024_memo_fields``, ``memos_in_fields``, ``memos_numbered``,
``memos_same_number``, ``hwpxlib_corpus/error__20251107__test`` and ``..._re``) all keep their memos so,
with no ``hp:memogroup``; the only file holding one is a python-hwpx fuzz fixture
(``fuzz_regressions/seed-000000-baseline``). Saving a python-hwpx 6.x memo again, Hangul 2024 drops the
``hp:memogroup`` copy and keeps the field's text (out/metrics7, notes-*).

A 6.x document (memo in both places) reads as before; changing one of its memos moves that memo into its
field and drops the memo-group copy, so the two never disagree. A memo made and never anchored is refused
at save (``note-memo-unanchored``): Hancom has nowhere to keep it.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.namespaces import HP

FIXTURES = Path(__file__).parent / "fixtures"
LEGACY = FIXTURES / "fuzz_regressions" / "seed-000000-baseline.hwpx"  # python-hwpx 6.x form


def _section_xml(data: bytes, index: int = 0) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(f"Contents/section{index}.xml").decode("utf-8")


def _fields(doc: HwpxDocument, section: int = 0) -> list:
    return [n for n in doc.sections[section].element.iter(f"{HP}fieldBegin") if n.get("type") == "MEMO"]


def _param(field, name: str) -> str | None:
    return next((p.text for p in field.iter() if p.get("name") == name and str(p.tag).endswith("Param")), None)


def test_hancoms_own_memo_documents_hold_no_memogroup() -> None:
    names = ["hancom_saved/hancom2024_memo_fields", "hancom_saved/memos_in_fields", "hancom_saved/memos_numbered",
             "hancom_saved/memos_same_number", "hwpxlib_corpus/error__20251107__test",
             "hwpxlib_corpus/error__20251107__test_re"]
    for name in names:
        doc = HwpxDocument.open(FIXTURES / f"{name}.hwpx")
        assert all(s.element.find(f"{HP}memogroup") is None for s in doc.sections), name
        assert doc.notes.memos and all(type(m).__name__ == "HwpxOxmlFieldMemo" for m in doc.notes.memos), name


def test_a_new_memo_is_written_in_its_field_only() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("검토 메모", paragraph=doc.add_paragraph("본문"), author="검토자")
    assert type(memo).__name__ == "HwpxOxmlFieldMemo"
    data = doc.to_bytes()
    xml = _section_xml(data)
    assert "<hp:memogroup" not in xml and "<hp:memo " not in xml and "<hp:paraList" not in xml
    assert 'memoShapeIDRef="0"' in xml  # the section's, as Hancom writes it
    again = HwpxDocument.open(data)
    [field] = _fields(again)
    assert _param(field, "MemoShapeIDRef") == "65535" and _param(field, "Author") == "검토자"
    assert [m.text for m in again.notes.memos] == ["검토 메모"]
    assert field.find(f"{HP}subList/{HP}p").get("id") == "0"


def test_a_memo_on_a_range_two_memos_and_a_memo_in_another_section() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("앞 글 메모 달 곳 뒤 글")
    doc.notes.add_memo("범위 메모", paragraph=first, match="메모 달 곳")
    doc.notes.add_memo("둘째 메모", paragraph=doc.add_paragraph("둘째 문단"))
    second = doc.add_section()
    doc.notes.add_memo("다른 구역 메모", paragraph=second.add_paragraph("둘째 구역 글"), section=1)
    data = doc.to_bytes()
    assert all("<hp:memogroup" not in _section_xml(data, i) for i in (0, 1))
    again = HwpxDocument.open(data)
    assert [m.text for m in again.notes.memos] == ["범위 메모", "둘째 메모", "다른 구역 메모"]
    assert [_param(f, "Number") for f in _fields(again)] == ["1", "2"]
    assert _param(_fields(again, 1)[0], "Number") == "3"
    assert again.notes.memos[0].paragraph.text == "앞 글 메모 달 곳 뒤 글"


def test_an_unanchored_memo_is_refused_until_anchored() -> None:
    doc = HwpxDocument.new()
    memo = doc.notes.add_memo("아직 걸지 않은 메모")
    with pytest.raises(HwpxValueError) as refused:
        doc.to_bytes()
    assert refused.value.code == "note-memo-unanchored" and refused.value.context["memos"] == [memo.id]
    assert "attach" in refused.value.suggestion
    memo.text = "고친 글"  # not anchored: changed in place
    doc.notes.attach(doc.add_paragraph("이제 건다"), memo)
    assert type(memo).__name__ == "HwpxOxmlFieldMemo" and doc.sections[0].memo_group is None
    again = HwpxDocument.open(doc.to_bytes())
    assert [m.text for m in again.notes.memos] == ["고친 글"]


def test_removing_an_unanchored_memo_lets_the_document_save() -> None:
    doc = HwpxDocument.new()
    doc.notes.remove_memo(doc.notes.add_memo("버릴 메모"))
    doc.to_bytes()


def test_a_6x_document_reads_and_saves_unchanged() -> None:
    data = LEGACY.read_bytes()
    doc = HwpxDocument.open(data)
    assert doc.sections[0].memo_group is not None
    texts = [m.text for m in doc.notes.memos]
    assert texts and all(texts)
    assert doc.to_bytes() == data  # an unedited save keeps every part


def test_changing_a_6x_memo_moves_it_into_its_field() -> None:
    doc = HwpxDocument.open(LEGACY)
    grouped = list(doc.sections[0].memo_group.memos)
    target = next(m for m in grouped if m.paragraph is not None)
    others = [m.id for m in grouped if m is not target]
    target.text = "고친 메모"
    assert type(target).__name__ == "HwpxOxmlFieldMemo"
    group = doc.sections[0].memo_group
    assert [m.id for m in (group.memos if group else ())] == others  # the others stay as they were read
    again = HwpxDocument.open(doc.to_bytes())
    assert "고친 메모" in [m.text for m in again.notes.memos]
    assert len(again.notes.memos) == len(grouped)  # once each: the changed one is no longer in the group


def test_copying_a_6x_anchor_writes_the_memo_into_the_copied_field() -> None:
    doc = HwpxDocument.open(LEGACY)
    target = next(m for m in doc.sections[0].memo_group.memos if m.paragraph is not None)
    before = [m.id for m in doc.sections[0].memo_group.memos]
    copy = target.paragraph.insert_after()  # a copy of the anchoring paragraph, field and all
    assert [m.id for m in doc.sections[0].memo_group.memos] == before  # no new memo-group entry
    [field] = [n for n in copy.element.iter(f"{HP}fieldBegin") if n.get("type") == "MEMO"]
    assert _param(field, "ID") not in before
    sub_list = field.find(f"{HP}subList")
    assert "".join(t.text or "" for t in sub_list.iter(f"{HP}t")) == target.text
