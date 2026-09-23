# SPDX-License-Identifier: Apache-2.0
"""Content-level read-fidelity harness tests.

The A1 harness (``roundtrip_diff``) measures *element-count* preservation. This
harness measures *content* fidelity: that per-run resolved formatting
(bold/italic/underline/strikeout/color/size/font) and footnote/endnote bodies
survive open->save->reopen, and provides the canonical extraction the installed
MCP surface is verified against (P2/P3).
"""
from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.read_fidelity import (
    RunSpan,
    collect_notes,
    corpus_fidelity,
    notes_fidelity,
    resolve_run_spans,
    roundtrip_fidelity,
    spans_fidelity,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SHOWCASE = EXAMPLES / "FormattingShowcase.hwpx"


def _authored_note_doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문 문장 하나.")
    note = p.add_footnote("각주 본문 ")
    note.add_run("강조", bold=True)
    p2 = doc.add_paragraph("두 번째 문장.")
    p2.add_endnote("미주 본문 END")
    return doc


# ── resolve_run_spans ────────────────────────────────────────────────
def test_resolve_run_spans_shape():
    doc = HwpxDocument.open(SHOWCASE)
    spans = resolve_run_spans(doc)
    assert spans and all(isinstance(s, RunSpan) for s in spans)


def test_strikeout_not_falsely_true():
    """Regression: <hh:strikeout shape='NONE'/> is ALWAYS present; membership
    check `'strikeout' in child_attributes` wrongly reports strikeout on plain
    runs. Fidelity must normalise on the shape attribute."""
    doc = HwpxDocument.open(SHOWCASE)
    spans = resolve_run_spans(doc)
    # FormattingShowcase has no struck-through text -> every span strikeout False
    assert all(s.strikeout is False for s in spans)


def test_bold_italic_detected():
    doc = HwpxDocument.open(SHOWCASE)
    spans = resolve_run_spans(doc)
    assert any(s.bold for s in spans), "expected at least one bold run"
    assert any(s.italic for s in spans), "expected at least one italic run"


def test_size_and_color_surfaced():
    doc = HwpxDocument.open(SHOWCASE)
    spans = resolve_run_spans(doc)
    sizes = {s.size_pt for s in spans if s.size_pt}
    assert len(sizes) >= 2, f"expected >=2 distinct run sizes, got {sizes}"
    assert any(s.color and s.color != "#000000" for s in spans), "expected a coloured run"


def test_underline_normalised_off_is_none():
    doc = HwpxDocument.open(SHOWCASE)
    spans = resolve_run_spans(doc)
    # underline type NONE must normalise to None, never the literal "NONE"
    assert all(s.underline != "NONE" for s in spans)


_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _span_for(doc: HwpxDocument, text: str) -> RunSpan:
    return next(s for s in resolve_run_spans(doc) if s.text == text)


def _set_char_pr_offset(doc: HwpxDocument, char_pr_id: str, value: str) -> None:
    char_props = doc.oxml.headers[0]._char_properties_element()
    offset = char_props.find(f"{_HH}charPr[@id='{char_pr_id}']/{_HH}offset")
    for lang in list(offset.attrib):
        offset.set(lang, value)


def test_script_read_from_its_element():
    """Hancom marks a script by ``hh:supscript``/``hh:subscript`` alone
    (offset 0), and so does ``ensure_run(script=...)``."""
    doc = HwpxDocument.new()
    doc.add_paragraph("보통")  # first: a later add_paragraph inherits the previous run's charPr
    doc.add_paragraph("위", char_pr_id_ref=doc.styles.ensure_run(script="sup"))
    doc.add_paragraph("아래", char_pr_id_ref=doc.styles.ensure_run(script="sub"))
    assert (_span_for(doc, "위").superscript, _span_for(doc, "위").subscript) == (True, False)
    assert (_span_for(doc, "아래").superscript, _span_for(doc, "아래").subscript) == (False, True)
    assert (_span_for(doc, "보통").superscript, _span_for(doc, "보통").subscript) == (False, False)


def test_script_with_legacy_offset_keeps_its_direction():
    """Earlier python-hwpx wrote offset -30 next to a superscript (a negative
    offset raises the glyphs, DEV-028). The element decides, not the sign."""
    doc = HwpxDocument.new()
    sup = doc.styles.ensure_run(script="sup")
    _set_char_pr_offset(doc, sup, "-30")
    doc.add_paragraph("위", char_pr_id_ref=sup)
    span = _span_for(doc, "위")
    assert (span.superscript, span.subscript) == (True, False)


def test_offset_alone_is_not_a_script():
    """A raised or lowered glyph without the element is Hancom's character
    offset, not a superscript or subscript."""
    doc = HwpxDocument.new()
    raised = doc.styles.ensure_run(bold=True)
    _set_char_pr_offset(doc, raised, "-30")
    doc.add_paragraph("올림", char_pr_id_ref=raised)
    span = _span_for(doc, "올림")
    assert (span.superscript, span.subscript) == (False, False)


# ── notes ────────────────────────────────────────────────────────────
def test_collect_notes_footnote_and_endnote():
    notes = collect_notes(_authored_note_doc())
    kinds = {n.kind for n in notes}
    assert "footNote" in kinds and "endNote" in kinds
    fn = next(n for n in notes if n.kind == "footNote")
    assert "각주 본문" in fn.body_text and "강조" in fn.body_text
    assert any(s.bold for s in fn.body_spans), "footnote body bold span lost"


# ── round-trip fidelity ──────────────────────────────────────────────
def test_roundtrip_run_format_fidelity_showcase():
    rep = roundtrip_fidelity(SHOWCASE)
    assert rep["run_format"]["fidelity"] == 1.0
    assert rep["run_format"]["count_match"] is True


def test_roundtrip_note_fidelity_authored():
    data = _authored_note_doc().to_bytes()
    rep = roundtrip_fidelity(data)
    assert rep["notes"]["fidelity"] == 1.0
    assert rep["notes"]["count_ref"] == 2


# ── comparators ──────────────────────────────────────────────────────
def test_spans_fidelity_detects_mismatch():
    a = [RunSpan(text="x", bold=True)]
    b = [RunSpan(text="x", bold=False)]
    rep = spans_fidelity(a, b)
    assert rep["fidelity"] == 0.0
    assert rep["first_mismatch"] is not None


def test_notes_fidelity_identical():
    notes = collect_notes(_authored_note_doc())
    rep = notes_fidelity(notes, notes)
    assert rep["fidelity"] == 1.0


# ── corpus aggregate ─────────────────────────────────────────────────
def test_corpus_fidelity_aggregate():
    rep = corpus_fidelity([SHOWCASE, EXAMPLES / "note_example.hwpx"])
    assert rep["files"] == 2
    assert 0.0 <= rep["run_format_fidelity"] <= 1.0
    assert rep["total_runs"] > 0
