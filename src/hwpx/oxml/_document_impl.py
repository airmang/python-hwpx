# SPDX-License-Identifier: Apache-2.0
"""Compatibility aggregate for the extracted HWPX OXML owners."""

from __future__ import annotations

import logging
from copy import deepcopy  # noqa: F401 - frozen compatibility re-export
from dataclasses import dataclass  # noqa: F401 - frozen compatibility re-export
from types import ModuleType as _ModuleType
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Mapping, Optional, Sequence, TypeVar  # noqa: F401 - frozen compatibility re-exports
import sys as _sys
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # noqa: F401 - frozen compatibility re-export

from . import body  # noqa: F401 - frozen compatibility re-export
from . import _document_primitives as _primitives
from ._document_primitives import (  # noqa: F401 - private compatibility seam
    _BASIC_BORDER_CHILDREN, _BASIC_BORDER_FILL_ATTRIBUTES, _BORDER_SIDE_ELEMENTS,
    _HP_NS,
    _HP,
    _HS_NS,
    _HS,
    _HH_NS,
    _HH,
    _HC_NS,
    _HC,
    _DEFAULT_PARAGRAPH_ATTRS,
    _DEFAULT_CELL_WIDTH,
    _DEFAULT_CELL_HEIGHT,
    _FONT_REF_ATTRIBUTES,
    _FONT_FACE_LANG_TO_REF,
    T,
    _sanitize_text,
    _child_tag_like,
    _children_by_local,
    _first_child_by_local,
    _normalize_color,
    _char_height_from_points,
    _serialize_xml,
    _paragraph_id,
    _object_id,
    _memo_id,
    _refresh_copied_paragraph_subtree_ids,
    _clone_paragraph_element,
    _create_paragraph_element,
    _clear_paragraph_layout_cache,
    _simple_paragraph_text_length,
    _remove_stale_paragraph_layout_cache,
    _element_local_name,
    _append_child,
    _is_tab_control_element,
    _append_text_with_tabs,
    _normalize_length,
    _is_integer_literal,
    _border_fill_is_basic_solid_line,
    _create_basic_border_fill_element,
    _border_fill_child_attrs,
    _normalize_border_side_names,
    _border_fill_fill_color,
    _border_fill_matches,
    _create_border_fill_element,
    _distribute_size,
    _default_cell_attributes,
    _default_cell_paragraph_attributes,
    _default_cell_margin_attributes,
    _get_int_attr,
    _default_sublist_attributes
)
from ._document_primitives import _ILLEGAL_XML_CHARS, _LAYOUT_CACHE_ELEMENT_NAMES, _re  # noqa: F401 - private compatibility seam
from .common import GenericElement  # noqa: F401 - frozen compatibility re-export
from .document_parts import HwpxOxmlDocument  # noqa: F401 - frozen compatibility re-export
from .header import (  # noqa: F401 - frozen compatibility re-exports
    Bullet,
    Header,
    MemoProperties,
    MemoShape,
    ParagraphProperty,
    Style,
    TrackChange,
    TrackChangeAuthor,
    memo_shape_from_attributes,
    parse_bullets,
    parse_border_fills,
    parse_header_element,
    parse_paragraph_properties,
    parse_styles,
    parse_track_change_authors,
    parse_track_change_config,
    parse_track_changes,
    track_change_author_to_xml,
    track_change_to_xml,
)
from .header_part import HwpxOxmlHeader  # noqa: F401 - frozen compatibility re-export
from .memo import HwpxOxmlMemo, HwpxOxmlMemoGroup, HwpxOxmlNote  # noqa: F401 - frozen compatibility re-exports
from .namespaces import (  # noqa: F401 - frozen compatibility re-exports
    HWPML_COMPAT_ROOT_NAMESPACES,
    HC,
    HC_NS,
    HH,
    HH_NS,
    HP,
    HP_NS,
    HS,
    HS_NS,
    register_owpml_namespaces,
    tag_local_name,
    tag_namespace,
)
from .numbering import DocumentNumbering, SectionStartNumbering  # noqa: F401 - frozen compatibility re-exports
from .objects import (  # noqa: F401 - frozen/private compatibility re-exports
    _DEFAULT_LINE_SHAPE_ATTRS, _IDENTITY_MATRIX,
    HwpxOxmlInlineObject,
    HwpxOxmlShape,
    _build_drawing_object_children,
    _build_shape_base_children,
    _build_shape_common_children,
    _create_ellipse_element,
    _create_line_element,
    _create_picture_element,
    _create_rectangle_element,
)
from .paragraph import HwpxOxmlParagraph  # noqa: F401 - frozen compatibility re-export
from .run import HwpxOxmlRun, RunStyle, _char_properties_from_header  # noqa: F401 - frozen/private compatibility re-exports
from .section import HwpxOxmlSection, HwpxOxmlSectionHeaderFooter, HwpxOxmlSectionProperties  # noqa: F401 - frozen compatibility re-exports
from .section_format import PageMargins, PageSize  # noqa: F401 - frozen compatibility re-exports
from .simple_parts import (  # noqa: F401 - frozen/private compatibility re-exports
    HwpxOxmlHistory,
    HwpxOxmlMasterPage,
    HwpxOxmlVersion,
    _HwpxOxmlSimplePart,
)
from .table import HwpxOxmlTable, HwpxOxmlTableCell, HwpxOxmlTableRow, HwpxTableGridPosition  # noqa: F401 - frozen compatibility re-exports
from .utils import parse_int  # noqa: F401 - frozen compatibility re-export

register_owpml_namespaces(ET.register_namespace)
logger = logging.getLogger(__name__)
uuid4 = _primitives.uuid4

class _DocumentImplFacade(_ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        if name == "uuid4":
            _primitives.uuid4 = value  # type: ignore[assignment]  # frozen monkeypatch seam
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name == "uuid4":
            delattr(_primitives, name)
        super().__delattr__(name)
_sys.modules[__name__].__class__ = _DocumentImplFacade
