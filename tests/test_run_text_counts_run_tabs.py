# SPDX-License-Identifier: Apache-2.0
"""``run.text`` counts as ``paragraph.text`` does (asks10a): a tab written as a child of the run -- not inside
``hp:t``, as Hancom writes every tab, but as some other writers put one -- is a character of the run too, so
the runs' texts of a paragraph joined are its text."""

from __future__ import annotations

from lxml import etree

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _paragraph_with_a_run_tab() -> tuple[HwpxDocument, object]:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 문단")  # takes the line holding the section settings
    paragraph = doc.add_paragraph("가나")
    run = paragraph.runs[0].element
    etree.SubElement(run, f"{HP}tab")
    etree.SubElement(run, f"{HP}t").text = "다"
    paragraph.add_run("라")
    return doc, paragraph


def test_the_runs_texts_joined_are_the_paragraph_text() -> None:
    doc, paragraph = _paragraph_with_a_run_tab()
    with doc:
        assert paragraph.text == "가나\t다라"
        assert [run.text for run in paragraph.runs] == ["가나\t다", "라"]
        assert "".join(run.text for run in paragraph.runs) == paragraph.text


def test_a_tab_control_counts_too() -> None:
    doc = HwpxDocument.new()
    with doc:
        doc.add_paragraph("첫 문단")
        paragraph = doc.add_paragraph("가")
        etree.SubElement(paragraph.runs[0].element, f"{HP}ctrl", {"id": "tab"})
        assert paragraph.runs[0].text == paragraph.text == "가\t"


def test_writing_the_run_text_replaces_its_run_tabs() -> None:
    doc, paragraph = _paragraph_with_a_run_tab()
    with doc:
        run = paragraph.runs[0]
        run.text = "새\t글"
        assert run.text == "새\t글"
        assert run.element.find(f"{HP}tab") is None  # the tab is in the hp:t now, as Hancom writes it
        assert paragraph.text == "새\t글라"


def test_hancom_runs_read_as_before() -> None:
    doc = HwpxDocument.new()
    with doc:
        doc.add_paragraph("첫 문단")
        paragraph = doc.add_paragraph("가\t나\n다")
        assert "".join(run.text for run in paragraph.runs) == paragraph.text == "가\t나\n다"
