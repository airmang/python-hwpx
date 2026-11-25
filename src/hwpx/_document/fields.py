# SPDX-License-Identifier: Apache-2.0
"""Form-field domain owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

import numbers
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, cast

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from ..errors import HwpxStateError, HwpxValueError, argument_type_error
from ._resolve import home_paragraph, refused_leaves_no_paragraph
from ..objects.checkbox import CheckBox, ComboBox, EditBox, RadioButton
from ..objects.form_field import (
    Bookmark,
    CellField,
    CrossReference,
    FieldLocation,
    FieldParameter,
    FormField,
    FormulaField,
    Hyperlink,
    TextBoxField,
)
from ..objects.results import FieldFillResult
from ..oxml import HwpxOxmlParagraph
from ..oxml._document_primitives import _clear_paragraph_layout_cache
from ..oxml.namespaces import HP
from ..oxml.section_story import control_twins

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..form_fit.policy import FitPolicy
    from ..form_fit.report import FitResult
    from ..oxml import HwpxOxmlSection

_HP = HP

_FORM_FIELD_EXCLUDED_TYPES = {"HYPERLINK", "MEMO"}
_FORM_FIELD_TYPES = {"FORM", "CLICKHERE", "CLICK_HERE", "CLICK-HERE", "NURUMTUL", "누름틀"}
_FORM_FIELD_NAME_ATTRS = ("fieldName", "fieldname", "name", "title", "id", "fieldid")
_FORM_FIELD_PROMPT_ATTRS = ("prompt", "instruction", "description", "desc", "help", "memo")
_FORM_FIELD_PARAM_NAMES = {
    "fieldname",
    "field_name",
    "name",
    "title",
    "prompt",
    "instruction",
    "description",
    "desc",
    "help",
    "memo",
    "guide",
}
_TEXT_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _local_name(node_or_tag: Any) -> str:
    tag = getattr(node_or_tag, "tag", node_or_tag)
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _owning_paragraph(element: Any, section: "HwpxOxmlSection") -> "HwpxOxmlParagraph | None":
    """Return the innermost ``<hp:p>`` ancestor of *element* within *section*.

    ``_iter_check_boxes`` finds ``<hp:checkBtn>`` elements with a section-wide
    ``.iter()`` search rather than by iterating paragraphs, so — unlike
    ``_iter_form_field_matches`` below, which already walks paragraph by
    paragraph — no paragraph reference comes along for free.

    Walks down from *section* rather than up from *element* via
    ``getparent()`` — mirrors ``oxml.memo._paragraph_containing`` (see there
    for why: lxml supports ``getparent()``, hand-built
    ``xml.etree.ElementTree`` test fixtures do not, and ``for child in node``
    works on both).
    """

    def _walk(node: Any, nearest: Any) -> Any:
        if _local_name(node) == "p":
            nearest = node
        if node is element:
            return nearest
        for child in node:
            found = _walk(child, nearest)
            if found is not None:
                return found
        return None

    node = _walk(section.element, None)
    if node is None:
        return None
    return HwpxOxmlParagraph(node, section)


def _sanitize_field_text(value: str) -> str:
    return _TEXT_ILLEGAL.sub("", value)


# Characters an hp:t holds as child elements; they belong to the text they sit in.
_TEXT_CHARACTER_NAMES = {"tab": "\t", "lineBreak": "\n", "hyphen": "", "nbSpace": "\u00a0", "fwSpace": "\u3000"}


def _text_node_value(node: Any) -> str:
    """The text of an ``hp:t``, with ``hp:lineBreak`` as a newline and ``hp:tab`` as a tab."""

    parts = [node.text or ""]
    for child in node:
        parts.append(_TEXT_CHARACTER_NAMES.get(_local_name(child), ""))
        parts.append(child.tail or "")
    return "".join(parts)


def _write_text_node(node: Any, value: str) -> None:
    """Put *value* in the ``hp:t`` *node* in place of its text.

    A line break (CRLF, LF or CR) becomes ``hp:lineBreak``, the element Hancom
    turns such a character into when it opens the file. The characters of the
    old text (tabs, line breaks) go; other marks stay, emptied.
    """

    for child in list(node):
        if _local_name(child) in _TEXT_CHARACTER_NAMES:
            node.remove(child)
        else:
            child.tail = ""
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    node.text = lines[0]
    for line in lines[1:]:
        line_break = node.makeelement(f"{_HP}lineBreak", {})
        node.append(line_break)
        line_break.tail = line


def _field_type_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        raw = str(value).strip()
        if not raw:
            continue
        tokens.add(raw.upper())
        tokens.add(raw.replace("_", "").replace("-", "").upper())
    return tokens


def _is_form_field_begin(ctrl: Any, field_begin: Any) -> bool:
    return _is_form_field_kind(
        ctrl.get("type"),
        field_begin.get("type"),
        field_begin.get("name"),
        field_begin.get("fieldName"),
        field_begin.get("fieldname"),
    )


@lru_cache(maxsize=4096)
def _is_form_field_kind(
    ctrl_type: str | None, begin_type: str | None, name: str | None, field_name: str | None, fieldname: str | None
) -> bool:
    tokens = _field_type_tokens(ctrl_type, begin_type, name, field_name, fieldname)
    if tokens & _FORM_FIELD_EXCLUDED_TYPES:
        return False
    if tokens & _FORM_FIELD_TYPES:
        return True
    return (ctrl_type or "").strip().upper() == "FORM"


def _field_identifier(field_begin: Any) -> str:
    for attr in ("id", "fieldid", "name", "fieldName", "fieldname"):
        value = (field_begin.get(attr) or "").strip()
        if value:
            return value
    return ""


def _field_end_matches(field_begin: Any, field_end: Any) -> bool:
    # An end that names its begin (beginIDRef) is that begin's end only: a fieldid
    # is shared by every field of a type (Hancom's control id), so it pairs only
    # ends that name no begin.
    if field_begin.get("id") and field_end.get("beginIDRef"):
        return field_begin.get("id") == field_end.get("beginIDRef")
    begin_keys = {
        value
        for value in (
            field_begin.get("id"),
            field_begin.get("fieldid"),
            field_begin.get("name"),
        )
        if value
    }
    end_keys = {
        value
        for value in (
            field_end.get("beginIDRef"),
            field_end.get("fieldid"),
            field_end.get("id"),
        )
        if value
    }
    if begin_keys and end_keys:
        return bool(begin_keys & end_keys)
    return not begin_keys


def _field_parameters(field_begin: Any) -> list[dict[str, str]]:
    parameters: list[dict[str, str]] = []
    for node in field_begin.iter():
        if not _local_name(node).endswith("Param"):
            continue
        name = (node.get("name") or "").strip()
        value = "".join(node.itertext()).strip()
        if name or value:
            parameters.append({"name": name, "value": value})
    return parameters


def _field_name(field_begin: Any, parameters: Sequence[dict[str, str]]) -> str:
    """The field's name. A ``name`` attribute is the name even when empty: Hancom
    treats such a field as unnamed (it lists and fills fields by name only)."""

    if field_begin.get("name") is not None:
        return field_begin.get("name", "").strip()
    name = _first_attr(field_begin, _FORM_FIELD_NAME_ATTRS)
    if not name:
        name = _field_parameter_value(parameters, "fieldName", "fieldname", "field_name", "name", "title")
    return name


def _first_attr(element: Any, names: Sequence[str]) -> str:
    for name in names:
        value = (element.get(name) or "").strip()
        if value:
            return value
    return ""


def _field_parameter_value(parameters: Sequence[dict[str, str]], *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for item in parameters:
        name = item.get("name", "").casefold()
        value = item.get("value", "").strip()
        if name in wanted and value:
            return value
    return ""


_COMMAND_DIRECTION = re.compile(r"(?:^|[\s:])Direction:wstring:(\d+):")


def _command_direction(parameters: Sequence[dict[str, str]]) -> str:
    """The prompt a field keeps only in its ``Command`` string
    (``Clickhere:set:N:Direction:wstring:<length>:<prompt> HelpState:...``)."""

    command = _field_parameter_value(parameters, "Command")
    found = _COMMAND_DIRECTION.search(command)
    if found is None:
        return ""
    start = found.end()
    return command[start : start + int(found.group(1))]


def _clear_form_field_layout_cache(paragraph: Any) -> int:
    """Drop the line layout cache of *paragraph*, whose field or check box changed, and of the
    paragraphs holding its table cell (or caption): a value that wraps makes the cell, and so
    the line holding the table, taller; with the old cache Hancom draws what follows over it."""

    return _clear_paragraph_layout_cache(paragraph)


def _find_field_end_position(
    doc: "HwpxDocument",
    runs: Sequence[Any],
    *,
    begin_run_index: int,
    begin_child_index: int,
    field_begin: Any,
) -> tuple[int, int, Any] | None:
    for run_index in range(begin_run_index, len(runs)):
        children = list(runs[run_index])
        start = begin_child_index + 1 if run_index == begin_run_index else 0
        for child_index in range(start, len(children)):
            child = children[child_index]
            if _local_name(child) != "ctrl":
                continue
            for field_end in child.findall(f"{_HP}fieldEnd"):
                if _field_end_matches(field_begin, field_end):
                    return run_index, child_index, field_end
    return None


def _find_field_end_in_following_paragraphs(
    paragraph_element: Any, field_begin: Any
) -> tuple[Any, list[Any], int, int, list[Any]] | None:
    """The end of a field whose content runs past its paragraph: the later
    paragraph beside it that holds the fieldEnd naming this field's id, that
    paragraph's runs, the end's run and child index, and the paragraphs in
    between. Only an end that names the begin's id counts here."""

    ids = {value for value in (field_begin.get("id"), field_begin.get("fieldid")) if value}
    if not ids:
        return None
    middle: list[Any] = []
    sibling = paragraph_element.getnext()
    while sibling is not None:
        if _local_name(sibling) == "p":
            runs = [child for child in sibling if _local_name(child) == "run"]
            for run_index, run in enumerate(runs):
                for child_index, child in enumerate(run):
                    if _local_name(child) != "ctrl":
                        continue
                    for field_end in child.findall(f"{_HP}fieldEnd"):
                        if _field_end_matches(field_begin, field_end) and (
                            ids & {field_end.get("beginIDRef"), field_end.get("fieldid")}
                        ):
                            return sibling, runs, run_index, child_index, middle
            middle.append(sibling)
        sibling = sibling.getnext()
    return None


def _run_texts(runs: Sequence[Any]) -> str:
    return "".join(_text_node_value(node) for run in runs for node in run if _local_name(node) == "t")


def _field_text_nodes(
    doc: "HwpxDocument",
    runs: Sequence[Any],
    *,
    begin_run_index: int,
    begin_child_index: int,
    end_run_index: int | None,
    end_child_index: int | None,
) -> list[Any]:
    nodes: list[Any] = []
    last_run = end_run_index if end_run_index is not None else begin_run_index
    for run_index in range(begin_run_index, last_run + 1):
        children = list(runs[run_index])
        start = begin_child_index + 1 if run_index == begin_run_index else 0
        stop = end_child_index if end_run_index == run_index and end_child_index is not None else len(children)
        for child in children[start:stop]:
            if _local_name(child) == "t":
                nodes.append(child)
    return nodes


