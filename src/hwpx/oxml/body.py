from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from lxml import etree

from .common import GenericElement, parse_generic_element
from .utils import local_name, parse_bool, parse_int


INLINE_OBJECT_NAMES = {
    "line",
    "rect",
    "ellipse",
    "arc",
    "polyline",
    "polygon",
    "curve",
    "picture",
    "tbl",
    "shape",
    "drawingObject",
    "equation",
    "ole",
    "chart",
    "video",
    "audio",
}


@dataclass(slots=True)
class TextSpan:
    text: str
    marks: List[GenericElement] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Run:
    char_pr_id_ref: Optional[int]
    section_properties: List[GenericElement] = field(default_factory=list)
    controls: List[GenericElement] = field(default_factory=list)
    inline_objects: List[GenericElement] = field(default_factory=list)
    text_spans: List[TextSpan] = field(default_factory=list)
    other_children: List[GenericElement] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Paragraph:
    id: Optional[int]
    para_pr_id_ref: Optional[int]
    style_id_ref: Optional[int]
    page_break: Optional[bool]
    column_break: Optional[bool]
    merged: Optional[bool]
    runs: List[Run] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    other_children: List[GenericElement] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    attributes: Dict[str, str]
    paragraphs: List[Paragraph] = field(default_factory=list)
    other_children: List[GenericElement] = field(default_factory=list)


def parse_text_span(node: etree._Element) -> TextSpan:
    parts: List[str] = []
    marks: List[GenericElement] = []

    if node.text:
        parts.append(node.text)

    for child in node:
        marks.append(parse_generic_element(child))
        if child.tail:
            parts.append(child.tail)

    text = "".join(parts)
    return TextSpan(text=text, marks=marks, attributes={key: value for key, value in node.attrib.items()})


def parse_run_element(node: etree._Element) -> Run:
    attributes = {key: value for key, value in node.attrib.items()}
    char_pr_id_ref = parse_int(attributes.pop("charPrIDRef", None))

    run = Run(char_pr_id_ref=char_pr_id_ref, attributes=attributes)

    for child in node:
        name = local_name(child)
        if name == "secPr":
            run.section_properties.append(parse_generic_element(child))
        elif name == "ctrl":
            run.controls.append(parse_generic_element(child))
        elif name == "t":
            run.text_spans.append(parse_text_span(child))
        elif name in INLINE_OBJECT_NAMES:
            run.inline_objects.append(parse_generic_element(child))
        else:
            run.other_children.append(parse_generic_element(child))

    return run


def parse_paragraph_element(node: etree._Element) -> Paragraph:
    attributes = {key: value for key, value in node.attrib.items()}

    paragraph = Paragraph(
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
            paragraph.runs.append(parse_run_element(child))
        else:
            paragraph.other_children.append(parse_generic_element(child))

    return paragraph


def parse_section_element(node: etree._Element) -> Section:
    section = Section(attributes={key: value for key, value in node.attrib.items()})

    for child in node:
        if local_name(child) == "p":
            section.paragraphs.append(parse_paragraph_element(child))
        else:
            section.other_children.append(parse_generic_element(child))

    return section


__all__ = [
    "Paragraph",
    "Run",
    "Section",
    "TextSpan",
    "parse_paragraph_element",
    "parse_run_element",
    "parse_section_element",
    "parse_text_span",
]
