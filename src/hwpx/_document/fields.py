# SPDX-License-Identifier: Apache-2.0
"""Form-field domain owner behind the :class:`HwpxDocument` facade (S-084)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, cast

from ..oxml import HwpxOxmlParagraph
from ..oxml.namespaces import HP

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..form_fit.policy import FitPolicy
    from ..form_fit.report import FitResult
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
        prompt = _field_parameter_value(parameters, *_FORM_FIELD_PARAM_NAMES)
    instruction = _field_parameter_value(parameters, "instruction", "guide", "help", "description", "desc")
    if not instruction:
        instruction = prompt
    return {
        "index": index,
        "field_id": _field_identifier(field_begin),
        "id": field_begin.get("id", ""),
        "fieldid": field_begin.get("fieldid", ""),
        "name": name,
        "prompt": prompt,
        "instruction": instruction,
        "current_value": current_value,
        "field_type": field_begin.get("type", ""),
        "control_type": ctrl.get("type", ""),
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


def list_form_fields(doc: "HwpxDocument") -> list[dict[str, Any]]:
    """Return native form/click-here fields in document order."""

    return [
        {key: value for key, value in match.items() if not key.startswith("_")}
        for match in _iter_form_field_matches(doc)
    ]


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
        raise ValueError("provide exactly one of field_index, field_id, or name")
    if field_index is not None:
        for match in matches:
            if match["index"] == field_index:
                return match
        raise ValueError(f"form field index not found: {field_index}")
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
        raise ValueError(f"form field not found for {selector}")
    if len(candidates) > 1:
        labels = [candidate.get("name") or candidate.get("field_id") for candidate in candidates]
        raise ValueError(f"form field selector is ambiguous: {labels}")
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
) -> dict[str, Any]:
    """Fill a native form/click-here field while preserving surrounding runs."""

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
    else:
        _insert_form_field_text_run(doc, match, sanitized)

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
    field = {key: value for key, value in updated.items() if not key.startswith("_")}
    response = {
        "ok": True if fit_result is None else fit_result.ok,
        "field": field,
        "before_value": before_value,
        "after_value": str(field.get("current_value", "")),
        "style_before": before_style,
        "style_after": after_style,
        "style_preserved": before_style == after_style[: len(before_style)],
    }
    if fit_result is not None:
        response["fit"] = fit_result.to_dict()
        if not fit_result.ok:
            response["suggestedRetry"] = fit_result.suggested_retry()
    return response


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
    style = doc.char_property(cast(Any, char_pr_id_ref))
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
        new_ref = doc.ensure_run_style(size=float(new_pt), base_char_pr_id=base_ref)
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
