# SPDX-License-Identifier: Apache-2.0
"""Character and paragraph formats read and changed on one run or one paragraph.

A run or a paragraph does not hold its format: it points at a definition in the
header (``hh:charPr`` by ``charPrIDRef``, ``hh:paraPr`` by ``paraPrIDRef``) that
other runs and paragraphs may share. Changing the format of one run therefore
means *deriving* a definition: copy the one the run points at, change the copy,
reuse an existing definition with the same content if there is one (so writing
the same value twice does not grow the header), else add the copy under the next
free id and keep the list's ``itemCnt`` right -- and point only this run at it.
:func:`derive_definition` does that for the four definition lists a format edit
touches (``charPr``, ``paraPr``, ``tabPr``, ``borderFill``); the run and paragraph
properties of :class:`~hwpx.oxml.run.HwpxOxmlRun` and
:class:`~hwpx.oxml.paragraph.HwpxOxmlParagraph` and the widened ``doc.styles``
verbs are built on it.

Character positions (``paragraph.split_run`` / ``paragraph.format_range``) count
the characters of ``paragraph.text``: each character of an ``hp:t``; a tab, a line
break, a no-break, full-width or soft-hyphen space inside an ``hp:t`` as one
character each; a run-level ``hp:tab`` (or a tab control) as one character; and
every other run child -- a control (field begin/end, bookmark, footnote, column
settings), a table, a picture, the section settings -- as no character. A cut at a
position keeps the zero-width children before it on the left.

Lives outside ``paragraph.py``/``run.py``/``header_part.py`` so those owner files
keep their headroom; they reach it lazily, so ``import hwpx`` does not load it.
"""

from __future__ import annotations

import difflib
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Sequence, cast
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from ..errors import HwpxLookupError, HwpxStateError, HwpxTypeError, HwpxValueError
from ..objects.results import (
    Alignment,
    LineSpacing,
    LineSpacingType,
    NumberingInfo,
    NumberingLevel,
)
from ._document_primitives import (
    _FONT_FACE_LANG_TO_REF,
    _HC,
    _HH,
    _HP,
    _clear_paragraph_layout_cache,
    _element_local_name,
    _is_tab_control_element,
    _text_element_content,
)
from .color import normalize_color
from .paragraph_heading import heading_outline_level, set_paragraph_heading

if TYPE_CHECKING:
    from ..objects.results import LanguageFonts
    from .document_parts import HwpxOxmlDocument
    from .header import Style
    from .header_part import HwpxOxmlHeader
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun

__all__ = [
    "CHAR_FORMAT_NAMES",
    "derive_definition",
    "find_definition",
    "format_range",
    "remove_style",
    "resolve_style",
    "set_run_format",
    "split_run",
]

#: The definition lists a derivation writes into, by the definition's local name.
_LISTS = {
    "charPr": "charProperties",
    "paraPr": "paraProperties",
    "tabPr": "tabProperties",
    "borderFill": "borderFills",
}

_HWPUNIT_PER_MM = 7200 / 25.4


# --------------------------------------------------------------------------
# Deriving a definition


def _container(header: "HwpxOxmlHeader", kind: str, *, create: bool = False) -> ET.Element | None:
    return header._ref_list_default_child(_LISTS[kind], create=create)


def _same_id(raw: str | None, wanted: str) -> bool:
    if raw is None:
        return False
    if raw == wanted:
        return True
    try:
        return int(raw) == int(wanted)
    except ValueError:
        return False


def find_definition(header: "HwpxOxmlHeader | None", kind: str, id_ref: "int | str | None") -> ET.Element | None:
    """The ``hh:<kind>`` whose id is *id_ref* (``"01"`` finds ``id="1"``), or ``None``."""

    if header is None or id_ref is None:
        return None
    container = _container(header, kind)
    if container is None:
        return None
    wanted = str(id_ref).strip()
    # the first with the id as written, through the header's checked index (one lookup does not
    # walk the whole list: a paragraph's shape is looked up per paragraph)
    exact = header._definition_element(container, kind, wanted, exact=True)
    if exact is not None:
        return exact
    return next(
        (child for child in container if _element_local_name(child) == kind and _same_id(child.get("id"), wanted)),
        None,
    )


def _signature(element: ET.Element, *, root: bool = True) -> tuple[object, ...]:
    """What a definition says: each element by namespace and name (not by prefix: a child made
    on a detached copy prints as ``ns0:`` until it joins the header), its attributes (the
    definition's own ``id`` left out), its text without surrounding white space, and its
    children in order. Two definitions with one signature are the same definition."""

    attributes = tuple(sorted((key, value) for key, value in element.attrib.items() if not (root and key == "id")))
    children = tuple(_signature(child, root=False) for child in element)
    return str(element.tag), attributes, (element.text or "").strip(), children


def _attributes_without_id(element: ET.Element) -> dict[str, str]:
    return {key: value for key, value in element.attrib.items() if key != "id"}


def _next_id(container: ET.Element, kind: str) -> str:
    numbers = []
    for child in container:
        if _element_local_name(child) == kind:
            try:
                numbers.append(int(child.get("id") or ""))
            except ValueError:
                continue
    if numbers:
        return str(max(numbers) + 1)
    return "1" if kind == "borderFill" else "0"  # Hancom numbers border fills from 1, the rest from 0


def derive_definition(
    header: "HwpxOxmlHeader",
    kind: str,
    base_id: "int | str | None",
    modify: Callable[[ET.Element], None],
) -> str:
    """Return the id of a ``hh:<kind>`` that is definition *base_id* changed by *modify*.

    *kind* is ``charPr``, ``paraPr``, ``tabPr`` or ``borderFill``. *modify* gets a copy
    of the base (without its id) and changes it in place. When the result says what
    the base says, the base's id comes back; when another definition says the same,
    that one's id; else the copy is added under the next free id and the list's
    ``itemCnt`` is set to its length. The base and every other definition are left as
    they were. *base_id* ``None`` builds on the list's first definition; an id the
    list does not have is ``HwpxLookupError(code="style-definition-not-found")``.
    """

    container = _container(header, kind, create=True)
    if container is None:  # pragma: no cover - the header always takes a refList
        raise HwpxStateError(f"failed to create the {_LISTS[kind]} list", code="document-header-missing")
    if base_id is None:
        base = next((child for child in container if _element_local_name(child) == kind), None)
    else:
        base = find_definition(header, kind, base_id)
        if base is None:
            raise HwpxLookupError(
                f"the header has no {kind} with id {base_id!r}",
                code="style-definition-not-found",
                context={"kind": kind, "id": str(base_id)},
                suggestion="Read the id from the run or paragraph (char_pr_id_ref, para_pr_id_ref) or from doc.styles.",
            )
    want = deepcopy(base) if base is not None else container.makeelement(f"{_HH}{kind}", {})
    want.attrib.pop("id", None)
    modify(want)

    attributes, size = _attributes_without_id(want), len(want)
    signature: tuple[object, ...] | None = None
    candidates = ([base] if base is not None else []) + [
        child for child in container if _element_local_name(child) == kind and child is not base
    ]
    for candidate in candidates:
        if len(candidate) != size or _attributes_without_id(candidate) != attributes:
            continue
        signature = signature or _signature(want)
        if _signature(candidate) == signature:
            found = candidate.get("id")
            if found is not None:
                return found

    new_id = _next_id(container, kind)
    kept = list(want.attrib.items())
    want.attrib.clear()
    want.set("id", new_id)  # first, as Hancom writes it
    for key, value in kept:
        want.set(key, value)
    if isinstance(container, LET._Element) and not isinstance(want, LET._Element):
        want = LET.fromstring(ET.tostring(want))
    container.append(want)
    container.set("itemCnt", str(sum(1 for child in container if _element_local_name(child) == kind)))
    header.mark_dirty()
    document = header.document
    if kind == "charPr" and document is not None:
        document.invalidate_char_property_cache()
    return new_id


def _header_of(document: "HwpxOxmlDocument | None") -> "HwpxOxmlHeader":
    headers = [] if document is None else document.headers
    if not headers:
        raise HwpxStateError(
            "the run or paragraph is not in a document with a header",
            code="document-header-missing",
            suggestion="Format runs and paragraphs of a document opened or made with HwpxDocument.",
        )
    return headers[0]


