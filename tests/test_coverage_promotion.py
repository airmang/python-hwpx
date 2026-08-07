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
    INLINE_OBJECT_NAMES,
    ComposedCharacter,
    FormComboBoxControl,
    FormEditControl,
    InlineObject,
    Label,
    LineSeg,
    LineSegArray,
    ListItem,
    Parameter,
    ParameterList,
    Table,
    TextMarkup,
    TransformMatrix,
    parameter_list_to_xml,
    parse_parameter_list_element,
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
#: 실코퍼스에서 유일하게 hp:parameterset(+중첩 hp:listParam)을 담은 파일 —
#: hp:rect 도형의 확장 속성 블록으로 쓰인다(직접 스캔 확인, 필드용 아님).
PARAMETERSET_SAMPLE = CORPUS / "error__20230809__test.hwpx"
SIMPLE_COMPOSE = CORPUS / "reader_writer__SimpleCompose.hwpx"
SIMPLE_CONTAINER = CORPUS / "reader_writer__SimpleContainer.hwpx"


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


def test_combo_box_list_items_are_typed_not_generic() -> None:
    section = parse_section_xml(_section_xml(SIMPLE_COMBO_BOX))
    combo = next(node for node in _walk(section) if isinstance(node, FormComboBoxControl))

    assert combo.list_items
    assert all(isinstance(item, ListItem) for item in combo.list_items)
    assert combo.list_items[0].display_text == ""
    assert combo.list_items[0].value == ""


def test_combo_box_list_items_are_editable_via_children_and_roundtrip() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_COMBO_BOX))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    combo = next(node for node in _walk(model) if isinstance(node, FormComboBoxControl))
    new_item = ListItem(tag=None, name="listItem", display_text="가", value="A")
    combo.children.append(new_item)

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_combo = next(node for node in _walk(updated) if isinstance(node, FormComboBoxControl))

    assert any(item.value == "A" and item.display_text == "가" for item in updated_combo.list_items)
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "listItem") == 2


def test_parameter_list_promoted_from_hwpxlib_sample_shape() -> None:
    """hp:rect의 hp:parameterset(+중첩 hp:listParam)을 실코퍼스에서 직접
    파싱 — cnt="1" name="539"/listParam cnt="1" name="12291"/
    unsignedintegerParam name="28673" 값 2 (직접 스캔 확인)."""

    xml = _section_xml(PARAMETERSET_SAMPLE)
    root = etree.fromstring(xml)
    (node,) = root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}parameterset")

    model = parse_parameter_list_element(node)

    assert model.name == "539"
    assert len(model.params) == 1
    outer = model.params[0]
    assert outer.kind == "list"
    assert outer.name == "12291"
    assert len(outer.items) == 1
    leaf = outer.items[0]
    assert leaf.kind == "unsignedinteger"
    assert leaf.name == "28673"
    assert leaf.value == 2


def test_parameter_list_roundtrips_structurally() -> None:
    xml = _section_xml(PARAMETERSET_SAMPLE)
    root = etree.fromstring(xml)
    (node,) = root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}parameterset")

    model = parse_parameter_list_element(node)
    rebuilt = parameter_list_to_xml(model)

    def struct_eq(a, b) -> bool:
        if etree.QName(a).localname != etree.QName(b).localname:
            return False
        if dict(a.attrib) != dict(b.attrib):
            return False
        if (a.text or "") != (b.text or ""):
            return False
        a_children, b_children = list(a), list(b)
        return len(a_children) == len(b_children) and all(
            struct_eq(x, y) for x, y in zip(a_children, b_children)
        )

    assert struct_eq(node, rebuilt)


def test_parameter_list_authors_field_click_action_parameters() -> None:
    """toc_author.py의 실증된 hp:parameters 패턴(HYPERLINK 필드 클릭
    액션)을 범용 ParameterList로도 만들 수 있는지 확인 — booleanParam 포함."""

    model = ParameterList(
        tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}parameters",
        name="",
        params=[
            Parameter(name="Prop", kind="integer", value=0),
            Parameter(name="Command", kind="string", value="?#123;0;1;0;"),
            Parameter(name="Fiexde", kind="boolean", value=True),
        ],
    )

    node = parameter_list_to_xml(model)

    assert node.get("cnt") == "3"
    assert node.get("name") == ""
    children = list(node)
    assert [etree.QName(c).localname for c in children] == [
        "integerParam",
        "stringParam",
        "booleanParam",
    ]
    assert children[0].text == "0"
    assert children[2].text == "1"

    reparsed = parse_parameter_list_element(node)
    assert reparsed.params[2].value is True