def _form_field_selection_keys(
    field_begin: Any, parameters: Sequence[dict[str, str]] | None = None
) -> tuple[str, str, str]:
    """A field's name, prompt and instruction -- what ``fill(name=)`` compares -- read from its begin alone."""

    if parameters is None:
        parameters = _field_parameters(field_begin)
    name = _field_name(field_begin, parameters)
    prompt = _first_attr(field_begin, _FORM_FIELD_PROMPT_ATTRS)
    if not prompt:
        # "Direction" is the real-Hancom 안내문 parameter (P0 gold contract).
        prompt = _field_parameter_value(parameters, "Direction", *_FORM_FIELD_PARAM_NAMES)
    if not prompt:
        # Some fields keep it only inside their Command string.
        prompt = _command_direction(parameters)
    instruction = _field_parameter_value(parameters, "instruction", "guide", "help", "description", "desc")
    if not instruction:
        instruction = prompt
    return name, prompt, instruction


def _form_field_payload(
    doc: "HwpxDocument",
    *,
    index: int,
    section_index: int,
    paragraph_index: int,
    paragraph_index_in_section: int,
    run_index: int,
    child_index: int,
    ctrl: Any,
    field_begin: Any,
    current_value: str,
    has_end: bool,
) -> dict[str, Any]:
    parameters = _field_parameters(field_begin)
    name, prompt, instruction = _form_field_selection_keys(field_begin, parameters)
    memo = _field_parameter_value(parameters, "HelpState", "memo")
    dirty = (field_begin.get("dirty") or "").strip()
    # Contract: while dirty != "1" the content between begin/end is the prompt
    # placeholder (screen-only, not printed), not a user value.
    is_placeholder = dirty != "1" and bool(prompt) and current_value == prompt
    return {
        "index": index,
        "field_id": _field_identifier(field_begin),
        "id": field_begin.get("id", ""),
        "fieldid": field_begin.get("fieldid", ""),
        "name": name,
        "prompt": prompt,
        "instruction": instruction,
        "memo": memo,
        "dirty": dirty,
        "is_placeholder": is_placeholder,
        "current_value": current_value,
        "field_type": field_begin.get("type", ""),
        "control_type": ctrl.get("type", ""),
        "_field_begin": field_begin,
        "section_index": section_index,
        "paragraph_index": paragraph_index,
        "paragraph_index_in_section": paragraph_index_in_section,
        "run_index": run_index,
        "child_index": child_index,
        "has_end": has_end,
        "parameters": parameters,
    }


def _iter_content_paragraphs(
    doc: "HwpxDocument",
) -> Iterator[tuple[int, int, int, Any, HwpxOxmlParagraph, list[Any]]]:
    """Every paragraph of the document in order, those in table cells and objects
    included: section index, paragraph index (over all of them), index among the
    section's own paragraphs (-1 for a nested one), the ``<hp:p>``, its view and
    its runs. Memo bodies are not content, and a header/footer python-hwpx keeps
    twice is walked once."""

    paragraph_index = 0
    for section_index, section in enumerate(doc.sections):
        direct_indexes = {
            paragraph.element: index
            for index, paragraph in enumerate(section.paragraphs)
        }
        # a header/footer python-hwpx keeps twice counts once: its hp:secPr copy
        twins = control_twins(section.element)

        def iter_content_paragraphs(element: Any) -> Iterator[Any]:
            for child in element:
                local = _local_name(child)
                if local == "memogroup" or child in twins:
                    continue
                if local == "p":
                    yield child
                yield from iter_content_paragraphs(child)

        for paragraph_element in iter_content_paragraphs(section.element):
            paragraph = HwpxOxmlParagraph(paragraph_element, section)
            runs = [child for child in paragraph_element if _local_name(child) == "run"]
            yield (
                section_index,
                paragraph_index,
                direct_indexes.get(paragraph_element, -1),
                paragraph_element,
                paragraph,
                runs,
            )
            paragraph_index += 1


def _iter_form_field_matches(doc: "HwpxDocument") -> list[dict[str, Any]]:
    return _iter_field_matches(doc, _is_form_field_begin)


def _iter_field_matches(doc: "HwpxDocument", accept: Any) -> list[dict[str, Any]]:
    return _field_matches_in(doc, accept, _iter_content_paragraphs(doc))


_CTRL_TAG, _RUN_TAG = f"{_HP}ctrl", f"{_HP}run"


def _form_field_begins(doc: "HwpxDocument") -> list[tuple[int, Any, int, Any, Any, Any]] | None:
    """Every form field's (section index, section, paragraph index, ``<hp:p>``, ``<hp:ctrl>``,
    ``<hp:fieldBegin>``) in the order of :func:`_iter_form_field_matches`, without reading their content.

    The same paragraphs as :func:`_iter_content_paragraphs` (in document order, memo bodies and the
    second copy of a header/footer left out) and the same begins as :func:`_field_matches_in` (a direct
    child of a ``ctrl`` that is a direct child of one of the paragraph's runs); lxml finds them, so a
    lookup costs little more than the number of fields. ``None`` for a tree that is not lxml's.
    """

    found: list[tuple[int, Any, int, Any, Any, Any]] = []
    offset = 0
    for section_index, section in enumerate(doc.sections):
        root = cast(Any, section.element)
        if not isinstance(root, etree._Element):
            return None
        # a header/footer kept twice needs a header or footer (control_twins reads every run)
        has_story = next(root.iter(f"{_HP}header", f"{_HP}footer"), None) is not None
        skipped = [*root.iter("{*}memogroup"), *(control_twins(root) if has_story else ())]
        excluded = {paragraph for skip in skipped for paragraph in skip.iter("{*}p")}
        positions: dict[Any, int] = {}
        for paragraph in root.iter("{*}p"):
            if paragraph is not root and paragraph not in excluded:
                positions[paragraph] = len(positions)
        fields: list[tuple[int, int, Any, Any, Any]] = []
        for order, begin in enumerate(root.iter(f"{_HP}fieldBegin")):
            ctrl = begin.getparent()
            if ctrl is None or (ctrl.tag != _CTRL_TAG and _local_name(ctrl) != "ctrl"):
                continue
            run = ctrl.getparent()
            if run is None or (run.tag != _RUN_TAG and _local_name(run) != "run"):
                continue
            paragraph = run.getparent()
            position = positions.get(paragraph)
            if position is not None and _is_form_field_begin(ctrl, begin):
                fields.append((position, order, paragraph, ctrl, begin))
        fields.sort(key=lambda field: (field[0], field[1]))
        found.extend(
            (section_index, section, offset + position, paragraph, ctrl, begin)
            for position, _order, paragraph, ctrl, begin in fields
        )
        offset += len(positions)
    return found


def _pick_form_field(
    doc: "HwpxDocument", *, index: int | None, field_id: str | None, name: str | None
) -> dict[str, Any] | None:
    """The match of the one field the selector names, read from that field's paragraph alone.

    ``None`` when the selector does not name exactly one field (or is not one selector): the full read
    (:func:`_select_form_field`) then decides and words the error. The result is the entry
    :func:`_iter_form_field_matches` would give for that field, so filling fields one after another
    does not read every field each time (#628).
    """

    if [index is not None, bool(field_id), bool(name)].count(True) != 1:
        return None
    begins = _form_field_begins(doc)
    if begins is None:
        return None
    if index is not None:
        picked = [position for position in range(len(begins)) if position == index]
    elif field_id:
        wanted = field_id.strip()
        picked = [
            position
            for position, (*_where, begin) in enumerate(begins)
            if wanted in {_field_identifier(begin), begin.get("id", ""), begin.get("fieldid", "")}
        ]
    else:
        wanted_name = (name or "").strip().casefold()
        if not wanted_name:
            return None
        picked = []
        for position, (*_where, begin) in enumerate(begins):
            # The name, prompt and instruction are attribute values or parameter text of the begin
            # (stripped), so a field whose attributes and text do not hold the name cannot match.
            text = etree.tostring(begin, method="text", encoding="unicode", with_tail=False)
            if wanted_name not in "\x00".join((*begin.attrib.values(), text)).casefold():
                continue
            keys = _form_field_selection_keys(begin)
            if keys[0] and wanted_name in {key.strip().casefold() for key in keys}:
                picked.append(position)
    if len(picked) != 1:
        return None
    section_index, section, paragraph_index, paragraph_element, _ctrl, field_begin = begins[picked[0]]
    # its place among the section's own paragraphs (``section.paragraphs``), -1 for a nested one
    own_index = -1
    if paragraph_element.getparent() is section.element:
        own_index = next(
            own for own, child in enumerate(section.element.iterchildren("{*}p")) if child is paragraph_element
        )
    source = (
        section_index, paragraph_index, own_index, paragraph_element,
        HwpxOxmlParagraph(paragraph_element, section),
        [child for child in paragraph_element if _local_name(child) == "run"],
    )
    found = _field_matches_in(doc, lambda _ctrl, begin: begin is field_begin, iter((source,)))
    if len(found) != 1:
        return None
    found[0]["index"] = picked[0]
    return found[0]


def _field_matches_in(
    doc: "HwpxDocument",
    accept: Any,
    paragraphs: Iterator[tuple[int, int, int, Any, HwpxOxmlParagraph, list[Any]]],
) -> list[dict[str, Any]]:
    """The fields whose ``<hp:fieldBegin>`` *accept(ctrl, field_begin)* takes, in
    document order, with their text up to the matching ``<hp:fieldEnd>``."""

    matches: list[dict[str, Any]] = []
    # where each paragraph is, for the end of a field running over paragraphs (made when one does)
    indexes: dict[Any, tuple[int, int]] | None = None
    for (
        section_index,
        paragraph_index,
        paragraph_index_in_section,
        paragraph_element,
        paragraph,
        runs,
    ) in paragraphs:
        for run_index, run in enumerate(runs):
            children = list(run)
            for child_index, child in enumerate(children):
                if _local_name(child) != "ctrl":
                    continue
                for field_begin in child.findall(f"{_HP}fieldBegin"):
                    if not accept(child, field_begin):
                        continue
                    end_position = _find_field_end_position(
                        doc,
                        runs,
                        begin_run_index=run_index,
                        begin_child_index=child_index,
                        field_begin=field_begin,
                    )
                    end_run_index: int | None = None
                    end_child_index: int | None = None
                    span = None
                    if end_position is not None:
                        end_run_index, end_child_index, _field_end = end_position
                    else:
                        span = _find_field_end_in_following_paragraphs(paragraph_element, field_begin)
                    text_nodes = _field_text_nodes(
                        doc,
                        runs,
                        begin_run_index=run_index,
                        begin_child_index=child_index,
                        end_run_index=end_run_index if span is None else len(runs) - 1,
                        end_child_index=end_child_index,
                    )
                    current_value = "".join(_text_node_value(node) for node in text_nodes)
                    all_text_nodes = list(text_nodes)
                    end_location: tuple[int, int, int, int, int] | None = None
                    if end_run_index is not None and end_child_index is not None:
                        end_location = (
                            section_index, paragraph_index, paragraph_index_in_section,
                            end_run_index, end_child_index,
                        )
                    if span is not None:
                        # the content goes on over paragraphs: their texts, one per line
                        end_paragraph, end_runs, span_run, span_child, middle = span
                        tail = _field_text_nodes(
                            doc,
                            end_runs,
                            begin_run_index=0,
                            begin_child_index=-1,
                            end_run_index=span_run,
                            end_child_index=span_child,
                        )
                        current_value = "\n".join(
                            [
                                current_value,
                                *(_run_texts([c for c in p if _local_name(c) == "run"]) for p in middle),
                                "".join(_text_node_value(node) for node in tail),
                            ]
                        )
                        all_text_nodes += [
                            node
                            for p in middle
                            for run in p
                            if _local_name(run) == "run"
                            for node in run
                            if _local_name(node) == "t"
                        ] + tail
                        if indexes is None:
                            indexes = {
                                element: (overall, own)
                                for _section, overall, own, element, _view, _runs in _iter_content_paragraphs(doc)
                            }
                        overall_index, own_index = indexes.get(end_paragraph, (-1, -1))
                        end_location = (section_index, overall_index, own_index, span_run, span_child)
                    payload = _form_field_payload(
                        doc,
                        index=len(matches),
                        section_index=section_index,
                        paragraph_index=paragraph_index,
                        paragraph_index_in_section=paragraph_index_in_section,
                        run_index=run_index,
                        child_index=child_index,
                        ctrl=child,
                        field_begin=field_begin,
                        current_value=current_value,
                        has_end=end_position is not None or span is not None,
                    )
                    payload["_paragraph"] = paragraph
                    payload["_runs"] = runs
                    payload["_begin_run_index"] = run_index
                    payload["_begin_child_index"] = child_index
                    payload["_end_run_index"] = end_run_index
                    payload["_end_child_index"] = end_child_index
                    payload["_text_nodes"] = text_nodes
                    payload["_all_text_nodes"] = all_text_nodes
                    payload["_end_location"] = end_location
                    payload["_span"] = span
                    matches.append(payload)
    return matches


