"""A line break typed into text ("\\n", "\\r\\n" or "\\r") is written as an
``hp:lineBreak`` inside ``hp:t``, the element Hancom writes for it.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.body_patch import apply_body_ops
from hwpx.patch import paragraph_patch


def _text_nodes(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    return re.findall(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", xml, re.S)


def _assert_no_raw_break(data: bytes) -> None:
    assert not [node for node in _text_nodes(data) if "\n" in node or "\r" in node or "&#13;" in node]


@pytest.mark.parametrize("line_break", ["\n", "\r\n", "\r"])
def test_add_paragraph_writes_a_line_break_as_an_element(line_break: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph(f"첫 줄{line_break}둘째 줄\t끝")
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "첫 줄<hp:lineBreak/>둘째 줄<hp:tab/>끝" in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == "첫 줄\n둘째 줄\t끝"


def test_setting_paragraph_text_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("원래")
    paragraph.text = "가\n나"
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "가<hp:lineBreak/>나" in _text_nodes(data)


def test_add_run_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_run("앞\n뒤")
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "앞<hp:lineBreak/>뒤" in _text_nodes(data)


def test_cell_text_writes_a_line_break_as_an_element() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).text = "칸\n둘"
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert "칸<hp:lineBreak/>둘" in _text_nodes(data)
    assert HwpxDocument.open(data).tables.all[0].cell(0, 0).text == "칸\n둘"


def _doc_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("원래 문단")
    return doc.to_bytes()


def test_paragraph_patch_writes_a_line_break_as_an_element() -> None:
    result = paragraph_patch(_doc_bytes(), [{"paragraph_index": 1, "text": "가\r\n나"}])

    _assert_no_raw_break(result.data)
    assert "가<hp:lineBreak/>나" in _text_nodes(result.data)


def test_body_ops_replace_text_writes_a_line_break_as_an_element() -> None:
    result = apply_body_ops(_doc_bytes(), [{"op": "replace_text", "find": "원래", "replace": "가\n나", "count": 1}])

    _assert_no_raw_break(result.data)
    assert any("가<hp:lineBreak/>나" in node for node in _text_nodes(result.data))


# The same text through both add_run paths (#563): expand_special_characters
# only adds the special-space atoms; tabs and every typed line break stay.
_ADD_RUN_CASES = [
    ("가\t나", "가<hp:tab/>나", "가\t나"),
    ("가\n나", "가<hp:lineBreak/>나", "가\n나"),
    ("가\r\n나", "가<hp:lineBreak/>나", "가\n나"),
    ("가\r나", "가<hp:lineBreak/>나", "가\n나"),
    (
        "가\t나\r\n다\r라\n마",
        "가<hp:tab/>나<hp:lineBreak/>다<hp:lineBreak/>라<hp:lineBreak/>마",
        "가\t나\n다\n라\n마",
    ),
    ("\r\r\n\t", "<hp:lineBreak/><hp:lineBreak/><hp:tab/>", "\n\n\t"),
]


@pytest.mark.parametrize("expand", [False, True], ids=["literal", "expand"])
@pytest.mark.parametrize(("text", "xml", "reopened"), _ADD_RUN_CASES)
def test_add_run_keeps_tabs_and_line_breaks_either_way(text: str, xml: str, reopened: str, expand: bool) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_run(text, expand_special_characters=expand)
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert xml in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == reopened


@pytest.mark.parametrize(
    ("expand", "xml"),
    [
        (False, "가 나<hp:tab/>다　라<hp:lineBreak/>마"),
        (True, "가<hp:nbSpace/>나<hp:tab/>다<hp:fwSpace/>라<hp:lineBreak/>마"),
    ],
    ids=["literal", "expand"],
)
def test_add_run_special_spaces_beside_tabs_and_line_breaks(expand: bool, xml: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_run("가 나\t다　라\r마", expand_special_characters=expand)
    data = doc.to_bytes()

    assert xml in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == "가 나\t다　라\n마"


# Find-and-replace and partial edits write the same elements as the setters
# (2026-11 audit ENG-05: they left "\n" as a character inside hp:t, and
# set_text_preserving_runs dropped the tab).
_VALUE = "가\n나\t다"
_WRITTEN = "가<hp:lineBreak/>나<hp:tab/>다"


def _replaced(edit) -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("앞 원래 뒤")
    edit(doc)
    return doc.to_bytes()


def _model_text(doc: HwpxDocument) -> None:
    paragraph = doc.paragraphs[1]
    model = paragraph.to_model()
    model.runs[0].text_spans[0].text = f"앞 {_VALUE} 뒤"
    paragraph.apply_model(model)


def _run_model_text(doc: HwpxDocument) -> None:
    run = doc.paragraphs[1].runs[0]
    model = run.to_model()
    model.text_spans[0].text = f"앞 {_VALUE} 뒤"
    run.apply_model(model)


@pytest.mark.parametrize(
    "edit",
    [
        lambda doc: doc.paragraphs[1].runs[0].replace_text("원래", _VALUE),
        lambda doc: doc.text.replace("원래", _VALUE),
        lambda doc: doc.text.replace("원래", _VALUE, everywhere=True),
        lambda doc: doc.replace_text_in_runs("원래", _VALUE),
        lambda doc: doc.paragraphs[1].set_text_preserving_runs(f"앞 {_VALUE} 뒤"),
        _model_text,
        _run_model_text,
    ],
    ids=[
        "run.replace_text",
        "text.replace",
        "text.replace-everywhere",
        "replace_text_in_runs",
        "set_text_preserving_runs",
        "paragraph.apply_model",
        "run.apply_model",
    ],
)
def test_replace_and_partial_edits_write_breaks_and_tabs_as_elements(edit, recwarn) -> None:
    data = _replaced(edit)

    _assert_no_raw_break(data)
    assert not [node for node in _text_nodes(data) if "\t" in node]
    assert f"앞 {_WRITTEN} 뒤" in _text_nodes(data)
    assert HwpxDocument.open(data).paragraphs[1].text == f"앞 {_VALUE} 뒤"


def test_replace_keeps_the_marks_around_the_match_in_place() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run("하나\t둘 원래 셋\n넷")

    assert paragraph.runs[-1].replace_text("원래", "A\r\nB") == 1
    data = doc.to_bytes()

    assert "하나<hp:tab/>둘 A<hp:lineBreak/>B 셋<hp:lineBreak/>넷" in _text_nodes(data)


def test_replace_across_runs_writes_a_line_break_where_the_match_ended() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run("앞 원")
    bold = doc.styles.ensure_run(bold=True)
    paragraph.add_run("래 뒤", char_pr_id_ref=bold)

    assert doc.text.replace("원래", "가\n나다", everywhere=True) == 1
    data = doc.to_bytes()

    _assert_no_raw_break(data)
    assert HwpxDocument.open(data).paragraphs[1].text == "앞 가\n나다 뒤"
