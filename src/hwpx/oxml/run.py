# SPDX-License-Identifier: Apache-2.0
"""Run content and character-format wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Sequence, cast
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import (
    SameElement,
    _HH,
    _HP,
    _clear_paragraph_layout_cache,
    _definition_id_keys,
    _element_local_name,
    _is_tab_control_element,
    _require_text,
    _TEXT_INLINE_ATOMS,
    _text_element_content,
)
from ._paragraph_text_edit import (
    live_paragraph,
    clear_text_element,
    section_setting_runs,
    set_text_with_tabs,
    text_marks_as_elements,
    text_marks_as_elements_in,
)

if TYPE_CHECKING:
    from ..objects.results import InlineItem, LanguageFonts
    from .paragraph import HwpxOxmlParagraph


def text_element_content(element: ET.Element, *, tab_token: str = "\t") -> str:
    """The text of an ``hp:t`` element as Hancom shows it.

    Hancom writes tabs, line breaks and special spaces *inside* ``hp:t``
    (``<hp:t>성<hp:fwSpace/>명<hp:tab/>홍길동</hp:t>``): a tab is *tab_token*, a line
    break ``"\\n"``, a special space its character. Other element children keep their
    own text; empty marks (highlight, tracked change) add nothing. ``Run.text`` is the
    run's ``hp:t`` elements read so. Works on lxml and ElementTree elements.
    """

    return _text_element_content(element, tab=tab_token)


#: The closed vocabulary :meth:`HwpxOxmlRun.content_kinds` answers in.
#: ``"other"`` stands for any element child outside the rest, so a caller that
#: only knows these names still sees that the run holds something.
RUN_CONTENT_KINDS: frozenset[str] = frozenset(
    {
        "text",
        "table",
        "picture",
        "shape",
        "equation",
        "ole",
        "chart",
        "video",
        "form",
        "control",
        "section_properties",
        "other",
    }
)

# Glyph atoms inside ``hp:t`` that stand for characters without holding any.
_TEXT_GLYPH_NAMES = frozenset({"tab", "lineBreak", "hyphen", "nbSpace", "fwSpace"})

# Run children by local name (OWPML ``hp:run`` choice, plus the non-schema
# ``picture``/``polyline``/``drawingObject``/``shape`` names the reader
# already accepts as inline objects).
_RUN_CHILD_KINDS: dict[str, str] = {
    "compose": "text",
    "dutmal": "text",
    "tbl": "table",
    "pic": "picture",
    "picture": "picture",
    **{
        name: "shape"
        for name in (
            "line",
            "rect",
            "ellipse",
            "arc",
            "polyline",
            "polygon",
            "curve",
            "connectLine",
            "container",
            "drawingObject",
            "shape",
            "textart",
        )
    },
    "equation": "equation",
    "ole": "ole",
    "chart": "chart",
    "video": "video",
    **{
        name: "form"
        for name in ("btn", "radioBtn", "checkBtn", "comboBox", "listBox", "edit", "scrollBar")
    },
    "ctrl": "control",
    "secPr": "section_properties",
}


#: ``InlineItem.kind`` of the glyphs and marks written inside ``hp:t`` (also taken when a
#: writer puts them right in the run).
_TEXT_PIECE_KINDS: dict[str, str] = {
    "tab": "tab",
    "lineBreak": "line_break",
    "nbSpace": "nb_space",
    "fwSpace": "fw_space",
    "hyphen": "hyphen",
    "markpenBegin": "markpen_begin",
    "markpenEnd": "markpen_end",
    "titleMark": "title_mark",
    "insertBegin": "insert_begin",
    "insertEnd": "insert_end",
    "deleteBegin": "delete_begin",
    "deleteEnd": "delete_end",
}
#: ``InlineItem.kind`` of the controls of ``hp:ctrl``.
_CONTROL_PIECE_KINDS: dict[str, str] = {
    "fieldBegin": "field_begin",
    "fieldEnd": "field_end",
    "footNote": "footnote",
    "endNote": "endnote",
    "bookmark": "bookmark",
    "autoNum": "auto_number",
    "pageNum": "page_number",
    "pageNumCtrl": "page_number_ctrl",
    "newNum": "number_restart",
    "pageHiding": "page_hiding",
    "colPr": "column_definition",
    "header": "header",
    "footer": "footer",
    "indexmark": "index_mark",
    "hiddenComment": "hidden_comment",
}
#: ``InlineItem.kind`` of the other run children (objects as ``doc.text.iter_objects()`` names them).
_RUN_PIECE_KINDS: dict[str, str] = {
    "tbl": "table",
    "pic": "picture",
    "equation": "equation",
    "ole": "ole",
    "chart": "chart",
    "video": "video",
    "textart": "textart",
    **{name: "shape" for name in ("line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine", "container")},
    **{name: "form" for name in ("btn", "radioBtn", "checkBtn", "comboBox", "listBox", "edit", "scrollBar")},
    "dutmal": "ruby",
    "compose": "composed_character",
    "secPr": "section_properties",
    "switch": "switch",
    **_TEXT_PIECE_KINDS,
}
_OBJECT_PIECE_KINDS = frozenset({"table", "picture", "equation", "ole", "chart", "video", "textart", "shape", "form"})


def _field_or_story_object(kind: str, element: Any, paragraph: Any) -> Any:
    """A field start's model (:class:`Hyperlink`, a memo held in its field, else :class:`FieldControl`) or a
    header's or footer's (``kind`` ``"header"``/``"footer"``), for :func:`_piece_object`."""

    if kind != "field_begin":
        from .section import HwpxOxmlSection
        from .section_story import HwpxOxmlSectionHeaderFooter

        section = paragraph.section
        return HwpxOxmlSectionHeaderFooter(element, section.properties) if isinstance(section, HwpxOxmlSection)             else None
    if element.get("type") == "HYPERLINK":
        from ..objects.form_field import Hyperlink

        return Hyperlink(element, paragraph)
    if element.get("type") == "MEMO" and element.find(f"{_HP}subList") is not None:
        from .memo import HwpxOxmlFieldMemo

        return HwpxOxmlFieldMemo(element, paragraph.section)
    from ..objects.form_field import FieldControl, field_parameters

    return FieldControl(field_type=element.get("type", ""), field_id=element.get("id", ""),
                        name=element.get("name", ""), parameters=field_parameters(element), element=element)


def switch_choice(element: Any, paragraph: Any) -> Any:
    """The :class:`~hwpx.objects.SwitchChoice` of the ``hp:switch`` *element* in a run of *paragraph*."""

    from ..objects.results import SwitchChoice
    from .objects import wrap_object

    def branch(name: str) -> Any:
        return next((child for child in element if _local_name(child) == name), None)

    def objects(holder: Any) -> tuple[Any, ...]:
        if holder is None:
            return ()
        return tuple(wrap_object(child, paragraph) for child in holder
                     if _RUN_PIECE_KINDS.get(_local_name(child)) in _OBJECT_PIECE_KINDS)

    case = branch("case")
    required = None
    if case is not None:
        required = next((value for key, value in case.attrib.items() if str(key).endswith("required-namespace")), None)
    return SwitchChoice(required_namespace=required, case=objects(case), default=objects(branch("default")),
                        element=element)


def _piece_object(kind: str, element: Any, run: "HwpxOxmlRun") -> Any:
    """The model object a piece of *run* stands for, ``None`` when it has none."""

    paragraph = run.paragraph
    if kind in _OBJECT_PIECE_KINDS:
        from .objects import wrap_object

        return wrap_object(element, paragraph)
    if kind in ("footnote", "endnote"):
        from .memo import HwpxOxmlNote

        return HwpxOxmlNote(element, paragraph)
    if kind in ("field_begin", "header", "footer"):
        return _field_or_story_object(kind, element, paragraph)
    if kind in ("ruby", "composed_character"):
        from ..objects.highlight import ComposedCharacter, Ruby

        return (Ruby if kind == "ruby" else ComposedCharacter)(element, paragraph)
    if kind in ("auto_number", "page_number", "number_restart", "page_hiding"):
        from .._document.ns import page as _page

        build = {
            "auto_number": _page.auto_number,
            "page_number": _page.page_number_control,
            "number_restart": _page.number_restart,
            "page_hiding": _page.page_hiding,
        }[kind]
        return build(element, paragraph)
    if kind == "switch":
        return switch_choice(element, paragraph)
    if kind == "column_definition":
        from .._document.ns.page import _column_definition
        from .section import HwpxOxmlSection

        section = paragraph.section
        return _column_definition(element, paragraph, section) if isinstance(section, HwpxOxmlSection) else None
    return None


#: Local names by tag, so reading a run's pieces does not split the same tags over and over.
_LOCAL_NAMES: dict[str, str] = {}


def _local_name(node: Any) -> str:
    tag = node.tag
    if not isinstance(tag, str):
        return ""  # a comment or processing instruction
    name = _LOCAL_NAMES.get(tag)
    if name is None:
        name = _LOCAL_NAMES[tag] = _element_local_name(node)
    return name


def _piece(
    kind: str, element: Any, container: str, run: "HwpxOxmlRun", text: str = "", child_index: int = 0
) -> "InlineItem":
    from ..objects.results import InlineItem

    return InlineItem(
        kind=kind,
        name=_local_name(element),
        container=container,
        text=text,
        attributes=tuple((str(key), str(value)) for key, value in element.attrib.items()),
        object=_piece_object(kind, element, run),
        element=element,
        child_index=child_index,
    )


def _text_pieces(
    node: Any, run: "HwpxOxmlRun", pieces: "list[InlineItem]", item: Any, child_index: int = 0
) -> None:
    """The pieces of the ``hp:t`` *node*: its characters, and the glyphs and marks between them.

    A comment or processing instruction inside ``hp:t`` holds no text of its own: the characters on
    either side of it are one stretch of text.
    """

    stretch: list[str] = [node.text] if node.text else []
    for child in node:
        name = _local_name(child)
        if name:
            if stretch:
                pieces.append(item(kind="text", name="", container="t", text="".join(stretch),
                                   child_index=child_index))
                stretch = []
            kind = _TEXT_PIECE_KINDS.get(name, "unknown")
            if name in _TEXT_INLINE_ATOMS:
                text = _TEXT_INLINE_ATOMS[name]
            elif kind == "unknown":
                text = "".join(child.itertext())
            else:
                text = ""
            pieces.append(_piece(kind, child, "t", run, text, child_index))
        if child.tail:
            stretch.append(child.tail)
    if stretch:
        pieces.append(item(kind="text", name="", container="t", text="".join(stretch), child_index=child_index))


def run_content(run: "HwpxOxmlRun") -> "tuple[InlineItem, ...]":
    """The pieces of *run* in file order (:attr:`HwpxOxmlRun.content`)."""

    from ..objects.results import InlineItem

    from dataclasses import replace

    from .formatting import _unit_length
    from .text_offsets import run_start

    pieces: list[InlineItem] = []
    index = -1
    position = run_start(run.paragraph.element, run.element)  # the paragraph's characters before the run
    for child in run.element:
        name = _local_name(child)
        if not name:
            continue  # a comment or processing instruction
        index += 1
        first = len(pieces)
        if name == "t":
            _text_pieces(child, run, pieces, InlineItem, index)
        elif name == "ctrl":
            for control in child:
                control_name = _local_name(control)
                if control_name:
                    pieces.append(_piece(_CONTROL_PIECE_KINDS.get(control_name, "unknown"), control, "ctrl", run,
                                         child_index=index))
        else:
            pieces.append(_piece(_RUN_PIECE_KINDS.get(name, "unknown"), child, "run", run,
                                 _TEXT_INLINE_ATOMS.get(name, ""), index))
        inside = position
        for at in range(first, len(pieces)):  # where each piece of this child stands
            pieces[at] = replace(pieces[at], offset=inside)
            if name == "t":
                inside += len(pieces[at].text)
        position += _unit_length(child)
    return tuple(pieces)


def _text_element_holds_text(node: ET.Element) -> bool:
    if "".join(node.itertext()):
        return True
    return any(_element_local_name(child) in _TEXT_GLYPH_NAMES for child in node.iter())


@dataclass(slots=True)
class RunStyle:
    """Represents the resolved character style applied to a run."""

    id: str
    attributes: dict[str, str]
    child_attributes: dict[str, dict[str, str]]
    #: The face each language's ``hh:fontRef`` names (``"HANGUL"`` .. ``"USER"`` -> face).
    fonts: dict[str, str] = field(default_factory=dict)

    @property
    def color(self) -> str | None:
        """The text colour (``textColor``)."""
        return self.attributes.get("textColor")

    @property
    def size(self) -> float | None:
        """The character size in points (``height`` / 100), or ``None`` without one."""
        height = self.attributes.get("height")
        try:
            return None if height is None else int(height) / 100
        except ValueError:
            return None

    @property
    def font(self) -> str | None:
        """The Hangul face of the shape (``fonts["HANGUL"]``)."""
        return self.fonts.get("HANGUL")

    @property
    def underline_type(self) -> str | None:
        """The underline's type (``hh:underline/@type``: ``NONE``, ``BOTTOM`` ...), ``None`` without one."""
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("type")

    @property
    def underline_color(self) -> str | None:
        """The underline's colour (``hh:underline/@color``), ``None`` without one."""
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("color")

    @property
    def outline_type(self) -> str | None:
        """The outline's type (``hh:outline/@type``), ``None`` without one."""
        outline = self.child_attributes.get("outline")
        if outline is None:
            return None
        return outline.get("type")

    @property
    def superscript(self) -> bool:
        """Whether the shape is superscript (``hh:supscript``), as ``run.superscript``."""
        return "supscript" in self.child_attributes

    @property
    def subscript(self) -> bool:
        """Whether the shape is subscript (``hh:subscript``), as ``run.subscript``."""
        return "subscript" in self.child_attributes

    @property
    def emboss(self) -> bool:
        """Whether the shape is embossed (``hh:emboss``, 양각)."""
        return "emboss" in self.child_attributes

    @property
    def engrave(self) -> bool:
        """Whether the shape is engraved (``hh:engrave``, 음각)."""
        return "engrave" in self.child_attributes

    def matches(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
    ) -> bool:
        """Whether the shape has the given text colour (``color``), underline type and underline colour;
        one left as ``None`` matches any."""
        if text_color is not None and self.color != text_color:
            return False
        if underline_type is not None and self.underline_type != underline_type:
            return False
        if underline_color is not None and self.underline_color != underline_color:
            return False
        return True


