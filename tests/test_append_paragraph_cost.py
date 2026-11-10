"""Appending a paragraph, a heading or a formatted paragraph does not wrap every body paragraph."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx._document import layout
from hwpx.oxml.section import HwpxOxmlSection


@pytest.fixture
def body_lists(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = HwpxOxmlSection.paragraphs.fget
    assert original is not None

    def counting(self: HwpxOxmlSection):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(HwpxOxmlSection, "paragraphs", property(counting))
    return calls


def test_add_paragraph_reads_only_the_last_paragraph(body_lists: list[int]) -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("하나", para_pr_id_ref=1, style_id_ref=2)
    second = document.add_paragraph("둘")

    assert (second.para_pr_id_ref, second.style_id_ref) == (first.para_pr_id_ref, first.style_id_ref)
    assert body_lists == []


def test_heading_and_object_format_do_not_list_the_body(body_lists: list[int]) -> None:
    document = HwpxDocument.new()
    for index in range(5):
        document.add_paragraph(f"문단 {index}")
    body_lists.clear()

    heading = document.add_heading("제목", level=2)
    result = document.styles.apply_paragraph_format(paragraphs=[heading], keep_with_next=True)

    assert result.paragraphs == (6,)
    assert body_lists == []


def test_body_indexes_match_the_body_list() -> None:
    document = HwpxDocument.new()
    for index in range(6):
        document.add_paragraph(f"문단 {index}")
    table = document.add_table(2, 2)
    body = document.paragraphs
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    other = HwpxDocument.new().add_paragraph("다른 문서")

    few = [body[4], cell_paragraph, body[0], other, body[-1]]
    assert layout._body_indexes(document, few) == [4, None, 0, None, len(body) - 1]

    many = list(body) + [cell_paragraph]
    assert layout._body_indexes(document, many) == [*range(len(body)), None]
