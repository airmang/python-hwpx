# SPDX-License-Identifier: Apache-2.0
"""A header or footer is written once, where Hancom keeps it (audit7 create C19).

Up to 6.x ``doc.page.set_header()``/``set_footer()`` wrote the story twice: a copy under ``hp:secPr``
with an ``hp:headerApply`` pointing at it (neither is in the OWPML schema) and an ``hp:ctrl`` copy in
the body, the only one Hancom reads. Every Hangul-saved document with a header in the public corpus
(68) has the ``hp:ctrl`` story alone. 7.0 writes that one copy; a 6.x document's ``hp:secPr`` copy
goes when its header is set again.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EVEN_ODD = next((FIXTURES / "hwpxlib_corpus").glob("error__20250808__*.hwpx"))
FUZZ_BASELINE = FIXTURES / "fuzz_regressions" / "seed-000000-baseline.hwpx"
HEADER_FOOTER = FIXTURES / "hwpxlib_corpus" / "reader_writer__HeaderFooter.hwpx"


def _section(data: bytes, index: int = 0) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return etree.fromstring(archive.read(f"Contents/section{index}.xml"))


def _under_secpr(section: etree._Element) -> list[str]:
    return [
        etree.QName(child).localname
        for sec_pr in section.iter(f"{HP}secPr")
        for child in sec_pr
        if etree.QName(child).localname in ("header", "footer", "headerApply", "footerApply")
    ]


def _control_stories(section: etree._Element, kind: str) -> list[tuple[str | None, str]]:
    return [
        (story.get("applyPageType"), "".join(story.itertext()))
        for ctrl in section.iter(f"{HP}ctrl")
        for story in ctrl
        if story.tag == f"{HP}{kind}"
    ]


@pytest.mark.parametrize("page_type", ["BOTH", "ODD", "EVEN"])
def test_set_header_and_footer_write_one_control_story(page_type: str) -> None:
    doc = HwpxDocument.new()
    doc.page.set_header(text="머리말", page_type=page_type)
    doc.page.set_footer(content=[{"children": [{"type": "run", "text": "쪽 "}, {"type": "page_number"}]}],
                        page_type=page_type)
    data = doc.to_bytes()

    section = _section(data)
    assert _under_secpr(section) == []
    assert _control_stories(section, "header") == [(page_type, "머리말")]
    assert [page for page, _ in _control_stories(section, "footer")] == [page_type]
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    assert [story.text for story in reopened.page.headers()] == ["머리말"]
    # the text of a header no longer comes twice out of the whole-document walk or a search
    assert [p.paragraph.text for p in reopened.text.paragraphs(where="header")] == ["머리말"]


def test_setting_a_header_again_changes_the_one_story_in_place() -> None:
    doc = HwpxDocument.new()
    first = doc.page.set_header(text="하나")
    second = doc.page.set_header(text="둘")

    section = _section(doc.to_bytes())
    assert second.id == first.id and second.element is first.element
    assert _control_stories(section, "header") == [("BOTH", "둘")]


@pytest.mark.parametrize("kind", ["header", "footer"])
def test_a_hangul_saved_story_is_set_where_hangul_keeps_it(kind: str) -> None:
    doc = HwpxDocument.open(HEADER_FOOTER)
    stories = getattr(doc.page, f"{kind}s")(section=0)
    before = [(story.page_type, story.id) for story in stories]
    assert [page for page, _id in before] == ["BOTH"]

    getattr(doc.page, f"set_{kind}")(text="바뀐 글", section=0)
    data = doc.to_bytes()

    section = _section(data)
    assert _under_secpr(section) == []
    reopened = HwpxDocument.open(data)
    assert [(story.page_type, story.id) for story in getattr(reopened.page, f"{kind}s")(section=0)] == before
    assert _control_stories(section, kind) == [("BOTH", "바뀐 글")]
    assert reopened.validate().ok


@pytest.mark.filterwarnings("ignore::UserWarning")  # the later ODD footer holds a page number
def test_a_hangul_saved_story_later_in_the_body_stays() -> None:
    # A footer control after the first paragraph changes the footer from its page on (Hangul-saved
    # EVEN/ODD footers here sit in paragraphs 83 and 93). Setting the section's footer adds the
    # first-paragraph one and leaves those.
    doc = HwpxDocument.open(EVEN_ODD)
    before = _control_stories(doc.sections[0].element, "footer")

    doc.page.set_footer(text="첫 쪽부터", page_type="ODD", section=0)

    after = _control_stories(_section(doc.to_bytes()), "footer")
    assert after[0] == ("ODD", "첫 쪽부터") and after[1:] == before
    assert _under_secpr(doc.sections[0].element) == []


def test_a_6x_document_keeps_one_copy_of_the_header_it_sets_again() -> None:
    doc = HwpxDocument.open(FUZZ_BASELINE)
    assert "header" in _under_secpr(doc.sections[0].element)
    kept = [name for name in _under_secpr(doc.sections[0].element) if name.startswith("footer")]

    doc.page.set_header(text="다시 쓴 머리말", page_type="BOTH", section=0)
    data = doc.to_bytes()

    section = _section(data)
    stories = [text for page, text in _control_stories(section, "header") if page == "BOTH"]
    assert stories == ["다시 쓴 머리말"]
    remaining = _under_secpr(section)
    # the BOTH header's hp:secPr copy and its apply element are gone; other stories stay as written
    secpr_both = [
        child for sec_pr in section.iter(f"{HP}secPr") for child in sec_pr
        if child.tag == f"{HP}header" and child.get("applyPageType", "BOTH") == "BOTH"
    ]
    assert secpr_both == []
    assert [name for name in remaining if name.startswith("footer")] == kept
    assert HwpxDocument.open(data).validate().ok


def test_a_refused_header_leaves_no_empty_control() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(ValueError):
        doc.page.set_header(content=[{"children": [{"type": "nope"}]}])
    section = _section(doc.to_bytes())
    assert _control_stories(section, "header") == [] and _under_secpr(section) == []