def _font_faces_by_lang(ref_list: ET.Element) -> dict[str, dict[str, ET.Element]]:
    """Each ``hh:fontface`` block's fonts: lang (``HANGUL`` ..) -> font id -> ``hh:font``."""

    faces: dict[str, dict[str, ET.Element]] = {}
    for fontface in ref_list.iter(f"{_HH}fontface"):
        faces.setdefault((fontface.get("lang") or "").upper(), {
            font.get("id") or "": font for font in fontface.findall(f"{_HH}font")
        })
    return faces


def _named_font_elements(faces: dict[str, dict[str, ET.Element]], refs: dict[str, str]) -> dict[str, ET.Element]:
    """The ``hh:font`` a ``hh:fontRef`` (*refs*, ``hangul`` -> id ..) names in each language."""

    return {
        lang: faces[lang][refs[lang.lower()]]
        for lang in faces
        if lang.lower() in refs and refs[lang.lower()] in faces[lang]
    }


def _font_signature(fonts: dict[str, ET.Element]) -> tuple[Any, ...]:
    """What the faces a shape names were read from: each ``hh:font``, its block and their values."""

    signature = []
    for lang, font in fonts.items():
        block = cast(Any, font).getparent() if isinstance(font, LET._Element) else None
        holder = None if block is None else block.getparent()
        signature.append((lang, font.get("id"), font.get("face"), block, None if block is None else block.get("lang"),
                          holder is not None))
    return tuple(signature)


