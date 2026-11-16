# SPDX-License-Identifier: Apache-2.0
"""Removing the paragraph that starts a section keeps the section's settings (7.0 fix).

The first paragraph of a section holds ``hp:secPr`` (paper, margins, numbering start) and the
page-level controls (columns, header, footer, page numbering). Removing it used to take them
along: the page became 0 x 0 and the save failed ("hp:secPr missing hp:startNum").
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURE = Path(__file__).parent / "fixtures" / "hancom_saved" / "new_page_number_largest_kept.hwpx"


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    return HwpxDocument.open(buffer.getvalue())


def _two_lines() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 줄")
    doc.add_paragraph("둘째")
    return doc


def test_removing_the_first_paragraph_keeps_the_page_setup() -> None:
    doc = _two_lines()
    size = doc.page.size()
    doc.paragraphs[0].remove()
    assert doc.page.size() == size
    assert size.width > 0 and size.height > 0
    again = _reopened(doc)
    assert [p.text for p in again.paragraphs] == ["둘째"]
    assert again.page.size() == size
    assert again.validate().ok


@pytest.mark.parametrize(
    "remove",
    [
        lambda doc: doc.paragraphs[0].remove(),
        lambda doc: doc.sections[0].remove_paragraph(0),
        lambda doc: doc.sections[0].remove_paragraph(doc.paragraphs[0]),
    ],
    ids=["paragraph.remove", "section.remove_paragraph-index", "section.remove_paragraph-object"],
)
def test_every_removal_path_moves_the_settings_to_the_next_paragraph(remove) -> None:
    doc = _two_lines()
    remove(doc)
    first = doc.sections[0].element.find(f"{HP}p")
    assert first.find(f"{HP}run/{HP}secPr") is not None
    assert first.find(f"{HP}run/{HP}ctrl/{HP}colPr") is not None
    # the settings come first, ahead of the text
    assert first.find(f"{HP}run").find(f"{HP}secPr") is not None
    assert doc.paragraphs[0].text == "둘째"


def test_the_model_level_remove_paragraph_moves_them_too() -> None:
    doc = _two_lines()
    doc.oxml.remove_paragraph(0, section=0)
    assert doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr") is not None
    assert _reopened(doc).page.size().width > 0


def test_a_header_set_on_the_page_survives_removing_the_first_paragraph() -> None:
    doc = HwpxDocument.new()
    doc.page.set_header(text="머리말")
    doc.add_paragraph("지울 줄")
    doc.add_paragraph("남는 줄")
    doc.paragraphs[0].remove()
    again = _reopened(doc)
    assert [p.text for p in again.paragraphs] == ["남는 줄"]
    assert [place.paragraph.text for place in again.text.iter_paragraphs(where="header")] == ["머리말"]


def test_a_hancom_saved_first_paragraph_hands_over_its_footer() -> None:
    doc = HwpxDocument.open(FIXTURE)
    size = doc.page.size(section=0)
    second_text = doc.paragraphs[1].text
    doc.paragraphs[0].remove()
    first = doc.sections[0].element.find(f"{HP}p")
    assert first.find(f"{HP}run/{HP}secPr") is not None
    assert first.find(f"{HP}run/{HP}ctrl/{HP}footer") is not None
    assert first.find(f"{HP}linesegarray") is None  # the controls in front shift every cached position
    assert doc.paragraphs[0].text == second_text
    again = _reopened(doc)
    assert again.page.size(section=0) == size
    assert again.validate().ok


def test_settings_sharing_a_run_with_text_move_without_the_text() -> None:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "설정과 같은 run의 글"
    doc.add_paragraph("다음")
    doc.paragraphs[0].remove()
    assert [p.text for p in doc.paragraphs] == ["다음"]
    assert doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr") is not None


def test_the_only_paragraph_is_still_refused() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.paragraphs[0].remove()
    assert excinfo.value.code == "paragraph-remove-last"


def test_settings_with_no_paragraph_after_them_are_refused() -> None:
    doc = _two_lines()
    section = doc.sections[0].element
    first, second = section.findall(f"{HP}p")
    section.remove(first)
    section.append(first)  # the settings paragraph is now the last one
    with pytest.raises(HwpxValueError) as excinfo:
        doc.sections[0].paragraphs[-1].remove()
    assert excinfo.value.code == "paragraph-remove-section-settings"
    assert section.find(f"{HP}p/{HP}run/{HP}secPr") is not None


def test_a_later_paragraph_is_removed_as_before() -> None:
    doc = _two_lines()
    doc.paragraphs[1].remove()
    assert [p.text for p in doc.paragraphs] == ["첫 줄"]


def test_removing_the_settings_run_is_refused() -> None:
    doc = _two_lines()
    runs = doc.paragraphs[0].runs
    settings_run = next(run for run in runs if run.element.find(f"{HP}secPr") is not None)
    with pytest.raises(HwpxValueError) as excinfo:
        settings_run.remove()
    assert excinfo.value.code == "paragraph-run-section-settings"
    assert doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr") is not None


def test_removing_a_run_that_shares_the_settings_keeps_them() -> None:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "글"
    (run,) = doc.paragraphs[0].runs
    run.remove()
    assert doc.paragraphs[0].text == ""
    assert doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr") is not None
    assert _reopened(doc).page.size().width > 0
