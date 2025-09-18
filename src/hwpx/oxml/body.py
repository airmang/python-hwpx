from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from lxml import etree

from .common import GenericElement, parse_generic_element
from .utils import local_name, parse_bool, parse_int


_DEFAULT_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_DEFAULT_HP = f"{{{_DEFAULT_HP_NS}}}"

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

InlineMark = Union[GenericElement, "TrackChangeMark"]
RunChild = Union[GenericElement, "Control", "Table", "InlineObject", "TextSpan"]
ParagraphChild = Union["Run", GenericElement]


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
    children: List[GenericElement] = field(default_factory=list)


@dataclass(slots=True)
class InlineObject:
    tag: str
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[GenericElement] = field(default_factory=list)


@dataclass(slots=True)
class Table:
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[GenericElement] = field(default_factory=list)


@dataclass(slots=True)
class Run:
    tag: str
    char_pr_id_ref: Optional[int]
    section_properties: List[GenericElement] = field(default_factory=list)
    controls: List[Control] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    inline_objects: List[InlineObject] = field(default_factory=list)
    text_spans: List[TextSpan] = field(default_factory=list)
    other_children: List[GenericElement] = field(default_factory=list)
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
    other_children: List[GenericElement] = field(default_factory=list)
    content: List[ParagraphChild] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    tag: str
    attributes: Dict[str, str]
    paragraphs: List[Paragraph] = field(default_factory=list)
    other_children: List[GenericElement] = field(default_factory=list)


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


def _parse_text_markup(node: etree._Element) -> InlineMark:
    name = local_name(node)
    if name in _TRACK_CHANGE_MARK_NAMES:
        return parse_track_change_mark(node)
    return parse_generic_element(node)


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
    children = [parse_generic_element(child) for child in node]
    return Control(tag=node.tag, control_type=control_type, attributes=attrs, children=children)


def parse_inline_object_element(node: etree._Element) -> InlineObject:
    return InlineObject(
        tag=node.tag,
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_generic_element(child) for child in node],
    )


def parse_table_element(node: etree._Element) -> Table:
    return Table(
        tag=node.tag,
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_generic_element(child) for child in node],
    )


def parse_run_element(node: etree._Element) -> Run:
    attributes = {key: value for key, value in node.attrib.items()}
    char_pr_id_ref = parse_int(attributes.pop("charPrIDRef", None))

    run = Run(tag=node.tag, char_pr_id_ref=char_pr_id_ref, attributes=attributes)

    for child in node:
        name = local_name(child)
        if name == "secPr":
            element = parse_generic_element(child)
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
        elif name == "tbl":
            table = parse_table_element(child)
            run.tables.append(table)
            run.content.append(table)
        elif name in INLINE_OBJECT_NAMES:
            obj = parse_inline_object_element(child)
            run.inline_objects.append(obj)
            run.content.append(obj)
        else:
            element = parse_generic_element(child)
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
            element = parse_generic_element(child)
            paragraph.other_children.append(element)
            paragraph.content.append(element)

    return paragraph


def parse_section_element(node: etree._Element) -> Section:
    section = Section(tag=node.tag, attributes={key: value for key, value in node.attrib.items()})

    for child in node:
        if local_name(child) == "p":
            section.paragraphs.append(parse_paragraph_element(child))
        else:
            section.other_children.append(parse_generic_element(child))

    return section


def _generic_element_to_xml(element: GenericElement) -> etree._Element:
    node = etree.Element(_qualified_tag(element.tag, element.name))
    for key, value in element.attributes.items():
        node.set(key, value)
    if element.text:
        node.text = element.text
    for child in element.children:
        node.append(_generic_element_to_xml(child))
    return node


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
    return _generic_element_to_xml(mark)


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


def _control_to_xml(control: Control) -> etree._Element:
    attrs = dict(control.attributes)
    if control.control_type is not None:
        attrs["type"] = control.control_type
    node = etree.Element(_qualified_tag(control.tag, "ctrl"), attrs)
    for child in control.children:
        node.append(_generic_element_to_xml(child))
    return node


def _table_to_xml(table: Table) -> etree._Element:
    node = etree.Element(_qualified_tag(table.tag, "tbl"), dict(table.attributes))
    for child in table.children:
        node.append(_generic_element_to_xml(child))
    return node


def _inline_object_to_xml(obj: InlineObject) -> etree._Element:
    node = etree.Element(_qualified_tag(obj.tag, obj.name), dict(obj.attributes))
    for child in obj.children:
        node.append(_generic_element_to_xml(child))
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
        elif isinstance(child, Table):
            node.append(_table_to_xml(child))
        elif isinstance(child, InlineObject):
            node.append(_inline_object_to_xml(child))
        else:
            node.append(_generic_element_to_xml(child))
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
            node.append(_generic_element_to_xml(child))
    return node


__all__ = [
    "Control",
    "InlineObject",
    "INLINE_OBJECT_NAMES",
    "Paragraph",
    "Run",
    "Section",
    "Table",
    "TextMarkup",
    "TextSpan",
    "TrackChangeMark",
    "parse_control_element",
    "parse_inline_object_element",
    "parse_paragraph_element",
    "parse_run_element",
    "parse_section_element",
    "parse_table_element",
    "parse_text_span",
    "parse_track_change_mark",
    "serialize_paragraph",
    "serialize_run",
]