def _char_properties_from_header(element: ET.Element) -> dict[str, RunStyle]:
    return {key: style for key, (style, _definition, _fonts) in _char_property_entries(element).items()}


def _char_property_box(element: ET.Element) -> ET.Element | None:
    ref_list = element.find(f"{_HH}refList")
    return None if ref_list is None else ref_list.find(f"{_HH}charProperties")


def _char_property_entries(
    element: ET.Element,
) -> dict[str, tuple[RunStyle, ET.Element, dict[str, ET.Element]]]:
    """Each ``hh:charPr`` of the header *element*, by id (and by its number), with the element read
    and the ``hh:font`` each language's face was read from."""

    mapping: dict[str, tuple[RunStyle, ET.Element, dict[str, ET.Element]]] = {}
    char_props_element = _char_property_box(element)
    if char_props_element is None:
        return mapping

    faces = _font_faces_by_lang(cast(ET.Element, element.find(f"{_HH}refList")))
    for child in char_props_element.findall(f"{_HH}charPr"):
        char_id = child.get("id")
        if not char_id:
            continue
        attributes = {key: value for key, value in child.attrib.items() if key != "id"}
        child_attributes: dict[str, dict[str, str]] = {}
        for grandchild in child:
            if len(list(grandchild)) == 0 and (grandchild.text is None or not grandchild.text.strip()):
                child_attributes[_element_local_name(grandchild)] = {
                    key: value for key, value in grandchild.attrib.items()
                }
        font_elements = _named_font_elements(faces, child_attributes.get("fontRef", {}))
        fonts = {lang: font.get("face") or "" for lang, font in font_elements.items()}
        style = RunStyle(id=char_id, attributes=attributes, child_attributes=child_attributes, fonts=fonts)
        if char_id not in mapping:
            mapping[char_id] = (style, child, font_elements)
        try:
            normalized = str(int(char_id))
        except (TypeError, ValueError):
            normalized = None
        if normalized and normalized not in mapping:
            mapping[normalized] = (style, child, font_elements)
    return mapping


def _char_property_signature(definition: ET.Element) -> tuple[Any, ...]:
    """What a shape was read from: its attributes and each child's name, attributes and whether
    it is empty (only an empty child's attributes are read)."""

    return (tuple(definition.attrib.items()),
            tuple((child.tag, tuple(child.attrib.items()), len(child), (child.text or "").strip())
                  for child in definition))


#: One kept shape: the style read, the ``hh:charPr`` it was read from, that element's
#: ``hh:charProperties`` box and its signature when read, and the ``hh:font`` elements its faces
#: were read from with their signature.
_CharEntry = tuple[RunStyle, ET.Element, "ET.Element | None", tuple[Any, ...], dict[str, ET.Element], tuple[Any, ...]]


