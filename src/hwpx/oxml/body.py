# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from lxml import etree

from .common import GenericElement, parse_generic_element
from .namespaces import HP
from .utils import local_name, parse_bool, parse_int


_DEFAULT_HP = HP

INLINE_OBJECT_NAMES = {
    "line",
    "rect",
    "ellipse",
    "arc",
    "polyline",
    "polygon",
    "curve",
    "connectLine",
    "picture",
    "pic",
    "shape",
    "drawingObject",
    "container",
    "equation",
    "ole",
    "chart",
    "video",
    "audio",
    "textart",
}

_TRACK_CHANGE_MARK_NAMES = {
    "insertBegin",
    "insertEnd",
    "deleteBegin",
    "deleteEnd",
}

PreservedElement = Union[
    GenericElement,
    "CommentElement",
    "LineSegArray",
    "LineSeg",
    "TransformMatrix",
    "FormEditControl",
    "FormComboBoxControl",
]
InlineMark = Union[PreservedElement, "TrackChangeMark"]
RunChild = Union[PreservedElement, "Control", "Table", "InlineObject", "TextSpan", "Tab"]
ParagraphChild = Union["Run", PreservedElement]


@dataclass(slots=True)
class TrackChangeMark:
    tag: str
    name: str
    change_type: str
    is_begin: bool
    para_end: Optional[bool]
    tc_id: Optional[int]
    id: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TextMarkup:
    element: InlineMark
    trailing_text: str = ""

    @property
    def name(self) -> str:
        if isinstance(self.element, TrackChangeMark):
            return self.element.name
        return self.element.name


@dataclass(slots=True)
class TextSpan:
    tag: str
    leading_text: str
    marks: List[TextMarkup] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.leading_text + "".join(mark.trailing_text for mark in self.marks)

    @text.setter
    def text(self, value: str) -> None:
        self.leading_text = value
        for mark in self.marks:
            mark.trailing_text = ""


@dataclass(slots=True)
class Control:
    tag: str
    control_type: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class InlineObject:
    tag: str
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class Tab:
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Table:
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class LineSeg:
    tag: str
    name: str
    text_pos: Optional[int]
    vert_pos: Optional[int]
    vert_size: Optional[int]
    text_height: Optional[int]
    baseline: Optional[int]
    spacing: Optional[int]
    horz_pos: Optional[int]
    horz_size: Optional[int]
    flags: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class LineSegArray:
    tag: str
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    linesegs: List[LineSeg] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)
    content: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class TransformMatrix:
    tag: str
    name: str
    e1: Optional[str]
    e2: Optional[str]
    e3: Optional[str]
    e4: Optional[str]
    e5: Optional[str]
    e6: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class FormEditControl:
    tag: str
    name: str
    multi_line: Optional[str]
    password_char: Optional[str]
    max_length: Optional[int]
    scroll_bars: Optional[str]
    tab_key_behavior: Optional[str]
    num_only: Optional[str]
    read_only: Optional[str]
    align_text: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class FormComboBoxControl:
    tag: str
    name: str
    list_box_rows: Optional[int]
    list_box_width: Optional[int]
    edit_enable: Optional[str]
    selected_value: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class CommentElement:
    """Round-trips an XML comment or processing-instruction child node.

    Comment and processing-instruction nodes expose a callable ``tag``
    (``etree.Comment`` / ``etree.PI``) rather than a string, so the generic
    element model cannot represent them: feeding that callable to
    ``etree.Element`` raises ``TypeError``. This dedicated model captures the
    node faithfully so it can be reconstructed via :func:`etree.Comment` /
    :func:`etree.ProcessingInstruction`.
    """

    kind: str  # "comment" or "pi"
    text: Optional[str] = None
    target: Optional[str] = None  # processing-instruction target


@dataclass(slots=True)
class Run:
    tag: str
    char_pr_id_ref: Optional[int]
    section_properties: List[PreservedElement] = field(default_factory=list)
    controls: List[Control] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    inline_objects: List[InlineObject] = field(default_factory=list)
    tabs: List[Tab] = field(default_factory=list)
    text_spans: List[TextSpan] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    content: List[RunChild] = field(default_factory=list)


@dataclass(slots=True)
class Paragraph:
    tag: str
    id: Optional[int]
    para_pr_id_ref: Optional[int]
    style_id_ref: Optional[int]
    page_break: Optional[bool]
    column_break: Optional[bool]
    merged: Optional[bool]
    runs: List[Run] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    other_children: List[PreservedElement] = field(default_factory=list)
    content: List[ParagraphChild] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    tag: str
    attributes: Dict[str, str]
    paragraphs: List[Paragraph] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)


