# SPDX-License-Identifier: Apache-2.0
"""책갈피·하이퍼링크·상호 참조 — 문서 전체 읽기, 고치기, 지우기."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.objects import CrossReference, Hyperlink

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not [issue for issue in again.validate().issues if issue.severity == "error"]
    return again


def _hancom_doc_with_link() -> Path:
    for path in sorted((FIXTURES / "gui_probes").glob("*.hwpx")):
        if HwpxDocument.open(path).refs.hyperlinks:
            return path
    pytest.skip("no Hancom-saved document with a hyperlink")


def test_links_are_reached_in_cells_and_notes() -> None:
    doc = HwpxDocument.new()
    host = doc.add_paragraph("표")
    cell = host.add_table(1, 1).cell(0, 0).paragraphs[0]
    cell.add_hyperlink("https://a.example", "칸 링크")
    note = doc.notes.add_footnote("각주 ", host)
    note.add_hyperlink("https://b.example", "각주 링크")
    doc.add_paragraph("본문 ").add_hyperlink("https://c.example", "본문 링크")
    links = doc.refs.hyperlinks
    assert all(isinstance(link, Hyperlink) for link in links)
    assert [(link.url, link.text) for link in links] == [
        ("https://a.example", "칸 링크"),
        ("https://b.example", "각주 링크"),
        ("https://c.example", "본문 링크"),
    ]
    assert links[0].paragraph.element is cell.element


def test_link_target_and_text_can_be_changed() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("보기: ")
    paragraph.add_hyperlink("https://old.example", "옛 글")
    (link,) = paragraph.hyperlinks
    style = link.element.getparent().getparent().getnext().get("charPrIDRef")
    link.url = "mailto:me@example.com"
    link.text = "새 글"
    assert (link.url, link.text) == ("mailto:me@example.com", "새 글")
    assert paragraph.text == "보기: 새 글"
    assert paragraph.element.find(f"{HP}linesegarray") is None
    again = _reopen(doc).refs.hyperlinks[0]
    assert (again.url, again.text) == ("mailto:me@example.com", "새 글")
    text_run = again.element.getparent().getparent().getnext()
    assert text_run.get("charPrIDRef") == style  # 링크 글의 모양이 남는다


def test_link_remove_leaves_its_text() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("보기: ")
    paragraph.add_hyperlink("https://x.example", "링크")
    paragraph.hyperlinks[0].remove()
    assert paragraph.hyperlinks == ()
    assert paragraph.text == "보기: 링크"
    assert paragraph.element.find(f".//{HP}fieldBegin") is None
    assert paragraph.element.find(f".//{HP}fieldEnd") is None
    _reopen(doc)


def test_link_remove_with_its_text() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("보기: ")
    paragraph.add_hyperlink("https://x.example", "링크")
    paragraph.hyperlinks[0].remove(keep_text=False)
    assert paragraph.text == "보기: "
    _reopen(doc)


def test_old_dict_reading_still_works_with_a_warning() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_hyperlink("https://x.example", "링크")
    with pytest.warns(DeprecationWarning):
        assert paragraph.hyperlinks[0]["url"] == "https://x.example"
    assert paragraph.hyperlinks[0].to_dict()["url"] == "https://x.example"


def test_edit_a_link_in_a_hancom_saved_document() -> None:
    path = _hancom_doc_with_link()
    original = path.read_bytes()
    doc = HwpxDocument.open(original)
    link = doc.refs.hyperlinks[0]
    link.url = "https://www.example.org/새"
    link.text = "바뀐 링크"
    data = doc.to_bytes()
    again = HwpxDocument.open(data)
    assert not [i for i in again.validate().issues if i.severity == "error"]
    first = again.refs.hyperlinks[0]
    assert (first.url, first.text) == ("https://www.example.org/새", "바뀐 링크")
    with zipfile.ZipFile(io.BytesIO(original)) as a, zipfile.ZipFile(io.BytesIO(data)) as b:
        changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
    assert changed and all(n.startswith("Contents/section") for n in changed)


def test_bookmark_rename_follows_links_to_it() -> None:
    doc = HwpxDocument.new()
    target = doc.add_paragraph("목표")
    doc.refs.add_bookmark("옛이름", paragraph=target)
    doc.add_paragraph("").add_hyperlink("#옛이름", "가기")
    (bookmark,) = doc.refs.bookmarks
    renamed = bookmark.rename("새이름")
    assert renamed.name == "새이름"
    assert [b.name for b in doc.refs.bookmarks] == ["새이름"]
    assert doc.refs.hyperlinks[0].url == "#새이름"
    again = _reopen(doc)
    assert [b.name for b in again.refs.bookmarks] == ["새이름"]
    assert again.refs.hyperlinks[0].url == "#새이름"


def test_bookmark_remove_point_and_field() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가")
    doc.refs.add_bookmark("점", paragraph=paragraph)
    doc.refs.bookmarks[0].remove()
    assert doc.refs.bookmarks == ()
    assert paragraph.element.find(f".//{HP}bookmark") is None
    assert paragraph.text == "가"
    _reopen(doc)

    # 한/글의 다른 저장 형태: fieldBegin type="BOOKMARK" … fieldEnd 가 글을 감싼다
    spanning = doc.add_paragraph("앞 ")
    spanning.add_hyperlink("https://x.example", "감싼 글")
    begin = spanning.element.find(f".//{HP}fieldBegin")
    begin.set("type", "BOOKMARK")
    begin.set("name", "구간")
    begin.remove(begin.find(f"{HP}parameters"))
    (field_mark,) = doc.refs.bookmarks
    assert (field_mark.kind, field_mark.text) == ("field", "감싼 글")
    field_mark.remove()
    assert doc.refs.bookmarks == ()
    assert spanning.text == "앞 감싼 글"
    assert spanning.element.find(f".//{HP}fieldEnd") is None
    _reopen(doc)


def test_cross_references_say_what_they_point_at() -> None:
    doc = HwpxDocument.open((FIXTURES / "m7_toc_gold" / "hancom-native-toc-A.hwpx").read_bytes())
    refs = doc.refs.cross_references
    assert refs and all(isinstance(ref, CrossReference) for ref in refs)
    ref = refs[0]
    assert (ref.ref_type, ref.content_type, ref.hyperlink) == ("TARGET_OUTLINE", "OBJECT_TYPE_PAGE", False)
    assert ref.target.startswith("#") and ref.target[1:].isdigit()
    assert ref.text == "2"
    ids = {p.get("id") for s in doc.oxml.sections for p in s.element.iter(f"{HP}p")}
    assert ref.target[1:] in ids  # 가리키는 문단이 문서에 있다
