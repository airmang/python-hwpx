"""Every field python-hwpx writes carries its type's control id as ``fieldid``, as Hancom writes it.

Hancom gives every field of a type the same ``fieldid``: the type's control id, four ASCII
characters read as a big-endian number (a click-here field's 627272811 is ``%clk``). The fields
of the documents Hancom saved in this repository all carry theirs.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.field_marks import FIELD_TYPE_CONTROL_IDS, field_type_id
from hwpx.tools.document_merge import append_document
from hwpx.tools.toc_author import add_native_toc, add_page_crossref

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"


def _hancom_documents() -> list[Path]:
    return sorted((FIXTURES / "hancom_saved").glob("*.hwpx")) + sorted((FIXTURES / "hwpxlib_corpus").glob("*.hwpx"))


def test_the_control_ids_are_the_numbers_hancom_writes() -> None:
    assert field_type_id("CLICK_HERE") == "627272811"
    assert field_type_id("MEMO") == "623209829"
    assert field_type_id("HYPERLINK") == "627600491"
    assert field_type_id("MAILMERGE") == "627928423"


def test_every_field_hancom_saved_carries_its_type_control_id() -> None:
    checked = 0
    for path in _hancom_documents():
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            continue
        with archive:
            for name in archive.namelist():
                if not re.fullmatch(r"Contents/section\d+\.xml", name):
                    continue
                xml = archive.read(name).decode("utf-8", "replace")
                for begin in re.findall(r"<hp:fieldBegin\b[^>]*>", xml):
                    field_type = re.search(r'\btype="([^"]*)"', begin)
                    if field_type is None or field_type.group(1) not in FIELD_TYPE_CONTROL_IDS:
                        continue
                    assert f'fieldid="{field_type_id(field_type.group(1))}"' in begin, (path.name, begin)
                    checked += 1
    assert checked > 300


def _pairs(document: HwpxDocument) -> tuple[list[tuple[str | None, str | None]], list[tuple[str | None, str | None]]]:
    begins, ends = [], []
    for section in document.sections:
        by_id = {begin.get("id"): begin for begin in section.element.iter(f"{HP}fieldBegin")}
        begins += [(begin.get("type"), begin.get("fieldid")) for begin in by_id.values()]
        for end in section.element.iter(f"{HP}fieldEnd"):
            begin = by_id.get(end.get("beginIDRef"))
            ends.append((None if begin is None else begin.get("fieldid"), end.get("fieldid")))
    return begins, ends


def test_new_fields_carry_their_type_control_id() -> None:
    document = HwpxDocument.new()
    heading = document.add_heading("제목", level=1)
    document.fields.add(name="이름", paragraph=document.add_paragraph(""))
    document.add_paragraph("").add_date_field("2000년 1월 1일")
    document.add_paragraph("").add_path_field("문서.hwpx")
    document.add_paragraph("").add_proofreading_mark()
    document.add_paragraph("").add_mail_merge_field(name="받는 사람")
    add_page_crossref(document, document.add_paragraph("쪽: "), heading)
    add_native_toc(document, at_index=1)

    begins, ends = _pairs(document)

    assert {kind for kind, _ in begins} == {
        "CLICK_HERE", "DATE", "PATH", "PROOFREADING_MARKS_SIGN", "MAILMERGE", "CROSSREF", "TABLEOFCONTENTS",
        "HYPERLINK",
    }
    assert all(fieldid == field_type_id(kind) for kind, fieldid in begins)
    assert ends and all(begin_fieldid == end_fieldid for begin_fieldid, end_fieldid in ends)


def test_a_copied_field_carries_its_type_control_id() -> None:
    source = HwpxDocument.new()
    paragraph = source.add_paragraph("")
    source.fields.add(name="이름", paragraph=paragraph)
    begin = next(paragraph.element.iter(f"{HP}fieldBegin"))
    for node in (begin, next(paragraph.element.iter(f"{HP}fieldEnd"))):
        node.set("fieldid", "1234567")  # as python-hwpx wrote it before

    target = HwpxDocument.new()
    append_document(target, source)

    begins, ends = _pairs(target)
    assert begins == [("CLICK_HERE", "627272811")]
    assert ends == [("627272811", "627272811")]


def test_a_field_without_an_end_does_not_take_the_next_fields_end() -> None:
    # Every click-here field shares its fieldid: an end pairs with the begin it names.
    document = HwpxDocument.new()
    first = document.add_paragraph("")
    document.fields.add(name="끝없음", paragraph=first)
    end = next(first.element.iter(f"{HP}fieldEnd"))
    end.getparent().getparent().remove(end.getparent())
    document.fields.add(name="다음", paragraph=document.add_paragraph(""))
    document.fields.fill("다음 값", name="다음")

    assert [(field.name, field.has_end) for field in document.fields.all] == [("끝없음", False), ("다음", True)]
    with pytest.raises(HwpxValueError) as raised:
        document.fields.fill("값", name="끝없음")
    assert raised.value.code == "field-end-missing"
    assert [field.value for field in document.fields.all][1] == "다음 값"