def _refresh_form_field_match(doc: "HwpxDocument", match: Mapping[str, Any]) -> dict[str, Any]:
    """Re-read the selected field after filling it, without rebuilding unrelated payloads.

    Filling can remove nested fields or following paragraphs, but retains the selected begin and everything
    before it. Its paragraph location and field index therefore stay valid. Read its runs and matching end
    afresh: inserting text or collapsing a span can change their indices and the result's style snapshot.
    """

    paragraph = match["_paragraph"]
    source = (match["section_index"], match["paragraph_index"], match["paragraph_index_in_section"],
              paragraph.element, paragraph, [child for child in paragraph.element if _local_name(child) == "run"])
    refreshed = _field_matches_in(doc, lambda ctrl, begin: begin is match["_field_begin"], iter((source,)))[0]
    refreshed["index"] = match["index"]
    return refreshed


def _form_field_from_match(doc: "HwpxDocument", match: Mapping[str, Any]) -> FormField:
    """Build the public :class:`FormField` view from an internal match payload.

    Consolidates the id aliases (``id``/``fieldid``/``field_id`` →
    ``field_id``), the prompt aliases (``prompt``/``instruction`` →
    ``prompt``), and the type aliases (``field_type``/``control_type`` →
    ``field_type``) that 5.x exposed as separate dict keys (design §2.3).
    """

    location = _match_location(match)
    parameters = _match_parameters(match)
    field_begin = match["_field_begin"]
    # Left out, ``editable`` is the OWPML schema's default for hp:fieldBegin, true (7.0; 6.x read false).
    editable = (field_begin.get("editable") or "1").strip().lower() in {"1", "true"}
    end = match.get("_end_location")
    return FormField(
        doc,
        field_begin,
        field_id=match["field_id"],
        name=match["name"],
        prompt=match["prompt"],
        memo=match["memo"],
        editable=editable,
        value=match["current_value"],
        field_type=match["field_type"],
        is_placeholder=match["is_placeholder"],
        location=location,
        parameters=parameters,
        has_end=match["has_end"],
        paragraph=match.get("_paragraph"),
        end_location=None if end is None else FieldLocation(*end),
        text_elements=tuple(match.get("_all_text_nodes") or ()),
    )


def list_form_fields(doc: "HwpxDocument") -> tuple[FormField, ...]:
    """Return native form/click-here fields in document order.

    Every field in the document is listed. An unnamed field (an empty ``name``) is
    listed with an empty name and told apart by its id: :func:`fill_form_field`
    does not find it by name, as Hancom does not, but ``index`` and
    ``field_id`` reach it.
    """

    return tuple(_form_field_from_match(doc, match) for match in _iter_form_field_matches(doc))


def _match_location(match: Mapping[str, Any]) -> FieldLocation:
    return FieldLocation(
        section_index=match["section_index"],
        paragraph_index=match["paragraph_index"],
        paragraph_index_in_section=match["paragraph_index_in_section"],
        run_index=match["run_index"],
        child_index=match["child_index"],
    )


def _match_parameters(match: Mapping[str, Any]) -> tuple[FieldParameter, ...]:
    return tuple(
        FieldParameter(name=parameter.get("name", ""), value=parameter.get("value", ""))
        for parameter in match.get("parameters", [])
    )


def _field_type_is(field_type: str) -> Any:
    def accept(_ctrl: Any, field_begin: Any) -> bool:
        return (field_begin.get("type") or "").strip().upper() == field_type

    return accept


def _cell_address(element: Any) -> tuple[int, int] | None:
    """``(row, column)`` of the innermost table cell holding *element*, else ``None``."""

    node = element.getparent()
    while node is not None:
        if _local_name(node) == "tc":
            address = node.find(f"{_HP}cellAddr")
            if address is None:
                return None
            try:
                return int(address.get("rowAddr", "")), int(address.get("colAddr", ""))
            except ValueError:
                return None
        node = node.getparent()
    return None


def list_formula_fields(doc: "HwpxDocument") -> tuple[FormulaField, ...]:
    """Return the table formulas Hancom saved (``fieldBegin type="FORMULA"``), in
    document order, with the values Hancom wrote. Nothing is recomputed."""

    formulas: list[FormulaField] = []
    for match in _iter_field_matches(doc, _field_type_is("FORMULA")):
        parameters = match["parameters"]
        command = _field_parameter_value(parameters, "Command")
        formulas.append(
            FormulaField(
                field_id=match["field_id"],
                # Hancom also writes the formula as the head of its Command
                # ("=SUM(A1:A3)??%g,;;6"); read it there when Formula is absent.
                formula=_field_parameter_value(parameters, "Formula") or command.split("??", 1)[0],
                result_format=_field_parameter_value(parameters, "ResultFormat"),
                last_result=_field_parameter_value(parameters, "LastResult"),
                command=command,
                value=match["current_value"],
                location=_match_location(match),
                cell_address=_cell_address(match["_paragraph"].element),
                parameters=_match_parameters(match),
                element=match["_field_begin"],
            )
        )
    return tuple(formulas)


def list_bookmarks(doc: "HwpxDocument") -> tuple[Bookmark, ...]:
    """Return every bookmark in document order, in either form Hancom saves it
    (see :class:`~hwpx.objects.Bookmark`), those in table cells and objects included."""

    fields = {
        match["_field_begin"]: match
        for match in _iter_field_matches(doc, _field_type_is("BOOKMARK"))
    }
    bookmarks: list[Bookmark] = []
    for section_index, paragraph_index, paragraph_index_in_section, _p, _view, runs in _iter_content_paragraphs(doc):
        for run_index, run in enumerate(runs):
            for child_index, child in enumerate(run):
                if _local_name(child) != "ctrl":
                    continue
                location = FieldLocation(
                    section_index=section_index,
                    paragraph_index=paragraph_index,
                    paragraph_index_in_section=paragraph_index_in_section,
                    run_index=run_index,
                    child_index=child_index,
                )
                section = doc.sections[section_index]
                for mark in child:
                    if mark.tag == f"{_HP}bookmark":
                        name = mark.get("name", "")
                        if name:
                            bookmarks.append(Bookmark(name, "point", "", location, mark, section))
                    elif mark in fields:
                        name = (mark.get("name") or "").strip()
                        if name:
                            bookmarks.append(
                                Bookmark(name, "field", fields[mark]["current_value"], location, mark, section)
                            )
    return tuple(bookmarks)


def list_hyperlinks(doc: "HwpxDocument") -> tuple[Hyperlink, ...]:
    """Every hyperlink of the document in order, those in table cells, text boxes, notes,
    headers and footers included, as live :class:`~hwpx.objects.Hyperlink` views."""

    links: list[Hyperlink] = []
    for _section_index, _index, _in_section, _element, paragraph, runs in _iter_content_paragraphs(doc):
        for run in runs:
            for child in run:
                if _local_name(child) != "ctrl":
                    continue
                for mark in child.findall(f"{_HP}fieldBegin"):
                    if (mark.get("type") or "").strip().upper() == "HYPERLINK":
                        links.append(Hyperlink(mark, paragraph))
    return tuple(links)


def list_cross_references(doc: "HwpxDocument") -> tuple[CrossReference, ...]:
    """The cross references Hancom saved (``fieldBegin type="CROSSREF"``), in document
    order, with what each points at, read as written."""

    return tuple(
        CrossReference(doc, match["_field_begin"], _match_location(match))
        for match in _iter_field_matches(doc, _field_type_is("CROSSREF"))
    )


#: What a cross reference points at, what of it it shows and how it opens, by the code Hancom writes
#: for each in its ``Command`` (``<path>;<type>;<content>;<hyperlink>;<open>;``). The codes are those
#: Hancom Office 2024 reads out of an .hwp cross reference into these parameters (hwp5/section_xml.py).
_XREF_TYPES = ("TARGET_TABLE", "TARGET_PICTURE", "TARGET_EQUATION", "TARGET_FOOTNOTE", "TARGET_ENDNOTE",
               "TARGET_OUTLINE", "TARGET_BOOKMARK")
_XREF_CONTENTS = ("OBJECT_TYPE_PAGE", "OBJECT_TYPE_NUMBER", "OBJECT_TYPE_CONTENTS", "OBJECT_TYPE_UPDOWNPOS")
_XREF_OPEN = ("HWPHYPERLINK_JUMP_CURRENTTAB", "HWPHYPERLINK_JUMP_NEWTAB", "HWPHYPERLINK_JUMP_NEWWINDOW")
#: The parameters of a CROSSREF field in Hancom's order (``Fiexde`` is Hancom's spelling).
_XREF_PARAMS = (("booleanParam", "Fiexde"), ("integerParam", "Prop"), ("stringParam", "Command"),
                ("stringParam", "RefPath"), ("stringParam", "RefType"), ("stringParam", "RefContentType"),
                ("booleanParam", "RefHyperLink"), ("stringParam", "RefOpenType"))


def cross_reference_text(doc: "HwpxDocument", field_begin: Any) -> str:
    """What the cross reference shows now: the text between its begin and end."""

    from ..oxml.hyperlink_form import between_marks, field_end_in_paragraph

    paragraph = field_begin.getparent()
    while paragraph is not None and _local_name(paragraph) != "p":
        paragraph = paragraph.getparent()
    end = field_end_in_paragraph(paragraph, field_begin) if paragraph is not None else None
    if end is not None:  # the usual case: read it in its paragraph, not by walking the document
        return "".join(
            _text_node_value(child) for _run, child in between_marks(paragraph, field_begin, end)
            if _local_name(child) == "t"
        )
    try:
        return str(_match_for_begin(doc, field_begin)["current_value"])
    except HwpxValueError:
        return ""


