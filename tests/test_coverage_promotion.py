# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from lxml import etree

from hwpx.oxml import HwpxOxmlSection, parse_section_xml
from hwpx.oxml import GenericElement
from hwpx.oxml.body import (
    FormComboBoxControl,
    FormEditControl,
    InlineObject,
    LineSeg,
    LineSegArray,
    Table,
    TransformMatrix,
)
from hwpx.tools import generic_inventory
from hwpx.tools.roundtrip_diff import roundtrip_report


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
SAMPLES = [
    sample["file"]
    for sample in json.loads((CORPUS / "manifest.json").read_text("utf-8"))["samples"]
]
SIMPLE_LINE = CORPUS / "reader_writer__SimpleLine.hwpx"
SIMPLE_EDIT = CORPUS / "reader_writer__SimpleEdit.hwpx"
SIMPLE_COMBO_BOX = CORPUS / "reader_writer__SimpleComboBox.hwpx"


def _section_xml(sample: Path, entry: str = "Contents/section0.xml") -> bytes:
    with zipfile.ZipFile(sample) as archive:
        return archive.read(entry)


def _walk(value: Any):
    if isinstance(value, (str, bytes, bytearray, dict)) or value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
        return
    yield value
    for field in getattr(value, "__dataclass_fields__", {}):
        yield from _walk(getattr(value, field))


def _local_count(xml: bytes, tag: str) -> int:
    root = etree.fromstring(xml)
    return len(root.xpath(".//*[local-name()=$tag]", tag=tag))


def test_generic_inventory_scans_engine_generic_body_elements() -> None:
    inventory = generic_inventory.scan_corpus(CORPUS)

    assert inventory
    assert "sec" not in inventory

    top = generic_inventory.top_entries(inventory, limit=10)
    assert top
    assert top[0]["tag"]
    assert top[0]["count"] >= top[0]["documents"] >= 1
    assert set(top[0]) == {"tag", "count", "documents", "samples"}


def test_generic_inventory_counts_outermost_generic_boundary_only() -> None:
    model = GenericElement(
        name="container",
        tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}container",
        children=[
            GenericElement(
                name="run",
                tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}run",
                children=[
                    GenericElement(
                        name="t",
                        tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}t",
                    )
                ],
            )
        ],
    )

    assert [element.name for element in generic_inventory._walk_model(model)] == ["container"]


def test_generic_inventory_counts_inline_object_as_content_boundary() -> None:
    model = InlineObject(
        tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}ellipse",
        name="ellipse",
        children=[
            GenericElement(
                name="pos",
                tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}pos",
            )
        ],
    )

    assert [element.name for element in generic_inventory._walk_model(model)] == ["ellipse"]


def test_generic_inventory_skips_table_internals_for_b3_boundary() -> None:
    model = Table(
        tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl",
        children=[
            GenericElement(
                name="tr",
                tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}tr",
            )
        ],
    )

    assert list(generic_inventory._walk_model(model)) == []


def test_generic_inventory_fixed_top_prefers_content_boundaries() -> None:
    inventory = generic_inventory.scan_corpus(CORPUS)
    top_tags = [row["tag"] for row in generic_inventory.top_entries(inventory, limit=10)]

    noisy_descendants = {
        "run",
        "p",
        "t",
        "tr",
        "tc",
        "cellSpan",
        "cellAddr",
        "cellMargin",
        "cellSz",
        "offset",
        "pos",
        "sz",
        "renderingInfo",
    }

    assert noisy_descendants.isdisjoint(top_tags)
    assert {"ellipse", "container", "pic"}.intersection(top_tags)


def test_generic_inventory_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "generic_inventory.json"

    written = generic_inventory.write_inventory(CORPUS, output, limit=10)

    payload = json.loads(output.read_text("utf-8"))
    assert written == payload
    assert payload["sample_count"] == len(SAMPLES)
    assert len(payload["top"]) == 10
    assert payload["inventory"]


def test_linesegarray_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_LINE))
    line_arrays = [node for node in _walk(section) if isinstance(node, LineSegArray)]

    assert line_arrays
    line_array = line_arrays[0]
    assert line_array.linesegs
    assert isinstance(line_array.linesegs[0], LineSeg)
    assert line_array.linesegs[0].text_pos == 0
    assert line_array.linesegs[0].horz_size == 42520


def test_linesegarray_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_LINE))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    line_array = next(node for node in _walk(model) if isinstance(node, LineSegArray))
    line_array.linesegs[0].horz_size = 12345

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_line_array = next(node for node in _walk(updated) if isinstance(node, LineSegArray))

    assert updated_line_array.linesegs[0].horz_size == 12345
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "linesegarray") == 1
    assert _local_count(paragraph_xml, "lineseg") == 1


