from __future__ import annotations

from typing import Callable, Dict, Optional

from lxml import etree

from . import body, header
from .common import parse_generic_element
from .schema import SchemaPath, load_schema
from .utils import XmlSource, coerce_xml_source, local_name

ParserFn = Callable[[etree._Element], object]


_ELEMENT_FACTORY: Dict[str, ParserFn] = {
    "head": header.parse_header_element,
    "beginNum": header.parse_begin_num,
    "refList": header.parse_ref_list,
    "docOption": header.parse_doc_option,
    "sec": body.parse_section_element,
    "p": body.parse_paragraph_element,
    "run": body.parse_run_element,
    "t": body.parse_text_span,
}


def element_to_model(node: etree._Element) -> object:
    """Convert *node* into the corresponding Python object."""

    parser = _ELEMENT_FACTORY.get(local_name(node))
    if parser is None:
        return parse_generic_element(node)
    return parser(node)


def _validate(tree: etree._ElementTree, schema_path: Optional[SchemaPath], schema: Optional[etree.XMLSchema]) -> None:
    schema_obj = schema or (load_schema(schema_path) if schema_path else None)
    if schema_obj is not None:
        schema_obj.assertValid(tree)


def parse_header_xml(source: XmlSource, *, schema_path: Optional[SchemaPath] = None, schema: Optional[etree.XMLSchema] = None) -> header.Header:
    root, tree = coerce_xml_source(source)
    if local_name(root) != "head":
        raise ValueError("Expected <head> root element")
    _validate(tree, schema_path, schema)
    return header.parse_header_element(root)


def parse_section_xml(source: XmlSource, *, schema_path: Optional[SchemaPath] = None, schema: Optional[etree.XMLSchema] = None) -> body.Section:
    root, tree = coerce_xml_source(source)
    if local_name(root) != "sec":
        raise ValueError("Expected <sec> root element")
    _validate(tree, schema_path, schema)
    return body.parse_section_element(root)


__all__ = [
    "element_to_model",
    "parse_header_xml",
    "parse_section_xml",
]
