"""Edits a downstream tool did through the XML, done with the public API (synthetic text only).

Each test is the engine's contract for one of them: removing every memo of a Hancom-converted
document while keeping the text it was on, removing drawings in headers and footers, a cross-run
search and replace, sizing a copied table, taking one table out of a run it shares, and cutting a
document down to a skeleton.
"""

from __future__ import annotations

import re
from pathlib import Path

from hwpx import HwpxDocument

SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f01f0005000201a5f6c2d40000000049454e44ae426082"
)


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    return reopened


def test_every_memo_goes_and_the_text_it_was_on_stays() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")  # Hancom writes memos as MEMO fields
    text = [p.text for p in doc.paragraphs]
    assert doc.notes.memos
    for memo in doc.notes.memos:
        doc.notes.remove_memo(memo)
    reopened = _reopened(doc)
    assert reopened.notes.memos == ()
    assert [p.text for p in reopened.paragraphs] == text
    assert not any(begin.get("type") == "MEMO" for begin in reopened.sections[0].element.iter(f"{HP}fieldBegin"))


def test_drawings_in_headers_and_footers_go_and_body_ones_stay() -> None:
    doc = HwpxDocument.new()
    header = doc.page.set_header(text="머리말")
    header.paragraphs[0].add_rectangle(1000, 1000)
    header.paragraphs[0].add_line(0, 0, 1000, 1000)
    doc.add_paragraph("").add_ellipse(1000, 1000)
    for place in list(doc.text.iter_objects(kinds="shape", where=("header", "footer"))):
        place.object.remove()
    assert [(p.kind, p.where) for p in _reopened(doc).text.iter_objects(kinds="shape")] == [("shape", "body")]


def test_a_pattern_across_runs_of_different_shapes_is_replaced_keeping_them() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run("총 ", bold=True)
    paragraph.add_run("12")
    paragraph.add_run("쪽", bold=True)
    assert doc.text.replace(re.compile(r"총 \d+쪽"), "총 7쪽", regex=True, everywhere=True) == 1
    assert paragraph.text == "총 7쪽"
    # only what changed is rewritten, in the run where the change starts; the runs keep their shapes
    bold, plain = paragraph.runs[-3].char_pr_id_ref, paragraph.runs[-2].char_pr_id_ref
    assert [(run.text, run.char_pr_id_ref) for run in paragraph.runs[-3:]] == [("총 ", bold), ("7쪽", plain), ("", bold)]


def test_a_copied_table_takes_new_row_heights_and_column_widths() -> None:
    doc = HwpxDocument.new()
    sample = doc.add_table(2, 3, width=30000)
    copy = sample.copy_to(doc.add_paragraph(""))
    copy.set_column_width(1, 12000)
    copy.set_row_height(1, 5000)
    reopened = _reopened(doc)
    copied = reopened.tables.all[1]
    assert copied.column_widths[1] == 12000 and copied.width == sample.width + 12000 - sample.column_widths[1]
    assert copied.row_heights[1] == 5000
    assert reopened.tables.all[0].column_widths == sample.column_widths  # the sample is untouched


def test_a_table_sharing_its_run_goes_alone() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    tables = [paragraph.add_table(1, 1) for _ in range(3)]
    first_run = tables[0].element.getparent()
    for table in tables[1:]:  # Hancom keeps tables side by side in one run
        old_run = table.element.getparent()
        first_run.append(table.element)
        paragraph.element.remove(old_run)
    for table, text in zip(paragraph.tables, "가나다"):
        table.cell(0, 0).set_text(text)
    paragraph.tables[1].remove()
    assert [t.cell(0, 0).text for t in _reopened(doc).paragraphs[-1].tables] == ["가", "다"]


def test_a_skeleton_keeps_the_page_setup_and_drops_body_and_pictures() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")
    page = doc.page.size(section=0)
    item = doc.media.add_image(PNG, "png")
    doc.add_paragraph("").add_picture(item, width=1000, height=1000)
    for memo in doc.notes.memos:
        doc.notes.remove_memo(memo)
    doc.sections[0].clear_body(on_control_content="strip")
    doc.media.remove_unused_images()
    reopened = _reopened(doc)
    assert [p.text for p in reopened.paragraphs] == [""]
    assert reopened.media.images == ()
    assert reopened.page.size(section=0) == page
