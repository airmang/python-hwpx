# SPDX-License-Identifier: Apache-2.0
"""7.0 removals that 6.0 announced: they fail by saying where the thing went.

- the 79 root names 6.0 moved into the namespaces (``HwpxAttributeError``),
- the ``section_index=`` / ``style_id_ref=`` arguments (``HwpxTypeError``,
  code ``hwpx-argument-removed``) — on the methods that take ``**extra_attrs``
  too, where a stray keyword would otherwise become an XML attribute,
- the 26 experimental names re-exported from ``hwpx`` (``MovedToExperimental``).

The model-level ``add_paragraph`` (document, section, table cell) takes
``style=`` in place of ``style_id_ref=``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import hwpx
from hwpx import HwpxDocument
from hwpx.errors import HwpxAttributeError, HwpxLookupError, HwpxTypeError

HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "auto_grow_cell_saved.hwpx"


def test_a_hancom_saved_document_names_the_new_place_too() -> None:
    with HwpxDocument.open(HANCOM_SAVED) as document:
        with pytest.raises(HwpxAttributeError) as excinfo:
            document.set_header_text("머리말")  # type: ignore[attr-defined]
        assert "doc.page.set_header(text=...)" in str(excinfo.value)
        assert excinfo.value.context["name"] == "set_header_text"
        document.page.set_header(text="머리말", section=0)
        assert not hasattr(document, "list_form_fields")


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.add_paragraph("x", section_index=0),
        lambda d: d.add_paragraph("x", style_id_ref=0),
        lambda d: d.oxml.add_paragraph("x", section_index=0),
        lambda d: d.oxml.add_paragraph("x", style_id_ref=0),
        lambda d: d.sections[0].add_paragraph("x", style_id_ref=0),
        lambda d: d.shapes.add_raw("rect", style_id_ref=0),
        lambda d: d.page.set_header(text="h", section_index=0),
    ],
    ids=["root-section", "root-style", "model-section", "model-style", "section-style", "raw-style", "page"],
)
def test_a_removed_argument_is_named_not_written_into_the_xml(call) -> None:
    document = HwpxDocument.new()
    before = len(document.paragraphs)
    with pytest.raises(HwpxTypeError) as excinfo:
        call(document)
    assert excinfo.value.code == "hwpx-argument-removed"
    assert excinfo.value.context["argument"] in {"section_index", "style_id_ref"}
    assert len(document.paragraphs) == before


def test_signatures_still_read_as_written() -> None:
    document = HwpxDocument.new()
    assert "section_index" not in inspect.signature(document.add_paragraph).parameters
    assert "section" in inspect.signature(document.page.set_header).parameters
    # add_ruby (6.x add_dutmal) keeps its own style_id_ref (the 덧말's style), so it is not refused.
    assert "style_id_ref" in inspect.signature(document.shapes.add_ruby).parameters


def test_model_add_paragraph_takes_a_style_name_and_its_shapes() -> None:
    document = HwpxDocument.new()
    heading = document.styles.resolve("개요 1")
    paragraph = document.sections[0].add_paragraph("제목", style="개요 1")
    assert paragraph.style_id_ref == str(heading.id)
    assert str(paragraph.para_pr_id_ref) == str(heading.para_pr_id_ref)
    cell = document.add_table(1, 1).cell(0, 0)
    in_cell = cell.add_paragraph("칸", style="개요 1", para_pr_id_ref=0)
    assert in_cell.style_id_ref == str(heading.id) and str(in_cell.para_pr_id_ref) == "0"
    with pytest.raises(HwpxLookupError) as excinfo:
        document.oxml.add_paragraph("x", section=0, style="개요1")
    assert excinfo.value.code == "style-not-found"


def test_setting_style_id_ref_keeps_the_label_only_path() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    shape = paragraph.para_pr_id_ref
    paragraph.style_id_ref = 2
    assert (paragraph.style_id_ref, paragraph.para_pr_id_ref) == ("2", shape)


def test_model_document_takes_a_section_index() -> None:
    document = HwpxDocument.new()
    document.add_section()
    paragraph = document.oxml.add_paragraph("둘째 구역", section=1)
    assert paragraph.section is document.sections[1] or paragraph.section.element is document.sections[1].element


def test_an_experimental_name_left_the_top_level() -> None:
    from hwpx.experimental import estimate_pages

    with pytest.raises(hwpx.MovedToExperimental, match="from hwpx.experimental import estimate_pages"):
        hwpx.estimate_pages  # noqa: B018
    assert callable(estimate_pages)


def test_a_document_saved_after_the_new_calls_reopens_valid(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문", section=0, style="개요 1")
    document.sections[0].add_paragraph("모델", style=0)
    target = tmp_path / "removed_7_0.hwpx"
    document.save(target)
    with HwpxDocument.open(target) as reopened:
        assert reopened.validate().ok
