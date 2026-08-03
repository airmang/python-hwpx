# SPDX-License-Identifier: Apache-2.0
"""Form-field domain owner behind the :class:`HwpxDocument` facade."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, cast

from ..errors import HwpxStateError, HwpxValueError
from ..objects.checkbox import CheckBox
from ..objects.form_field import FieldLocation, FieldParameter, FormField
from ..objects.results import FieldFillResult
from ..oxml import HwpxOxmlParagraph
from ..oxml.namespaces import HP

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..form_fit.policy import FitPolicy
    from ..form_fit.report import FitResult
    from ..oxml import HwpxOxmlSection
    from ..tools.table_navigation import TableFillResult

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
    tokens = _field_type_tokens(
        ctrl.get("type"),
        field_begin.get("type"),
        field_begin.get("name"),
        field_begin.get("fieldName"),
        field_begin.get("fieldname"),
    )
    if tokens & _FORM_FIELD_EXCLUDED_TYPES:
        return False
    if tokens & _FORM_FIELD_TYPES:
        return True
    return (ctrl.get("type") or "").strip().upper() == "FORM"


def _field_identifier(field_begin: Any) -> str:
    for attr in ("id", "fieldid", "name", "fieldName", "fieldname"):
        value = (field_begin.get(attr) or "").strip()
        if value:
            return value
    return ""


def _field_end_matches(field_begin: Any, field_end: Any) -> bool:
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


def _clear_form_field_layout_cache(paragraph: Any) -> int:
    removed = 0
    for child in list(paragraph):
        if _local_name(child).lower() == "linesegarray":
            paragraph.remove(child)
            removed += 1
    return removed


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
    name = _first_attr(field_begin, _FORM_FIELD_NAME_ATTRS)
    if not name:
        name = _field_parameter_value(parameters, "fieldName", "fieldname", "field_name", "name", "title")
    prompt = _first_attr(field_begin, _FORM_FIELD_PROMPT_ATTRS)
    if not prompt:
        # "Direction" is the real-Hancom 안내문 parameter (P0 gold contract).
        prompt = _field_parameter_value(parameters, "Direction", *_FORM_FIELD_PARAM_NAMES)
    instruction = _field_parameter_value(parameters, "instruction", "guide", "help", "description", "desc")
    if not instruction:
        instruction = prompt
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


def _iter_form_field_matches(doc: "HwpxDocument") -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    paragraph_index = 0
    for section_index, section in enumerate(doc.sections):
        direct_indexes = {
            paragraph.element: index
            for index, paragraph in enumerate(section.paragraphs)
        }

        def iter_content_paragraphs(element: Any) -> Iterator[Any]:
            for child in element:
                local = _local_name(child)
                if local == "memogroup":
                    continue
                if local == "p":
                    yield child
                yield from iter_content_paragraphs(child)

        for paragraph_element in iter_content_paragraphs(section.element):
            paragraph = HwpxOxmlParagraph(paragraph_element, section)
            paragraph_index_in_section = direct_indexes.get(paragraph_element, -1)
            runs = [child for child in paragraph.element if _local_name(child) == "run"]
            for run_index, run in enumerate(runs):
                children = list(run)
                for child_index, child in enumerate(children):
                    if _local_name(child) != "ctrl":
                        continue
                    for field_begin in child.findall(f"{_HP}fieldBegin"):
                        if not _is_form_field_begin(child, field_begin):
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
                        if end_position is not None:
                            end_run_index, end_child_index, _field_end = end_position
                        text_nodes = _field_text_nodes(
                            doc,
                            runs,
                            begin_run_index=run_index,
                            begin_child_index=child_index,
                            end_run_index=end_run_index,
                            end_child_index=end_child_index,
                        )
                        current_value = "".join("".join(node.itertext()) for node in text_nodes)
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
                            has_end=end_position is not None,
                        )
                        payload["_paragraph"] = paragraph
                        payload["_runs"] = runs
                        payload["_begin_run_index"] = run_index
                        payload["_begin_child_index"] = child_index
                        payload["_end_run_index"] = end_run_index
                        payload["_end_child_index"] = end_child_index
                        payload["_text_nodes"] = text_nodes
                        matches.append(payload)
            paragraph_index += 1
    return matches


def _form_field_from_match(doc: "HwpxDocument", match: Mapping[str, Any]) -> FormField:
    """Build the public :class:`FormField` view from an internal match payload.

    Consolidates the id aliases (``id``/``fieldid``/``field_id`` →
    ``field_id``), the prompt aliases (``prompt``/``instruction`` →
    ``prompt``), and the type aliases (``field_type``/``control_type`` →
    ``field_type``) that 5.x exposed as separate dict keys (design §2.3).
    """

    location = FieldLocation(
        section_index=match["section_index"],
        paragraph_index=match["paragraph_index"],
        paragraph_index_in_section=match["paragraph_index_in_section"],
        run_index=match["run_index"],
        child_index=match["child_index"],
    )
    parameters = tuple(
        FieldParameter(name=parameter.get("name", ""), value=parameter.get("value", ""))
        for parameter in match.get("parameters", [])
    )
    field_begin = match["_field_begin"]
    editable = (field_begin.get("editable") or "").strip().lower() in {"1", "true"}
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
    )


def list_form_fields(doc: "HwpxDocument") -> tuple[FormField, ...]:
    """Return native form/click-here fields in document order."""

    return tuple(_form_field_from_match(doc, match) for match in _iter_form_field_matches(doc))


_PROMPT_TEXT_COLOR = "#FF0000"


def add_form_field(
    doc: "HwpxDocument",
    name: str,
    *,
    prompt: str = "",
    memo: str = "",
    editable: bool = True,
    paragraph: Any | None = None,
    section: Any | None = None,
    section_index: int | None = None,
) -> FormField:
    """Create a click-here (누름틀) form field and return it as a :class:`FormField`.

    The emitted XML follows the real-Hancom CLICKHERE contract
    (reverse-engineered from Hancom Office 12.0.0.3288 gold documents). The
    prompt (안내문) is materialized as a screen-only red-italic run, exactly as
    Hancom authors it. The created field is immediately re-read through the
    standard ``list_form_fields`` matcher — creation fails loudly if the
    standard consumer would not recognize it (no special-casing by design).
    """

    if not str(name).strip():
        raise HwpxValueError(
            "누름틀 이름은 비어 있을 수 없습니다.",
            code="field-name-empty",
            suggestion="양식에서 이 칸을 가리킬 이름을 지정하세요.",
        )
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index, include_run=False,
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

    field_begin = control.element.find(f"{_HP}fieldBegin")
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
        section_index=match["sectionIndex"],
    )


def list_check_boxes(doc: "HwpxDocument") -> tuple[CheckBox, ...]:
    """Return check-box form objects in document order."""

    return tuple(_check_box_from_match(match) for match in _iter_check_boxes(doc))


def add_check_box(
    doc: "HwpxDocument",
    caption: str,
    *,
    checked: bool = False,
    name: str | None = None,
    paragraph: Any | None = None,
    section: Any | None = None,
    section_index: int | None = None,
) -> CheckBox:
    """Create a check-box form object and return it as a :class:`CheckBox`.

    The emitted XML follows the check-box contract measured against real
    Hancom (specs/060): ``value`` selects ☑/□ and the ``<hp:formCharPr>`` child
    is mandatory — without it Hancom refuses the document. The created object is
    re-read through the standard :func:`list_check_boxes` reader, so creation
    fails loudly if the ordinary consumer would not see it.
    """

    if not str(caption).strip():
        raise HwpxValueError(
            "check box caption must be a non-empty string",
            code="field-checkbox-caption-empty",
            suggestion="Pass the caption printed next to the box.",
        )
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index, include_run=False,
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
    field_index: int | None,
    field_id: str | None,
    name: str | None,
) -> dict[str, Any]:
    selectors = [field_index is not None, bool(field_id), bool(name)]
    if selectors.count(True) != 1:
        raise HwpxValueError(
            "provide exactly one of field_index, field_id, or name",
            code="field-selector-conflict",
            suggestion="List doc.fields.all to see the candidates.",
        )
    if field_index is not None:
        for match in matches:
            if match["index"] == field_index:
                return match
        raise HwpxValueError(
            f"form field index not found: {field_index}",
            code="field-not-found",
            context={"requested": field_index},
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
            and wanted_name
            in {
                str(match.get("name", "")).strip().casefold(),
                str(match.get("prompt", "")).strip().casefold(),
                str(match.get("instruction", "")).strip().casefold(),
            }
        ]
    if not candidates:
        selector = f"field_id={field_id!r}" if field_id else f"name={name!r}"
        raise HwpxValueError(
            f"form field index not found: {field_index}",
            code="field-not-found",
            context={"selector": str(selector)},
            suggestion="List doc.fields.all to see the candidates.",
        )
    if len(candidates) > 1:
        labels = [candidate.get("name") or candidate.get("field_id") for candidate in candidates]
        raise HwpxValueError(
            f"form field selector is ambiguous: {labels}",
            code="field-ambiguous",
            context={"candidates": list(labels) if isinstance(labels, (list, tuple)) else str(labels)},
            suggestion="Pass field_index= to pick one.",
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
    paragraph = match["_paragraph"]
    runs: list[Any] = match["_runs"]
    begin_run_index = int(match["_begin_run_index"])
    end_run_index = match.get("_end_run_index")
    begin_run = runs[begin_run_index]
    char_ref = begin_run.get("charPrIDRef") or paragraph.char_pr_id_ref or "0"
    run = paragraph.element.makeelement(f"{_HP}run", {"charPrIDRef": str(char_ref)})
    text_node = run.makeelement(f"{_HP}t", {})
    text_node.text = _sanitize_field_text(value)
    run.append(text_node)
    if end_run_index is None:
        paragraph.element.insert(begin_run_index + 1, run)
    else:
        paragraph.element.insert(int(end_run_index), run)


def fill_form_field(
    doc: "HwpxDocument",
    value: str,
    *,
    field_index: int | None = None,
    field_id: str | None = None,
    name: str | None = None,
    fit_policy: "FitPolicy | None" = None,
    box_width: int | None = None,
    font_pt: float | None = None,
) -> FieldFillResult:
    """Fill a native form/click-here field while preserving surrounding runs.

    When *fit_policy* cannot be satisfied (a hard overflow), this raises
    ``HwpxValueError(code="field-fit-failed")`` *before* touching the XML —
    fail-closed (constitution VI) rather than 5.x's ``ok: bool`` key, which
    reported the failure and still wrote the overflowing value.
    """

    matches = _iter_form_field_matches(doc)
    match = _select_form_field(
        doc,
        matches,
        field_index=field_index,
        field_id=field_id,
        name=name,
    )
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
    if fit_policy is not None:
        fit_result = _measure_form_field_fit(
            doc, str(value), match, fit_policy, box_width, font_pt
        )
        if not fit_result.ok:
            selector = f"field_index={field_index!r}" if field_id is None and name is None else (
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
    if text_nodes:
        primary = text_nodes[0]
        primary.text = sanitized
        for child in list(primary):
            child.tail = ""
        for node in text_nodes[1:]:
            node.text = ""
            for child in list(node):
                child.tail = ""
        if match.get("is_placeholder"):
            # Contract (P0 gold): Hancom swaps the screen-only prompt style for
            # the surrounding style when a value replaces the placeholder.
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

    _clear_form_field_layout_cache(paragraph.element)
    paragraph.section.mark_dirty()
    updated = _iter_form_field_matches(doc)[int(match["index"])]
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


def _measure_form_field_fit(
    doc: "HwpxDocument",
    value: str,
    match: Mapping[str, Any],
    fit_policy: "FitPolicy",
    box_width: int | None,
    font_pt: float | None,
) -> "FitResult":
    """Run the FormFit engine for a native field (plan §2 C)."""

    from hwpx.form_fit import DEFAULT_SAFETY, FitEngine, FitResult, SlotMetrics

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

    slot = SlotMetrics(
        available_width=float(box_width) * DEFAULT_SAFETY,
        font_pt=resolved_pt,
        max_lines=fit_policy.effective_max_lines,
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


def fill_by_path(
    doc: "HwpxDocument",
    mappings: Mapping[str, str],
) -> TableFillResult:
    """Fill table cells using ``label > direction > ...`` navigation paths."""

    from ..tools.table_navigation import fill_by_path

    return fill_by_path(doc, mappings)
