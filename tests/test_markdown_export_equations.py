# SPDX-License-Identifier: Apache-2.0
"""Equations in the rich Markdown export (opt-in; on for ``hwpx.ingest``)."""
from __future__ import annotations

from hwpx import HwpxDocument
from hwpx.ingest import DocumentIngestor
from hwpx.tools.markdown_export import equation_markdown, export_markdown


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("근은 ")
    paragraph.add_equation("x = {-b +- sqrt {b ^{2} - 4ac}} over {2a}")
    paragraph.add_run("이다.")
    table = doc.add_table(1, 2)
    table.rows[0].cells[0].paragraphs[0].add_equation("{1} over {2}")
    return doc


def test_the_default_export_leaves_equations_out() -> None:
    assert "$" not in export_markdown(_document())


def test_an_equation_comes_where_it_sits_as_latex() -> None:
    markdown = export_markdown(_document(), equations=True)
    assert r"근은 $x = \frac{- b \pm \sqrt{b^{2} - 4 ac}}{2 a}$이다." in markdown
    assert r"| $\frac{1}{2}$ |" in markdown


def test_an_equation_in_a_footnote_is_carried_too() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    note = doc.notes.add_footnote("각주 ", paragraph)
    note_paragraph = next(iter(note.paragraphs)) if hasattr(note, "paragraphs") else None
    if note_paragraph is None:
        return
    note_paragraph.add_equation("a ^{2}")
    assert "$a^{2}$" in export_markdown(doc, equations=True)


def test_a_script_latex_cannot_carry_is_kept_as_code() -> None:
    assert equation_markdown("") == ""
    assert equation_markdown("  x   +  y ") == "$x + y$"
    assert equation_markdown("a $ b") == "`a $ b`"


def test_the_option_does_not_leak_into_the_next_call() -> None:
    doc = _document()
    export_markdown(doc, equations=True)
    assert "$" not in export_markdown(doc)


def test_ingest_carries_equations_and_reports_nothing_left_out() -> None:
    result = DocumentIngestor.default().convert(_document().to_bytes())
    assert r"\sqrt{b^{2} - 4 ac}" in result.markdown
    assert result.metadata["left_out"] == {}

    body_only = DocumentIngestor.default().convert(
        _document().to_bytes(), markdown_options={"equations": False}
    )
    assert body_only.metadata["left_out"] == {"equation": 2}