def _xref_refuse(message: str, suggestion: str, **context: Any) -> HwpxValueError:
    return HwpxValueError(message, code="ref-cross-reference-target-unsupported", context=context or None,
                          suggestion=suggestion)


def _cross_reference_target(doc: "HwpxDocument", target: Any) -> tuple[str, str]:
    """``(RefPath without its ';', RefType)`` for *target*, as Hancom writes a cross reference to it.

    An outline paragraph is ``?#<paragraph id>`` (the Hancom-saved m7_toc_gold pair), a table
    ``?#<table id>`` and a bookmark ``?<name>`` (the cross references of Hancom-made public .hwp
    samples, as Hancom opens them). Nothing else has been seen in a Hancom file, so nothing else is
    written."""

    from ..oxml import HwpxOxmlParagraph, HwpxOxmlTable
    from ..objects.form_field import Bookmark

    if isinstance(target, HwpxOxmlTable):
        table_id = (target.element.get("id") or "").strip()
        if not table_id.isdigit() or not any(
            element is target.element for section in doc.sections for element in section.element.iter(f"{_HP}tbl")
        ):
            raise _xref_refuse("the table is not a numbered table of this document",
                               "Pass a table of this document (doc.tables).")
        return f"?#{table_id}", "TARGET_TABLE"
    if isinstance(target, HwpxOxmlParagraph):
        from ._resolve import resolve_paragraph

        paragraph = resolve_paragraph(doc, target, caller="cross reference target")
        if not paragraph.outline_level:
            raise _xref_refuse(
                "a cross reference points at an outline paragraph (개요), a bookmark or a table; "
                "this paragraph is none of them",
                "Make the paragraph a heading (doc.add_heading, paragraph.outline_level = 1), or put a "
                "bookmark on it (doc.refs.add_bookmark) and point at the bookmark.",
            )
        from ..tools.toc_author import ensure_paragraph_anchor_id

        before = paragraph.element.get("id")
        anchor = ensure_paragraph_anchor_id(doc, paragraph)  # Hancom finds it by a unique paragraph id
        if anchor != before:
            paragraph.section.mark_dirty()
        return f"?#{anchor}", "TARGET_OUTLINE"
    if isinstance(target, (Bookmark, str)):
        name = target.name if isinstance(target, Bookmark) else target.strip()
        if not name or ";" in name or name.startswith("#"):
            raise _xref_refuse(f"{name!r} cannot name a bookmark in a cross reference",
                               "Pass the name of a bookmark of this document (doc.refs.bookmarks).",
                               requested=name)
        if name not in {bookmark.name for bookmark in list_bookmarks(doc)}:
            raise _xref_refuse(f"this document has no bookmark named {name!r}",
                               "Add it first (doc.refs.add_bookmark), or pass a name from doc.refs.bookmarks.",
                               requested=name)
        return f"?{name}", "TARGET_BOOKMARK"
    raise _xref_refuse(
        f"a cross reference points at an outline paragraph, a bookmark or a table; got {type(target).__name__}",
        "Pass a heading paragraph, a bookmark (or its name) or a table of this document. Pictures, "
        "equations and notes are not written: python-hwpx has seen no Hancom file pointing at them.",
        requested=type(target).__name__,
    )


def _set_parameter(holder: Any, kind: str, name: str, value: str) -> None:
    for param in holder:
        if param.get("name") == name:
            if param.text != value:
                param.text = value
            return
    param = holder.makeelement(f"{_HP}{kind}", {"name": name})
    param.text = value
    order = [n for _k, n in _XREF_PARAMS]
    rank = order.index(name) if name in order else len(order)
    position = sum(1 for other in holder if other.get("name") in order[:rank])
    holder.insert(position, param)
    holder.set("cnt", str(len(holder)))


def _write_cross_reference(
    field_begin: Any, *, path: str, ref_type: str, content_type: str, hyperlink: bool
) -> None:
    """Write the CROSSREF parameters of *field_begin*: ``Command`` and the parameters it spells out."""

    holder = next((child for child in field_begin if _local_name(child) == "parameters"), None)
    if holder is None:
        holder = field_begin.makeelement(f"{_HP}parameters", {"cnt": "0", "name": ""})
        field_begin.insert(0, holder)
    open_type = next((p.text for p in holder if p.get("name") == "RefOpenType" and p.text in _XREF_OPEN),
                     _XREF_OPEN[0])
    command = (f"{path};{_XREF_TYPES.index(ref_type)};{_XREF_CONTENTS.index(content_type)};"
               f"{1 if hyperlink else 0};{_XREF_OPEN.index(open_type)};")
    for kind, name, value in (
        ("booleanParam", "Fiexde", next((p.text or "1" for p in holder if p.get("name") == "Fiexde"), "1")),
        ("integerParam", "Prop", next((p.text or "0" for p in holder if p.get("name") == "Prop"), "0")),
        ("stringParam", "Command", command),
        ("stringParam", "RefPath", f"{path};"),
        ("stringParam", "RefType", ref_type),
        ("stringParam", "RefContentType", content_type),
        ("booleanParam", "RefHyperLink", "true" if hyperlink else "false"),
        ("stringParam", "RefOpenType", open_type),
    ):
        _set_parameter(holder, kind, name, value)


def _empty_field_text(doc: "HwpxDocument", field_begin: Any) -> None:
    """Take out what lies between the field's begin and end (its shown text), in its paragraph."""

    match = _match_for_begin(doc, field_begin)
    if match.get("_end_run_index") is None:
        return
    _drop_field_content(match)
    _clear_paragraph_layout_cache(match["_paragraph"].element)


def _check_xref_choices(content_type: Any, hyperlink: Any) -> None:
    if content_type is not None and content_type not in _XREF_CONTENTS:
        raise HwpxValueError(
            f"content_type must be one of {', '.join(_XREF_CONTENTS)}; got {content_type!r}",
            code="ref-cross-reference-content-value",
            context={"requested": repr(content_type)},
            suggestion="OBJECT_TYPE_PAGE shows the page number, OBJECT_TYPE_NUMBER its number, "
            "OBJECT_TYPE_CONTENTS its text, OBJECT_TYPE_UPDOWNPOS above or below.",
        )
    if hyperlink is not None and not isinstance(hyperlink, bool):
        raise HwpxValueError(
            f"hyperlink must be True or False; got {hyperlink!r}",
            code="ref-cross-reference-hyperlink-value",
            context={"requested": repr(hyperlink)},
            suggestion="Pass True to jump to the target on a click, False not to.",
        )


def set_cross_reference(
    view: Any, *, target: Any = None, content_type: Any = None, hyperlink: Any = None
) -> None:
    """Change what the cross reference *view* points at, what it shows or whether it links. When
    the target or what is shown changes, the shown text is emptied for Hancom to fill in."""

    doc, begin = view._doc, view.element
    _check_xref_choices(content_type, hyperlink)
    old_path = view._parameter("RefPath")
    old_path = old_path[:-1] if old_path.endswith(";") else old_path
    old_type, old_content = view.ref_type, view.content_type
    path, ref_type = old_path, old_type
    if target is not None:
        path, ref_type = _cross_reference_target(doc, target)
    elif ref_type not in _XREF_TYPES or not path:
        raise _xref_refuse(
            f"the cross reference points at {ref_type or 'nothing'!r}, which python-hwpx does not write",
            "Point it at a heading paragraph, a bookmark or a table first (set_target).",
            ref_type=ref_type,
        )
    new_content = content_type if content_type is not None else (
        old_content if old_content in _XREF_CONTENTS else _XREF_CONTENTS[0])
    link = view.hyperlink if hyperlink is None else hyperlink
    if (path, ref_type, new_content, link) == (old_path, old_type, old_content, view.hyperlink):
        return
    _write_cross_reference(begin, path=path, ref_type=ref_type, content_type=new_content, hyperlink=link)
    if (path, ref_type, new_content) != (old_path, old_type, old_content):
        _empty_field_text(doc, begin)
    _match_for_begin(doc, begin)["_paragraph"].section.mark_dirty()