def test_parameter_list_promoted_from_hwpxlib_sample_via_real_dispatch() -> None:
    """위 `_promoted_from_hwpxlib_sample_shape`은 `parse_parameter_list_element`를
    직접 불러 클래스 자체의 정확성만 증명한다 — 실 문서를 여는 진짜 경로
    (`parse_section_xml` → ... → `parse_preserved_element`)가 이 요소를
    실제로 이 클래스로 뜨는지는 별개 질문이다(DEV-011 2026-08 트레인⑰
    재검증이 지목한 갭: 그때는 디스패치에 분기가 없어 `GenericElement`로
    강등됐다 — 트레인⑳에서 배선). 다른 모든 프리저브드 타입(linesegarray·
    edit·comboBox·composedCharacter)의 `_promoted_from_hwpxlib_sample`
    자매 테스트와 같은 패턴 — `parse_section_xml`이 진짜 디스패치다."""

    section = parse_section_xml(_section_xml(PARAMETERSET_SAMPLE))
    promoted = [node for node in _walk(section) if isinstance(node, ParameterList)]
    generic_leftovers = [
        node
        for node in _walk(section)
        if isinstance(node, GenericElement) and node.name in {"parameters", "parameterset"}
    ]

    assert promoted, "hp:parameterset never reached ParameterList through the real dispatch chain"
    assert generic_leftovers == [], (
        "hp:parameterset/parameters still falling through to GenericElement via "
        f"parse_preserved_element: {generic_leftovers}"
    )
    param_list = promoted[0]
    assert param_list.name == "539"
    assert param_list.params[0].kind == "list"
    assert param_list.params[0].items[0].value == 2


def test_parameter_list_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(PARAMETERSET_SAMPLE)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}


def test_text_markup_name_reads_parameterlist_tag_not_its_name_attribute() -> None:
    """`ParameterList` joining `PreservedElement` (트레인⑳ 배선) made it a
    theoretically reachable `TextMarkup.element` too (`_parse_text_markup`
    falls through to the same `parse_preserved_element` dispatcher used
    everywhere else) — even though no real corpus sample places `parameters`/
    `parameterset` directly under `hp:t` today. Every sibling type's
    `TextMarkup.name` is its tag's local name; naively proxying through would
    have returned `ParameterList.name` instead, which means something
    unrelated (the `name=` XML attribute, nullable) and broke the `-> str`
    contract for the common empty-name case (304/306 real occurrences)."""

    markup = TextMarkup(
        element=ParameterList(
            tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}parameters",
            name="",
            params=[],
        )
    )

    assert markup.name == "parameters"


def test_text_markup_name_reads_label_tag_since_it_has_no_name_field() -> None:
    """`Label` joining `PreservedElement` (트레인㉖, DEV-023) made it the
    same theoretically-reachable `TextMarkup.element` case as `ParameterList`
    -- `Label` has no `.name` field at all (its 11 attributes are all typed
    individually), so proxying through would fail with `AttributeError`,
    not just return the wrong value."""

    markup = TextMarkup(
        element=Label(tag="{http://www.hancom.co.kr/hwpml/2011/paragraph}label")
    )

    assert markup.name == "label"


def test_composed_character_promoted_from_hwpxlib_sample() -> None:
    """hp:compose는 hp:t의 자식이 아니라 hp:run 직속(hp:ctrl 다음, hp:t
    형제) — 실코퍼스 SimpleCompose.hwpx로 직접 확인."""

    section = parse_section_xml(_section_xml(SIMPLE_COMPOSE))
    composed = [node for node in _walk(section) if isinstance(node, ComposedCharacter)]

    assert composed
    first = composed[0]
    assert first.circle_type == "SHAPE_REVERSAL_TIRANGLE"
    assert first.compose_type == "SPREAD"
    assert first.compose_text == "12"
    assert first.char_pr_cnt == 10
    assert len(first.slots) == 10
    assert first.slots[0].pr_id_ref == 7
    assert first.slots[1].pr_id_ref == 4294967295


def test_composed_character_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(SIMPLE_COMPOSE)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}


def test_composed_character_model_roundtrips_through_paragraph_apply() -> None:
    section_element = ET.fromstring(_section_xml(SIMPLE_COMPOSE))
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]

    model = paragraph.to_model()
    composed = next(node for node in _walk(model) if isinstance(node, ComposedCharacter))
    composed.compose_text = "34"
    composed.char_sz = -5

    paragraph.apply_model(model)
    updated = paragraph.to_model()
    updated_composed = next(node for node in _walk(updated) if isinstance(node, ComposedCharacter))

    assert updated_composed.compose_text == "34"
    assert updated_composed.char_sz == -5
    paragraph_xml = ET.tostring(paragraph.element, encoding="utf-8")
    assert _local_count(paragraph_xml, "compose") >= 1
    assert _local_count(paragraph_xml, "charPr") >= updated_composed.char_pr_cnt


def test_container_nested_shapes_are_typed_not_generic() -> None:
    """hp:container 최상위 자식뿐 아니라 그 *안에* 중첩된 pic/line 등도
    InlineObject로 뜬다 — 이전엔 재귀 한 겹만 지나면 GenericElement로
    강등됐다(cycle-6.3 트레인⑫ 이전 상태)."""

    section = parse_section_xml(_section_xml(SIMPLE_CONTAINER))
    containers = [node for node in _walk(section) if isinstance(node, InlineObject) and node.name == "container"]

    assert containers
    container = containers[0]
    shape_children = [
        child for child in container.children
        if getattr(child, "name", None) in INLINE_OBJECT_NAMES
    ]
    assert shape_children
    assert {child.name for child in shape_children} == {"pic", "line"}
    assert all(isinstance(child, InlineObject) for child in shape_children), (
        f"expected nested shape children to be InlineObject, got "
        f"{[type(c).__name__ for c in shape_children]}"
    )


def test_container_sample_roundtrip_has_no_a1_loss() -> None:
    rep = roundtrip_report(SIMPLE_CONTAINER)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}