def _qualified_tag(tag: Optional[str], name: str) -> str:
    if tag:
        return tag
    return f"{_DEFAULT_HP}{name}"


def _bool_to_str(value: bool) -> str:
    return "true" if value else "false"


def parse_track_change_mark(node: etree._Element) -> TrackChangeMark:
    attrs = {key: value for key, value in node.attrib.items()}
    para_end = parse_bool(attrs.pop("paraend", None))
    tc_id = parse_int(attrs.pop("TcId", None))
    mark_id = parse_int(attrs.pop("Id", None))
    name = local_name(node)
    change_type = "insert" if name.startswith("insert") else "delete"
    is_begin = name.endswith("Begin")
    return TrackChangeMark(
        tag=node.tag,
        name=name,
        change_type=change_type,
        is_begin=is_begin,
        para_end=para_end,
        tc_id=tc_id,
        id=mark_id,
        attributes=attrs,
    )


def _parse_int_attribute(attributes: Dict[str, str], name: str) -> Optional[int]:
    return parse_int(attributes.pop(name, None))


def parse_line_seg_element(node: etree._Element) -> LineSeg:
    attrs = {key: value for key, value in node.attrib.items()}
    return LineSeg(
        tag=node.tag,
        name=local_name(node),
        text_pos=_parse_int_attribute(attrs, "textpos"),
        vert_pos=_parse_int_attribute(attrs, "vertpos"),
        vert_size=_parse_int_attribute(attrs, "vertsize"),
        text_height=_parse_int_attribute(attrs, "textheight"),
        baseline=_parse_int_attribute(attrs, "baseline"),
        spacing=_parse_int_attribute(attrs, "spacing"),
        horz_pos=_parse_int_attribute(attrs, "horzpos"),
        horz_size=_parse_int_attribute(attrs, "horzsize"),
        flags=_parse_int_attribute(attrs, "flags"),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_line_seg_array_element(node: etree._Element) -> LineSegArray:
    line_array = LineSegArray(
        tag=node.tag,
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        text=node.text if node.text is not None else None,
    )

    for child in node:
        element = parse_preserved_element(child)
        if isinstance(element, LineSeg):
            line_array.linesegs.append(element)
        else:
            line_array.other_children.append(element)
        line_array.content.append(element)

    return line_array


def parse_transform_matrix_element(node: etree._Element) -> TransformMatrix:
    attrs = {key: value for key, value in node.attrib.items()}
    return TransformMatrix(
        tag=node.tag,
        name=local_name(node),
        e1=attrs.pop("e1", None),
        e2=attrs.pop("e2", None),
        e3=attrs.pop("e3", None),
        e4=attrs.pop("e4", None),
        e5=attrs.pop("e5", None),
        e6=attrs.pop("e6", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_form_edit_element(node: etree._Element) -> FormEditControl:
    attrs = {key: value for key, value in node.attrib.items()}
    return FormEditControl(
        tag=node.tag,
        name=local_name(node),
        multi_line=attrs.pop("multiLine", None),
        password_char=attrs.pop("passwordChar", None),
        max_length=_parse_int_attribute(attrs, "maxLength"),
        scroll_bars=attrs.pop("scrollBars", None),
        tab_key_behavior=attrs.pop("tabKeyBehavior", None),
        num_only=attrs.pop("numOnly", None),
        read_only=attrs.pop("readOnly", None),
        align_text=attrs.pop("alignText", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_form_combo_box_element(node: etree._Element) -> FormComboBoxControl:
    attrs = {key: value for key, value in node.attrib.items()}
    return FormComboBoxControl(
        tag=node.tag,
        name=local_name(node),
        list_box_rows=_parse_int_attribute(attrs, "listBoxRows"),
        list_box_width=_parse_int_attribute(attrs, "listBoxWidth"),
        edit_enable=attrs.pop("editEnable", None),
        selected_value=attrs.pop("selectedValue", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_comment_element(node: etree._Element) -> CommentElement:
    """Build a :class:`CommentElement` from a comment / PI *node*.

    Such nodes expose a callable ``tag`` instead of a string; ``node.tag is
    etree.PI`` distinguishes processing instructions (which carry a ``target``)
    from plain comments.
    """

    if node.tag is etree.PI:
        return CommentElement(kind="pi", text=node.text, target=node.target)
    return CommentElement(kind="comment", text=node.text)


def parse_preserved_element(node: etree._Element) -> PreservedElement:
    if not isinstance(node.tag, str):
        # Comment / processing-instruction node: ``local_name`` would return ""
        # and ``GenericElement`` cannot round-trip a callable tag.
        return parse_comment_element(node)
    name = local_name(node)
    if name == "linesegarray":
        return parse_line_seg_array_element(node)
    if name == "lineseg":
        return parse_line_seg_element(node)
    if name in {"transMatrix", "scaMatrix", "rotMatrix"}:
        return parse_transform_matrix_element(node)
    if name == "edit":
        return parse_form_edit_element(node)
    if name == "comboBox":
        return parse_form_combo_box_element(node)
    return GenericElement(
        name=name,
        tag=node.tag,
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def _parse_text_markup(node: etree._Element) -> InlineMark:
    name = local_name(node)
    if name in _TRACK_CHANGE_MARK_NAMES:
        return parse_track_change_mark(node)
    return parse_preserved_element(node)


def parse_text_span(node: etree._Element) -> TextSpan:
    leading = node.text or ""
    marks: List[TextMarkup] = []

    for child in node:
        mark = _parse_text_markup(child)
        trailing = child.tail or ""
        marks.append(TextMarkup(mark, trailing))

    return TextSpan(
        tag=node.tag,
        leading_text=leading,
        marks=marks,
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_control_element(node: etree._Element) -> Control:
    attrs = {key: value for key, value in node.attrib.items()}
    control_type = attrs.pop("type", None)
    children = [parse_preserved_element(child) for child in node]
    return Control(tag=node.tag, control_type=control_type, attributes=attrs, children=children)


def parse_inline_object_element(node: etree._Element) -> InlineObject:
    return InlineObject(
        tag=node.tag,
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
    )


def parse_table_element(node: etree._Element) -> Table:
    return Table(
        tag=node.tag,
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
    )


def parse_tab_element(node: etree._Element) -> Tab:
    return Tab(tag=node.tag, attributes={key: value for key, value in node.attrib.items()})


def parse_run_element(node: etree._Element) -> Run:
    attributes = {key: value for key, value in node.attrib.items()}
    char_pr_id_ref = parse_int(attributes.pop("charPrIDRef", None))

    run = Run(tag=node.tag, char_pr_id_ref=char_pr_id_ref, attributes=attributes)

    for child in node:
        name = local_name(child)
        if name == "secPr":
            element = parse_preserved_element(child)
            run.section_properties.append(element)
            run.content.append(element)
        elif name == "ctrl":
            control = parse_control_element(child)
            run.controls.append(control)
            run.content.append(control)
        elif name == "t":
            span = parse_text_span(child)
            run.text_spans.append(span)
            run.content.append(span)
        elif name == "tab":
            tab = parse_tab_element(child)
            run.tabs.append(tab)
            run.content.append(tab)
        elif name == "tbl":
            table = parse_table_element(child)
            run.tables.append(table)
            run.content.append(table)
        elif name in INLINE_OBJECT_NAMES:
            obj = parse_inline_object_element(child)
            run.inline_objects.append(obj)
            run.content.append(obj)
        else:
            element = parse_preserved_element(child)
            run.other_children.append(element)
            run.content.append(element)

    return run


def parse_paragraph_element(node: etree._Element) -> Paragraph:
    attributes = {key: value for key, value in node.attrib.items()}

    paragraph = Paragraph(
        tag=node.tag,
        id=parse_int(attributes.pop("id", None)),
        para_pr_id_ref=parse_int(attributes.pop("paraPrIDRef", None)),
        style_id_ref=parse_int(attributes.pop("styleIDRef", None)),
        page_break=parse_bool(attributes.pop("pageBreak", None)),
        column_break=parse_bool(attributes.pop("columnBreak", None)),
        merged=parse_bool(attributes.pop("merged", None)),
        attributes=attributes,
    )

    for child in node:
        if local_name(child) == "run":
            run = parse_run_element(child)
            paragraph.runs.append(run)
            paragraph.content.append(run)
        else:
            element = parse_preserved_element(child)
            paragraph.other_children.append(element)
            paragraph.content.append(element)

    return paragraph


def parse_section_element(node: etree._Element) -> Section:
    section = Section(tag=node.tag, attributes={key: value for key, value in node.attrib.items()})

    for child in node:
        if local_name(child) == "p":
            section.paragraphs.append(parse_paragraph_element(child))
        else:
            section.other_children.append(parse_preserved_element(child))

    return section


def _generic_element_to_xml(element: GenericElement) -> etree._Element:
    node = etree.Element(_qualified_tag(element.tag, element.name))
    for key, value in element.attributes.items():
        node.set(key, value)
    if element.text:
        node.text = element.text
    for child in element.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _set_int_attr(attrs: Dict[str, str], name: str, value: Optional[int]) -> None:
    if value is not None:
        attrs[name] = str(value)


def _line_seg_to_xml(line_seg: LineSeg) -> etree._Element:
    attrs = dict(line_seg.attributes)
    _set_int_attr(attrs, "textpos", line_seg.text_pos)
    _set_int_attr(attrs, "vertpos", line_seg.vert_pos)
    _set_int_attr(attrs, "vertsize", line_seg.vert_size)
    _set_int_attr(attrs, "textheight", line_seg.text_height)
    _set_int_attr(attrs, "baseline", line_seg.baseline)
    _set_int_attr(attrs, "spacing", line_seg.spacing)
    _set_int_attr(attrs, "horzpos", line_seg.horz_pos)
    _set_int_attr(attrs, "horzsize", line_seg.horz_size)
    _set_int_attr(attrs, "flags", line_seg.flags)
    node = etree.Element(_qualified_tag(line_seg.tag, line_seg.name), attrs)
    if line_seg.text:
        node.text = line_seg.text
    for child in line_seg.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _line_seg_array_to_xml(line_array: LineSegArray) -> etree._Element:
    node = etree.Element(_qualified_tag(line_array.tag, line_array.name), dict(line_array.attributes))
    if line_array.text:
        node.text = line_array.text
    for child in line_array.content:
        node.append(_preserved_element_to_xml(child))
    return node


def _set_str_attr(attrs: Dict[str, str], name: str, value: Optional[str]) -> None:
    if value is not None:
        attrs[name] = value


def _transform_matrix_to_xml(matrix: TransformMatrix) -> etree._Element:
    attrs = dict(matrix.attributes)
    _set_str_attr(attrs, "e1", matrix.e1)
    _set_str_attr(attrs, "e2", matrix.e2)
    _set_str_attr(attrs, "e3", matrix.e3)
    _set_str_attr(attrs, "e4", matrix.e4)
    _set_str_attr(attrs, "e5", matrix.e5)
    _set_str_attr(attrs, "e6", matrix.e6)
    node = etree.Element(_qualified_tag(matrix.tag, matrix.name), attrs)
    if matrix.text:
        node.text = matrix.text
    for child in matrix.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _form_edit_to_xml(edit: FormEditControl) -> etree._Element:
    attrs = dict(edit.attributes)
    _set_str_attr(attrs, "multiLine", edit.multi_line)
    _set_str_attr(attrs, "passwordChar", edit.password_char)
    _set_int_attr(attrs, "maxLength", edit.max_length)
    _set_str_attr(attrs, "scrollBars", edit.scroll_bars)
    _set_str_attr(attrs, "tabKeyBehavior", edit.tab_key_behavior)
    _set_str_attr(attrs, "numOnly", edit.num_only)
    _set_str_attr(attrs, "readOnly", edit.read_only)
    _set_str_attr(attrs, "alignText", edit.align_text)
    node = etree.Element(_qualified_tag(edit.tag, edit.name), attrs)
    if edit.text:
        node.text = edit.text
    for child in edit.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _form_combo_box_to_xml(combo: FormComboBoxControl) -> etree._Element:
    attrs = dict(combo.attributes)
    _set_int_attr(attrs, "listBoxRows", combo.list_box_rows)
    _set_int_attr(attrs, "listBoxWidth", combo.list_box_width)
    _set_str_attr(attrs, "editEnable", combo.edit_enable)
    _set_str_attr(attrs, "selectedValue", combo.selected_value)
    node = etree.Element(_qualified_tag(combo.tag, combo.name), attrs)
    if combo.text:
        node.text = combo.text
    for child in combo.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _comment_element_to_xml(element: CommentElement) -> etree._Element:
    if element.kind == "pi":
        return etree.ProcessingInstruction(element.target or "", element.text or "")
    return etree.Comment(element.text)


def _preserved_element_to_xml(element: PreservedElement) -> etree._Element:
    if isinstance(element, CommentElement):
        return _comment_element_to_xml(element)
    if isinstance(element, LineSegArray):
        return _line_seg_array_to_xml(element)
    if isinstance(element, LineSeg):
        return _line_seg_to_xml(element)
    if isinstance(element, TransformMatrix):
        return _transform_matrix_to_xml(element)
    if isinstance(element, FormEditControl):
        return _form_edit_to_xml(element)
    if isinstance(element, FormComboBoxControl):
        return _form_combo_box_to_xml(element)
    return _generic_element_to_xml(element)


def _track_change_mark_to_xml(mark: TrackChangeMark) -> etree._Element:
    attrs = dict(mark.attributes)
    if mark.para_end is not None:
        attrs["paraend"] = _bool_to_str(mark.para_end)
    if mark.tc_id is not None:
        attrs["TcId"] = str(mark.tc_id)
    if mark.id is not None:
        attrs["Id"] = str(mark.id)
    return etree.Element(_qualified_tag(mark.tag, mark.name), attrs)


def _inline_mark_to_xml(mark: InlineMark) -> etree._Element:
    if isinstance(mark, TrackChangeMark):
        return _track_change_mark_to_xml(mark)
    return _preserved_element_to_xml(mark)


def _text_span_to_xml(span: TextSpan) -> etree._Element:
    node = etree.Element(_qualified_tag(span.tag, "t"), dict(span.attributes))
    if span.leading_text:
        node.text = span.leading_text
    for mark in span.marks:
        child = _inline_mark_to_xml(mark.element)
        node.append(child)
        if mark.trailing_text:
            child.tail = mark.trailing_text
    return node


def _tab_to_xml(tab: Tab) -> etree._Element:
    return etree.Element(_qualified_tag(tab.tag, "tab"), dict(tab.attributes))


def _control_to_xml(control: Control) -> etree._Element:
    attrs = dict(control.attributes)
    if control.control_type is not None:
        attrs["type"] = control.control_type
    node = etree.Element(_qualified_tag(control.tag, "ctrl"), attrs)
    for child in control.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _table_to_xml(table: Table) -> etree._Element:
    node = etree.Element(_qualified_tag(table.tag, "tbl"), dict(table.attributes))
    for child in table.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _inline_object_to_xml(obj: InlineObject) -> etree._Element:
    node = etree.Element(_qualified_tag(obj.tag, obj.name), dict(obj.attributes))
    for child in obj.children:
        node.append(_preserved_element_to_xml(child))
    return node


def serialize_run(run: Run) -> etree._Element:
    attrs = dict(run.attributes)
    if run.char_pr_id_ref is not None:
        attrs["charPrIDRef"] = str(run.char_pr_id_ref)
    node = etree.Element(_qualified_tag(run.tag, "run"), attrs)
    for child in run.content:
        if isinstance(child, TextSpan):
            node.append(_text_span_to_xml(child))
        elif isinstance(child, Control):
            node.append(_control_to_xml(child))
        elif isinstance(child, Tab):
            node.append(_tab_to_xml(child))
        elif isinstance(child, Table):
            node.append(_table_to_xml(child))
        elif isinstance(child, InlineObject):
            node.append(_inline_object_to_xml(child))
        else:
            node.append(_preserved_element_to_xml(child))
    return node


def serialize_paragraph(paragraph: Paragraph) -> etree._Element:
    attrs = dict(paragraph.attributes)
    if paragraph.id is not None:
        attrs["id"] = str(paragraph.id)
    if paragraph.para_pr_id_ref is not None:
        attrs["paraPrIDRef"] = str(paragraph.para_pr_id_ref)
    if paragraph.style_id_ref is not None:
        attrs["styleIDRef"] = str(paragraph.style_id_ref)
    if paragraph.page_break is not None:
        attrs["pageBreak"] = _bool_to_str(paragraph.page_break)
    if paragraph.column_break is not None:
        attrs["columnBreak"] = _bool_to_str(paragraph.column_break)
    if paragraph.merged is not None:
        attrs["merged"] = _bool_to_str(paragraph.merged)

    node = etree.Element(_qualified_tag(paragraph.tag, "p"), attrs)
    for child in paragraph.content:
        if isinstance(child, Run):
            node.append(serialize_run(child))
        else:
            node.append(_preserved_element_to_xml(child))
    return node


__all__ = [
    "CommentElement",
    "Control",
    "FormComboBoxControl",
    "FormEditControl",
    "InlineObject",
    "INLINE_OBJECT_NAMES",
    "LineSeg",
    "LineSegArray",
    "Paragraph",
    "PreservedElement",
    "Run",
    "Section",
    "Table",
    "TextMarkup",
    "TextSpan",
    "TrackChangeMark",
    "TransformMatrix",
    "parse_comment_element",
    "parse_control_element",
    "parse_form_combo_box_element",
    "parse_form_edit_element",
    "parse_inline_object_element",
    "parse_line_seg_array_element",
    "parse_line_seg_element",
    "parse_paragraph_element",
    "parse_preserved_element",
    "parse_run_element",
    "parse_section_element",
    "parse_table_element",
    "parse_text_span",
    "parse_track_change_mark",
    "parse_transform_matrix_element",
    "serialize_paragraph",
    "serialize_run",
]

logger = logging.getLogger(__name__)