class CharPropertyCache:
    """The character shapes (``hh:charPr``) of a document's headers as :class:`RunStyle`, read
    from the XML as it is now.

    The parsed shapes are kept between reads, but every read checks what it answers against the
    header first, so an edit through ``.element`` is seen with no cache to invalidate by hand:

    * the ``hh:charProperties`` boxes are the same elements (else every shape is read again);
    * the shape answered is still in its box and has the attributes and children (with their
      attributes) it was read with, and each ``hh:font`` its faces were read from is still in its
      ``hh:fontface`` block with the same id and face (else every shape is read again);
    * an id with no kept shape is looked for among the box's children, so a shape added, or
      given that id in place, is found;
    * with more than one header holding shapes, every kept shape is checked (a later header's
      shape wins, and an in-place edit there may hide an earlier one);
    * going over all of them (``len``, iteration, ``items()``) also counts each box's children
      and checks every kept shape, as the answer covers them all.

    So one lookup (``char_property(id)``, ``char_properties[id]``) costs one shape's check however
    many shapes the header has, and a lookup that finds nothing reads every id once. The one thing
    a lookup does not see is a second shape (or font) given an id that another already has (a
    header with two shapes or two fonts of one language under one id, which Hangul does not write):
    it keeps answering from the one it found until that one changes.
    """

    def __init__(self) -> None:
        self._valid = False
        # The ``hh:charProperties`` elements the shapes were read from. Holding them keeps lxml's
        # proxies alive, so the next lookup finds the very same objects and an ``is`` check is
        # meaningful; without it a proxy freed between reads could come back as another object
        # and every read parsed every shape again (a big table's page estimate looks a shape
        # up per cell: quadratic).
        self._boxes: list[Any] = []
        self._counts: list[int] = []
        self._entries: dict[str, _CharEntry] = {}

    def clear(self) -> None:
        self._valid = False
        self._boxes = []
        self._counts = []
        self._entries = {}

    def _fresh(self, headers: Sequence[Any], *, counted: bool = False) -> dict[str, _CharEntry]:
        boxes = [_char_property_box(header.element) for header in headers]
        same = self._valid and len(boxes) == len(self._boxes) and all(
            box is kept for box, kept in zip(boxes, self._boxes))
        if same and counted:
            same = self._counts == [-1 if box is None else len(box) for box in boxes]
        if not same:
            entries: dict[str, _CharEntry] = {}
            for header, box in zip(headers, boxes):  # a later header's shape wins, as it always did
                for key, (style, definition, fonts) in _char_property_entries(header.element).items():
                    entries[key] = (style, definition, box, _char_property_signature(definition), fonts,
                                    _font_signature(fonts))
            self._boxes, self._entries, self._valid = boxes, entries, True
            self._counts = [-1 if box is None else len(box) for box in boxes]
        return self._entries

    @staticmethod
    def _unchanged(entry: _CharEntry) -> bool:
        _style, definition, box, signature, fonts, font_signature = entry
        if isinstance(definition, LET._Element):
            in_box = cast(Any, definition).getparent() is box
        else:  # a plain ElementTree header has no parent links
            in_box = box is not None and any(child is definition for child in box)
        return in_box and _char_property_signature(definition) == signature and _font_signature(fonts) == font_signature

    def verified(self, headers: Sequence[Any]) -> dict[str, _CharEntry]:
        """Every kept shape, each checked against the header (read again when one changed)."""

        entries = self._fresh(headers, counted=True)
        if not all(self._unchanged(entry) for entry in entries.values()):
            self._valid = False
            entries = self._fresh(headers, counted=True)
        return entries

    def _defined(self, keys: Sequence[str]) -> bool:
        """Whether a box holds an ``hh:charPr`` found under one of *keys* (looked for by id)."""

        wanted = set(keys)
        return any(
            not wanted.isdisjoint(_definition_id_keys(child.get("id")))
            for box in self._boxes if box is not None
            for child in box.iterchildren(f"{_HH}charPr")
        )

    def lookup(self, headers: Sequence[Any], keys: Sequence[str]) -> RunStyle | None:
        """The shape the first of *keys* that has one names, read from the headers as they are now."""

        entries = self._fresh(headers)
        if sum(box is not None for box in self._boxes) > 1:
            entries = self.verified(headers)
        for key in keys:
            entry = entries.get(key)
            if entry is None:
                continue
            if not self._unchanged(entry):
                self._valid = False  # a shape changed in place: read them all again
                return self.lookup(headers, keys)
            return entry[0]
        if keys and self._defined(keys):  # an id given in place to a shape: read them all again
            self._valid = False
            entries = self._fresh(headers)
            return next((entries[key][0] for key in keys if key in entries), None)
        return None

    def styles(self, headers: Sequence[Any]) -> "CharPropertyView":
        return CharPropertyView(self, headers)

    def get(self, headers: Sequence[Any], key: str) -> RunStyle | None:
        try:
            normalized = str(int(key))
        except (TypeError, ValueError):
            return self.lookup(headers, (key,))
        return self.lookup(headers, (key,) if normalized == key else (key, normalized))


def detached_style(style: RunStyle) -> RunStyle:
    """A copy of the cached *style* to hand out: changing its dictionaries changes nothing the cache or the
    document answers afterwards (it is a reading of the header, not the header)."""

    return RunStyle(
        id=style.id,
        attributes=dict(style.attributes),
        child_attributes={name: dict(values) for name, values in style.child_attributes.items()},
        fonts=dict(style.fonts),
    )


class CharPropertyView(Mapping[str, RunStyle]):
    """A document's character shapes by id (as written and as a plain number), read from its
    headers as they are at each access: ``doc.styles.char_properties``.

    A read-only view, not a copy: what it answers follows the header, an edit through
    ``.element`` included (see :class:`CharPropertyCache` for how each read checks it). Looking
    one id up costs the same however many shapes the header has; ``len``, iteration and
    ``items()`` check every shape. ``dict(view)`` takes a copy that stays as it was.
    """

    __slots__ = ("_cache", "_headers")

    def __init__(self, cache: CharPropertyCache, headers: Sequence[Any]) -> None:
        self._cache = cache
        self._headers = headers

    def __getitem__(self, key: str) -> RunStyle:
        style = self._cache.lookup(self._headers, (key,)) if isinstance(key, str) and key else None
        if style is None:
            from ..errors import HwpxLookupError  # a KeyError, so get() and ``in`` answer as for a dict

            raise HwpxLookupError(
                f"no character shape (hh:charPr) has the id {key!r}",
                code="style-char-pr-missing",
                context={"requested": repr(key)},
                suggestion="Read the id from a run (run.char_pr_id_ref) or use doc.styles.char_property(id), which answers None.",
            )
        return detached_style(style)

    def __iter__(self) -> Iterator[str]:
        return iter(list(self._cache.verified(self._headers)))

    def __len__(self) -> int:
        return len(self._cache.verified(self._headers))

    def __repr__(self) -> str:
        return f"CharPropertyView({dict(self)!r})"