@refused_leaves_no_paragraph
def add_cross_reference(
    doc: "HwpxDocument",
    target: Any,
    *,
    content_type: str = "OBJECT_TYPE_PAGE",
    hyperlink: bool = False,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> CrossReference:
    """Append a cross reference to *target* at the end of *paragraph* (a new paragraph at the end of
    *section* when ``None``), written as Hancom writes one, and return it.

    It shows nothing yet: Hancom fills in the page, number or text when it lays the page out."""

    _check_xref_choices(content_type, hyperlink)
    path, ref_type = _cross_reference_target(doc, target)
    if paragraph is None:
        paragraph = home_paragraph(doc, "", section=section, include_run=False)
    from ..oxml._document_primitives import _object_id
    from ..oxml.field_marks import field_type_id

    ids = paragraph.section._ids  # the source of the document the reference goes into
    field_id = _object_id(ids)
    begin_run = paragraph._create_run_for_object()
    ctrl = begin_run.makeelement(f"{_HP}ctrl", {})
    begin_run.append(ctrl)
    begin = ctrl.makeelement(f"{_HP}fieldBegin", {
        "id": field_id, "type": "CROSSREF", "name": "", "editable": "0", "dirty": "0", "zorder": "-1",
        "fieldid": field_type_id("CROSSREF", ids=ids), "metaTag": "",
    })
    ctrl.append(begin)
    _write_cross_reference(begin, path=path, ref_type=ref_type, content_type=content_type, hyperlink=hyperlink)
    end_ctrl = begin_run.makeelement(f"{_HP}ctrl", {})
    end_ctrl.append(end_ctrl.makeelement(f"{_HP}fieldEnd", {"beginIDRef": field_id, "fieldid": begin.get("fieldid")}))
    begin_run.append(end_ctrl)
    paragraph.section.mark_dirty()
    return CrossReference(doc, begin, _match_location(_match_for_begin(doc, begin)))


def _named_cells(paragraphs: Any) -> Iterator[Any]:
    for paragraph in paragraphs:
        for table in paragraph.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.field_name:
                        yield cell
                    yield from _named_cells(cell.paragraphs)


def list_cell_fields(doc: "HwpxDocument") -> tuple[CellField, ...]:
    """Named table cells (Hancom's cell fields) in document order: body tables and the tables in their cells."""

    return tuple(CellField(cell) for section in doc.sections for cell in _named_cells(section.paragraphs))


def fill_cell_fields(doc: "HwpxDocument", value: str, *, name: str, index: int | None = None) -> tuple[CellField, ...]:
    """Set the text of every cell field called *name*, or of the *index*-th of them only."""

    wanted = (name or "").strip()
    fields = [field for field in list_cell_fields(doc) if wanted and field.name == wanted]
    if index is not None:
        fields = fields[index : index + 1] if index >= 0 else []
    if not fields:
        where = f"{wanted!r}" if index is None else f"{wanted!r} at index {index}"
        raise HwpxValueError(
            f"no cell field named {where}",
            code="field-cell-not-found",
            context={"name": wanted, "index": index},
            suggestion="List doc.fields.cells to see the cell field names.",
        )
    for field in fields:
        field.text = value
    return tuple(fields)


def list_text_box_fields(doc: "HwpxDocument") -> tuple[TextBoxField, ...]:
    """Named text boxes in document order: Hancom lists a text box whose ``hp:drawText``
    has a name among its fields (and leaves an unnamed one out)."""

    return tuple(
        TextBoxField(draw_text, section)
        for section in doc.sections
        for draw_text in section.element.iter(f"{_HP}drawText")
        if (draw_text.get("name") or "").strip()
    )


def fill_text_box_fields(
    doc: "HwpxDocument", value: str, *, name: str, index: int | None = None
) -> tuple[TextBoxField, ...]:
    """Set the text of every text box called *name*, or of the *index*-th of them only."""

    wanted = (name or "").strip()
    fields = [field for field in list_text_box_fields(doc) if wanted and field.name == wanted]
    if index is not None:
        fields = fields[index : index + 1] if index >= 0 else []
    if not fields:
        where = f"{wanted!r}" if index is None else f"{wanted!r} at index {index}"
        raise HwpxValueError(
            f"no text box named {where}",
            code="field-text-box-not-found",
            context={"name": wanted, "index": index},
            suggestion="List doc.fields.text_boxes to see the text box names.",
        )
    for field in fields:
        field.text = value
    return tuple(fields)


def text_box_text(draw_text: Any) -> str:
    """The text of a text box, a line per paragraph."""

    return "\n".join(
        "".join(_text_node_value(node) for node in paragraph.iter(f"{_HP}t"))
        for paragraph in draw_text.findall(f"{_HP}subList/{_HP}p")
    )


def set_text_box_text(draw_text: Any, section: Any, value: str) -> None:
    """Put *value* in a text box as Hancom fills a text box field: the box keeps its
    first paragraph and that paragraph's first run, which hold the value alone."""

    sub_list = draw_text.find(f"{_HP}subList")
    if sub_list is None:
        sub_list = draw_text.makeelement(f"{_HP}subList", {})
        draw_text.insert(0, sub_list)
    paragraphs = sub_list.findall(f"{_HP}p")
    first = paragraphs[0] if paragraphs else sub_list.makeelement(
        f"{_HP}p", {"id": "0", "paraPrIDRef": "0", "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"}
    )
    if not paragraphs:
        sub_list.append(first)
    for extra in paragraphs[1:]:
        sub_list.remove(extra)
    runs = first.findall(f"{_HP}run")
    run = runs[0] if runs else first.makeelement(f"{_HP}run", {"charPrIDRef": "0"})
    if not runs:
        first.insert(0, run)
    for extra in runs[1:]:
        first.remove(extra)
    for child in list(run):
        run.remove(child)
    text = run.makeelement(f"{_HP}t", {})
    run.append(text)
    _write_text_node(text, value)
    _clear_form_field_layout_cache(first)
    section.mark_dirty()


_PROMPT_TEXT_COLOR = "#FF0000"


@refused_leaves_no_paragraph
def add_form_field(
    doc: "HwpxDocument",
    name: str,
    *,
    prompt: str = "",
    memo: str = "",
    editable: bool = True,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> FormField:
    """Create a click-here (누름틀) form field and return it as a :class:`FormField`.

    The emitted XML follows the real-Hancom CLICKHERE contract
    (inferred from Hancom Office 12.0.0.3288 gold documents). The
    prompt (안내문) is materialized as a screen-only red-italic run, exactly as
    Hancom authors it. The created field is immediately re-read through the
    standard ``list_form_fields`` matcher — creation fails loudly if the
    standard consumer would not recognize it (no special-casing by design).
    """

    if not isinstance(name, str):
        raise argument_type_error("name", name, "str", suggestion="양식에서 이 칸을 가리킬 이름을 글로 주세요.")
    if not name.strip():
        raise HwpxValueError(
            "누름틀 이름은 비어 있을 수 없습니다.",
            code="field-name-empty",
            suggestion="양식에서 이 칸을 가리킬 이름을 지정하세요.",
        )
    for argument, value in (("prompt", prompt), ("memo", memo)):
        if not isinstance(value, str):
            raise argument_type_error(argument, value, "str")
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section, include_run=False,
        )

    prompt_char_pr: str | None = None
    if _sanitize_field_text(prompt):
        # `doc._root.ensure_run_style` rather than `doc.ensure_run_style` —
        # that facade name moved in 6.0 (design table row 52); the facade
        # method is a pure passthrough to `_root`, so this is byte-identical
        # minus the DeprecationWarning it would otherwise fire on every
        # `add_form_field` call.
        prompt_char_pr = doc._root.ensure_run_style(italic=True, color=_PROMPT_TEXT_COLOR)

    control = paragraph.add_form_field(
        name,
        prompt=prompt,
        memo=memo,
        editable=editable,
        prompt_char_pr_id_ref=prompt_char_pr,
    )
    _clear_form_field_layout_cache(paragraph.element)

    field_begin = control.element  # paragraph.add_form_field gives the FormField: its element is the fieldBegin
    created_id = field_begin.get("id", "") if field_begin is not None else ""
    for match in _iter_form_field_matches(doc):
        if match.get("id") == created_id:
            return _form_field_from_match(doc, match)
    raise HwpxStateError(
        "created form field was not recognized by the standard form-field matcher",
        code="field-not-created",
        suggestion="Check that this document has a standard form-field structure.",
    )


_CHECK_BOX_TAG = f"{_HP}checkBtn"


def _iter_check_boxes(doc: "HwpxDocument") -> list[dict[str, Any]]:
    """Every ``<hp:checkBtn>`` in document order, with its owning element."""

    found: list[dict[str, Any]] = []
    index = 0
    for section_index, section in enumerate(doc.sections):
        for element in section.element.iter(_CHECK_BOX_TAG):
            found.append(
                {
                    "index": index,
                    "sectionIndex": section_index,
                    "name": element.get("name", ""),
                    "caption": element.get("caption", ""),
                    "checked": element.get("value", "").upper() == "CHECKED",
                    "value": element.get("value", ""),
                    "_element": element,
                    "_section": section,
                }
            )
            index += 1
    return found


def _check_box_from_match(match: Mapping[str, Any]) -> CheckBox:
    element = match["_element"]
    section = match["_section"]
    return CheckBox(
        element,
        section,
        _owning_paragraph(element, section),
        index=match["index"],
    )


def list_check_boxes(doc: "HwpxDocument") -> tuple[CheckBox, ...]:
    """Return check-box form objects in document order."""

    return tuple(_check_box_from_match(match) for match in _iter_check_boxes(doc))


@refused_leaves_no_paragraph
def add_check_box(
    doc: "HwpxDocument",
    caption: str,
    *,
    checked: bool = False,
    name: str | None = None,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> CheckBox:
    """Create a check-box form object and return it as a :class:`CheckBox`.

    The emitted XML follows the check-box contract measured against real
    Hancom (specs/060): ``value`` selects ☑/□ and the ``<hp:formCharPr>`` child
    is mandatory — without it Hancom refuses the document. The created object is
    re-read through the standard :func:`list_check_boxes` reader, so creation
    fails loudly if the ordinary consumer would not see it.
    """

    if not isinstance(caption, str):
        raise argument_type_error("caption", caption, "str", suggestion="Pass the caption printed next to the box.")
    if name is not None and not isinstance(name, str):
        raise argument_type_error("name", name, "str or None")
    if not caption.strip():
        raise HwpxValueError(
            "check box caption must be a non-empty string",
            code="field-checkbox-caption-empty",
            suggestion="Pass the caption printed next to the box.",
        )
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section, include_run=False,
        )

    control = paragraph.add_check_box(caption, checked=checked, name=name)
    _clear_form_field_layout_cache(paragraph.element)

    created_name = control.element.get("name", "")
    for match in _iter_check_boxes(doc):
        if match["_element"] is control.element:
            return _check_box_from_match(match)
    raise HwpxStateError(
        f"created check box {created_name!r} was not recognized by the standard reader",
        code="field-checkbox-not-created",
        context={"name": created_name},
        suggestion="Check that this document has a standard check-box structure.",
    )


def set_check_box(
    doc: "HwpxDocument",
    checked: bool,
    *,
    index: int | None = None,
    name: str | None = None,
) -> CheckBox:
    """Set a check box's state, selecting it by ``index`` or ``name``.

    Exactly one selector is required — an ambiguous or missing selector is a
    typed refusal, never a guess.
    """

    if (index is None) == (name is None):
        raise HwpxValueError(
            "provide exactly one of index or name",
            code="field-selector-conflict",
            suggestion="List doc.fields.check_boxes to see the candidates.",
        )
    matches = _iter_check_boxes(doc)
    if index is not None:
        chosen = [m for m in matches if m["index"] == index]
        if not chosen:
            raise HwpxValueError(
                f"check box index not found: {index}",
                code="field-checkbox-not-found",
                context={"requested": index, "count": len(matches)},
                suggestion="List doc.fields.check_boxes to see the candidates.",
            )
    else:
        wanted = str(name).strip()
        chosen = [m for m in matches if m["name"] == wanted]
        if not chosen:
            raise HwpxValueError(
                f"check box name not found: {wanted}",
                code="field-checkbox-not-found",
                context={"requested": wanted, "count": len(matches)},
                suggestion="List doc.fields.check_boxes to see the candidates.",
            )
        if len(chosen) > 1:
            raise HwpxValueError(
                f"check box name is ambiguous ({len(chosen)} matches): {wanted}",
                code="field-checkbox-ambiguous",
                context={"requested": wanted, "matches": len(chosen)},
                suggestion="Pass index= to pick one.",
            )
    match = chosen[0]
    match["_element"].set("value", "CHECKED" if checked else "UNCHECKED")
    match["_section"].mark_dirty()
    return _check_box_from_match(match)


def _select_form_field(
    doc: "HwpxDocument",
    matches: Sequence[dict[str, Any]],
    *,
    index: int | None,
    field_id: str | None,
    name: str | None,
) -> dict[str, Any]:
    selectors = [index is not None, bool(field_id), bool(name)]
    if selectors.count(True) != 1:
        raise HwpxValueError(
            "provide exactly one of index, field_id, or name",
            code="field-selector-conflict",
            suggestion="List doc.fields.all to see the candidates.",
        )
    if index is not None:
        for match in matches:
            if match["index"] == index:
                return match
        indexes = sorted(int(match["index"]) for match in matches)
        where = (
            f"the document has {len(indexes)} form fields, index {indexes[0]}..{indexes[-1]}"
            if indexes
            else "the document has no form fields"
        )
        raise HwpxValueError(
            f"form field index not found: {index} ({where})",
            code="field-not-found",
            context={"requested": index, "count": len(indexes), "indexes": indexes[:50]},
            suggestion="List doc.fields.all to see the candidates.",
        )
    if field_id:
        wanted = field_id.strip()
        candidates = [
            match
            for match in matches
            if wanted in {match.get("field_id"), match.get("id"), match.get("fieldid")}
        ]
    else:
        wanted_name = (name or "").strip().casefold()
        candidates = [
            match
            for match in matches
            if wanted_name
            and match.get("name")
            and wanted_name
            in {
                str(match.get("name", "")).strip().casefold(),
                str(match.get("prompt", "")).strip().casefold(),
                str(match.get("instruction", "")).strip().casefold(),
            }
        ]
    if not candidates:
        selector = f"field_id={field_id!r}" if field_id else f"name={name!r}"
        if field_id:
            known = [str(match.get("field_id") or match.get("id") or "") for match in matches]
        else:
            known = [str(match.get("name") or "") for match in matches]
        known = list(dict.fromkeys(item for item in known if item))
        if known:
            shown = ", ".join(repr(item) for item in known[:10]) + (", ..." if len(known) > 10 else "")
            where = f"the document has: {shown}"
        else:
            where = "the document has no named form fields" if matches else "the document has no form fields"
        raise HwpxValueError(
            f"form field not found: {selector} ({where})",
            code="field-not-found",
            context={"selector": str(selector), "candidates": known[:50], "count": len(matches)},
            suggestion="List doc.fields.all to see the candidates.",
        )
    if len(candidates) > 1:
        labels = [candidate.get("name") or candidate.get("field_id") for candidate in candidates]
        raise HwpxValueError(
            f"form field selector is ambiguous: {labels}",
            code="field-ambiguous",
            context={"candidates": list(labels) if isinstance(labels, (list, tuple)) else str(labels)},
            suggestion="Pass index= to pick one.",
        )
    return candidates[0]


def _field_run_style_snapshot(
    doc: "HwpxDocument",
    runs: Sequence[Any],
    *,
    begin_run_index: int,
    end_run_index: int | None,
) -> list[str | None]:
    last_run = end_run_index if end_run_index is not None else begin_run_index
    return [runs[index].get("charPrIDRef") for index in range(begin_run_index, last_run + 1)]


def _insert_form_field_text_run(
    doc: "HwpxDocument",
    match: dict[str, Any],
    value: str,
) -> None:
    # A field may begin and end within one run. A run index is not a
    # paragraph-child insertion point, and inserting before the end run can
    # put the value before fieldBegin. Insert the text immediately after the
    # actual begin control, retaining its surrounding run and character style.
    runs: list[Any] = match["_runs"]
    begin_run = runs[int(match["_begin_run_index"])]
    text_node = begin_run.makeelement(f"{_HP}t", {})
    _write_text_node(text_node, _sanitize_field_text(value))
    begin_run.insert(int(match["_begin_child_index"]) + 1, text_node)


def _value_char_shape(
    doc: "HwpxDocument", match: Mapping[str, Any], char_pr_id_ref: object, fit: object
) -> str:
    """The checked ``fields.fill(char_pr_id_ref=)``: a character shape of the document's header, not
    together with *fit* (which sets the value's shape itself)."""

    selector = {"name": match.get("name"), "index": match.get("index")}
    if fit is not None:
        raise HwpxValueError(
            "fields.fill takes char_pr_id_ref= or fit=, not both: fit gives the value its own character shape",
            code="field-fill-char-shape-conflict",
            context=selector,
            suggestion="Fill with char_pr_id_ref= and leave fit out, or let fit shrink the begin run's shape.",
        )
    key = "" if isinstance(char_pr_id_ref, bool) or not isinstance(char_pr_id_ref, (str, int)) else str(char_pr_id_ref).strip()
    if not key or doc.oxml.char_property(key) is None:
        raise HwpxValueError(
            f"char_pr_id_ref {char_pr_id_ref!r} is not a character shape of this document",
            code="field-char-pr-not-found",
            context={**selector, "charPrIDRef": repr(char_pr_id_ref)},
            suggestion="Pass an id from doc.styles.char_properties, or make one with doc.styles.ensure_run(...).",
        )
    return key


def _give_value_char_shape(text_nodes: Sequence[Any], char_pr_id_ref: str) -> None:
    """Give the field's value (its ``hp:t`` *text_nodes*) the character shape *char_pr_id_ref*.

    A run holding nothing but the value takes it. A run holding the value beside other children (the
    field's begin or end, text before or after the field) is cut between children into runs of the
    same attributes, and only the value's pieces take the shape: the rest keep theirs.
    """

    value = {id(node) for node in text_nodes}
    runs: list[Any] = []
    for node in text_nodes:
        run = node.getparent()
        if run is not None and all(run is not seen for seen in runs):
            runs.append(run)
    for run in runs:
        children = list(run)
        if all(id(child) in value for child in children):
            run.set("charPrIDRef", char_pr_id_ref)
            continue
        groups: list[tuple[bool, list[Any]]] = []
        for child in children:
            inside = id(child) in value
            if groups and groups[-1][0] == inside:
                groups[-1][1].append(child)
            else:
                groups.append((inside, [child]))
        parent, attributes = run.getparent(), dict(run.attrib)
        at = parent.index(run)
        for offset, (inside, members) in enumerate(groups):
            piece = run if offset == 0 else run.makeelement(run.tag, dict(attributes))
            for member in members:
                piece.append(member)  # moves it out of the run it was in, in order
            if inside:
                piece.set("charPrIDRef", char_pr_id_ref)
            if offset:
                parent.insert(at + offset, piece)


def _drop_nested_fields(match: Mapping[str, Any]) -> None:
    """Hancom's way with a field that holds other fields: the value replaces
    them with the rest of the content, so the begin and end of every field
    lying wholly between this field's begin and end go."""

    runs: list[Any] = match["_runs"]
    end_run_index = match.get("_end_run_index")
    if end_run_index is None:
        return
    begin_run_index = int(match["_begin_run_index"])
    inside: list[tuple[Any, Any]] = []
    for run_index in range(begin_run_index, int(end_run_index) + 1):
        children = list(runs[run_index])
        start = int(match["_begin_child_index"]) + 1 if run_index == begin_run_index else 0
        stop = int(match["_end_child_index"]) if run_index == end_run_index else len(children)
        inside.extend((runs[run_index], child) for child in children[start:stop] if _local_name(child) == "ctrl")
    begun = {mark.get("id") for _, ctrl in inside for mark in ctrl.findall(f"{_HP}fieldBegin")}
    ended = {mark.get("beginIDRef") for _, ctrl in inside for mark in ctrl.findall(f"{_HP}fieldEnd")}
    nested = (begun & ended) - {None, ""}
    for run, ctrl in inside:
        marks = [(mark.get("id") if _local_name(mark) == "fieldBegin" else mark.get("beginIDRef"))
                 for mark in ctrl if _local_name(mark) in ("fieldBegin", "fieldEnd")]
        if marks and all(mark in nested for mark in marks):
            run.remove(ctrl)


def _collapse_field_span(match: Mapping[str, Any]) -> None:
    """Hancom's way with a field whose content runs over paragraphs: the
    content between the begin and the end goes, paragraphs and all, and the
    end with the rest of its paragraph joins the begin's paragraph."""

    end_paragraph, end_runs, end_run_index, end_child_index, middle = match["_span"]
    paragraph_element = match["_paragraph"].element
    runs: list[Any] = match["_runs"]
    begin_run_index = int(match["_begin_run_index"])
    begin_run = runs[begin_run_index]
    for child in list(begin_run)[int(match["_begin_child_index"]) + 1 :]:
        begin_run.remove(child)
    for run in runs[begin_run_index + 1 :]:
        paragraph_element.remove(run)
    for element in middle:
        element.getparent().remove(element)
    end_run = end_runs[end_run_index]
    moved = end_run.makeelement(end_run.tag, dict(end_run.attrib))
    for child in list(end_run)[end_child_index:]:
        moved.append(child)
    position = paragraph_element.index(begin_run) + 1
    for offset, run in enumerate([moved, *end_runs[end_run_index + 1 :]]):
        paragraph_element.insert(position + offset, run)
    end_paragraph.getparent().remove(end_paragraph)


def fill_form_field(
    doc: "HwpxDocument",
    value: str,
    *,
    index: int | None = None,
    field_id: str | None = None,
    name: str | None = None,
    fit: "FitPolicy | None" = None,
    box_width: int | None = None,
    font_pt: float | None = None,
    char_pr_id_ref: str | int | None = None,
) -> FieldFillResult:
    """Fill a native form/click-here field while preserving surrounding runs.

    When *fit* cannot be satisfied (a hard overflow), this raises
    ``HwpxValueError(code="field-fit-failed")`` *before* touching the XML —
    fail-closed (constitution VI) rather than 5.x's ``ok: bool`` key, which
    reported the failure and still wrote the overflowing value.

    *char_pr_id_ref* gives the value that character shape instead of the one of the run holding
    the field's begin (see :meth:`hwpx._document.ns.fields.FieldsNamespace.fill`).
    """

    if value is None:  # str(None) would put the word "None" in the form
        raise argument_type_error(
            "value", value, "str", suggestion='To empty the field pass "": doc.fields.fill("", name=...).'
        )
    if not isinstance(value, (str, numbers.Number)) or isinstance(value, bool):
        # str() of a list, a dict or True puts Python's spelling of it in the form (#811); a number keeps its digits
        raise argument_type_error(
            "value", value, "str or a number",
            suggestion="Pass the text the field should show, e.g. \", \".join(items) for a list.",
        )
    match = _pick_form_field(doc, index=index, field_id=field_id, name=name)
    if match is None:
        match = _select_form_field(
            doc,
            _iter_form_field_matches(doc),
            index=index,
            field_id=field_id,
            name=name,
        )
    if not match.get("has_end"):
        raise HwpxValueError(
            f"the field {match.get('name') or match.get('index')!r} has no end, so it has no content to replace",
            code="field-end-missing",
            context={"name": match.get("name"), "index": match.get("index")},
            suggestion="Hancom leaves such a field unchanged too; give it an end or remove it.",
        )
    value_char = None if char_pr_id_ref is None else _value_char_shape(doc, match, char_pr_id_ref, fit)
    paragraph = match["_paragraph"]
    runs = match["_runs"]
    before_value = str(match.get("current_value", ""))
    before_style = _field_run_style_snapshot(
        doc,
        runs,
        begin_run_index=int(match["_begin_run_index"]),
        end_run_index=match.get("_end_run_index"),
    )

    fit_result = None
    write_value = str(value)
    if fit is not None:
        fit_result = _measure_form_field_fit(
            doc, str(value), match, fit, box_width, font_pt
        )
        if not fit_result.ok:
            selector = f"index={index!r}" if field_id is None and name is None else (
                f"field_id={field_id!r}" if field_id is not None else f"name={name!r}"
            )
            raise HwpxValueError(
                f"value does not fit the field ({selector}) within the given FitPolicy",
                code="field-fit-failed",
                context={
                    "fit": fit_result.to_dict(),
                    "suggestedRetry": fit_result.suggested_retry(),
                },
                suggestion=(
                    "Widen the field, shorten the value, or relax the FitPolicy "
                    "(e.g. mode='shrink' with a lower min_font_pt)."
                ),
            )
        write_value = fit_result.applied_value

    text_nodes: list[Any] = match.get("_text_nodes", [])
    sanitized = _sanitize_field_text(write_value)
    if match.get("_span") is None:
        _drop_nested_fields(match)
    if match.get("_span") is not None:
        _collapse_field_span(match)
        _insert_form_field_text_run(doc, match, sanitized)
    elif text_nodes:
        primary = text_nodes[0]
        _write_text_node(primary, sanitized)
        for node in text_nodes[1:]:
            _write_text_node(node, "")
        # Hancom writes the value in the shape of the run holding the field's
        # begin, whatever shape the old value or the screen-only prompt had.
        begin_run = runs[int(match["_begin_run_index"])]
        begin_ref = begin_run.get("charPrIDRef")
        primary_run = primary.getparent()
        if begin_ref is not None and primary_run is not None:
            primary_run.set("charPrIDRef", begin_ref)
    else:
        _insert_form_field_text_run(doc, match, sanitized)

    # Contract (P0 gold): a field that went through fill machinery carries
    # dirty="1"; while dirty != "1" readers treat the content as the prompt.
    field_begin = match.get("_field_begin")
    if field_begin is not None:
        field_begin.set("dirty", "1")

    if fit_result is not None:
        _apply_form_field_fit_style(doc, match, fit_result)
    if value_char is not None:
        _give_value_char_shape(_refresh_form_field_match(doc, match).get("_text_nodes", []), value_char)

    _clear_form_field_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()
    updated = _refresh_form_field_match(doc, match)
    after_style = _field_run_style_snapshot(
        doc,
        updated["_runs"],
        begin_run_index=int(updated["_begin_run_index"]),
        end_run_index=updated.get("_end_run_index"),
    )
    after_value = str(updated.get("current_value", ""))
    return FieldFillResult(
        field=_form_field_from_match(doc, updated),
        before=before_value,
        after=after_value,
        style_preserved=before_style == after_style[: len(before_style)],
        style_before=tuple(ref or "" for ref in before_style),
        style_after=tuple(ref or "" for ref in after_style),
        fit=fit_result,
    )


def _match_for_begin(doc: "HwpxDocument", field_begin: Any) -> dict[str, Any]:
    """The match of the field whose ``<hp:fieldBegin>`` is *field_begin*, read afresh."""

    for match in _field_matches_in(doc, lambda _ctrl, begin: begin is field_begin, _iter_content_paragraphs(doc)):
        return match
    raise HwpxValueError(
        "the field is no longer in the document",
        code="field-not-found",
        suggestion="List doc.fields.all again to get the current fields.",
    )


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


_CLICK_HERE_HEAD = re.compile(r"^Clickhere:set:\d+:")
_CLICK_HERE_ENTRY = re.compile(r"([A-Za-z]+):([A-Za-z]+):(\d+):")


def _click_here_entries(command: str) -> list[list[str]] | None:
    """The ``name:type:length:value`` entries of a click-here ``Command`` string, or
    ``None`` when it is not one. Lengths count UTF-16 units, as Hancom writes them."""

    head = _CLICK_HERE_HEAD.match(command)
    if head is None:
        return None
    entries: list[list[str]] = []
    position = head.end()
    while position < len(command):
        if command[position] == " ":
            position += 1
            continue
        found = _CLICK_HERE_ENTRY.match(command, position)
        if found is None:
            return None
        start, units = found.end(), int(found.group(3))
        end = start
        while end < len(command) and _utf16_length(command[start:end]) < units:
            end += 1
        entries.append([found.group(1), found.group(2), command[start:end]])
        position = end
    return entries


def _click_here_command(entries: Sequence[Sequence[str]]) -> str:
    payload = "".join(f"{name}:{kind}:{_utf16_length(value)}:{value} " for name, kind, value in entries)
    return f"Clickhere:set:{_utf16_length(payload)}:{payload} "


def _set_click_here_parameter(field_begin: Any, name: str, value: str) -> None:
    """Write *value* as the field's *name* parameter (``Direction`` or ``HelpState``):
    its own string parameter (left out when empty, as Hancom writes it) and its entry in
    the ``Command`` string."""

    parameters = field_begin.find(f"{_HP}parameters")
    if parameters is None:
        parameters = field_begin.makeelement(f"{_HP}parameters", {"cnt": "0", "name": ""})
        field_begin.insert(0, parameters)
    params = {param.get("name"): param for param in parameters}
    command = params.get("Command")
    if command is not None:
        entries = _click_here_entries(command.text or "")
        if entries is not None:
            for entry in entries:
                if entry[0] == name:
                    entry[2] = value
                    break
            else:
                entries.append([name, "wstring", value])
            command.text = _click_here_command(entries)
    param = params.get(name)
    if value:
        if param is None:
            param = parameters.makeelement(f"{_HP}stringParam", {"name": name})
            parameters.append(param)
        param.text = value
    elif param is not None:
        parameters.remove(param)
    parameters.set("cnt", str(len(parameters)))


_UNSET: Any = object()


def update_form_field(
    doc: "HwpxDocument",
    field_begin: Any,
    *,
    name: Any = _UNSET,
    prompt: Any = _UNSET,
    memo: Any = _UNSET,
    editable: Any = _UNSET,
) -> FormField:
    """Change a click-here field's name, 안내문 (*prompt*), memo or editable setting, as
    Hancom's field dialog does, and return the field read afresh.

    A prompt the field shows because nothing was entered yet (``dirty`` is not set)
    is shown anew; a value someone entered stays.
    """

    from ..oxml.field_marks import check_click_here_text

    if prompt is not _UNSET:
        check_click_here_text(prompt=str(prompt))
    if memo is not _UNSET:
        check_click_here_text(memo=str(memo))
    match = _match_for_begin(doc, field_begin)
    paragraph = match["_paragraph"]
    if name is not _UNSET:
        field_begin.set("name", _sanitize_field_text(str(name)).strip())
    if editable is not _UNSET:
        field_begin.set("editable", "1" if editable else "0")
    if memo is not _UNSET:
        _set_click_here_parameter(field_begin, "HelpState", _sanitize_field_text(str(memo)))
    if prompt is not _UNSET:
        new_prompt = _sanitize_field_text(str(prompt))
        showing_prompt = match["dirty"] != "1" and (match["is_placeholder"] or not match["current_value"])
        _set_click_here_parameter(field_begin, "Direction", new_prompt)
        if showing_prompt and match["has_end"] and match.get("_span") is None:
            text_nodes = match.get("_text_nodes", [])
            if text_nodes:
                _write_text_node(text_nodes[0], new_prompt)
                for node in text_nodes[1:]:
                    _write_text_node(node, "")
            elif new_prompt:
                _insert_form_field_text_run(doc, match, new_prompt)
            _clear_paragraph_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()
    return _form_field_from_match(doc, _match_for_begin(doc, field_begin))


def _remove_mark(mark: Any) -> None:
    """Take a field's begin or end out: the mark, the ``hp:ctrl`` it leaves empty, and the
    run left empty by that when its paragraph keeps another run."""

    ctrl = mark.getparent()
    if ctrl is None:
        return
    ctrl.remove(mark)
    if _local_name(ctrl) != "ctrl" or len(ctrl):
        return
    run = ctrl.getparent()
    if run is None:
        return
    run.remove(ctrl)
    paragraph = run.getparent()
    if not len(run) and paragraph is not None and len([c for c in paragraph if _local_name(c) == "run"]) > 1:
        paragraph.remove(run)


def _field_end_of(match: Mapping[str, Any]) -> Any:
    field_begin = match["_field_begin"]
    if match.get("_end_run_index") is not None:
        ctrl = list(match["_runs"][int(match["_end_run_index"])])[int(match["_end_child_index"])]
    elif match.get("_span") is not None:
        _end_paragraph, end_runs, span_run, span_child, _middle = match["_span"]
        ctrl = list(end_runs[span_run])[span_child]
    else:
        return None
    for field_end in ctrl.findall(f"{_HP}fieldEnd"):
        if _field_end_matches(field_begin, field_end):
            return field_end
    return None


def _drop_field_content(match: Mapping[str, Any]) -> None:
    """Remove what lies between a field's begin and its end in one paragraph."""

    runs: list[Any] = match["_runs"]
    begin_run_index = int(match["_begin_run_index"])
    end_run_index = int(match["_end_run_index"])
    for run_index in range(begin_run_index, end_run_index + 1):
        run = runs[run_index]
        children = list(run)
        start = int(match["_begin_child_index"]) + 1 if run_index == begin_run_index else 0
        stop = int(match["_end_child_index"]) if run_index == end_run_index else len(children)
        for child in children[start:stop]:
            run.remove(child)
    paragraph = match["_paragraph"].element
    for run in runs[begin_run_index + 1 : end_run_index]:
        if not len(run):
            paragraph.remove(run)


def remove_form_field(doc: "HwpxDocument", field_begin: Any, *, keep_text: bool = True) -> None:
    """Remove a field: its begin and end go, and with them what lies between unless
    *keep_text* (then the field's text stays as plain text, as Hancom's "누름틀 지우기"
    leaves it). A field running over paragraphs loses those paragraphs with its
    content, and the end's paragraph joins the begin's. The paragraphs are laid out
    again."""

    match = _match_for_begin(doc, field_begin)
    paragraph = match["_paragraph"]
    touched = [paragraph.element]
    if not keep_text and match["has_end"]:
        if match.get("_span") is not None:
            _collapse_field_span(match)
            match = _refresh_form_field_match(doc, match)
        _drop_field_content(match)
        match = _refresh_form_field_match(doc, match)
    elif match.get("_span") is not None:
        touched.append(match["_span"][0])
    field_end = _field_end_of(match)
    _remove_mark(field_begin)
    if field_end is not None:
        _remove_mark(field_end)
    for element in touched:
        _clear_paragraph_layout_cache(element)
    paragraph.section.mark_dirty()


_FORM_OBJECT_TAGS = {"radioBtn", "comboBox", "edit"}


def _iter_form_objects(doc: "HwpxDocument", local: str) -> list[tuple[Any, Any, int]]:
    found: list[tuple[Any, Any, int]] = []
    for section in doc.sections:
        for element in section.element.iter(f"{_HP}{local}"):
            found.append((element, section, len(found)))
    return found


def list_form_objects(doc: "HwpxDocument", local: str) -> tuple[Any, ...]:
    """The document's radio buttons, combo boxes, edit boxes or command buttons (*local* is the
    element's name), in document order, as live views."""

    from ..objects.checkbox import Button, ComboBox, EditBox, RadioButton

    cls: Any = {"radioBtn": RadioButton, "comboBox": ComboBox, "edit": EditBox, "btn": Button}[local]
    return tuple(
        cls(element, section, _owning_paragraph(element, section), index=index)
        for element, section, index in _iter_form_objects(doc, local)
    )


#: A new form object as Hancom writes one (the Hancom-saved ``reader_writer__SimpleButtons``,
#: ``SimpleComboBox`` and ``SimpleEdit`` samples, and the form objects of the Hancom-made public
#: samples ``form-01.hwp``/``form-02.hwp`` as Hancom opens them): the kind's own attributes in
#: Hancom's order with their values for a new object, then its colours, border type and size. The
#: attributes every form object has follow the kind's own, as in those samples. A new edit box
#: masks nothing (``passwordChar=""``, the schema's ``*`` is not what Hancom writes).
_FORM_OWN_ATTRIBUTES: dict[str, tuple[tuple[str, str], ...]] = {
    "radioBtn": (("caption", ""), ("value", "UNCHECKED"), ("radioGroupName", ""), ("triState", "0"),
                 ("backStyle", "OPAQUE")),
    "comboBox": (("listBoxRows", "10"), ("listBoxWidth", "0"), ("editEnable", "1"), ("selectedValue", "")),
    "edit": (("multiLine", "0"), ("passwordChar", ""), ("maxLength", "2147483647"), ("scrollBars", "NONE"),
             ("tabKeyBehavior", "NEXT_OBJECT"), ("numOnly", "0"), ("readOnly", "0"), ("alignText", "LEFT")),
}
#: foreColor, backColor, borderTypeIDRef, width and height (HWPUNIT) of a new one.
_FORM_LOOK: dict[str, tuple[str, str, str, int, int]] = {
    "radioBtn": ("#000000", "#FFFFFF", "0", 8504, 1984),
    "comboBox": ("#000000", "#F0F0F0", "5", 9921, 1984),
    "edit": ("#000000", "#F0F0F0", "5", 7087, 1984),
}
#: The name Hancom gives the n-th of a kind (``RadioButton1``, ``ComboBox1``, ``Edit1``).
_FORM_NAMES = {"radioBtn": "RadioButton", "comboBox": "ComboBox", "edit": "Edit"}
_FORM_KINDS = ("btn", "radioBtn", "checkBtn", "comboBox", "listBox", "edit", "scrollBar")


def _next_form_name(doc: "HwpxDocument", local: str) -> str:
    taken = {element.get("name", "") for element, _s, _i in _iter_form_objects(doc, local)}
    number = len(taken) + 1
    while f"{_FORM_NAMES[local]}{number}" in taken:
        number += 1
    return f"{_FORM_NAMES[local]}{number}"


def _next_tab_order(doc: "HwpxDocument") -> str:
    """One past the highest ``tabOrder`` of the document's form objects, as Hancom numbers them."""

    highest = 0
    for section in doc.sections:
        for element in section.element.iter():
            if _local_name(element) in _FORM_KINDS:
                value = (element.get("tabOrder") or "").strip()
                if value.lstrip("-").isdigit():
                    highest = max(highest, int(value))
    return str(highest + 1)


def _form_name(doc: "HwpxDocument", local: str, name: str | None) -> str:
    if name is None or not str(name).strip():
        return _next_form_name(doc, local)
    return _sanitize_field_text(str(name).strip())


@refused_leaves_no_paragraph
def _add_form_object(
    doc: "HwpxDocument",
    local: str,
    own: Mapping[str, str],
    *,
    name: str,
    paragraph: Any | None,
    section: Any | None,
    content: Sequence[tuple[str, dict[str, str], str | None]] = (),
) -> Any:
    """Append a new ``hp:<local>`` form object, built as Hancom writes one, to *paragraph* (a new
    paragraph at the end of *section* when ``None``) and return its live view.

    Like a check box it is a direct child of a run, set as a character, with the mandatory
    ``hp:formCharPr`` first, then *content* (``hp:listItem``, ``hp:text``), size, position and
    outer margin. The paragraph (and the one holding its table) loses its line layout cache.
    """

    if paragraph is None:
        paragraph = home_paragraph(doc, "", section=section, include_run=False)
    fore, back, border, width, height = _FORM_LOOK[local]
    attributes = {key: own.get(key, default) for key, default in _FORM_OWN_ATTRIBUTES[local]}
    attributes.update({
        "name": name, "foreColor": fore, "backColor": back, "groupName": "", "tabStop": "1", "editable": "1",
        "tabOrder": _next_tab_order(doc), "enabled": "1", "borderTypeIDRef": border, "drawFrame": "1",
        "printable": "1", "command": "",
    })
    run = paragraph._create_run_for_object()
    element = run.makeelement(f"{_HP}{local}", attributes)
    run.append(element)
    element.append(element.makeelement(
        f"{_HP}formCharPr", {"charPrIDRef": "0", "followContext": "0", "autoSz": "0", "wordWrap": "0"}
    ))
    for child_name, child_attributes, text in content:
        child = element.makeelement(f"{_HP}{child_name}", child_attributes)
        if text is not None:
            child.text = text
        element.append(child)
    element.append(element.makeelement(f"{_HP}sz", {
        "width": str(width), "widthRelTo": "ABSOLUTE", "height": str(height), "heightRelTo": "ABSOLUTE",
        "protect": "0",
    }))
    element.append(element.makeelement(f"{_HP}pos", {
        "treatAsChar": "1", "affectLSpacing": "0", "flowWithText": "1", "allowOverlap": "1",
        "holdAnchorAndSO": "0", "vertRelTo": "PARA", "horzRelTo": "COLUMN", "vertAlign": "TOP",
        "horzAlign": "LEFT", "vertOffset": "0", "horzOffset": "0",
    }))
    element.append(element.makeelement(f"{_HP}outMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"}))
    run.append(run.makeelement(f"{_HP}t", {}))
    paragraph.section.mark_dirty()
    for view in list_form_objects(doc, local):
        if view.element is element:
            return view
    raise HwpxStateError(  # pragma: no cover - defensive: the reader walks every section
        f"the new {local} was not found by the form object reader",
        code="field-form-not-created",
        context={"kind": local, "name": name},
        suggestion="Check that the paragraph belongs to this document.",
    )