# --------------------------------------------------------------------------
# Character formats


#: The keyword arguments ``run.set_format`` and ``paragraph.format_range`` take.
CHAR_FORMAT_NAMES = (
    "size", "font", "font_by_lang", "color", "highlight", "bold", "italic", "underline",
    "strike", "superscript", "subscript", "letter_spacing", "ratio",
)

#: Child order of ``hh:charPr`` in the OWPML schema, which Hancom writes.
_CHAR_PR_ORDER = (
    "fontRef", "ratio", "spacing", "relSz", "offset", "italic", "bold", "underline",
    "strikeout", "outline", "shadow", "emboss", "engrave", "supscript", "subscript",
)
_LANG_ATTRIBUTES = tuple(_FONT_FACE_LANG_TO_REF.values())


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if _element_local_name(child) == name), None)


def _ensure_child(element: ET.Element, name: str, attributes: Mapping[str, str] | None = None) -> ET.Element:
    found = _child(element, name)
    if found is None:
        found = element.makeelement(f"{_HH}{name}", dict(attributes or {}))
        element.append(found)
    return found


def _set_flag_child(element: ET.Element, name: str, on: bool) -> None:
    found = _child(element, name)
    if on and found is None:
        element.append(element.makeelement(f"{_HH}{name}", {}))
    elif not on and found is not None:
        element.remove(found)


def _order_char_pr(element: ET.Element) -> None:
    rank = {name: index for index, name in enumerate(_CHAR_PR_ORDER)}
    children = list(element)
    ordered = sorted(children, key=lambda child: rank.get(_element_local_name(child), len(rank)))
    if ordered != children:
        for child in children:
            element.remove(child)
        element.extend(ordered)


