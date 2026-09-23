# SPDX-License-Identifier: Apache-2.0
"""Hyperlinks carry the target where Hancom reads it: the field's parameters.

A link written with only ``fieldBegin@name`` survived a Hancom SDK 13.60 save
but pointed nowhere (Hancom added ``Category=HWPHYPERLINK_TYPE_HWP`` and no
``Command``). The expected forms below are Hancom's own, from the SDK gold
corpus (1,267 web and mail links, 434 bookmark links).
"""
from __future__ import annotations

import io
from zipfile import ZipFile

from hwpx import HwpxDocument
from hwpx.tools.markdown_export import export_markdown
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _field_begin(paragraph):
    return next(n for n in paragraph.element.iter(f"{HP}fieldBegin") if n.get("type") == "HYPERLINK")


def _params(field_begin) -> dict[str, str | None]:
    params = field_begin.find(f"{HP}parameters")
    assert params is not None
    return {p.get("name"): p.text for p in params}


def test_web_link_carries_hancoms_command_and_path() -> None:
    doc = HwpxDocument.new()
    doc.refs.add_hyperlink("https://example.com/a?b=c", "링크")
    begin = _field_begin(doc.paragraphs[-1])
    params = _params(begin)
    assert list(params) == ["Prop", "Command", "Path", "Category", "TargetType", "DocOpenType"]
    assert params["Command"] == "https\\://example.com/a\\?b=c;1;0;0;"
    assert params["Path"] == "https://example.com/a?b=c"
    assert params["Category"] == "HWPHYPERLINK_TYPE_URL"
    assert params["TargetType"] == "HWPHYPERLINK_TARGET_BOOKMARK"
    assert params["DocOpenType"] == "HWPHYPERLINK_JUMP_CURRENTTAB"
    assert begin.get("fieldid") == "627600491"
    assert begin.find(f"{HP}parameters").get("cnt") == "6"


def test_mail_link_uses_hancoms_email_form() -> None:
    doc = HwpxDocument.new()
    doc.refs.add_hyperlink("mailto:someone@example.com", "메일")
    params = _params(_field_begin(doc.paragraphs[-1]))
    assert params["Command"] == "mailto:someone@example.com;2;0;0"
    assert params["Path"] == "mailto:someone@example.com"
    assert params["Category"] == "HWPHYPERLINK_TYPE_EMAIL"


def test_bookmark_link_uses_hancoms_in_document_form() -> None:
    doc = HwpxDocument.new()
    doc.refs.add_bookmark("책갈피1", paragraph=doc.add_paragraph("대상"))
    doc.refs.add_hyperlink("#책갈피1", "책갈피로")
    params = _params(_field_begin(doc.paragraphs[-1]))
    assert params["Command"] == "?책갈피1;0;0;0;"
    assert "Path" not in params
    assert params["Category"] == "HWPHYPERLINK_TYPE_HWP"


def test_every_reader_gives_back_the_url_it_was_given() -> None:
    doc = HwpxDocument.new()
    doc.refs.add_hyperlink("https://example.com/a?b=c", "링크")
    assert doc.paragraphs[-1].hyperlinks[0]["url"] == "https://example.com/a?b=c"
    # the link text may carry the link's own character styling
    assert "](https://example.com/a?b=c)" in export_markdown(doc)
    options = AnnotationOptions(hyperlink="target", hyperlink_target_format="<{target}>")
    with ZipFile(io.BytesIO(doc.to_bytes())) as archive, TextExtractor(archive) as extractor:
        texts = [p.text(annotations=options) for p in extractor.iter_document_paragraphs(include_nested=False)]
    assert any("<https://example.com/a?b=c>" in text for text in texts)


def _hancom_link(doc: HwpxDocument, params: dict[str, str]) -> None:
    """Append a link in the exact shape Hancom writes (empty @name)."""
    paragraph = doc.add_paragraph("")
    doc.refs.add_hyperlink("https://placeholder.invalid", "한컴 링크", paragraph=paragraph)
    begin = _field_begin(paragraph)
    begin.set("name", "")
    holder = begin.find(f"{HP}parameters")
    for child in list(holder):
        holder.remove(child)
    for name, text in params.items():
        param = holder.makeelement(f"{HP}{'integerParam' if name == 'Prop' else 'stringParam'}", {"name": name})
        param.text = text
        holder.append(param)
    holder.set("cnt", str(len(params)))


def test_readers_resolve_a_hancom_authored_web_link() -> None:
    doc = HwpxDocument.new()
    _hancom_link(doc, {"Prop": "0", "Command": "https\\://www.example.go.kr;1;0;0;",
                       "Path": "https://www.example.go.kr", "Category": "HWPHYPERLINK_TYPE_URL"})
    assert doc.paragraphs[-1].hyperlinks[0]["url"] == "https://www.example.go.kr"
    assert "](https://www.example.go.kr)" in export_markdown(doc)


def test_command_only_link_is_unescaped_and_loses_its_tail() -> None:
    doc = HwpxDocument.new()
    _hancom_link(doc, {"Prop": "0", "Command": "http\\://example.kr/a\\?b=1|tip;1;0;0;",
                       "Category": "HWPHYPERLINK_TYPE_URL"})
    assert doc.paragraphs[-1].hyperlinks[0]["url"] == "http://example.kr/a?b=1"


def test_hancom_bookmark_link_reads_back_as_hash_name() -> None:
    doc = HwpxDocument.new()
    _hancom_link(doc, {"Prop": "0", "Command": "?책갈피1;0;0;0;", "Category": "HWPHYPERLINK_TYPE_HWP"})
    assert doc.paragraphs[-1].hyperlinks[0]["url"] == "#책갈피1"
