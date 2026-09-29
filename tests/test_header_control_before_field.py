"""A header or footer control goes ahead of a field that starts in the section's first run.

A document can open with a field: the first run of its first paragraph holds ``hp:secPr``, the column control
and the control that starts a click-here field, whose end is in a later run.
``header_inside_field_saved.hwpx``: Hancom saved such a document with a header control added after the field
start, inside the field's span, and dropped the header. ``header_before_field_saved.hwpx``: the same document
with the header control ahead of the field start; Hancom kept the header.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


def _controls(data: bytes) -> list[list[str]]:
    """The controls in the runs of the first paragraph, in document order, as the names of their children."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml"))
    paragraph = root.find(f"{HP}p")
    return [
        [child.tag.rsplit("}", 1)[-1] for child in ctrl]
        for run in paragraph.findall(f"{HP}run")
        for ctrl in run.findall(f"{HP}ctrl")
    ]


def _document_opening_with_a_field() -> HwpxDocument:
    doc = HwpxDocument.new()
    first = doc.paragraphs[0]
    first.add_form_field("title", prompt="제목을 입력하세요")
    runs = first.element.findall(f"{HP}run")
    begin = next(c for r in runs for c in r.findall(f"{HP}ctrl") if c.find(f"{HP}fieldBegin") is not None)
    holder = next(r for r in runs if begin in list(r))
    holder.remove(begin)
    runs[0].append(begin)  # the field starts in the first run, after hp:secPr and the column control
    if not list(holder):
        first.element.remove(holder)
    doc.add_paragraph("본문 문단")
    return doc


def test_hancom_keeps_a_header_control_ahead_of_a_field_and_drops_one_inside_it() -> None:
    assert ["header"] not in _controls((HANCOM_SAVED / "header_inside_field_saved.hwpx").read_bytes())
    kept = _controls((HANCOM_SAVED / "header_before_field_saved.hwpx").read_bytes())
    assert kept.index(["header"]) < kept.index(["fieldBegin"])


@pytest.mark.parametrize("kind", ["header", "footer"])
def test_a_header_or_footer_control_goes_ahead_of_a_field_that_starts_in_the_first_run(kind: str) -> None:
    doc = _document_opening_with_a_field()

    getattr(doc.page, f"set_{kind}")(text="머리말 글")

    controls = _controls(doc.to_bytes())
    assert controls.index([kind]) < controls.index(["fieldBegin"])


def test_a_restored_control_copy_goes_ahead_of_the_field() -> None:
    doc = _document_opening_with_a_field()
    doc.page.set_header(text="머리말 글")
    run = doc.paragraphs[0].element.find(f"{HP}run")
    for ctrl in list(run.findall(f"{HP}ctrl")):
        if ctrl.find(f"{HP}header") is not None:
            run.remove(ctrl)  # only the hp:secPr copy is left

    doc.sections[0].properties.headers[0].set_simple_text_preserving("새 머리말")

    controls = _controls(doc.to_bytes())
    assert controls.index(["header"]) < controls.index(["fieldBegin"])