def _check_bool(name: str, value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise HwpxTypeError(
        f"{name} must be True, False or None; got {value!r}",
        code="style-run-format-invalid",
        context={"name": name, "requested": repr(value)},
        suggestion=f"Pass {name}=True or {name}=False.",
    )


def _check_number(name: str, value: object, low: float, high: float, *, code: str, suggestion: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= float(value) <= high:
        raise HwpxValueError(
            f"{name} must be a number from {low:g} to {high:g}; got {value!r}",
            code=code,
            context={"name": name, "requested": repr(value), "min": low, "max": high},
            suggestion=suggestion,
        )
    return float(value)


def _char_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    """*changes* checked and put in stored form before anything is written."""

    unknown = sorted(set(changes) - set(CHAR_FORMAT_NAMES))
    if unknown:
        raise HwpxTypeError(
            f"unknown character format {unknown!r}",
            code="style-run-format-invalid",
            context={"unknown": unknown, "known": list(CHAR_FORMAT_NAMES)},
            suggestion="Use the names of " + ", ".join(CHAR_FORMAT_NAMES) + ".",
        )
    spec: dict[str, Any] = {}
    for name in ("bold", "italic", "underline", "strike", "superscript", "subscript"):
        flag = _check_bool(name, changes.get(name))
        if flag is not None:
            spec[name] = flag
    if spec.get("superscript") and spec.get("subscript"):
        raise HwpxValueError(
            "a run cannot be superscript and subscript at once",
            code="style-run-format-invalid",
            suggestion="Pass one of superscript=True and subscript=True.",
        )
    size = changes.get("size")
    if size is not None:
        points = _check_number("size", size, 0.01, 21474836.47, code="style-run-size-value",
                               suggestion="Pass the character size in points, e.g. 10.")
        spec["height"] = str(round(points * 100))
    for name, attribute in (("color", "textColor"), ("highlight", "shadeColor")):
        value = changes.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise HwpxTypeError(f"{name} must be a colour string; got {value!r}", code="style-color-invalid",
                                context={"name": name}, suggestion='Pass "#RRGGBB".')
        color = normalize_color(value)
        if color is None or (color == "none" and name == "color"):
            raise HwpxValueError(f"{name} {value!r} is not a colour", code="style-color-invalid",
                                 context={"name": name, "requested": value},
                                 suggestion='Pass "#RRGGBB"' + (' or "none".' if name == "highlight" else "."))
        spec[attribute] = color
    if changes.get("letter_spacing") is not None:
        spec["spacing"] = int(_check_number("letter_spacing", changes["letter_spacing"], -50, 100,
                                            code="style-run-format-invalid",
                                            suggestion="자간은 -50 ~ 100 (%) 입니다."))
    if changes.get("ratio") is not None:
        spec["ratio"] = int(_check_number("ratio", changes["ratio"], 50, 200, code="style-run-format-invalid",
                                          suggestion="장평은 50 ~ 200 (%) 입니다."))
    font, by_lang = changes.get("font"), changes.get("font_by_lang")
    if font is not None:
        if not isinstance(font, str) or not font.strip():
            raise HwpxValueError(f"font must be a font name; got {font!r}", code="style-font-face-empty",
                                 suggestion='Pass a face such as "맑은 고딕".')
        spec["font_by_lang"] = {lang: font.strip() for lang in _FONT_FACE_LANG_TO_REF}
    if by_lang is not None:
        from .header_fonts import _font_by_lang

        spec["font_by_lang"] = {**spec.get("font_by_lang", {}), **_font_by_lang(by_lang)}
    return spec


def _apply_char_changes(element: ET.Element, spec: Mapping[str, Any], font_ids: Mapping[str, str]) -> None:
    for attribute in ("height", "textColor", "shadeColor"):
        if attribute in spec:
            element.set(attribute, spec[attribute])
    if font_ids:
        font_ref = _ensure_child(element, "fontRef", {name: "0" for name in _LANG_ATTRIBUTES})
        for attribute, font_id in font_ids.items():
            font_ref.set(attribute, font_id)
    for name in ("bold", "italic"):
        if name in spec:
            _set_flag_child(element, name, spec[name])
    if "underline" in spec:
        underline = _ensure_child(element, "underline", {"type": "NONE", "shape": "SOLID", "color": "#000000"})
        if spec["underline"]:
            if (underline.get("type") or "NONE").upper() == "NONE":
                underline.set("type", "BOTTOM")
            underline.set("shape", underline.get("shape") or "SOLID")
            underline.set("color", underline.get("color") or "#000000")
        else:
            underline.set("type", "NONE")
    if "strike" in spec:
        strike = _ensure_child(element, "strikeout", {"shape": "NONE", "color": "#000000"})
        if spec["strike"]:
            if (strike.get("shape") or "NONE").upper() == "NONE":
                strike.set("shape", "SOLID")
        else:
            strike.set("shape", "NONE")
        strike.set("color", strike.get("color") or "#000000")
    for name, other in (("superscript", "subscript"), ("subscript", "superscript")):
        if name in spec:
            tag = "supscript" if name == "superscript" else "subscript"
            _set_flag_child(element, tag, spec[name])
            if spec[name]:
                _set_flag_child(element, "supscript" if other == "superscript" else "subscript", False)
    for name in ("spacing", "ratio"):
        if name in spec:
            node = _ensure_child(element, name)
            for attribute in _LANG_ATTRIBUTES:
                node.set(attribute, str(spec[name]))
    _order_char_pr(element)


def _font_ids(header: "HwpxOxmlHeader", spec: Mapping[str, Any]) -> dict[str, str]:
    """The font ids *spec*'s faces have in their languages' blocks, declared where missing as
    ``ensure_run(font=)`` declares them (:func:`~.header_fonts.declare_face`)."""

    from .header_fonts import declare_face

    ids: dict[str, str] = {}
    for lang, face in (spec.get("font_by_lang") or {}).items():
        ids.update(declare_face(header, face, [lang]))
    return ids


def derive_char_pr(header: "HwpxOxmlHeader", base_id: "int | str | None", changes: Mapping[str, Any]) -> str:
    """The id of a ``hh:charPr`` that is *base_id* with the character *changes*
    (the keyword arguments of ``run.set_format``)."""

    spec = _char_changes(changes)
    if not spec:
        raise HwpxValueError(
            "no character format to change",
            code="style-run-format-empty",
            suggestion="Pass at least one of " + ", ".join(CHAR_FORMAT_NAMES) + ".",
        )
    if base_id is not None and find_definition(header, "charPr", base_id) is None:
        raise HwpxLookupError(
            f"the header has no charPr with id {base_id!r}",
            code="style-definition-not-found",
            context={"kind": "charPr", "id": str(base_id)},
        )
    font_ids = _font_ids(header, spec)
    return derive_definition(header, "charPr", base_id, lambda element: _apply_char_changes(element, spec, font_ids))


def set_run_format(run: "HwpxOxmlRun", changes: Mapping[str, Any]) -> None:
    """Give *run* alone the character *changes* (``run.set_format``)."""

    header = _header_of(run.paragraph.section.document)
    run.char_pr_id_ref = derive_char_pr(header, run.char_pr_id_ref, changes)


def run_char_pr(run: "HwpxOxmlRun") -> ET.Element | None:
    """The ``hh:charPr`` *run* points at, or ``None``."""

    document = run.paragraph.section.document
    if document is None or run.char_pr_id_ref is None:
        return None
    for header in document.headers:
        found = find_definition(header, "charPr", run.char_pr_id_ref)
        if found is not None:
            return found
    return None


def char_value(run: "HwpxOxmlRun", name: str) -> Any:
    """One character format of *run* read from its ``hh:charPr`` (``None`` without one)."""

    element = run_char_pr(run)
    if element is None:
        return None
    if name == "size":
        height = element.get("height")
        return None if height is None else int(height) / 100
    if name in ("color", "highlight"):
        value = element.get("textColor" if name == "color" else "shadeColor")
        return None if value is None or (name == "highlight" and value.strip().lower() in ("none", "")) else value
    if name in ("bold", "italic"):
        return _child(element, name) is not None
    if name == "superscript":
        return _child(element, "supscript") is not None
    if name == "subscript":
        return _child(element, "subscript") is not None
    if name == "strike":
        strike = _child(element, "strikeout")
        return strike is not None and (strike.get("shape") or "NONE").upper() not in ("NONE", "")
    if name in ("letter_spacing", "ratio"):
        node = _child(element, "spacing" if name == "letter_spacing" else "ratio")
        value = None if node is None else node.get("hangul")
        return None if value is None else int(value)
    return None  # pragma: no cover - callers name the formats above


def run_font(run: "HwpxOxmlRun", lang: str = "HANGUL") -> str | None:
    from .header_fonts import font_face

    document = run.paragraph.section.document
    if document is None or not document.headers:
        return None
    return font_face(document.headers[0], run.char_pr_id_ref, lang)


def run_fonts(run: "HwpxOxmlRun") -> "LanguageFonts":
    """The face of *run*'s text in each of the seven language blocks (``run.fonts``)."""

    from ..objects.results import LanguageFonts

    return LanguageFonts(**{lang.lower(): run_font(run, lang) for lang in _FONT_FACE_LANG_TO_REF})


# --------------------------------------------------------------------------
# Splitting runs and formatting a range of characters


def _unit_length(child: ET.Element) -> int:
    name = _element_local_name(child)
    if name == "t":
        return len(_text_element_content(child))
    if name == "tab" or _is_tab_control_element(child):
        return 1
    return 0


def _run_length(run: ET.Element) -> int:
    return sum(_unit_length(child) for child in run)


def _split_text_element(text: ET.Element, offset: int) -> ET.Element:
    """Cut the ``hp:t`` *text* at character *offset* (inside it); return the new right half."""

    from ._document_primitives import _TEXT_INLINE_ATOMS

    right = text.makeelement(text.tag, dict(text.attrib))
    leading = text.text or ""
    children = list(text)
    if offset <= len(leading):
        text.text = leading[:offset]
        right.text = leading[offset:] or None
        for child in children:
            right.append(child)
        return right
    position = len(leading)
    for index, child in enumerate(children):
        name = _element_local_name(child)
        length = 1 if name in _TEXT_INLINE_ATOMS else (len("".join(child.itertext())) if name else 0)
        if position < offset < position + length:
            raise HwpxValueError(
                "the position falls inside an element of the text that cannot be divided",
                code="paragraph-split-inside-element",
                context={"element": name},
                suggestion="Pick a position before or after that element.",
            )
        position += length
        tail = child.tail or ""
        if offset <= position + len(tail):
            cut = offset - position
            child.tail = tail[:cut] or None
            right.text = tail[cut:] or None
            for moved in children[index + 1:]:
                right.append(moved)
            return right
        position += len(tail)
    return right  # pragma: no cover - the offset is inside the text


def _split_run_element(paragraph: ET.Element, run: ET.Element, offset: int) -> ET.Element:
    """Divide *run* at its character *offset* (strictly inside it) into two sibling runs."""

    right = run.makeelement(run.tag, dict(run.attrib))
    consumed = 0
    children = list(run)
    moving: list[ET.Element] = []
    for index, child in enumerate(children):
        length = _unit_length(child)
        if consumed + length <= offset:  # before the cut; so is a zero-width child right at it
            consumed += length
            continue
        if consumed < offset:  # the cut is inside this hp:t
            right.append(_split_text_element(child, offset - consumed))
            moving = children[index + 1:]
        else:
            moving = children[index:]
        break
    for child in moving:
        right.append(child)
    paragraph.insert(list(paragraph).index(run) + 1, right)
    return right


def _run_elements(paragraph: "HwpxOxmlParagraph") -> list[ET.Element]:
    return [child for child in paragraph.element if _element_local_name(child) == "run"]


def _cut_at(paragraph: "HwpxOxmlParagraph", offset: int) -> tuple[ET.Element | None, bool]:
    """Make *offset* a run boundary; return the run whose first character is at *offset*
    (``None`` at the end of the text) and whether a run was divided."""

    position = 0
    for run in _run_elements(paragraph):
        length = _run_length(run)
        if length and position == offset:
            return run, False
        if position < offset < position + length:
            return _split_run_element(paragraph.element, run, offset - position), True
        position += length
    return None, False


def _check_offset(name: str, value: object, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HwpxTypeError(f"{name} must be an int; got {value!r}", code="paragraph-range-invalid",
                            context={"name": name, "requested": repr(value)},
                            suggestion="Count characters as paragraph.text does.")
    if not low <= value <= high:
        raise HwpxValueError(
            f"{name} {value} is outside {low}..{high}",
            code="paragraph-range-invalid",
            context={"name": name, "requested": value, "min": low, "max": high},
            suggestion="Count characters as paragraph.text does (a tab or a line break is one).",
        )
    return value


def _changed(paragraph: "HwpxOxmlParagraph") -> None:
    _clear_paragraph_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()


def split_run(paragraph: "HwpxOxmlParagraph", offset: int) -> "HwpxOxmlRun":
    """``paragraph.split_run``: make *offset* a run boundary, return the run starting there."""

    from .run import HwpxOxmlRun

    _check_offset("offset", offset, 1, len(paragraph.text) - 1)
    run, divided = _cut_at(paragraph, offset)
    assert run is not None  # offset is inside the text
    if divided:
        _changed(paragraph)
    return HwpxOxmlRun(run, paragraph)


def format_range(
    paragraph: "HwpxOxmlParagraph", start: int, end: int, changes: Mapping[str, Any]
) -> "tuple[HwpxOxmlRun, ...]":
    """``paragraph.format_range``: give characters ``[start, end)`` the character *changes*."""

    from .run import HwpxOxmlRun

    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    spec = _char_changes(changes)
    if not spec:
        raise HwpxValueError("no character format to change", code="style-run-format-empty",
                             suggestion="Pass at least one of " + ", ".join(CHAR_FORMAT_NAMES) + ".")
    if start == end:
        return ()
    header = _header_of(paragraph.section.document)
    _, cut_end = _cut_at(paragraph, end)
    _, cut_start = _cut_at(paragraph, start)
    targets: list[ET.Element] = []
    position = 0
    for run in _run_elements(paragraph):
        run_length = _run_length(run)
        if run_length and start <= position and position + run_length <= end:
            targets.append(run)
        position += run_length
    derived: dict[str | None, str] = {}
    font_ids = _font_ids(header, spec)
    for run in targets:
        base = run.get("charPrIDRef")
        if base not in derived:
            derived[base] = derive_definition(
                header, "charPr", base, lambda element: _apply_char_changes(element, spec, font_ids)
            )
        run.set("charPrIDRef", derived[base])
    if targets or cut_end or cut_start:
        _changed(paragraph)
    return tuple(HwpxOxmlRun(run, paragraph) for run in targets)


def replace_range(paragraph: "HwpxOxmlParagraph", start: int, end: int, text: str) -> None:
    """``paragraph.replace_range``: put *text* in place of characters ``[start, end)``, the runs as
    they are, by the rule ``doc.text.replace`` follows (each new character takes the run of the old
    one at its position)."""

    from ._paragraph_text_edit import text_marks_as_elements_in
    from .run import _overlay_replacement, text_stretch_spans

    if not isinstance(text, str):
        raise HwpxTypeError(f"text must be a str; got {type(text).__name__}", code="paragraph-text-invalid-type",
                            suggestion="Pass the new text as a str ('' removes the range).")
    length = len(paragraph.text)
    start = _check_offset("start", start, 0, length)
    end = _check_offset("end", end, start, length)
    if start == end and not text:
        return
    runs = _run_elements(paragraph)
    chosen = next(
        ((begin, segments) for begin, segments in text_stretch_spans(runs)
         if begin <= start and end <= begin + sum(len(segment.text) for segment in segments)),
        None,
    )
    if chosen is None:
        raise HwpxValueError(
            f"characters {start}..{end} are not one stretch of text: a tab, a line break, a control or an "
            "object lies in or around them",
            code="paragraph-range-crosses-element",
            context={"start": start, "end": end},
            suggestion="Replace the text on each side of the tab, line break or object separately.",
        )
    begin, segments = chosen
    local_start, local_end = start - begin, end - begin
    if start < end:
        _overlay_replacement(segments, local_start, local_end, text)
    else:
        # an insertion goes into the segment holding the character before it (at the start of the
        # stretch, the first segment)
        offset = 0
        for segment in segments:
            segment_end = offset + len(segment.text)
            if local_start <= segment_end and (local_start > offset or local_start == 0):
                at = local_start - offset
                segment.set(segment.text[:at] + text + segment.text[at:])
                break
            offset = segment_end
    for run in runs:
        text_marks_as_elements_in(run)
    _changed(paragraph)


# --------------------------------------------------------------------------
# Paragraph formats


def paragraph_para_pr(paragraph: "HwpxOxmlParagraph") -> ET.Element | None:
    document = paragraph.section.document
    if document is None or paragraph.para_pr_id_ref is None:
        return None
    for header in reversed(document.headers):
        found = find_definition(header, "paraPr", paragraph.para_pr_id_ref)
        if found is not None:
            return found
    return None


def _branches(para_pr: ET.Element, name: str) -> tuple[ET.Element | None, ET.Element | None, ET.Element | None]:
    """The *name* child of *para_pr*'s ``hp:case``, its own, and its ``hp:default`` one."""

    case = default = None
    for switch in para_pr:
        if _element_local_name(switch) != "switch":
            continue
        for branch in switch:
            found = _child(branch, name)
            if found is None:
                continue
            if _element_local_name(branch) == "case" and case is None:
                case = found
            elif _element_local_name(branch) == "default" and default is None:
                default = found
    return case, _child(para_pr, name), default


def _margin_value(margin: ET.Element, name: str) -> int | None:
    node = _child(margin, name)
    if node is None:
        return None
    if (node.get("unit") or "HWPUNIT").upper() != "HWPUNIT":
        return None
    raw = node.get("value") if node.get("value") is not None else (node.text or "").strip()
    try:
        return int(raw or "")
    except ValueError:
        return None


def paragraph_margin(paragraph: "HwpxOxmlParagraph", name: str) -> int | None:
    """Margin *name* (``intent``/``left``/``right``/``prev``/``next``) in HWPUNIT, as Hancom reads it."""

    para_pr = paragraph_para_pr(paragraph)
    if para_pr is None:
        return None
    case, own, default = _branches(para_pr, "margin")
    for margin, scale in ((case, 1), (own, 1), (default, 2)):
        if margin is not None:
            value = _margin_value(margin, name)
            if value is not None:
                return value // scale
    return None


def paragraph_line_spacing(paragraph: "HwpxOxmlParagraph") -> LineSpacing | None:
    para_pr = paragraph_para_pr(paragraph)
    if para_pr is None:
        return None
    case, own, default = _branches(para_pr, "lineSpacing")
    for node, from_default in ((case, False), (own, False), (default, True)):
        if node is None:
            continue
        kind = (node.get("type") or "PERCENT").upper()
        try:
            spacing_type = LineSpacingType(kind)
            value = int(node.get("value") or "0")
        except ValueError:
            return None
        if from_default and spacing_type is not LineSpacingType.PERCENT:
            value //= 2
        return LineSpacing(spacing_type, value)
    return None


def paragraph_alignment(paragraph: "HwpxOxmlParagraph") -> Alignment | None:
    para_pr = paragraph_para_pr(paragraph)
    align = None if para_pr is None else _child(para_pr, "align")
    horizontal = None if align is None else (align.get("horizontal") or "").upper()
    try:
        return Alignment(horizontal) if horizontal else None
    except ValueError:
        return None


_BREAK_ATTRIBUTES = {
    "page_break_before": "pageBreakBefore",
    "keep_with_next": "keepWithNext",
    "keep_lines": "keepLines",
    "widow_orphan": "widowOrphan",
}


def paragraph_break_flag(paragraph: "HwpxOxmlParagraph", name: str) -> bool | None:
    para_pr = paragraph_para_pr(paragraph)
    setting = None if para_pr is None else _child(para_pr, "breakSetting")
    if setting is None:
        return None if para_pr is None else False
    return (setting.get(_BREAK_ATTRIBUTES[name]) or "0").strip().lower() in ("1", "true")


def paragraph_outline_level(paragraph: "HwpxOxmlParagraph") -> int:
    """``Paragraph.outline_level``: :func:`~hwpx.oxml.paragraph_heading.heading_outline_level`
    of the paragraph's shape, 0 for a paragraph that is not an outline paragraph."""

    para_pr = paragraph_para_pr(paragraph)
    return (heading_outline_level(para_pr) or 0) if para_pr is not None else 0


def para_pr_outline_level(document: "HwpxOxmlDocument", para_pr_id_ref: "int | str | None") -> int | None:
    """The outline level (1 to 10) the paragraph shape *para_pr_id_ref* gives its paragraphs, or
    ``None`` (:func:`~hwpx.oxml.paragraph_heading.heading_outline_level`, the one rule)."""

    for header in reversed(document.headers):
        found = find_definition(header, "paraPr", para_pr_id_ref)
        if found is not None:
            return heading_outline_level(found)
    return None


def _derive_paragraph(paragraph: "HwpxOxmlParagraph", modify: Callable[["HwpxOxmlHeader", ET.Element], None]) -> None:
    header = _header_of(paragraph.section.document)
    base = paragraph.para_pr_id_ref
    if base is not None and find_definition(header, "paraPr", base) is None:
        base = None  # a reference the header lacks: build on the first shape, as Hancom shows it
    paragraph.para_pr_id_ref = derive_definition(header, "paraPr", base, lambda element: modify(header, element))


def normalize_alignment(value: object) -> str:
    from .header_part import HwpxOxmlHeader

    raw = getattr(value, "value", value)
    try:
        return HwpxOxmlHeader._normalize_paragraph_alignment(str(raw))
    except ValueError:
        raise HwpxValueError(
            f"unsupported paragraph alignment {value!r}",
            code="paragraph-alignment-invalid",
            context={"requested": repr(value), "allowed": [item.value for item in Alignment]},
            suggestion="Use one of " + ", ".join(item.value for item in Alignment) + ".",
        ) from None


def set_paragraph_alignment(paragraph: "HwpxOxmlParagraph", value: object) -> None:
    horizontal = normalize_alignment(value)

    def modify(header: "HwpxOxmlHeader", element: ET.Element) -> None:
        align = header._ensure_direct_para_child(element, "align", after_local_names=set())
        align.set("horizontal", horizontal)
        if align.get("vertical") is None:
            align.set("vertical", "BASELINE")

    _derive_paragraph(paragraph, modify)


def _check_length(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HwpxTypeError(f"{name} must be a number; got {value!r}", code="paragraph-format-invalid",
                            context={"name": name, "requested": repr(value)})
    return float(value)


def set_paragraph_margin(paragraph: "HwpxOxmlParagraph", name: str, value: object, *, unit: str) -> None:
    number = _check_length(f"{name}_{unit}", value)
    if name in ("prev", "next") and number < 0:
        raise HwpxValueError(f"paragraph spacing must not be negative; got {value!r}",
                             code="paragraph-format-invalid", context={"requested": repr(value)})
    hwpunit = round(number * (_HWPUNIT_PER_MM if unit == "mm" else 100))
    _derive_paragraph(paragraph, lambda header, element: header._apply_paragraph_margins(element, {name: hwpunit}))


def line_spacing_value(value: object) -> LineSpacing:
    if isinstance(value, LineSpacing):
        spacing = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        spacing = LineSpacing(LineSpacingType.PERCENT, round(float(value)))
    else:
        raise HwpxTypeError(
            f"line spacing must be a LineSpacing or a percentage; got {value!r}",
            code="paragraph-line-spacing-invalid",
            suggestion='Pass 160 (percent) or LineSpacing("FIXED", 2000) (HWPUNIT).',
        )
    if spacing.value <= 0 if spacing.type is LineSpacingType.PERCENT else spacing.value < 0:
        raise HwpxValueError("line spacing must be positive", code="paragraph-line-spacing-invalid",
                             context={"requested": spacing.to_dict()}, suggestion="160 is Hancom's default (160%).")
    return spacing


def apply_line_spacing(header: "HwpxOxmlHeader", element: ET.Element, spacing: LineSpacing) -> None:
    """Write *spacing* into every ``hh:lineSpacing`` of paragraph shape *element*:
    Hancom keeps twice a length (not a percentage) in the ``hp:default`` branch."""

    case, own, default = _branches(element, "lineSpacing")
    nodes = [node for node in (case, own, default) if node is not None]
    if not nodes:
        nodes = [header._ensure_direct_para_child(element, "lineSpacing", after_local_names={"margin"})]
    for node in nodes:
        doubled = node is default and spacing.type is not LineSpacingType.PERCENT
        node.set("type", spacing.type.value)
        node.set("value", str(spacing.value * 2 if doubled else spacing.value))
        node.set("unit", "HWPUNIT")


def set_paragraph_line_spacing(paragraph: "HwpxOxmlParagraph", value: object) -> None:
    spacing = line_spacing_value(value)
    _derive_paragraph(paragraph, lambda header, element: apply_line_spacing(header, element, spacing))


def set_paragraph_break_flag(paragraph: "HwpxOxmlParagraph", name: str, value: object) -> None:
    flag = _check_bool(name, value)
    if flag is None:
        raise HwpxTypeError(f"{name} must be True or False", code="paragraph-format-invalid",
                            context={"name": name})
    _derive_paragraph(paragraph, lambda header, element: header._apply_paragraph_break_setting(element, {name: flag}))


#: ``hh:breakSetting`` word-break values Hancom writes.
_WORD_BREAKS = frozenset({"KEEP_WORD", "BREAK_WORD", "HYPHENATION"})
_LINE_WRAPS = frozenset({"BREAK", "SQUEEZE", "KEEP"})


def apply_break_words(header: "HwpxOxmlHeader", element: ET.Element, settings: Mapping[str, object]) -> None:
    """``break_latin_word``/``break_non_latin_word``/``line_wrap`` of ``ensure_paragraph_format``'s
    *break_setting* (the other keys go through the header's own writer)."""

    wanted = {
        "break_latin_word": ("breakLatinWord", _WORD_BREAKS),
        "break_non_latin_word": ("breakNonLatinWord", _WORD_BREAKS),
        "line_wrap": ("lineWrap", _LINE_WRAPS),
    }
    for key, (attribute, allowed) in wanted.items():
        value = settings.get(key)
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if normalized not in allowed:
            raise HwpxValueError(
                f"unsupported {key} {value!r}",
                code="paragraph-format-invalid",
                context={"name": key, "requested": repr(value), "allowed": sorted(allowed)},
                suggestion="Use one of " + ", ".join(sorted(allowed)) + ".",
            )
        setting = header._ensure_direct_para_child(element, "breakSetting", after_local_names={"align", "heading"})
        setting.set(attribute, normalized)


def check_condense(value: object) -> int:
    number = _check_number("condense", value, 0, 75, code="paragraph-format-invalid",
                           suggestion="condense 는 공백 최소값 0 ~ 75 (%) 입니다.")
    return int(number)


def paragraph_extras(
    line_spacing: object, condense: object
) -> Callable[["HwpxOxmlHeader", ET.Element, Mapping[str, object]], None]:
    """``ensure_paragraph_format``'s *line_spacing*, *condense* and word-break settings,
    checked now and written by the returned function."""

    spacing = None if line_spacing is None else line_spacing_value(line_spacing)
    condense_value = None if condense is None else check_condense(condense)

    def write(header: "HwpxOxmlHeader", element: ET.Element, break_setting: Mapping[str, object]) -> None:
        apply_break_words(header, element, break_setting)
        if spacing is not None:
            apply_line_spacing(header, element, spacing)
        if condense_value is not None:
            element.set("condense", str(condense_value))

    return write


def set_paragraph_outline_level(paragraph: "HwpxOxmlParagraph", value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
        raise HwpxValueError(
            "outline_level must be between 0 and 10",
            code="paragraph-outline-level-out-of-range",
            context={"requested": repr(value), "min": 0, "max": 10},
            suggestion="0 means no outline. Use doc.add_heading() for heading paragraphs.",
        )
    attributes = (
        {"type": "NONE", "idRef": "0", "level": "0"} if value == 0
        else {"type": "OUTLINE", "idRef": "0", "level": str(value - 1)}
    )
    _derive_paragraph(paragraph, lambda header, element: set_paragraph_heading(element, attributes))


def set_paragraph_page_break(paragraph: "HwpxOxmlParagraph", value: object) -> None:
    flag = _check_bool("page_break", value)
    if flag is None:
        raise HwpxTypeError("page_break must be True or False", code="paragraph-format-invalid")
    wanted = "1" if flag else "0"
    if paragraph.element.get("pageBreak") != wanted:
        paragraph.element.set("pageBreak", wanted)
        _changed(paragraph)


# --------------------------------------------------------------------------
# Styles


def _style_names(document: "HwpxOxmlDocument") -> list[str]:
    seen: dict[str, None] = {}
    for style in document.styles.values():
        for label in ((style.name or "").strip(), (style.eng_name or "").strip()):
            if label:
                seen.setdefault(label, None)
    return list(seen)


def style_not_found(document: "HwpxOxmlDocument", spec: object) -> HwpxLookupError:
    requested = spec if isinstance(spec, (int, str)) else repr(spec)
    available = _style_names(document)
    closest = difflib.get_close_matches(str(requested), available, n=3, cutoff=0.6)
    hint = f"가장 가까운 이름: {', '.join(repr(name) for name in closest)}. " if closest else ""
    return HwpxLookupError(
        f"스타일 {requested!r} 을(를) 찾을 수 없습니다.",
        code="style-not-found",
        context={"requested": requested, "available": available, "availableCount": len(available), "closest": closest},
        suggestion=f"{hint}전체 목록: doc.styles.names",
    )


def resolve_style(document: "HwpxOxmlDocument", spec: "int | str | Style | None") -> "Style":
    """*spec* as one style: a ``Style``, a number id, a ``name``, then an ``engName`` (any case)."""

    if spec is None:
        raise style_not_found(document, spec)
    if not isinstance(spec, (int, str)) or isinstance(spec, bool):
        from .header import Style

        if isinstance(spec, Style):
            return spec
        from ..errors import argument_type_error

        raise argument_type_error(
            "style", spec, "a style name, id or Style",
            suggestion="Pass the style's name ('본문'), its id (2) or a Style from doc.styles.",
        )
    styles = document.styles
    if isinstance(spec, int) or spec.strip().lstrip("-").isdigit():
        wanted = str(int(str(spec).strip()))
        for style_id, style in styles.items():
            if str(style_id) == wanted or str(style.id) == wanted:
                return style
        raise style_not_found(document, spec)
    wanted_name = spec.strip()
    aliases = document.style_name_aliases()
    ids = aliases.get(wanted_name)
    if ids is None:
        lowered = wanted_name.lower()
        ids = next((found for alias, found in aliases.items() if alias.lower() == lowered), None)
    if ids is None:
        raise style_not_found(document, spec)
    if len(ids) > 1:
        raise HwpxLookupError(
            f"스타일 이름 {wanted_name!r} 이(가) 모호합니다 — {len(ids)}개가 같은 이름을 씁니다.",
            code="style-ambiguous",
            context={
                "requested": wanted_name,
                "candidates": [
                    {"id": style_id, "name": ((styles[style_id].name or styles[style_id].eng_name or "").strip()
                                              if style_id in styles else "")}
                    for style_id in ids
                ],
            },
            suggestion=f"숫자 id 로 지정하세요 — 후보: {', '.join(ids)}.",
        )
    resolved = styles.get(ids[0]) if ids else None
    if resolved is None:  # pragma: no cover - the alias table comes from the same header
        raise style_not_found(document, spec)
    return resolved


def _style_id(style: "Style") -> str:
    return style.raw_id or str(style.id)


def apply_paragraph_style(paragraph: "HwpxOxmlParagraph", spec: object) -> None:
    """``paragraph.style = ...``: the style's name, paragraph shape and character shape, as Hancom applies it."""

    document = paragraph.section.document
    if document is None:
        raise HwpxStateError("the paragraph is not in a document", code="document-header-missing")
    style = resolve_style(document, spec)  # type: ignore[arg-type]
    if (style.type or "PARA").upper() == "CHAR":
        raise HwpxValueError(
            f"style {style.name!r} is a character style",
            code="paragraph-style-char-type",
            context={"style": style.name, "type": style.type},
            suggestion="Give a paragraph style (type PARA); a character style applies to runs.",
        )
    paragraph.style_id_ref = _style_id(style)
    if style.para_pr_id_ref is not None:
        paragraph.para_pr_id_ref = style.para_pr_id_ref
    if style.char_pr_id_ref is not None:
        paragraph.char_pr_id_ref = style.char_pr_id_ref


def _story_parts(document: "HwpxOxmlDocument") -> list[Any]:
    """Every part that holds paragraphs: the sections and the master pages."""

    return [*document.sections, *document.master_pages]


def _paragraphs_with_style(document: "HwpxOxmlDocument", style_id: str) -> list[tuple[Any, ET.Element]]:
    found = []
    for part in _story_parts(document):
        for element in part.element.iter(f"{_HP}p"):
            if _same_id(element.get("styleIDRef"), style_id):
                found.append((part, element))
    return found


def set_style_format(
    document: "HwpxOxmlDocument",
    spec: object,
    char_changes: Mapping[str, Any],
    para_modify: Callable[["HwpxOxmlHeader", ET.Element], None] | None,
) -> None:
    """Change the character and paragraph shapes of a style, as Hancom's style edit does.

    The style gets derived shapes; every paragraph of that style that used the old
    paragraph shape, and every run of such a paragraph that used the old character
    shape, follows. Other users of the old shapes stay as they were.
    """

    header = _header_of(document)
    style = resolve_style(document, spec)  # type: ignore[arg-type]
    style_id = _style_id(style)
    old_char = None if style.char_pr_id_ref is None else str(style.char_pr_id_ref)
    old_para = None if style.para_pr_id_ref is None else str(style.para_pr_id_ref)
    new_char = derive_char_pr(header, old_char, char_changes) if char_changes else old_char
    new_para = old_para
    if para_modify is not None:
        new_para = derive_definition(header, "paraPr", old_para, lambda element: para_modify(header, element))
    if new_char == old_char and new_para == old_para:
        return
    element = find_style_element(header, style_id)
    if element is not None:
        if new_para is not None:
            element.set("paraPrIDRef", new_para)
        if new_char is not None:
            element.set("charPrIDRef", new_char)
        header.mark_dirty()
    for part, paragraph in _paragraphs_with_style(document, style_id):
        changed = False
        if new_para != old_para and _same_id(paragraph.get("paraPrIDRef"), old_para or ""):
            paragraph.set("paraPrIDRef", str(new_para))
            changed = True
        if new_char != old_char:
            for run in paragraph.findall(f"{_HP}run"):
                if _same_id(run.get("charPrIDRef"), old_char or ""):
                    run.set("charPrIDRef", str(new_char))
                    changed = True
        if changed:
            _clear_paragraph_layout_cache(paragraph)
            part.mark_dirty()


def set_char_property_in_place(document: "HwpxOxmlDocument", char_pr_id_ref: object,
                               changes: Mapping[str, Any]) -> int:
    """``doc.styles.set_char_property``: change the ``hh:charPr`` *char_pr_id_ref* itself.

    Every run, style, numbering or bullet pointing at that id follows; no copy is made. The paragraphs
    whose runs point at it lose their line layout caches (with the paragraphs holding their cells and
    captions), and so does every numbered or bulleted paragraph when a numbering or bullet draws its
    number with it. Returns how many paragraphs lost a cache.
    """

    from ._document_primitives import _clear_paragraph_layout_cache

    header = _header_of(document)
    spec = _char_changes(changes)
    if not spec:
        raise HwpxValueError(
            "no character format to change",
            code="style-run-format-empty",
            suggestion="Pass at least one of " + ", ".join(CHAR_FORMAT_NAMES) + ".",
        )
    element = None if char_pr_id_ref is None or isinstance(char_pr_id_ref, bool) else find_definition(
        header, "charPr", char_pr_id_ref)  # type: ignore[arg-type]
    if element is None:
        raise HwpxLookupError(
            f"the header has no charPr with id {char_pr_id_ref!r}",
            code="style-definition-not-found",
            context={"kind": "charPr", "id": str(char_pr_id_ref)},
            suggestion="Read the id from a run (run.char_pr_id_ref) or from doc.styles.char_properties.",
        )
    own_id = str(element.get("id"))
    before = (_attributes_without_id(element), _signature(element))
    _apply_char_changes(element, spec, _font_ids(header, spec))
    if (_attributes_without_id(element), _signature(element)) == before:
        return 0
    header.mark_dirty()
    document.invalidate_char_property_cache()
    headed = any(
        _same_id(node.get("charPrIDRef"), own_id)
        for node in header.element.iter()
        if _element_local_name(node) in ("paraHead", "bullet")
    )
    cleared = 0
    for part in _story_parts(document):
        touched = False
        for paragraph in part.element.iter(f"{_HP}p"):
            uses = any(_same_id(run.get("charPrIDRef"), own_id) for run in paragraph.findall(f"{_HP}run"))
            if not uses and headed:
                para_pr = find_definition(header, "paraPr", paragraph.get("paraPrIDRef"))
                heading = None if para_pr is None else next(
                    (node for node in para_pr.iter() if _element_local_name(node) == "heading"), None)
                uses = heading is not None and (heading.get("type") or "NONE").upper() != "NONE"
            if uses and _clear_paragraph_layout_cache(paragraph):
                cleared += 1
                touched = True
        if touched:
            part.mark_dirty()
    return cleared


#: ``doc.styles`` name of each definition list, its ``hh:`` kind and the attribute that points at one.
UNUSED_DEFINITION_KINDS = {
    "char_properties": ("charPr", "charPrIDRef"),
    "paragraph_properties": ("paraPr", "paraPrIDRef"),
    "border_fills": ("borderFill", "borderFillIDRef"),
    "tab_properties": ("tabPr", "tabPrIDRef"),
}


def remove_unused_definitions(document: "HwpxOxmlDocument", kinds: "Sequence[str]") -> dict[str, tuple[str, ...]]:
    """``doc.styles.remove_unused_definitions``: drop the definitions at the end of each list that nothing
    points at, so that no other id moves.

    A definition is used when any element of the header, a section (its headers, footers, notes, memos and
    cells included) or a master page names its id in the list's reference attribute (``charPrIDRef`` …, a
    style, a numbering head, a character shape's border fill as much as a run). Only the unused ones that
    end the list go, back to the first used one, and never the list's first definition: the ids stay
    ``0..N-1`` (border fills ``1..N``) as Hancom writes them, with no reference to renumber.
    """

    _name = _element_local_name
    headers = list(document.headers)
    if not headers:
        raise HwpxStateError("the document has no header", code="document-header-missing",
                             suggestion="Open or make the document with HwpxDocument.")
    trees = [header.element for header in headers] + [part.element for part in _story_parts(document)]
    removed: dict[str, tuple[str, ...]] = {}
    for name in kinds:
        kind, attribute = UNUSED_DEFINITION_KINDS[name]
        used: set[str] = set()
        for tree in trees:
            for node in tree.iter():
                value = node.get(attribute) if isinstance(node.tag, str) else None
                if value is not None:
                    used.add(value.strip())
        used_numbers = {int(value) for value in used if value.lstrip("-").isdigit()}
        gone: list[str] = []
        for header in headers:
            container = _container(header, kind)
            if container is None:
                continue
            members = [child for child in container if _name(child) == kind]
            while len(members) > 1:
                last = members[-1]
                raw = (last.get("id") or "").strip()
                if raw in used or (raw.lstrip("-").isdigit() and int(raw) in used_numbers):
                    break
                container.remove(last)
                members.pop()
                gone.append(raw)
            if gone:
                container.set("itemCnt", str(len(members)))
                header.mark_dirty()
        removed[name] = tuple(reversed(gone))
    if removed.get("char_properties"):
        document.invalidate_char_property_cache()
    return removed


def find_style_element(header: "HwpxOxmlHeader", style_id: str) -> ET.Element | None:
    styles = header._styles_element()
    if styles is None:
        return None
    return next((child for child in styles if _element_local_name(child) == "style"
                 and _same_id(child.get("id"), style_id)), None)


def remove_style(document: "HwpxOxmlDocument", spec: object, replacement: object = None) -> None:
    """``doc.styles.remove_style``: take a style out; its paragraphs take *replacement*.

    Style ids stay ``0..N-1``: the styles after it move down one, and every
    ``styleIDRef``/``nextStyleIDRef`` follows them.
    """

    header = _header_of(document)
    style = resolve_style(document, spec)  # type: ignore[arg-type]
    style_id = _style_id(style)
    if _same_id(style_id, "0"):
        raise HwpxValueError(
            "the first style (바탕글) cannot be removed",
            code="style-remove-default",
            context={"style": style.name},
            suggestion="Hancom keeps style 0 as the default style; change it with set_style_format instead.",
        )
    users = _paragraphs_with_style(document, style_id)
    target: "Style | None" = None
    if replacement is not None:
        target = resolve_style(document, replacement)  # type: ignore[arg-type]
        if _same_id(_style_id(target), style_id):
            raise HwpxValueError("the replacement is the style being removed", code="style-in-use",
                                 context={"style": style.name}, suggestion="Name another style.")
    elif users:
        raise HwpxValueError(
            f"style {style.name!r} is used by {len(users)} paragraph(s)",
            code="style-in-use",
            context={"style": style.name, "paragraphs": len(users)},
            suggestion="Pass replacement= (a style name or id) for those paragraphs.",
        )
    if target is not None:
        if (target.type or "PARA").upper() == "CHAR":
            raise HwpxValueError(f"style {target.name!r} is a character style", code="paragraph-style-char-type",
                                 context={"style": target.name}, suggestion="Name a paragraph style.")
        for part, paragraph in users:
            paragraph.set("styleIDRef", _style_id(target))
            if target.para_pr_id_ref is not None:
                paragraph.set("paraPrIDRef", str(target.para_pr_id_ref))
            if target.char_pr_id_ref is not None:
                for run in paragraph.findall(f"{_HP}run"):
                    run.set("charPrIDRef", str(target.char_pr_id_ref))
            _clear_paragraph_layout_cache(paragraph)
            part.mark_dirty()
    styles_element = header._styles_element()
    element = find_style_element(header, style_id)
    if styles_element is None or element is None:  # pragma: no cover - resolved from this header
        return
    removed = _int(element.get("id"))
    styles_element.remove(element)

    def moved(raw: str | None) -> str | None:
        """A style id after the removal: the ids past the removed one move down one."""
        try:
            number = int(raw or "")
        except ValueError:
            return raw
        return str(number - 1) if number > removed else raw

    fallback = None if target is None else moved(_style_id(target))
    for child in styles_element:
        if _element_local_name(child) != "style":
            continue
        own = moved(child.get("id"))
        next_ref = child.get("nextStyleIDRef")
        if next_ref is not None:
            # A style whose next style was the removed one goes on with the replacement, else with itself.
            child.set("nextStyleIDRef", str(fallback or own) if _same_id(next_ref, str(removed)) else str(moved(next_ref)))
        if own is not None:
            child.set("id", own)
    styles_element.set("itemCnt", str(sum(1 for child in styles_element if _element_local_name(child) == "style")))
    header.mark_dirty()
    for part in _story_parts(document):
        touched = False
        for paragraph in part.element.iter(f"{_HP}p"):
            raw = paragraph.get("styleIDRef")
            new = str(fallback or "0") if _same_id(raw, str(removed)) else moved(raw)
            if raw is not None and new is not None and new != raw:
                paragraph.set("styleIDRef", new)
                touched = True
        if touched:
            part.mark_dirty()


# --------------------------------------------------------------------------
# Numbering definitions as values


def _int(raw: str | None, default: int = 0) -> int:
    try:
        return int(raw or "")
    except ValueError:
        return default


def _level_alignment(head: Any) -> Alignment:
    """A numbering level's ``hh:paraHead/@align`` as an :class:`Alignment` (``LEFT`` when unsaid);
    a token outside the list reads as written."""

    token = (head.get("align") or "LEFT").strip().upper()
    try:
        return Alignment(token)
    except ValueError:
        return cast(Alignment, token)


def numbering_info(header: "HwpxOxmlHeader | None", numbering_id_ref: "int | str | None") -> NumberingInfo | None:
    if header is None or numbering_id_ref is None:
        return None
    container = header._numberings_element()
    if container is None:
        return None
    wanted = str(numbering_id_ref).strip()
    element = next((child for child in container if _element_local_name(child) == "numbering"
                    and _same_id(child.get("id"), wanted)), None)
    if element is None:
        return None
    heads = [node for node in element if _element_local_name(node) == "paraHead"]
    for switch in (node for node in element if _element_local_name(node) == "switch"):
        for case in (node for node in switch if _element_local_name(node) == "case"):
            heads.extend(node for node in case if _element_local_name(node) == "paraHead")
    levels = []
    for index, head in enumerate(heads, start=1):
        char_ref = head.get("charPrIDRef")
        levels.append(NumberingLevel(
            level=_int(head.get("level"), index),
            start=_int(head.get("start"), 1),
            number_format=(head.get("numFormat") or "DIGIT"),
            text="".join(head.itertext()),
            alignment=_level_alignment(head),
            char_pr_id_ref=None if char_ref in (None, "", "4294967295") else char_ref,
            # an attribute left out reads as the OWPML schema's default (useInstWidth/autoIndent true, textOffset 50)
            auto_indent=(head.get("autoIndent") or "1") in ("1", "true"),
            width_adjust=_int(head.get("widthAdjust")),
            text_offset=_int(head.get("textOffset"), 50),
            text_offset_type=(head.get("textOffsetType") or "PERCENT"),
            checkable=(head.get("checkable") or "0") in ("1", "true"),
            use_instance_width=(head.get("useInstWidth") or "1") in ("1", "true"),
        ))
    return NumberingInfo(id=element.get("id") or wanted, start=_int(element.get("start"), 1), levels=tuple(levels))


# --------------------------------------------------------------------------
# Border fills derived from another


_SIDE_CHILDREN = {"left": "leftBorder", "right": "rightBorder", "top": "topBorder", "bottom": "bottomBorder"}


def derive_border_fill(
    header: "HwpxOxmlHeader",
    base_id: "int | str",
    *,
    sides: "Mapping[str, Mapping[str, Any] | None] | None",
    fill_color: str | None,
) -> str:
    """The id of a ``hh:borderFill`` that is *base_id* with the named *sides* and the
    solid *fill_color* changed; a side's ``type``/``width``/``color`` left out keeps the base's."""

    from ._document_primitives import _normalize_border_sides

    base = find_definition(header, "borderFill", base_id)
    if base is None:
        raise HwpxLookupError(
            f"the header has no borderFill with id {base_id!r}",
            code="style-definition-not-found",
            context={"kind": "borderFill", "id": str(base_id)},
        )
    lines: dict[str, tuple[str, str, str]] = {}
    for side, spec in (sides or {}).items():
        key = str(side).strip().lower()
        current = _child(base, _SIDE_CHILDREN.get(key, ""))
        lines.update(_normalize_border_sides(
            {side: spec},
            border_color=(None if current is None else current.get("color")) or "#000000",
            border_width=(None if current is None else current.get("width")) or "0.12 mm",
            border_type=(None if current is None else current.get("type")) or "SOLID",
            allowed_types=header._BORDER_LINE_TYPES,
            type_aliases=header._BORDER_LINE_TYPE_ALIASES,
        ))
    color = None if fill_color is None else normalize_color(fill_color)

    def modify(element: ET.Element) -> None:
        for key, (line_type, width, line_color) in lines.items():
            node = _child(element, _SIDE_CHILDREN[key])
            if node is None:
                node = element.makeelement(f"{_HH}{_SIDE_CHILDREN[key]}", {})
                anchor = [index for index, child in enumerate(element)
                          if _element_local_name(child) in ("slash", "backSlash", *_SIDE_CHILDREN.values())]
                element.insert(anchor[-1] + 1 if anchor else 0, node)
            node.set("type", line_type)
            node.set("width", width)
            node.set("color", line_color)
        if color is not None:
            set_border_fill_color(element, color)

    return derive_definition(header, "borderFill", base_id, modify)


# The fill of a border fill derived from another: one rule for every derivation (doc.styles.
# ensure_border_fill(base_border_fill_id_ref=), table.set_shading / set_borders / set_cell_shading,
# set_cell_fill_image / set_cell_fill_gradient). Hancom's cell fill has a face (a solid colour,
# hc:winBrush, or a gradation, hc:gradation: one or the other) and, apart from it, a picture
# (hc:imgBrush). In the 1,299 HWPX files of the public and test corpora a fillBrush holds a winBrush, an imgBrush, a
# winBrush then an imgBrush (29), or a gradation, never a winBrush and a gradation. So a new
# face replaces the old face and keeps the picture, a new picture keeps the face, and lines,
# diagonals (slash, backSlash, diagonal) and the borderFill's attributes are never touched.

_FACE_BRUSHES = ("winBrush", "gradation")


def _fill_brush(element: ET.Element) -> ET.Element:
    brush = _child(element, "fillBrush")
    if brush is None:
        brush = element.makeelement(f"{_HC}fillBrush", {})
        element.append(brush)
    return brush


def _remove_fill_children(brush: ET.Element, names: Iterable[str]) -> None:
    for child in list(brush):
        if _element_local_name(child) in names:
            brush.remove(child)


def set_border_fill_color(element: ET.Element, color: str | None) -> None:
    """Give the ``hh:borderFill`` *element* the solid face *color* (``#RRGGBB``), or no face (``None``).

    A colour goes into its ``hc:winBrush`` (made with Hancom's usual pattern colour and no
    transparency when there is none; the pattern and transparency of one there are kept) and a
    gradation goes. ``None`` takes the face away. The picture (``hc:imgBrush``) stays either way;
    a ``hc:fillBrush`` left with nothing in it goes."""

    if color is None:
        brush = _child(element, "fillBrush")
        if brush is not None:
            _remove_fill_children(brush, _FACE_BRUSHES)
            if len(brush) == 0:
                element.remove(brush)
        return
    brush = _fill_brush(element)
    _remove_fill_children(brush, ("gradation",))
    win = _child(brush, "winBrush")
    if win is None:
        win = brush.makeelement(f"{_HC}winBrush", {"faceColor": color, "hatchColor": "#999999", "alpha": "0"})
        brush.insert(0, win)
    win.set("faceColor", color)


def _new_fill_child(element: ET.Element, **fill: "Mapping[str, object] | None") -> ET.Element:
    """The ``hc:imgBrush`` or ``hc:gradation`` ``_append_fill_brush`` writes for *fill*."""

    from ._document_primitives import _append_fill_brush

    holder = element.makeelement(f"{_HH}borderFill", {})
    _append_fill_brush(holder, fill_color=None, **fill)  # type: ignore[arg-type]
    return holder[0][0]


def set_border_fill_gradient(element: ET.Element, gradient: "Mapping[str, object]") -> None:
    """Give the ``hh:borderFill`` *element* the gradation *gradient* (the mapping
    ``set_cell_fill_gradient`` builds) as its face, in place of its face; its picture stays."""

    brush = _fill_brush(element)
    _remove_fill_children(brush, _FACE_BRUSHES)
    brush.insert(0, _new_fill_child(element, fill_gradient=gradient))


def set_border_fill_image(element: ET.Element, image: "Mapping[str, str]") -> None:
    """Give the ``hh:borderFill`` *element* the picture *image* (the mapping
    ``set_cell_fill_image`` builds), in place of its picture; its face stays."""

    brush = _fill_brush(element)
    _remove_fill_children(brush, ("imgBrush",))
    brush.append(_new_fill_child(element, fill_image=image))


def tab_stops_in_hwpunit(tab_stops: "Iterable[Mapping[str, object]] | None") -> list[dict[str, object]] | None:
    """``pos_mm`` stops of ``doc.styles.ensure_tab_definition`` as ``pos`` (HWPUNIT) ones."""

    if tab_stops is None:
        return None
    converted: list[dict[str, object]] = []
    for stop in tab_stops:
        item = dict(stop)
        if item.get("pos") is None and item.get("pos_mm") is not None:
            item["pos"] = round(_check_length("pos_mm", item["pos_mm"]) * _HWPUNIT_PER_MM)
        item.pop("pos_mm", None)
        converted.append(item)
    return converted


def para_shape_modifier(
    *,
    alignment: object = None,
    line_spacing: object = None,
    margins: Mapping[str, float | None] | None = None,
) -> Callable[["HwpxOxmlHeader", ET.Element], None] | None:
    """One paragraph-shape modifier for ``set_style_format``; ``None`` when nothing changes."""

    horizontal = None if alignment is None else normalize_alignment(alignment)
    spacing = None if line_spacing is None else line_spacing_value(line_spacing)
    clean = {name: value for name, value in (margins or {}).items() if value is not None}
    if horizontal is None and spacing is None and not clean:
        return None
    hwpunits = {}
    for name, value in clean.items():
        number = _check_length(name, value)
        hwpunits[name] = round(number * (100 if name in ("prev", "next") else _HWPUNIT_PER_MM))

    def modify(header: "HwpxOxmlHeader", element: ET.Element) -> None:
        if horizontal is not None:
            align = header._ensure_direct_para_child(element, "align", after_local_names=set())
            align.set("horizontal", horizontal)
            if align.get("vertical") is None:
                align.set("vertical", "BASELINE")
        if hwpunits:
            header._apply_paragraph_margins(element, hwpunits)
        if spacing is not None:
            apply_line_spacing(header, element, spacing)

    return modify


def runs_text_length(runs: Sequence[ET.Element]) -> int:
    return sum(_run_length(run) for run in runs)