class _ReplaceSegment:
    __slots__ = ("element", "attr", "text")

    def __init__(self, element: ET.Element, attr: str, text: str) -> None:
        self.element = element
        self.attr = attr
        self.text = text

    def set(self, value: str) -> None:
        self.text = value
        if value:
            setattr(self.element, self.attr, value)
        else:
            setattr(self.element, self.attr, "")


def _replace_segment_boundaries(segments: Sequence[_ReplaceSegment]) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    offset = 0
    for segment in segments:
        start = offset
        offset += len(segment.text)
        bounds.append((start, offset))
    return bounds


def _distribute_replacement(total: int, weights: Sequence[int]) -> list[int]:
    if not weights:
        return []
    if total <= 0:
        return [0 for _ in weights]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        # Evenly spread characters when no weight information is
        # available (e.g. replacement inside empty segments).
        base = total // len(weights)
        remainder = total - base * len(weights)
        allocation = [base] * len(weights)
        for index in range(remainder):
            allocation[index] += 1
        return allocation

    allocation = []
    remainder = total
    residuals: list[tuple[int, int]] = []
    for index, weight in enumerate(weights):
        share = total * weight // weight_sum
        allocation.append(share)
        remainder -= share
        residuals.append((total * weight % weight_sum, index))

    # Distribute leftover characters based on the size of the modulus so
    # that larger weights receive the extra characters first.
    residuals.sort(key=lambda item: (-item[0], item[1]))
    idx = 0
    while remainder > 0 and residuals:
        _, target = residuals[idx]
        allocation[target] += 1
        remainder -= 1
        idx = (idx + 1) % len(residuals)

    if remainder > 0:
        allocation[-1] += remainder
    return allocation


def _apply_run_replacement(
    segments: list[_ReplaceSegment],
    start: int,
    end: int,
    replacement_text: str,
) -> None:
    bounds = _replace_segment_boundaries(segments)
    affected: list[tuple[int, int, int]] = []
    for index, (seg_start, seg_end) in enumerate(bounds):
        if start >= seg_end or end <= seg_start:
            continue
        local_start = max(0, start - seg_start)
        local_end = min(len(segments[index].text), end - seg_start)
        affected.append((index, local_start, local_end))

    if not affected:
        return

    weights = [local_end - local_start for _, local_start, local_end in affected]
    allocation = _distribute_replacement(len(replacement_text), weights)

    replacement_offset = 0
    first_index = affected[0][0]
    last_index = affected[-1][0]

    for (segment_index, local_start, local_end), share in zip(affected, allocation):
        segment = segments[segment_index]
        prefix = segment.text[:local_start] if segment_index == first_index else ""
        suffix = segment.text[local_end:] if segment_index == last_index else ""
        portion = replacement_text[replacement_offset : replacement_offset + share]
        replacement_offset += share
        segment.set(prefix + portion + suffix)


def _replace_all_occurrences(
    segments: list[_ReplaceSegment], search: str, replacement: str, count: int | None
) -> int:
    total_replacements = 0
    remaining = count
    search_start = 0
    combined = "".join(segment.text for segment in segments)

    while True:
        if remaining is not None and remaining <= 0:
            break
        position = combined.find(search, search_start)
        if position == -1:
            break
        end_position = position + len(search)
        _apply_run_replacement(segments, position, end_position, replacement)
        total_replacements += 1
        if remaining is not None:
            remaining -= 1
        combined = "".join(segment.text for segment in segments)
        if replacement:
            search_start = position + len(replacement)
        else:
            search_start = position
        if search_start > len(combined):
            search_start = len(combined)

    return total_replacements


#: Character elements inside ``hp:t``: a tab, a line break, a soft hyphen, a non-breaking or
#: fixed-width space. Hancom's search reads each as a character, so text is not joined across one.
_TEXT_CHARACTER_ELEMENTS = frozenset({"tab", "lineBreak", "hyphen", "nbSpace", "fwSpace"})


def _text_stretches(runs: Sequence[ET.Element]) -> list[list[_ReplaceSegment]]:
    """Split the text of consecutive runs into the stretches one match may cover."""

    return [segments for _start, segments in text_stretch_spans(runs)]


def text_stretch_spans(runs: Sequence[ET.Element]) -> list[tuple[int, list[_ReplaceSegment]]]:
    """The stretches of :func:`_text_stretches`, each with where it starts in the runs' text.

    The position counts as ``paragraph.text`` does when *runs* are all of a paragraph's runs: a
    character element inside ``hp:t`` (tab, line break, special space) and a run-level tab are
    one character each, other run children (controls, objects) none. A stretch never holds those
    characters, so a match inside it is text a search can cover as one word.
    """

    walk = _StretchWalk()
    for run in runs:
        for child in run:
            walk.run_child(child)
    walk.cut()
    return walk.stretches


class _StretchWalk:
    """The walk behind :func:`text_stretch_spans`: segments, stretches and the position in the text."""

    def __init__(self) -> None:
        self.stretches: list[tuple[int, list[_ReplaceSegment]]] = []
        self.current: list[_ReplaceSegment] = []
        self.start = 0
        self.position = 0

    def cut(self) -> None:
        if self.current:
            self.stretches.append((self.start, self.current))
            self.current = []

    def add(self, element: ET.Element, attr: str, text: str) -> None:
        if not self.current:
            self.start = self.position
        self.current.append(_ReplaceSegment(element, attr, text))
        self.position += len(text)

    def run_child(self, child: ET.Element) -> None:
        name = _element_local_name(child)
        if name == "t":
            self.visit(child, top=True)
            return
        self.cut()
        if name == "tab" or _is_tab_control_element(child):
            self.position += 1  # paragraph.text reads a run-level tab as one character

    def visit(self, element: ET.Element, *, top: bool) -> None:
        self.add(element, "text", element.text or "")
        for child in list(element):
            # a comment or processing instruction is no text: the text around it still joins
            if isinstance(child.tag, str):
                self.text_child(child, top=top)
            self.add(child, "tail", child.tail or "")

    def text_child(self, child: ET.Element, *, top: bool) -> None:
        if _element_local_name(child) in _TEXT_CHARACTER_ELEMENTS:
            self.cut()
            if top:
                self.position += 1  # paragraph.text reads it as one character
        else:
            self.visit(child, top=False)


