# SPDX-License-Identifier: Apache-2.0
"""Every container of paragraphs takes ``add_paragraph(text="", *, style=None, para_pr_id_ref=None,
char_pr_id_ref=None)`` and returns a ``Paragraph`` (7.0, N8): the document and its sections, a table
cell, a header or footer, a master page and a note.

``style`` gives the paragraph the style and its paragraph and character shapes unless those are
passed; the rest is a property of the returned paragraph.
"""

from __future__ import annotations

import inspect

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.model import Paragraph

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
COMMON = ("style", "para_pr_id_ref", "char_pr_id_ref")


def _containers(document: HwpxDocument) -> dict[str, object]:
    document.add_paragraph("본문")
    header = document.page.set_header(text="머리말")
    master = document.parts.add_master_page(text="바탕쪽", section=0)
    master_page = next(page for page in document.parts.master_pages if page.id == getattr(master, "id", master))
    note = document.paragraphs[-1].add_footnote("각주")
    cell = document.add_table(1, 1).cell(0, 0)
    return {
        "Document": document.oxml,
        "Section": document.oxml.sections[0],
        "TableCell": cell,
        "HeaderFooter": header,
        "MasterPage": master_page,
        "Note": note,
    }


def _first_run_char_pr(paragraph: Paragraph) -> str | None:
    run = paragraph.element.find(f"{HP}run")
    return None if run is None else run.get("charPrIDRef")


@pytest.mark.parametrize("name", ["Document", "Section", "TableCell", "HeaderFooter", "MasterPage", "Note"])
def test_each_container_takes_the_common_keywords(name: str) -> None:
    container = _containers(HwpxDocument.new())[name]
    parameters = inspect.signature(container.add_paragraph).parameters  # type: ignore[attr-defined]
    first = next(iter(parameters.values()))
    assert first.name == "text" and first.default == ""
    for keyword in COMMON:
        assert parameters[keyword].kind is inspect.Parameter.KEYWORD_ONLY and parameters[keyword].default is None
    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())


@pytest.mark.parametrize("name", ["HeaderFooter", "MasterPage", "Note"])
def test_style_gives_the_style_and_its_shapes(name: str) -> None:
    document = HwpxDocument.new()
    container = _containers(document)[name]
    style = document.styles.resolve("차례 제목")
    paragraph = container.add_paragraph("글", style="차례 제목")  # type: ignore[attr-defined]
    assert isinstance(paragraph, Paragraph) and paragraph.text == "글"
    assert paragraph.element.get("styleIDRef") == str(style.id)
    assert paragraph.element.get("paraPrIDRef") == str(style.para_pr_id_ref)
    assert _first_run_char_pr(paragraph) == str(style.char_pr_id_ref)
    # shapes given win over the style's
    other = container.add_paragraph("둘", style="차례 제목", para_pr_id_ref=1, char_pr_id_ref=0)  # type: ignore[attr-defined]
    assert (other.element.get("paraPrIDRef"), _first_run_char_pr(other)) == ("1", "0")
    reopened = HwpxDocument.open(document.to_bytes())
    assert reopened.validate().ok


def test_an_unknown_style_is_refused_before_anything_changes() -> None:
    document = HwpxDocument.new()
    header = _containers(document)["HeaderFooter"]
    before = len(header.paragraphs)  # type: ignore[attr-defined]
    with pytest.raises(HwpxError) as caught:
        header.add_paragraph("글", style="없는 스타일")  # type: ignore[attr-defined]
    assert caught.value.code == "style-not-found"
    assert len(header.paragraphs) == before  # type: ignore[attr-defined]


def test_note_add_hyperlink_returns_the_link_as_paragraph_hyperlinks_reads_it() -> None:
    from hwpx.objects import Hyperlink

    document = HwpxDocument.new()
    note = _containers(document)["Note"]
    link = note.add_hyperlink("https://example.com", "보기")  # type: ignore[attr-defined]
    assert isinstance(link, Hyperlink)
    assert (link.url, link.text) == ("https://example.com", "보기")
    assert link.element is note.body_paragraph.hyperlinks[-1].element  # type: ignore[attr-defined]


def test_a_header_paragraph_without_options_is_written_as_before() -> None:
    document = HwpxDocument.new()
    header = _containers(document)["HeaderFooter"]
    paragraph = header.add_paragraph("둘째 줄")  # type: ignore[attr-defined]
    runs = paragraph.element.findall(f"{HP}run")
    assert [run.get("charPrIDRef") for run in runs] == ["0"]
    assert paragraph.element.get("paraPrIDRef") == "0" and paragraph.element.get("styleIDRef") == "0"
    empty = header.add_paragraph()  # type: ignore[attr-defined]
    assert empty.element.find(f"{HP}run") is None