def _check_caption(caption: object, code: str) -> str:
    text = _sanitize_field_text(caption) if isinstance(caption, str) else ""
    if not text.strip():
        raise HwpxValueError(
            "a radio button needs a caption: the text drawn beside it",
            code=code,
            context={"requested": repr(caption)},
            suggestion="Pass the caption printed next to the button.",
        )
    return text


def add_radio_button(
    doc: "HwpxDocument",
    caption: str,
    *,
    group: str = "",
    checked: bool = False,
    name: str | None = None,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> RadioButton:
    """Create a radio button (라디오 단추) as Hancom writes one and return it as a
    :class:`~hwpx.objects.RadioButton`. Checking it unchecks the other buttons of its *group*."""

    text = _check_caption(caption, "field-radio-caption-empty")
    if not isinstance(group, str):
        raise HwpxValueError(
            f"group must be a str (the radio group's name); got {group!r}",
            code="field-radio-group-value",
            context={"requested": repr(group)},
            suggestion="Pass the same group name to the buttons one choice is made among.",
        )
    view = _add_form_object(
        doc, "radioBtn", {"caption": text, "radioGroupName": _sanitize_field_text(group)},
        name=_form_name(doc, "radioBtn", name), paragraph=paragraph, section=section,
    )
    if checked:
        view.checked = True
    return cast(RadioButton, view)


def add_combo_box(
    doc: "HwpxDocument",
    text: str = "",
    *,
    editable_text: bool = True,
    name: str | None = None,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> ComboBox:
    """Create a combo box (콤보 상자) as Hancom writes one and return it as a
    :class:`~hwpx.objects.ComboBox`: one list item holding the text the box shows."""

    if not isinstance(text, str):
        raise HwpxValueError(
            f"text must be a str (what the box shows); got {text!r}",
            code="field-form-text-value",
            context={"requested": repr(text)},
            suggestion="Pass the text the box shows, or leave it out for an empty box.",
        )
    return cast(ComboBox, _add_form_object(
        doc, "comboBox", {"editEnable": "1" if editable_text else "0"},
        name=_form_name(doc, "comboBox", name), paragraph=paragraph, section=section,
        content=(("listItem", {"displayText": "", "value": _sanitize_field_text(text)}, None),),
    ))


def add_edit_box(
    doc: "HwpxDocument",
    text: str = "",
    *,
    multi_line: bool = False,
    read_only: bool = False,
    name: str | None = None,
    paragraph: Any | None = None,
    section: Any | None = None,
) -> EditBox:
    """Create an edit box (입력 상자) as Hancom writes one and return it as an
    :class:`~hwpx.objects.EditBox`. A box of one line takes line breaks as spaces."""

    if not isinstance(text, str):
        raise HwpxValueError(
            f"text must be a str (what the box holds); got {text!r}",
            code="field-form-text-value",
            context={"requested": repr(text)},
            suggestion="Pass the text the box holds, or leave it out for an empty box.",
        )
    value = _sanitize_field_text(text)
    if not multi_line:
        value = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return cast(EditBox, _add_form_object(
        doc, "edit", {"multiLine": "1" if multi_line else "0", "readOnly": "1" if read_only else "0"},
        name=_form_name(doc, "edit", name), paragraph=paragraph, section=section,
        content=(("text", {}, value),),
    ))


def _measure_form_field_fit(
    doc: "HwpxDocument",
    value: str,
    match: Mapping[str, Any],
    fit_policy: "FitPolicy",
    box_width: int | None,
    font_pt: float | None,
) -> "FitResult":
    """Run the FormFit engine for a native field (plan §2 C)."""

    from dataclasses import replace

    from hwpx.form_fit import DEFAULT_SAFETY, FitEngine, FitResult, SlotMetrics
    from hwpx.form_fit.measure import text_style_from_refs

    runs = match["_runs"]
    begin_index = int(match["_begin_run_index"])
    begin_ref = None
    if 0 <= begin_index < len(runs):
        begin_ref = runs[begin_index].get("charPrIDRef")
    if begin_ref is None:
        begin_ref = match["_paragraph"].char_pr_id_ref or "0"
    resolved_pt = font_pt if font_pt is not None else _font_pt_for_ref(doc, begin_ref)
    field_id = str(match.get("name") or match.get("field_id") or match.get("index"))

    if not box_width:
        # No reliable geometry: measure-free, low-confidence, never a hard fail.
        return FitResult(
            ok=True,
            value=value,
            applied_value=value,
            font_pt=resolved_pt,
            confidence="low",
            warnings=[
                "native field has no box_width; fit is unverified — supply "
                "box_width or rely on the render oracle"
            ],
            field_id=field_id,
        )

    # The field sits inside its paragraph, so the paragraph's indent does not
    # apply to the box.
    text_style = text_style_from_refs(
        doc._root, match["_paragraph"].para_pr_id_ref, [begin_ref]
    )
    slot = SlotMetrics(
        available_width=float(box_width) * DEFAULT_SAFETY,
        font_pt=resolved_pt,
        max_lines=fit_policy.effective_max_lines,
        text_style=replace(text_style, indent=0),
    )
    return FitEngine().fit(value, slot, fit_policy, field_id=field_id)


def _font_pt_for_ref(doc: "HwpxDocument", char_pr_id_ref: object) -> float:
    # `doc._root.char_property` rather than `doc.char_property` — that facade
    # name moved in 6.0 (design table row 49) and is a pure passthrough to
    # `_root`, so calling `_root` directly is byte-identical minus the
    # DeprecationWarning it would otherwise fire on every fit measurement.
    style = doc._root.char_property(cast(Any, char_pr_id_ref))
    if style is not None:
        height = style.attributes.get("height")
        if height:
            try:
                return int(height) / 100.0
            except (TypeError, ValueError):  # pragma: no cover - defensive
                pass
    return 10.0


def _apply_form_field_fit_style(
    doc: "HwpxDocument", match: Mapping[str, Any], fit_result: "FitResult"
) -> None:
    """Materialise a font shrink on the field's primary run (real change)."""

    new_pt = fit_result.applied_style_changes.get("font_pt")
    if not new_pt:
        return
    text_nodes: list[Any] = match.get("_text_nodes", [])
    run = None
    if text_nodes and hasattr(text_nodes[0], "getparent"):
        run = text_nodes[0].getparent()
    if run is None:
        return
    base_ref = run.get("charPrIDRef")
    try:
        # `doc._root.ensure_run_style` rather than `doc.ensure_run_style` —
        # see `_font_pt_for_ref` above for why.
        new_ref = doc._root.ensure_run_style(size=float(new_pt), base_char_pr_id=base_ref)
    except Exception:  # pragma: no cover - defensive: never break the fill
        fit_result.warnings.append("font shrink could not be materialised")
        return
    run.set("charPrIDRef", str(new_ref))