def regex_matches(pattern: "re.Pattern[str]", text: str) -> list["re.Match[str]"]:
    """The non-empty, non-overlapping matches of *pattern* in *text*, left to right.

    An empty match (``^``, ``\\b``, ``x*`` where there is no ``x``) is no match: a search reports
    and a replacement changes characters, never the space between two.
    """

    return [match for match in pattern.finditer(text) if match.end() > match.start()]


def _overlay_replacement(segments: Sequence[_ReplaceSegment], start: int, end: int, replacement: str) -> None:
    """Replace ``[start, end)`` of the joined *segments* character by character, as Hancom does.

    The i-th replacement character takes the place of the i-th matched character, so it keeps
    that character's run. Replacement characters beyond the match follow its last character;
    matched characters beyond the replacement are removed.
    """

    affected: list[tuple[_ReplaceSegment, int, int]] = []
    offset = 0
    for segment in segments:
        segment_start, offset = offset, offset + len(segment.text)
        if offset <= start or segment_start >= end:
            continue
        affected.append((segment, max(start - segment_start, 0), min(end - segment_start, len(segment.text))))
    used = 0
    for index, (segment, local_start, local_end) in enumerate(affected):
        last = index == len(affected) - 1
        portion = replacement[used:] if last else replacement[used : used + local_end - local_start]
        used += len(portion)
        segment.set(segment.text[:local_start] + portion + segment.text[local_end:])


def replace_across_runs(
    paragraph: "HwpxOxmlParagraph",
    runs: Sequence[ET.Element],
    search: "str | re.Pattern[str]",
    replacement: str,
    *,
    count: int | None = None,
) -> int:
    """Replace non-empty *search* in consecutive *runs* of *paragraph* as Hancom's find and replace does.

    A match may start in one run and end in a later one. Each replacement character takes the
    place, and so the run, of the matched character at the same position; extra replacement
    characters follow the last matched one, and matched characters left over are removed (a
    run may be left empty). Text is joined across run boundaries and markup such as
    highlights, but not across a tab, a line break or another character element, nor across a
    control or an object. Returns the number of replacements.

    A compiled regular expression *search* replaces each of its non-empty matches with
    *replacement* expanded as :meth:`re.Match.expand` does (``\\1``, ``\\g<name>``); its ``^`` and
    ``$`` are the ends of the stretch of text a match may cover.
    """

    total = 0
    for segments in _text_stretches(runs):
        if count is not None and total >= count:
            break
        if isinstance(search, re.Pattern):
            matches = regex_matches(search, "".join(segment.text for segment in segments))
            if count is not None:
                matches = matches[: count - total]
            for match in reversed(matches):  # from the right, so the earlier positions stay put
                _overlay_replacement(segments, match.start(), match.end(), match.expand(replacement))
            total += len(matches)
            continue
        combined = "".join(segment.text for segment in segments)
        position = combined.find(search)
        while position != -1 and (count is None or total < count):
            _overlay_replacement(segments, position, position + len(search), replacement)
            total += 1
            combined = "".join(segment.text for segment in segments)
            position = combined.find(search, position + len(replacement))
    if total:
        for run in runs:
            text_marks_as_elements_in(run)  # a tab or line break in the replacement, as Hancom writes it
        _clear_paragraph_layout_cache(paragraph.element)
        paragraph.section.mark_dirty()
    return total


def _is_run_tab(node: ET.Element) -> bool:
    """A tab written as a child of the run (``hp:tab`` or a tab ``hp:ctrl``), which ``paragraph.text`` counts."""

    return node.tag == f"{_HP}tab" or _is_tab_control_element(node)


