# SPDX-License-Identifier: Apache-2.0
"""Reading the fields Hancom saves beside 누름틀: table formulas (#578) and
bookmarks in their ``fieldBegin type="BOOKMARK"`` form (#579).

The fixtures are synthetic. Each field run is shaped the way Hancom saves it:
``<hp:run><hp:ctrl><hp:fieldBegin/></hp:ctrl><hp:t>..</hp:t><hp:ctrl><hp:fieldEnd/></hp:ctrl></hp:run>``,
and a Hancom-saved bookmark field has nothing between its begin and end.
"""

from __future__ import annotations

import dataclasses
import itertools

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.objects import Bookmark, FormulaField

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_ids = itertools.count(1001)


def _field_run(paragraph, field_type, name, params, text):
    """Replace *paragraph*'s runs with one field run."""

    p = paragraph.element
    for run in p.findall(f"{{{HP}}}run"):
        p.remove(run)
    field_id = str(next(_ids))
    run = etree.SubElement(p, f"{{{HP}}}run", charPrIDRef="0")
    begin = etree.SubElement(
        etree.SubElement(run, f"{{{HP}}}ctrl"),
        f"{{{HP}}}fieldBegin",
        id=field_id, type=field_type, name=name, editable="0", dirty="0",
        zorder="-1", fieldid="627469685", metaTag="",
    )
    plist = etree.SubElement(begin, f"{{{HP}}}parameters", cnt=str(len(params)), name="")
    for kind, pname, value in params:
        etree.SubElement(plist, f"{{{HP}}}{kind}", name=pname).text = value
    if text:
        etree.SubElement(run, f"{{{HP}}}t").text = text
    etree.SubElement(
        etree.SubElement(run, f"{{{HP}}}ctrl"), f"{{{HP}}}fieldEnd",
        beginIDRef=field_id, fieldid="627469685",
    )
    etree.SubElement(run, f"{{{HP}}}t")
    paragraph.section.mark_dirty()


def _formula_params(formula, result, *, with_formula=True):
    params = [("integerParam", "Prop", "8"), ("stringParam", "Command", f"{formula}??%g,;;{result}")]
    if with_formula:
        params.append(("stringParam", "Formula", formula))
    params += [("stringParam", "ResultFormat", "%g,"), ("stringParam", "LastResult", result)]
    return params


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(doc.to_bytes())


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 2)
    table.set_cell_text(0, 1, "10")
    table.set_cell_text(1, 1, "19")
    _field_run(table.cell(2, 1).paragraphs[0], "FORMULA", "", _formula_params("=SUM(?1:?2)", "29"), "29")
    nested = table.cell(2, 0).add_table(1, 1)
    _field_run(nested.cell(0, 0).paragraphs[0], "FORMULA", "", _formula_params("=SUM(A1:A1)", "7", with_formula=False), "7")
    _field_run(doc.add_paragraph(""), "BOOKMARK", "saved-by-hancom", [("integerParam", "Prop", "2")], "")
    _field_run(table.cell(0, 0).paragraphs[0], "BOOKMARK", "in-a-cell", [("integerParam", "Prop", "2")], "covered")
    doc.add_paragraph("").add_bookmark("point-mark")
    return _reopen(doc)


def test_formulas_are_read_as_hancom_wrote_them(document: HwpxDocument) -> None:
    inner, outer = document.fields.formulas  # cell (2, 0)'s nested table comes before cell (2, 1)

    assert isinstance(outer, FormulaField)
    assert outer.formula == "=SUM(?1:?2)"
    assert outer.result_format == "%g,"
    assert outer.last_result == "29"
    assert outer.command == "=SUM(?1:?2)??%g,;;29"
    assert outer.value == "29"
    assert outer.cell_address == (2, 1)
    assert outer.field_id
    assert outer.element.tag == f"{{{HP}}}fieldBegin"
    assert ("Formula", "=SUM(?1:?2)") in [(p.name, p.value) for p in outer.parameters]


def test_a_formula_in_a_nested_table_reports_its_own_cell(document: HwpxDocument) -> None:
    inner = document.fields.formulas[0]
    assert inner.cell_address == (0, 0)
    assert inner.location.paragraph_index_in_section == -1


def test_a_formula_without_a_formula_parameter_reads_it_from_the_command(document: HwpxDocument) -> None:
    assert document.fields.formulas[0].formula == "=SUM(A1:A1)"
    assert document.fields.formulas[0].last_result == "7"


def test_a_formula_outside_a_table_has_no_cell_address() -> None:
    doc = HwpxDocument.new()
    _field_run(doc.add_paragraph(""), "FORMULA", "", _formula_params("=3+4", "7"), "7")
    (formula,) = _reopen(doc).fields.formulas
    assert formula.cell_address is None
    assert formula.location.paragraph_index_in_section >= 0


def test_formulas_and_bookmark_fields_are_not_form_fields(document: HwpxDocument) -> None:
    assert document.fields.all == ()


def test_paragraph_bookmarks_include_the_field_form(document: HwpxDocument) -> None:
    names = [name for paragraph in document.paragraphs for name in paragraph.bookmarks]
    assert names == ["saved-by-hancom", "point-mark"]
    assert document.tables[0].cell(0, 0).paragraphs[0].bookmarks == ["in-a-cell"]


def test_refs_bookmarks_lists_both_forms_in_document_order(document: HwpxDocument) -> None:
    bookmarks = document.refs.bookmarks
    assert [(b.name, b.kind, b.text) for b in bookmarks] == [
        ("in-a-cell", "field", "covered"),
        ("saved-by-hancom", "field", ""),
        ("point-mark", "point", ""),
    ]
    assert all(isinstance(b, Bookmark) for b in bookmarks)
    assert bookmarks[0].location.paragraph_index_in_section == -1
    assert bookmarks[2].element.tag == f"{{{HP}}}bookmark"


def test_a_bookmark_added_by_the_engine_is_listed() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.refs.add_bookmark("앵커", section=0)
    assert [(b.name, b.kind) for b in doc.refs.bookmarks] == [("앵커", "point")]


def test_reading_leaves_the_package_unchanged(document: HwpxDocument) -> None:
    before = document.to_bytes()
    _ = document.fields.formulas
    _ = document.refs.bookmarks
    assert document.to_bytes() == before


@pytest.mark.parametrize("cls", (Bookmark, FormulaField), ids=lambda c: c.__name__)
def test_snapshots_are_frozen_with_camel_case_dicts(cls, document: HwpxDocument) -> None:
    assert cls.__dataclass_params__.frozen is True
    instance = (document.refs.bookmarks if cls is Bookmark else document.fields.formulas)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, dataclasses.fields(cls)[0].name, None)
    payload = instance.to_dict()
    assert "element" not in payload
    assert all("_" not in key for key in payload)
    assert payload["location"]["sectionIndex"] == 0
