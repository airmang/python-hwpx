# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlSection, parse_section_xml
from hwpx.oxml.body import LineSeg, LineSegArray, TransformMatrix
from hwpx.tools import generic_inventory
from hwpx.tools.roundtrip_diff import roundtrip_report


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
SAMPLES = [
    sample["file"]
    for sample in json.loads((CORPUS / "manifest.json").read_text("utf-8"))["samples"]
]
SIMPLE_LINE = CORPUS / "reader_writer__SimpleLine.hwpx"


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