class HwpxOxmlRun(SameElement):
    """Lightweight wrapper around an ``<hp:run>`` element."""

    if TYPE_CHECKING:
        paragraph: "HwpxOxmlParagraph"
    else:
        paragraph = live_paragraph  # the paragraph holding it now, also after a move

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    def to_model(self) -> "body.Run":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_run_element(node)

    @property
    def model(self) -> "body.Run":
        return self.to_model()

    def apply_model(self, model: "body.Run") -> None:
        new_node = body.serialize_run(model)
        xml_bytes = LET.tostring(new_node)
        parent = self.paragraph.element
        if isinstance(parent, LET._Element):
            replacement = LET.fromstring(xml_bytes)
        else:
            replacement = ET.fromstring(xml_bytes)
        text_marks_as_elements_in(replacement)  # "\n" set on a model span, as hp:lineBreak
        run_children = list(parent)
        index = run_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        # Replacing the run rewrites its text/markup, so the cached line layout
        # of the containing paragraph no longer holds. Tracked-change marks also
        # make the paragraph unjudgeable for the save-time stale sweep, so this
        # is the only point that can invalidate it.
        _clear_paragraph_layout_cache(parent)
        self.paragraph.section.mark_dirty()

    def _current_format_flags(self) -> tuple[bool, bool, bool] | None:
        style = self.style
        if style is None:
            return None
        bold = "bold" in style.child_attributes
        italic = "italic" in style.child_attributes
        underline_attrs = style.child_attributes.get("underline")
        underline = False
        if underline_attrs is not None:
            underline = underline_attrs.get("type", "").upper() != "NONE"
        return bold, italic, underline

    def _apply_format_change(
        self,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
    ) -> None:
        document = self.paragraph.section.document
        if document is None:
            raise RuntimeError("run is not attached to a document")

        current = self._current_format_flags()
        if current is None:
            current = (False, False, False)

        target = [
            current[0] if bold is None else bool(bold),
            current[1] if italic is None else bool(italic),
            current[2] if underline is None else bool(underline),
        ]

        if tuple(target) == current:
            return

        style_id = document.ensure_run_style(
            bold=target[0],
            italic=target[1],
            underline=target[2],
            base_char_pr_id=self.char_pr_id_ref,
        )
        self.char_pr_id_ref = style_id

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the character property reference applied to the run."""
        return self.element.get("charPrIDRef")

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "charPrIDRef" in self.element.attrib:
                del self.element.attrib["charPrIDRef"]
                _clear_paragraph_layout_cache(self.paragraph.element)
                self.paragraph.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("charPrIDRef") != new_value:
            self.element.set("charPrIDRef", new_value)
            # A style swap changes glyph metrics, so the cached line layout of
            # the containing paragraph no longer holds.
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()

    def _plain_text_nodes(self) -> list[ET.Element]:
        return [
            node
            for node in self.element.findall(f"{_HP}t")
            if len(list(node)) == 0
        ]

    def _ensure_plain_text_node(self) -> ET.Element:
        nodes = self._plain_text_nodes()
        if nodes:
            return nodes[0]
        t = self.element.makeelement(f"{_HP}t", {})
        self.element.append(t)
        return t

    @property
    def text(self) -> str:
        """The run's characters, counted as ``paragraph.text`` counts them: its ``hp:t`` texts (the tabs,
        line breaks and special spaces in them included) and a tab written as a child of the run
        (``hp:tab``, or a tab ``hp:ctrl``, as some writers other than Hancom put one), in the order the
        file has them. So the runs' texts of a paragraph, joined, are its text."""

        parts: list[str] = []
        for node in self.element:
            if node.tag == f"{_HP}t":
                parts.append(_text_element_content(node))
            elif _is_run_tab(node):
                parts.append("	")
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        # The value replaces the run's whole text in place: the first hp:t
        # (which may sit between field controls) takes it, tabs as hp:tab
        # elements, and every hp:t loses its old text together with the line
        # breaks, tabs and spaces inside it and the text after them.
        _require_text(value)  # before the old text goes
        changed = self.text != value
        nodes = self.element.findall(f"{_HP}t")
        primary = nodes[0] if nodes else self._ensure_plain_text_node()
        set_text_with_tabs(primary, value)
        for node in nodes[1:]:
            clear_text_element(node)
        for node in [child for child in self.element if _is_run_tab(child)]:  # its tabs are in the value now
            self.element.remove(node)
        if changed:
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()

    @property
    def style(self) -> RunStyle | None:
        document = self.paragraph.section.document
        if document is None:
            return None
        char_pr_id = self.char_pr_id_ref
        if char_pr_id is None:
            return None
        return document.char_property(char_pr_id)

    def replace_text(
        self,
        search: str,
        replacement: str,
        *,
        count: int | None = None,
    ) -> int:
        """Replace ``search`` with ``replacement`` within ``<hp:t>`` nodes.

        The replacement traverses nested markup tags (e.g. highlights) and
        preserves the existing element structure so formatting metadata remains
        intact. Text on the two sides of a tab, a line break or another
        character element, or of a control, is not joined -- Hancom reads each
        as a character of its own. Returns the number of replacements.
        """

        if not search:
            raise ValueError("search text must be a non-empty string")

        if count is not None and count <= 0:
            return 0

        total_replacements = 0
        for segments in _text_stretches([self.element]):
            remaining = None if count is None else count - total_replacements
            if remaining is not None and remaining <= 0:
                break
            total_replacements += _replace_all_occurrences(segments, search, replacement, remaining)

        if total_replacements:
            # A tab or line break in the replacement goes in as hp:tab / hp:lineBreak,
            # as the text setters write it, not as a character inside hp:t.
            for node in self.element.findall(f"{_HP}t"):
                text_marks_as_elements(node)
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()
        return total_replacements

    @property
    def content_kinds(self) -> frozenset[str]:
        """What this run holds, judged from its direct children.

        The answer uses the closed vocabulary :data:`RUN_CONTENT_KINDS`:
        ``"text"`` for an ``hp:t`` holding characters or a glyph atom (tab,
        line break, hyphen, non-breaking or fixed-width space), and for
        ``hp:compose``/``hp:dutmal``; ``"table"``; ``"picture"``; ``"shape"``
        (drawing objects, containers and text art); ``"equation"``; ``"ole"``;
        ``"chart"``; ``"video"``; ``"form"`` (buttons, combo/list boxes, edits,
        scroll bars); ``"control"`` (``hp:ctrl``); ``"section_properties"``
        (``hp:secPr``); and ``"other"`` for any other element child. An empty
        ``hp:t`` contributes nothing. What sits inside a child (a header's text
        inside an ``hp:ctrl``, a cell's text inside a table) is not looked at.
        """

        kinds: set[str] = set()
        for child in self.element:
            name = _element_local_name(child)
            if not name:
                continue
            if name == "t":
                if _text_element_holds_text(child):
                    kinds.add("text")
                continue
            kinds.add(_RUN_CHILD_KINDS.get(name, "other"))
        return frozenset(kinds)

    @property
    def has_text_element(self) -> bool:
        """Whether the run has an ``hp:t``, an empty one too (``run.content`` gives no piece for an empty
        ``hp:t``: it holds nothing). Hancom writes an empty ``<hp:t/>`` in a run that holds no text but a
        paragraph's end or an object (6,548 of them in ``tests/fixtures/hancom_saved``)."""

        return any(_local_name(child) == "t" for child in self.element)

    @property
    def is_plain_text(self) -> bool:
        """Whether the run holds text and nothing else: one or more ``hp:t`` and no control, object, mark,
        덧말 or 글자 겹치기 -- in its ``hp:t`` only characters, tabs, line breaks, no-break and fixed-width
        spaces and hyphens (an empty ``hp:t`` counts as text)."""

        children = [child for child in self.element if _local_name(child)]
        return bool(children) and all(
            _local_name(child) == "t" and all(_local_name(inner) in _TEXT_INLINE_ATOMS for inner in child
                                              if _local_name(inner))
            for child in children
        )

    @property
    def content(self) -> "tuple[InlineItem, ...]":
        """Everything this run holds, piece by piece, in the order the file writes it.

        Each piece is an :class:`hwpx.objects.InlineItem`: the characters of an ``hp:t`` and
        the glyphs between them (tab, line break, 묶음 빈칸, 고정폭 빈칸, hyphen), the marks
        written there (형광펜, 차례 표시, 변경 추적), each control of an ``hp:ctrl`` (field
        begin and end, note, bookmark, auto number, ...) and each object, 덧말 or 글자 겹치기
        of the run. Nothing is interpreted or dropped: an element this reading does not know
        comes as ``kind="unknown"`` with its ``name``. The ``text`` of the pieces written in
        ``hp:t`` and of a tab written in the run, joined, is :attr:`text`. The document's tree is read where it is; nothing is
        copied or parsed again, and the document is not changed.
        """

        return run_content(self)

    def remove(self) -> None:
        """Remove this run from its paragraph.

        The run that starts a section also holds the section's settings (``hp:secPr``: paper,
        margins; and its columns, header, footer and page numbering). Those stay: the rest of the
        run goes and the run is left holding them. A run holding nothing else is refused with
        :class:`~hwpx.errors.HwpxValueError` (``code="paragraph-run-section-settings"``).
        """

        from ..errors import HwpxValueError
        from .note_authoring import note_kinds_in_document, renumber_note_kinds

        parent = self.paragraph.element
        if not any(child is self.element for child in parent):
            return
        section = self.paragraph.section
        note_kinds = note_kinds_in_document(section, self.element)
        settings = dict(section_setting_runs(parent)).get(self.element, [])
        if settings:
            if len(settings) == len(self.element):
                raise HwpxValueError(
                    "이 run은 구역 설정(용지·여백·단·머리말·꼬리말·쪽 번호)만 담고 있어 지울 수 없습니다.",
                    code="paragraph-run-section-settings",
                    suggestion="글을 지우려면 그 글을 담은 run을 지우거나 paragraph.text 를 바꾸세요.",
                )
            for child in list(self.element):
                if not any(child is kept for kept in settings):
                    self.element.remove(child)
        else:
            parent.remove(self.element)
        _clear_paragraph_layout_cache(parent)  # the cache's line starts would point past what is left
        section.mark_dirty()
        renumber_note_kinds(section, note_kinds)  # the notes after the ones (or the restart) it held

    @property
    def bold(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[0]

    @bold.setter
    def bold(self, value: bool | None) -> None:
        self._apply_format_change(bold=value)

    @property
    def italic(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[1]

    @italic.setter
    def italic(self, value: bool | None) -> None:
        self._apply_format_change(italic=value)

    @property
    def underline(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[2]

    @underline.setter
    def underline(self, value: bool | None) -> None:
        self._apply_format_change(underline=value)

    # -- Character formats read and written on this run alone ----------------
    #
    # Reads come from the run's own ``hh:charPr``; ``None`` when the run has none.
    # A write gives the run a derived character shape (the old one copied and
    # changed, or an existing one with that content): other runs that shared the
    # old shape keep it, and writing a value the run has changes nothing.

    def _char_value(self, name: str) -> Any:
        from .formatting import char_value

        return char_value(self, name)

    def set_format(self, **changes: Any) -> None:
        """Change several character formats of this run at once (one derived shape).

        Takes ``size`` (pt), ``font`` (a face for every language), ``font_by_lang``
        (language -> face, as ``doc.styles.ensure_run``), ``color``, ``highlight``
        (``"none"`` takes it off), ``bold``, ``italic``, ``underline``, ``strike``,
        ``superscript``, ``subscript``, ``letter_spacing`` (자간 %, -50..100) and
        ``ratio`` (장평 %, 50..200). Left out or ``None`` means unchanged. An unknown
        name or a value out of range is refused before anything changes.
        """

        from .formatting import set_run_format

        set_run_format(self, changes)

    @property
    def size(self) -> float | None:
        """The character size in points (``10.0`` for Hancom's default)."""
        return self._char_value("size")

    @size.setter
    def size(self, value: float) -> None:
        self.set_format(size=value)

    @property
    def font(self) -> str | None:
        """The face of the run's Hangul text. Setting it sets the face of every
        language (Hangul, Latin, Hanja, ...), as Hancom's representative font does;
        :meth:`set_font` names the languages."""

        from .formatting import run_font

        return run_font(self)

    @font.setter
    def font(self, value: str) -> None:
        self.set_format(font=value)

    @property
    def fonts(self) -> "LanguageFonts":
        """The face of the run's text in each language block, as a value: ``run.fonts.latin``.

        Hancom keeps one face per language (Hangul, Latin, Hanja, Japanese, other, symbol and
        user) in the run's character shape; :attr:`font` is the Hangul one. A language with no
        face (or a run with no character shape) reads ``None``. :meth:`set_font` changes them.
        """

        from .formatting import run_fonts

        return run_fonts(self)

    def set_font(self, face: str, *, lang: "str | Sequence[str] | None" = None) -> None:
        """Use *face* for the languages *lang* (``"HANGUL"``, ``"LATIN"``, ... or several;
        ``None`` for all seven). A face a language does not declare is declared there."""

        if lang is None:
            self.set_format(font=face)
            return
        langs = [lang] if isinstance(lang, str) else list(lang)
        self.set_format(font_by_lang={name: face for name in langs})

    @property
    def color(self) -> str | None:
        """The text colour as stored (``"#000000"``)."""
        return self._char_value("color")

    @color.setter
    def color(self, value: str) -> None:
        self.set_format(color=value)

    @property
    def highlight(self) -> str | None:
        """The shade colour behind the text (``shadeColor``), ``None`` without one.
        Setting ``None`` takes it off. (A marker-pen highlight, ``add_highlight``, is
        a mark in the text, not this.)"""
        return self._char_value("highlight")

    @highlight.setter
    def highlight(self, value: str | None) -> None:
        self.set_format(highlight="none" if value is None else value)

    @property
    def strike(self) -> bool | None:
        """Whether the run is struck through."""
        return self._char_value("strike")

    @strike.setter
    def strike(self, value: bool) -> None:
        self.set_format(strike=value)

    @property
    def superscript(self) -> bool | None:
        """Whether the run is superscript (``hh:supscript``). Setting it ``True`` drops subscript."""
        return self._char_value("superscript")

    @superscript.setter
    def superscript(self, value: bool) -> None:
        self.set_format(superscript=value)

    @property
    def subscript(self) -> bool | None:
        """Whether the run is subscript (``hh:subscript``). Setting it ``True`` drops superscript."""
        return self._char_value("subscript")

    @subscript.setter
    def subscript(self, value: bool) -> None:
        self.set_format(subscript=value)

    @property
    def letter_spacing(self) -> int | None:
        """자간: the spacing between characters in percent of the size (Hangul's; a write sets every language's)."""
        return self._char_value("letter_spacing")

    @letter_spacing.setter
    def letter_spacing(self, value: int) -> None:
        self.set_format(letter_spacing=value)

    @property
    def ratio(self) -> int | None:
        """장평: the width of the characters in percent (Hangul's; a write sets every language's)."""
        return self._char_value("ratio")

    @ratio.setter
    def ratio(self, value: int) -> None:
        self.set_format(ratio=value)


__all__ = ["RUN_CONTENT_KINDS", "HwpxOxmlRun", "RunStyle", "replace_across_runs", "text_element_content"]