def test_linesegarray_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(SIMPLE_LINE)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}


def test_transmatrix_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_LINE))
    matrices = [
        node
        for node in _walk(section)
        if isinstance(node, TransformMatrix) and node.name == "transMatrix"
    ]

    assert matrices
    matrix = matrices[0]
    assert matrix.e1 == "1"
    assert matrix.e5 == "1"
    assert matrix.e6 == "0"


def test_transmatrix_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_LINE))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    matrix = next(
        node
        for node in _walk(model)
        if isinstance(node, TransformMatrix) and node.name == "transMatrix"
    )
    matrix.e6 = "99"

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_matrix = next(
        node
        for node in _walk(updated)
        if isinstance(node, TransformMatrix) and node.name == "transMatrix"
    )

    assert updated_matrix.e6 == "99"
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "transMatrix") == 1


def test_scamatrix_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_LINE))
    matrices = [
        node
        for node in _walk(section)
        if isinstance(node, TransformMatrix) and node.name == "scaMatrix"
    ]

    assert matrices
    matrix = matrices[0]
    assert matrix.e1 == "0.721061"
    assert matrix.e5 == "2.456967"


def test_scamatrix_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_LINE))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    matrix = next(
        node
        for node in _walk(model)
        if isinstance(node, TransformMatrix) and node.name == "scaMatrix"
    )
    matrix.e1 = "2.5"

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_matrix = next(
        node
        for node in _walk(updated)
        if isinstance(node, TransformMatrix) and node.name == "scaMatrix"
    )

    assert updated_matrix.e1 == "2.5"
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "scaMatrix") == 1


def test_rotmatrix_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_LINE))
    matrices = [
        node
        for node in _walk(section)
        if isinstance(node, TransformMatrix) and node.name == "rotMatrix"
    ]

    assert matrices
    matrix = matrices[0]
    assert matrix.e1 == "1"
    assert matrix.e5 == "1"


def test_rotmatrix_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_LINE))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    matrix = next(
        node
        for node in _walk(model)
        if isinstance(node, TransformMatrix) and node.name == "rotMatrix"
    )
    matrix.e2 = "0.5"

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_matrix = next(
        node
        for node in _walk(updated)
        if isinstance(node, TransformMatrix) and node.name == "rotMatrix"
    )

    assert updated_matrix.e2 == "0.5"
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "rotMatrix") == 1


def test_edit_control_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_EDIT))
    edits = [node for node in _walk(section) if isinstance(node, FormEditControl)]

    assert edits
    edit = edits[0]
    assert edit.name == "edit"
    assert edit.multi_line == "0"
    assert edit.password_char == "X"
    assert edit.max_length == 2147483647
    assert edit.scroll_bars == "NONE"
    assert edit.tab_key_behavior == "NEXT_OBJECT"
    assert edit.num_only == "1"
    assert edit.read_only == "0"
    assert edit.align_text == "LEFT"
    assert edit.attributes["name"] == "Edit1"
    assert [child.name for child in edit.children[:2]] == ["formCharPr", "text"]


def test_edit_control_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_EDIT))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    edit = next(node for node in _walk(model) if isinstance(node, FormEditControl))
    edit.max_length = 42
    edit.read_only = "1"

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_edit = next(node for node in _walk(updated) if isinstance(node, FormEditControl))

    assert updated_edit.max_length == 42
    assert updated_edit.read_only == "1"
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "edit") == 1
    assert _local_count(paragraph_xml, "formCharPr") == 1


def test_edit_control_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(SIMPLE_EDIT)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}


def test_combo_box_control_promoted_from_hwpxlib_sample() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_COMBO_BOX))
    controls = [node for node in _walk(section) if isinstance(node, FormComboBoxControl)]

    assert controls
    combo = controls[0]
    assert combo.name == "comboBox"
    assert combo.list_box_rows == 10
    assert combo.list_box_width == 0
    assert combo.edit_enable == "1"
    assert combo.selected_value == ""
    assert combo.attributes["name"] == "ComboBox1"
    assert [child.name for child in combo.children[:2]] == ["formCharPr", "listItem"]


def test_combo_box_control_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_COMBO_BOX))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    combo = next(node for node in _walk(model) if isinstance(node, FormComboBoxControl))
    combo.list_box_rows = 7
    combo.selected_value = "selected"

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_combo = next(node for node in _walk(updated) if isinstance(node, FormComboBoxControl))

    assert updated_combo.list_box_rows == 7
    assert updated_combo.selected_value == "selected"
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "comboBox") == 1
    assert _local_count(paragraph_xml, "listItem") == 1


def test_combo_box_control_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(SIMPLE_COMBO_BOX)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}
