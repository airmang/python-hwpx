# SPDX-License-Identifier: Apache-2.0
"""Atomic, allow-listed mutation commands for the semantic agent interface.

The public contract in :mod:`hwpx.agent.model` deliberately has no raw XML or
package-part escape hatch.  This module is the only compiler from that compact
command vocabulary to the existing python-hwpx editing primitives.  A batch is
applied to one disposable in-memory document, serialized once, and handed to
the normal :class:`~hwpx.quality.SavePipeline` exactly once.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlTable
from hwpx.quality import SavePipeline

from .catalog import catalog_hash
from .document import HwpxAgentDocument, NodeRecord
from .model import (
    NODE_PROPERTY_CATALOG_V1,
    AgentBatchResult,
    AgentContractError,
    validate_agent_batch,
)
from .path import parse_path
from .story import (
    HEADER_STORY_EDITABLE_PROPERTIES,
    HEADER_STORY_KIND,
    HeaderStoryBinding,
    try_parse_header_story_path,
)
# Verification/orchestration primitives for apply_document_commands live in
# _batch_verification (S-088 P3 split, keeps this file under its line-count
# ratchet). _error_from_exception/_member_diff/_quality_policy/_revision are
# re-exported here (explicit `as` aliases) because blueprint/replay.py still
# imports them from this module.
from ._batch_verification import (
    DomainVerifier,
    FaultInjector,
    IdempotencyStore,
    _EMPTY_REVISION,
    _apply_commands_build_candidate_report,
    _apply_commands_domain_verification,
    _apply_commands_idempotency_lookup,
    _apply_commands_run_save_pipeline,
    _call_fault,
    _error_from_exception as _error_from_exception,
    _failure_result,
    _member_diff as _member_diff,
    _quality_policy as _quality_policy,
    _request_hash,
    _require_candidate_structural_safety,
    _revision as _revision,
    _validate_apply_commands_input,
)

_HWP_UNITS_PER_MM = 7200 / 25.4
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_PARAGRAPH_ALIGNMENTS = frozenset(
    {"LEFT", "CENTER", "RIGHT", "JUSTIFY", "DISTRIBUTE", "DISTRIBUTE_SPACE"}
)
_TABLE_ALIGNMENTS = frozenset({"LEFT", "CENTER", "RIGHT", "INSIDE", "OUTSIDE"})
_VERTICAL_ALIGNMENTS = frozenset({"TOP", "CENTER", "BOTTOM"})
_INLINE_KINDS = frozenset({"table", "picture", "shape", "footnote", "endnote"})
_SHAPE_KINDS = frozenset({"line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine"})

# Creation needs a few geometry fields that are readable, rather than editable,
# after the node exists.  Everything else comes directly from the frozen v1
# property catalog.
_CREATE_PROPERTIES: dict[str, frozenset[str]] = {
    "section": frozenset({"pageWidthMm", "pageHeightMm"}),
    "paragraph": frozenset(NODE_PROPERTY_CATALOG_V1["paragraph"]["editable"]),
    "run": frozenset(NODE_PROPERTY_CATALOG_V1["run"]["editable"]),
    "table": frozenset({"rowCount", "columnCount", "caption", "widthMm", "alignment"}),
    "row": frozenset({"cellCount", "heightMm"}),
}

_ADD_PARENTS = {
    "section": "document",
    "paragraph": "section",
    "run": "paragraph",
    "table": "paragraph",
    "row": "table",
}

_MOVE_COPY_PARENTS = {
    "paragraph": "section",
    "run": "paragraph",
    "table": "paragraph",
    "row": "table",
    "picture": "paragraph",
    "shape": "paragraph",
    "memo": "section",
    "footnote": "paragraph",
    "endnote": "paragraph",
}

def _local_name(element: Any) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _tag_like(element: Any, local_name: str) -> str:
    tag = str(element.tag)
    return f"{tag.rsplit('}', 1)[0]}}}{local_name}" if "}" in tag else local_name


def _element(native: Any) -> Any:
    return getattr(native, "element", native)


def _require_string(value: Any, name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise AgentContractError("invalid_syntax", f"{name} must be a string", target=name)
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AgentContractError("invalid_syntax", f"{name} must be boolean", target=name)
    return value


def _require_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentContractError("invalid_syntax", f"{name} must be numeric", target=name)
    result = float(value)
    if positive and result <= 0:
        raise AgentContractError("invalid_syntax", f"{name} must be positive", target=name)
    return result


def _require_integer(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentContractError("invalid_syntax", f"{name} must be an integer", target=name)
    if positive and value <= 0:
        raise AgentContractError("invalid_syntax", f"{name} must be positive", target=name)
    return value


def _require_color(value: Any, name: str) -> str:
    color = _require_string(value, name, allow_empty=False)
    if not _COLOR_PATTERN.fullmatch(color):
        raise AgentContractError("invalid_syntax", f"{name} must be #RRGGBB", target=name)
    return color.upper()


def _require_enum(value: Any, name: str, choices: frozenset[str]) -> str:
    text = _require_string(value, name, allow_empty=False).upper()
    if text not in choices:
        raise AgentContractError(
            "invalid_syntax", f"{name} must be one of {sorted(choices)}", target=name
        )
    return text


def _validate_property_values(kind: str, properties: Mapping[str, Any], *, creating: bool) -> None:
    allowed = (
        _CREATE_PROPERTIES.get(kind, frozenset())
        if creating
        else frozenset(NODE_PROPERTY_CATALOG_V1[kind]["editable"])
    )
    unknown = sorted(set(properties) - allowed)
    if unknown:
        raise AgentContractError(
            "unknown_property",
            f"{kind} does not support properties: {unknown}",
            target=f"{kind}.{unknown[0]}",
        )
    for name, value in properties.items():
        target = f"{kind}.{name}"
        if name in {"text", "value", "altText", "caption", "fontName", "style"}:
            _require_string(value, target)
        elif name in {"bold", "italic", "underline", "breakBefore", "keepWithNext", "readOnly"}:
            _require_bool(value, target)
        elif name in {"fontSizePt", "lineSpacingPercent", "heightMm", "widthMm", "pageWidthMm", "pageHeightMm"}:
            _require_number(value, target, positive=True)
        elif name in {"rowCount", "columnCount", "cellCount"}:
            _require_integer(value, target, positive=True)
        elif name == "color" or name == "backgroundColor":
            _require_color(value, target)
        elif name == "alignment":
            _require_enum(
                value,
                target,
                _TABLE_ALIGNMENTS if kind == "table" else _PARAGRAPH_ALIGNMENTS,
            )
        elif name == "verticalAlignment":
            _require_enum(value, target, _VERTICAL_ALIGNMENTS)
        else:  # pragma: no cover - catalog additions must choose a type above
            raise AgentContractError("unknown_property", f"untyped property: {target}", target=target)


def _validate_header_story_properties(properties: Mapping[str, Any]) -> None:
    unknown = sorted(set(properties) - HEADER_STORY_EDITABLE_PROPERTIES)
    if unknown:
        raise AgentContractError(
            "unknown_property",
            f"header does not support properties: {unknown}",
            target=f"header.{unknown[0]}",
        )
    if "text" not in properties:
        raise AgentContractError(
            "invalid_syntax", "existing header set requires text", target="header.text"
        )
    _require_string(properties["text"], "header.text")


def _preflight_reference_kind(value: str, alias_kinds: Mapping[str, Mapping[str, str]]) -> str:
    if value.startswith("$"):
        command_id, field = value[1:].split(".", 1)
        try:
            return alias_kinds[command_id][field]
        except KeyError as exc:  # validate_agent_batch already checks ordering
            raise AgentContractError("not_found", f"unknown command alias: {value}") from exc
    story = try_parse_header_story_path(value)
    if story is not None:
        return story.kind
    parsed = parse_path(value)
    return parsed.segments[-1].kind if parsed.segments else "document"


def _preflight_parent_kind(value: str, alias_kinds: Mapping[str, Mapping[str, str]]) -> str:
    if value.startswith("$"):
        command_id, field = value[1:].split(".", 1)
        try:
            return alias_kinds[command_id]["parentPath" if field == "path" else field]
        except KeyError:
            return "document"
    story = try_parse_header_story_path(value)
    if story is not None:
        return "section"
    parsed = parse_path(value)
    return parsed.segments[-2].kind if len(parsed.segments) > 1 else "document"


def _preflight_add_command(command: Mapping[str, Any], alias_kinds: dict[str, dict[str, str]]) -> None:
    kind = command["kind"]
    if kind not in _ADD_PARENTS:
        raise AgentContractError(
            "unsupported_operation", f"add is unsupported for {kind}", target=command["commandId"]
        )
    _validate_property_values(kind, command["properties"], creating=True)
    if kind == "table" and not {"rowCount", "columnCount"} <= set(command["properties"]):
        raise AgentContractError(
            "invalid_syntax", "table add requires rowCount and columnCount", target=command["commandId"]
        )
    if kind == "row" and "cellCount" not in command["properties"]:
        raise AgentContractError(
            "invalid_syntax", "row add requires cellCount", target=command["commandId"]
        )
    destination_kind = _preflight_reference_kind(command["parent"], alias_kinds)
    expected_parent = _ADD_PARENTS[kind]
    if destination_kind != expected_parent:
        raise AgentContractError(
            "incompatible_parent",
            f"{kind} requires a {expected_parent} parent, not {destination_kind}",
            target=command["commandId"],
        )
    alias_kinds[command["commandId"]] = {
        "path": kind,
        "parentPath": destination_kind,
    }


def _preflight_mutate_command(
    op: str, command: Mapping[str, Any], alias_kinds: dict[str, dict[str, str]]
) -> None:
    source_kind = _preflight_reference_kind(command["path"], alias_kinds)
    if source_kind == HEADER_STORY_KIND:
        if op != "set":
            raise AgentContractError(
                "unsupported_operation",
                f"{op} is unsupported for {source_kind}",
                target=command["commandId"],
            )
        _validate_header_story_properties(command["properties"])
        alias_kinds[command["commandId"]] = {
            "path": source_kind,
            "parentPath": "section",
        }
        return
    if op not in NODE_PROPERTY_CATALOG_V1[source_kind]["operations"]:
        raise AgentContractError(
            "unsupported_operation",
            f"{op} is unsupported for {source_kind}",
            target=command["commandId"],
        )
    if op == "set":
        _validate_property_values(source_kind, command["properties"], creating=False)
    destination_kind = _preflight_parent_kind(command["path"], alias_kinds)
    if op in {"move", "copy"}:
        destination_kind = _preflight_reference_kind(command["parent"], alias_kinds)
        move_parent = _MOVE_COPY_PARENTS.get(source_kind)
        if destination_kind != move_parent:
            raise AgentContractError(
                "incompatible_parent",
                f"{source_kind} requires a {move_parent} parent, not {destination_kind}",
                target=command["commandId"],
            )
    alias_kinds[command["commandId"]] = {
        "path": source_kind,
        "parentPath": destination_kind,
    }


def _preflight(batch: Mapping[str, Any]) -> None:
    """Reject the complete static command matrix before the first mutation."""

    alias_kinds: dict[str, dict[str, str]] = {}

    for command in batch["commands"]:
        op = command["op"]
        if op == "add":
            _preflight_add_command(command, alias_kinds)
            continue
        _preflight_mutate_command(op, command, alias_kinds)


def _resolve_alias(value: str, aliases: Mapping[str, Mapping[str, str]]) -> str:
    if not value.startswith("$"):
        return value
    command_id, field = value[1:].split(".", 1)
    try:
        return aliases[command_id][field]
    except KeyError as exc:
        raise AgentContractError(
            "not_found", f"command alias is unavailable: {value}", target=value
        ) from exc


def _resolved_position(
    position: Mapping[str, Any], aliases: Mapping[str, Mapping[str, str]]
) -> dict[str, Any]:
    result = dict(position)
    if "path" in result:
        result["path"] = _resolve_alias(str(result["path"]), aliases)
    return result


def _record_for_native(view: HwpxAgentDocument, native_or_element: Any) -> NodeRecord:
    target = _element(native_or_element)
    for record in view.records:
        if _element(record.native) is target:
            return record
    raise AgentContractError("not_found", "mutated node was not present after projection")


def _ensure_operation(record: NodeRecord, operation: str) -> None:
    if operation not in NODE_PROPERTY_CATALOG_V1[record.kind]["operations"]:
        raise AgentContractError(
            "unsupported_operation",
            f"{operation} is unsupported for {record.kind}",
            target=record.path,
        )


def _ensure_parent(record: NodeRecord, *, source_kind: str, operation: str) -> None:
    expected = _ADD_PARENTS.get(source_kind) if operation == "add" else _MOVE_COPY_PARENTS.get(source_kind)
    if expected != record.kind:
        raise AgentContractError(
            "incompatible_parent",
            f"{source_kind} requires a {expected} parent, not {record.kind}",
            target=record.path,
        )


def _sibling_elements(view: HwpxAgentDocument, parent: NodeRecord, kind: str) -> list[Any]:
    return [
        _element(record.native)
        for record in view.records
        if record.parent_path == parent.path and record.kind == kind
    ]


def _insertion_index(
    view: HwpxAgentDocument,
    parent: NodeRecord,
    kind: str,
    position: Mapping[str, Any],
    *,
    siblings: list[Any] | None = None,
) -> int:
    siblings = list(siblings if siblings is not None else _sibling_elements(view, parent, kind))
    mode = position["mode"]
    if mode == "append":
        return len(siblings)
    if mode == "prepend":
        return 0
    if mode == "index":
        index = int(position["index"])
        if index > len(siblings) + 1:
            raise AgentContractError(
                "not_found", f"one-based insertion index {index} is out of range", target=parent.path
            )
        return index - 1
    anchor = view.resolve_record(str(position["path"]))
    if anchor.parent_path != parent.path or anchor.kind != kind:
        raise AgentContractError(
            "incompatible_parent", "position anchor is not a compatible sibling", target=anchor.path
        )
    try:
        index = siblings.index(_element(anchor.native))
    except ValueError as exc:
        raise AgentContractError("not_found", "position anchor is unavailable", target=anchor.path) from exc
    return index + (1 if mode == "after" else 0)


def _insert_direct_child(
    view: HwpxAgentDocument,
    parent: NodeRecord,
    kind: str,
    element: Any,
    position: Mapping[str, Any],
) -> None:
    siblings = _sibling_elements(view, parent, kind)
    index = _insertion_index(view, parent, kind, position, siblings=siblings)
    container = _element(parent.native)
    if index >= len(siblings):
        if siblings:
            absolute = list(container).index(siblings[-1]) + 1
            container.insert(absolute, element)
        else:
            container.append(element)
    else:
        container.insert(list(container).index(siblings[index]), element)


def _insert_inline(
    view: HwpxAgentDocument,
    parent: NodeRecord,
    kind: str,
    element: Any,
    position: Mapping[str, Any],
) -> Any:
    paragraph = parent.native
    siblings = _sibling_elements(view, parent, kind)
    index = _insertion_index(view, parent, kind, position, siblings=siblings)
    run = paragraph.element.makeelement(
        _tag_like(paragraph.element, "run"),
        {"charPrIDRef": paragraph.char_pr_id_ref or "0"},
    )
    run.append(element)
    if index >= len(siblings):
        paragraph.element.append(run)
    else:
        anchor = siblings[index]
        anchor_run = anchor.getparent() if hasattr(anchor, "getparent") else next(
            child for child in paragraph.element if anchor in list(child)
        )
        paragraph.element.insert(list(paragraph.element).index(anchor_run), run)
    paragraph.section.mark_dirty()
    return run


def _remove_inline_element(element: Any, paragraph: Any) -> None:
    run = element.getparent() if hasattr(element, "getparent") else next(
        child for child in paragraph.element if element in list(child)
    )
    run.remove(element)
    if not list(run) and run in list(paragraph.element):
        paragraph.element.remove(run)
    paragraph.section.mark_dirty()


def _set_shape_comment(element: Any, value: str) -> None:
    comment = next((child for child in element if _local_name(child) == "shapeComment"), None)
    if comment is None:
        comment = element.makeelement(_tag_like(element, "shapeComment"), {})
        element.append(comment)
    comment.text = value


def _next_numeric_identity(document: HwpxDocument) -> str:
    maximum = 0
    for section in document.sections:
        for node in section.element.iter():
            for name in ("id", "instid", "instId"):
                value = node.get(name)
                if value and value.isdigit():
                    maximum = max(maximum, int(value))
    return str(maximum + 1)


def _table_caption(table: Any, value: str) -> None:
    element = table.element
    caption = next((child for child in element if _local_name(child) == "caption"), None)
    if caption is None:
        caption = element.makeelement(
            _tag_like(element, "caption"),
            {"side": "TOP", "fullSz": "0", "width": "0", "gap": "850", "lastWidth": "0"},
        )
        sublist = caption.makeelement(
            _tag_like(caption, "subList"),
            {
                "id": "",
                "textDirection": "HORIZONTAL",
                "lineWrap": "BREAK",
                "vertAlign": "TOP",
                "linkListIDRef": "0",
                "linkListNextIDRef": "0",
                "textWidth": "0",
                "textHeight": "0",
                "hasTextRef": "0",
                "hasNumRef": "0",
            },
        )
        paragraph = sublist.makeelement(
            _tag_like(sublist, "p"),
            {
                "id": _next_numeric_identity(table.paragraph.section.document),
                "paraPrIDRef": "0",
                "styleIDRef": "0",
                "pageBreak": "0",
                "columnBreak": "0",
                "merged": "0",
            },
        )
        run = paragraph.makeelement(_tag_like(paragraph, "run"), {"charPrIDRef": "0"})
        text = run.makeelement(_tag_like(run, "t"), {})
        run.append(text)
        paragraph.append(run)
        sublist.append(paragraph)
        caption.append(sublist)
        children = list(element)
        position_index = next(
            (index + 1 for index, child in enumerate(children) if _local_name(child) == "pos"),
            min(2, len(children)),
        )
        element.insert(position_index, caption)
    text_nodes = [node for node in caption.iter() if _local_name(node) == "t"]
    if not text_nodes:
        raise AgentContractError("unsupported_content", "table caption has no editable text node")
    text_nodes[0].text = value
    for node in text_nodes[1:]:
        node.text = ""
    table.mark_dirty()


def _global_paragraph_index(document: HwpxDocument, paragraph: Any) -> int:
    for index, candidate in enumerate(document.paragraphs):
        if candidate.element is paragraph.element:
            return index
    raise AgentContractError("not_found", "paragraph is detached")


def _style_id(document: HwpxDocument, value: str) -> str:
    if value in document.styles:
        return value
    matches = [style_id for style_id, style in document.styles.items() if style.name == value]
    if len(matches) != 1:
        raise AgentContractError(
            "not_found" if not matches else "ambiguous_target",
            f"paragraph style is not uniquely resolvable: {value!r}",
            target="paragraph.style",
        )
    return matches[0]


def _mark_containing_section(document: HwpxDocument, target: Any) -> None:
    for section in document.sections:
        if any(node is target for node in section.element.iter()):
            section.mark_dirty()
            return
    raise AgentContractError("not_found", "mutated element is detached")


def _apply_header_story_set(
    binding: HeaderStoryBinding, properties: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply the bounded existing-header mutation through its OXML owner."""

    _validate_header_story_properties(properties)
    try:
        binding.native.set_simple_text_preserving(properties["text"])
    except AgentContractError:
        raise
    except ValueError as exc:
        # The OXML owner uses ValueError for rich/control-bearing or otherwise
        # structurally unsafe headers.  Do not let it degrade to the generic
        # invariant envelope or fall back to the destructive whole-story setter.
        message = str(exc) or "header content cannot be edited losslessly"
        lowered = message.lower()
        code = (
            "ambiguous_target"
            if "ambiguous" in lowered
            else "not_found"
            if "not found" in lowered
            else "unsupported_content"
        )
        raise AgentContractError(
            code,
            message,
            target=binding.path,
        ) from exc
    return {
        "text": {
            "before": binding.text,
            "after": properties["text"],
        }
    }


def _apply_set_paragraph(document: HwpxDocument, native: Any, properties: Mapping[str, Any]) -> None:
    if "text" in properties:
        native.text = properties["text"]
    if "style" in properties:
        native.style_id_ref = _style_id(document, properties["style"])
    format_kwargs: dict[str, Any] = {}
    if "alignment" in properties:
        format_kwargs["alignment"] = properties["alignment"]
    if "lineSpacingPercent" in properties:
        format_kwargs["line_spacing_percent"] = properties["lineSpacingPercent"]
    if "keepWithNext" in properties:
        format_kwargs["keep_with_next"] = properties["keepWithNext"]
    if "breakBefore" in properties:
        format_kwargs["page_break_before"] = properties["breakBefore"]
    if format_kwargs:
        document.set_paragraph_format(
            paragraph_index=_global_paragraph_index(document, native), **format_kwargs
        )


def _apply_set_run(document: HwpxDocument, native: Any, properties: Mapping[str, Any]) -> None:
    if "text" in properties:
        native.text = properties["text"]
    style = native.style
    child_attrs = style.child_attributes if style is not None else {}
    flags = {
        "bold": "bold" in child_attrs,
        "italic": "italic" in child_attrs,
        "underline": child_attrs.get("underline", {}).get("type", "NONE").upper() != "NONE",
    }
    for name in flags:
        if name in properties:
            flags[name] = properties[name]
    if set(properties) - {"text"}:
        requested_font = properties.get("fontName")
        if requested_font is not None and not any(
            header.font_ref_for_face(requested_font) is not None
            for header in document._root.headers  # type: ignore[attr-defined]
        ):
            raise AgentContractError(
                "not_found", f"font is not declared by the document: {requested_font!r}", target="run.fontName"
            )
        style_id = document.ensure_run_style(
            **flags,
            color=properties.get("color"),
            font=requested_font,
            size=properties.get("fontSizePt"),
            base_char_pr_id=native.char_pr_id_ref,
        )
        native.char_pr_id_ref = style_id


def _apply_set_table(native: Any, properties: Mapping[str, Any], record: NodeRecord) -> None:
    if "caption" in properties:
        _table_caption(native, properties["caption"])
    if "alignment" in properties:
        pos = next((child for child in native.element if _local_name(child) == "pos"), None)
        if pos is None:
            raise AgentContractError("unsupported_content", "table has no position element", target=record.path)
        pos.set("horzAlign", properties["alignment"].upper())
        native.mark_dirty()


def _apply_set_row(native: Any, properties: Mapping[str, Any]) -> None:
    height = round(_require_number(properties["heightMm"], "row.heightMm", positive=True) * _HWP_UNITS_PER_MM)
    for cell in native.cells:
        cell.set_size(height=height)


def _apply_set_cell(native: Any, properties: Mapping[str, Any], record: NodeRecord) -> None:
    if "text" in properties:
        native.text = properties["text"]
    if "verticalAlignment" in properties:
        sublist = next((child for child in native.element if _local_name(child) == "subList"), None)
        if sublist is None:
            raise AgentContractError("unsupported_content", "cell has no subList", target=record.path)
        sublist.set("vertAlign", properties["verticalAlignment"].upper())
        native.table.mark_dirty()
    if "backgroundColor" in properties:
        row, column = native.address
        native.table.set_cell_shading(row, column, properties["backgroundColor"])


def _apply_set_form_field(document: HwpxDocument, native: Any, properties: Mapping[str, Any], record: NodeRecord) -> None:
    if "value" in properties:
        document.fill_form_field(properties["value"], field_index=int(native["index"]))
    if "readOnly" in properties:
        runs = native.get("_runs") or []
        try:
            ctrl = list(runs[int(native["run_index"])])[int(native["child_index"])]
            begin = next(child for child in ctrl if _local_name(child) == "fieldBegin")
        except (IndexError, KeyError, StopIteration, TypeError) as exc:
            raise AgentContractError(
                "unsupported_content", "form-field control is incomplete", target=record.path
            ) from exc
        begin.set("editable", "false" if properties["readOnly"] else "true")
        paragraph = native["_paragraph"]
        paragraph.section.mark_dirty()


def _apply_set_picture_shape(document: HwpxDocument, native: Any, kind: str, properties: Mapping[str, Any]) -> None:
    target_element = _element(native)
    _set_shape_comment(target_element, properties["altText"])
    if kind == "shape":
        native.paragraph.section.mark_dirty()
    else:
        _mark_containing_section(document, target_element)


def _set_result_summary(record: NodeRecord, properties: Mapping[str, Any]) -> dict[str, Any]:
    return {name: {"before": record.summary.get(name), "after": value} for name, value in properties.items()}


def _apply_set(document: HwpxDocument, record: NodeRecord, properties: Mapping[str, Any]) -> dict[str, Any]:
    _ensure_operation(record, "set")
    _validate_property_values(record.kind, properties, creating=False)
    native = record.native
    kind = record.kind

    if kind == "paragraph":
        _apply_set_paragraph(document, native, properties)
    elif kind == "run":
        _apply_set_run(document, native, properties)
    elif kind == "table":
        _apply_set_table(native, properties, record)
    elif kind == "row":
        _apply_set_row(native, properties)
    elif kind == "cell":
        _apply_set_cell(native, properties, record)
    elif kind == "form-field":
        _apply_set_form_field(document, native, properties, record)
    elif kind in {"picture", "shape"}:
        _apply_set_picture_shape(document, native, kind, properties)
    elif kind == "memo":
        native.text = properties["text"]
    elif kind in {"footnote", "endnote"}:
        native.text = properties["text"]
    else:
        raise AgentContractError("unsupported_operation", f"set is unsupported for {kind}", target=record.path)
    return _set_result_summary(record, properties)


def _apply_create_properties(
    document: HwpxDocument, record: NodeRecord, properties: Mapping[str, Any]
) -> dict[str, Any]:
    # Geometry used to create tables/rows/sections is already present.  Apply the
    # remaining editable subset through the exact same set compiler.
    editable = set(NODE_PROPERTY_CATALOG_V1[record.kind]["editable"])
    setters = {name: value for name, value in properties.items() if name in editable}
    return _apply_set(document, record, setters) if setters else {}


def _add(
    document: HwpxDocument,
    view: HwpxAgentDocument,
    parent: NodeRecord,
    kind: str,
    properties: Mapping[str, Any],
    position: Mapping[str, Any],
) -> Any:
    _ensure_parent(parent, source_kind=kind, operation="add")
    if kind == "section":
        if position["mode"] != "append":
            raise AgentContractError(
                "unsupported_operation", "section insertion is append-only in v1", target=parent.path
            )
        created = document.add_section()
        size_kwargs: dict[str, int] = {}
        if "pageWidthMm" in properties:
            size_kwargs["width"] = round(properties["pageWidthMm"] * _HWP_UNITS_PER_MM)
        if "pageHeightMm" in properties:
            size_kwargs["height"] = round(properties["pageHeightMm"] * _HWP_UNITS_PER_MM)
        if size_kwargs:
            created.properties.set_page_size(
                width=size_kwargs.get("width"),
                height=size_kwargs.get("height"),
            )
        return created
    if kind == "paragraph":
        created = parent.native.add_paragraph(str(properties.get("text", "")))
        # add_paragraph appends; relocate its native element for all other positions.
        if position["mode"] != "append":
            if hasattr(created.element, "getparent"):
                created.element.getparent().remove(created.element)
            else:
                parent.native.element.remove(created.element)
            _insert_direct_child(view, parent, kind, created.element, position)
            parent.native.mark_dirty()
        return created
    if kind == "run":
        run_kwargs = {
            key: value
            for key, value in {
                "bold": properties.get("bold", False),
                "italic": properties.get("italic", False),
                "underline": properties.get("underline", False),
                "color": properties.get("color"),
                "font": properties.get("fontName"),
                "size": properties.get("fontSizePt"),
            }.items()
            if value is not None
        }
        created = parent.native.add_run(str(properties.get("text", "")), **run_kwargs)
        if position["mode"] != "append":
            parent.native.element.remove(created.element)
            _insert_direct_child(view, parent, kind, created.element, position)
            parent.native.section.mark_dirty()
        return created
    if kind == "table":
        created = parent.native.add_table(
            int(properties["rowCount"]),
            int(properties["columnCount"]),
            width=(round(properties["widthMm"] * _HWP_UNITS_PER_MM) if "widthMm" in properties else None),
        )
        if position["mode"] != "append":
            _remove_inline_element(created.element, parent.native)
            _insert_inline(view, parent, kind, created.element, position)
        return created
    if kind == "row":
        table = parent.native
        if int(properties["cellCount"]) != table.column_count:
            raise AgentContractError(
                "incompatible_parent", "row cellCount must equal table columnCount", target=parent.path
            )
        sample = HwpxOxmlTable.create(
            1,
            table.column_count,
            width=next(
                (int(child.get("width", "0")) for child in table.element if _local_name(child) == "sz"),
                None,
            ),
            border_fill_id_ref=table.element.get("borderFillIDRef") or "0",
        )
        created = next(child for child in sample if _local_name(child) == "tr")
        if type(created) is not type(table.element):
            payload = ET.tostring(created, encoding="utf-8")
            created = LET.fromstring(payload) if isinstance(table.element, LET._Element) else ET.fromstring(payload)
        _insert_direct_child(view, parent, kind, created, position)
        table.mark_dirty()
        _refresh_table_rows(table)
        return created
    raise AgentContractError("unsupported_operation", f"add is unsupported for {kind}")


def _table_has_vertical_merge(table: Any) -> bool:
    return any(cell.span[0] > 1 for row in table.rows for cell in row.cells)


def _refresh_table_rows(table: Any) -> None:
    rows = table.rows
    table.element.set("rowCnt", str(len(rows)))
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row.cells):
            addr = next((child for child in cell.element if _local_name(child) == "cellAddr"), None)
            if addr is not None:
                addr.set("rowAddr", str(row_index))
                # Preserve explicit merged-cell column addresses where present.
                if addr.get("colAddr") is None:
                    addr.set("colAddr", str(column_index))
    table.mark_dirty()


def _remove(document: HwpxDocument, record: NodeRecord) -> None:
    _ensure_operation(record, "remove")
    native = record.native
    if record.kind == "paragraph":
        native.remove()
    elif record.kind == "run":
        native.remove()
    elif record.kind == "table":
        _remove_inline_element(native.element, native.paragraph)
    elif record.kind == "row":
        table = native.table
        if len(table.rows) <= 1:
            raise AgentContractError("invariant_violation", "a table must retain one row", target=record.path)
        if _table_has_vertical_merge(table):
            raise AgentContractError(
                "unsupported_content", "row removal with vertical merges is unsupported", target=record.path
            )
        table.element.remove(native.element)
        _refresh_table_rows(table)
    elif record.kind == "picture":
        parent = _element(record.native).getparent()
        if parent is None:
            raise AgentContractError("not_found", "picture is detached", target=record.path)
        parent.remove(_element(record.native))
        _mark_containing_section(document, parent)
    elif record.kind == "shape":
        _remove_inline_element(native.element, native.paragraph)
    elif record.kind == "memo":
        native.remove()
    elif record.kind in {"footnote", "endnote"}:
        _remove_inline_element(native.element, native.paragraph)
    else:
        raise AgentContractError(
            "unsupported_operation", f"remove is unsupported for {record.kind}", target=record.path
        )


def _detach(view: HwpxAgentDocument, record: NodeRecord) -> Any:
    element = _element(record.native)
    if record.kind == "paragraph":
        record.native.section.element.remove(element)
        record.native.section.mark_dirty()
    elif record.kind == "run":
        record.native.paragraph.element.remove(element)
        record.native.paragraph.section.mark_dirty()
    elif record.kind in _INLINE_KINDS:
        paragraph = record.native.paragraph if hasattr(record.native, "paragraph") else None
        if paragraph is None and record.parent_path is not None:
            parent_record = view.resolve_record(record.parent_path)
            paragraph = parent_record.native if parent_record.kind == "paragraph" else None
        if paragraph is None:
            raise AgentContractError("unsupported_content", "inline object has no paragraph binding")
        _remove_inline_element(element, paragraph)
    elif record.kind == "row":
        table = record.native.table
        if _table_has_vertical_merge(table):
            raise AgentContractError(
                "unsupported_content", "row movement with vertical merges is unsupported", target=record.path
            )
        table.element.remove(element)
        _refresh_table_rows(table)
    elif record.kind == "memo":
        record.native.group.element.remove(element)
        record.native.group.section.mark_dirty()
    else:
        raise AgentContractError("unsupported_operation", f"cannot detach {record.kind}")
    return element


def _move(
    view: HwpxAgentDocument,
    source: NodeRecord,
    parent: NodeRecord,
    position: Mapping[str, Any],
) -> Any:
    _ensure_operation(source, "move")
    _ensure_parent(parent, source_kind=source.kind, operation="move")
    if source.path == parent.path or parent.path.startswith(source.path.rstrip("/") + "/"):
        raise AgentContractError(
            "incompatible_parent", "a node cannot move into its own subtree", target=parent.path
        )
    if source.kind == "row" and source.native.table.column_count != parent.native.column_count:
        raise AgentContractError(
            "incompatible_parent", "row destination must have the same column count", target=parent.path
        )

    element = _element(source.native)
    siblings = _sibling_elements(view, parent, source.kind)
    # Resolve before detaching so before/after anchors still exist.  Moving to an
    # explicit index uses the final sibling list after the source disappears.
    anchor_index = _insertion_index(view, parent, source.kind, position, siblings=siblings)
    if element in siblings:
        old_index = siblings.index(element)
        siblings.pop(old_index)
        if position["mode"] in {"append", "prepend", "index"}:
            anchor_index = _insertion_index(view, parent, source.kind, position, siblings=siblings)
        elif old_index < anchor_index:
            anchor_index -= 1
    detached = _detach(view, source)

    if source.kind in {"paragraph", "run", "row"}:
        container = _element(parent.native)
        if anchor_index >= len(siblings):
            if siblings:
                container.insert(list(container).index(siblings[-1]) + 1, detached)
            else:
                container.append(detached)
        else:
            container.insert(list(container).index(siblings[anchor_index]), detached)
        if source.kind == "paragraph":
            parent.native.mark_dirty()
        elif source.kind == "run":
            parent.native.section.mark_dirty()
        else:
            _refresh_table_rows(source.native.table)
            _refresh_table_rows(parent.native)
    elif source.kind in _INLINE_KINDS:
        synthetic_position = {"mode": "index", "index": anchor_index + 1}
        fresh_view = HwpxAgentDocument.from_document(view.document, revision=view.revision)
        fresh_parent = _record_for_native(fresh_view, parent.native)
        _insert_inline(fresh_view, fresh_parent, source.kind, detached, synthetic_position)
    elif source.kind == "memo":
        group = parent.native._memo_group_element(create=True)
        if group is None:  # pragma: no cover
            raise AgentContractError("invariant_violation", "memo group creation failed")
        siblings = [memo.element for memo in parent.native.memos]
        if position["mode"] == "append" or not siblings:
            group.append(detached)
        else:
            fresh_view = HwpxAgentDocument.from_document(view.document, revision=view.revision)
            fresh_parent = _record_for_native(fresh_view, parent.native)
            index = _insertion_index(fresh_view, fresh_parent, "memo", position)
            group.insert(index, detached)
        parent.native.mark_dirty()
    return detached


def _identity_kind(local: str) -> str:
    return {
        "p": "paragraph",
        "tbl": "table",
        "pic": "picture",
        "memo": "memo",
        "footNote": "footnote",
        "endNote": "endnote",
        "fieldBegin": "form-field",
    }.get(local, "shape" if local in _SHAPE_KINDS else local)


def _refresh_copy_identities(document: HwpxDocument, clone: Any) -> list[dict[str, str]]:
    used: set[str] = set()
    max_numeric = 0
    for section in document.sections:
        for node in section.element.iter():
            for name in ("id", "instid", "instId"):
                value = node.get(name)
                if value:
                    used.add(value)
                    if value.isdigit():
                        max_numeric = max(max_numeric, int(value))

    def allocate() -> str:
        nonlocal max_numeric
        while True:
            max_numeric += 1
            value = str(max_numeric)
            if value not in used:
                used.add(value)
                return value

    identity_map: list[dict[str, str]] = []
    field_ids: dict[str, str] = {}
    for node in clone.iter():
        local = _local_name(node)
        names: tuple[str, ...] = ()
        if local in {"p", "tbl", "pic", "memo", "fieldBegin", *_SHAPE_KINDS}:
            names = tuple(name for name in ("id", "instid", "instId") if node.get(name) is not None)
        elif local in {"footNote", "endNote"}:
            names = tuple(name for name in ("instId", "id") if node.get(name) is not None)
        paired_identity = allocate() if len(names) > 1 and local in {"pic", *_SHAPE_KINDS} else None
        for name in names:
            old = str(node.get(name))
            new = paired_identity or allocate()
            node.set(name, new)
            identity_map.append(
                {"kind": _identity_kind(local), "attribute": name, "old": old, "new": new}
            )
            if local == "fieldBegin" and name == "id":
                field_ids[old] = new
    if field_ids:
        for node in clone.iter():
            if _local_name(node) != "fieldEnd":
                continue
            old = node.get("beginIDRef")
            if old in field_ids:
                node.set("beginIDRef", field_ids[old])
    return identity_map


def _copy_node(
    document: HwpxDocument,
    view: HwpxAgentDocument,
    source: NodeRecord,
    parent: NodeRecord,
    position: Mapping[str, Any],
) -> tuple[Any, list[dict[str, str]]]:
    _ensure_operation(source, "copy")
    _ensure_parent(parent, source_kind=source.kind, operation="copy")
    if source.kind == "row":
        if source.native.table.column_count != parent.native.column_count:
            raise AgentContractError(
                "incompatible_parent", "row destination must have the same column count", target=parent.path
            )
        if _table_has_vertical_merge(source.native.table) or _table_has_vertical_merge(parent.native):
            raise AgentContractError(
                "unsupported_content", "row copy with vertical merges is unsupported", target=source.path
            )
    clone = copy.deepcopy(_element(source.native))
    identity_map = _refresh_copy_identities(document, clone)
    if source.kind in {"paragraph", "run", "row"}:
        _insert_direct_child(view, parent, source.kind, clone, position)
        if source.kind == "paragraph":
            parent.native.mark_dirty()
        elif source.kind == "run":
            parent.native.section.mark_dirty()
        else:
            _refresh_table_rows(parent.native)
    elif source.kind in _INLINE_KINDS:
        _insert_inline(view, parent, source.kind, clone, position)
    elif source.kind == "memo":
        group = parent.native._memo_group_element(create=True)
        if group is None:  # pragma: no cover
            raise AgentContractError("invariant_violation", "memo group creation failed")
        siblings = [memo.element for memo in parent.native.memos]
        index = _insertion_index(view, parent, "memo", position, siblings=siblings)
        group.insert(index, clone)
        parent.native.mark_dirty()
    else:
        raise AgentContractError("unsupported_operation", f"copy is unsupported for {source.kind}")
    return clone, identity_map


def _dispatch_command_op(
    document: HwpxDocument,
    view: HwpxAgentDocument,
    command: Mapping[str, Any],
    aliases: dict[str, dict[str, str]],
    input_revision: str,
) -> tuple[str | None, str | None, dict[str, Any], list[dict[str, str]], Any, HeaderStoryBinding | None]:
    """Apply one command's op and return its raw effects.

    Returns (resolved_path, parent_path, changed, generated, target_native, story_before).
    """

    op = command["op"]
    resolved_path: str | None = None
    parent_path: str | None = None
    changed: dict[str, Any] = {}
    generated: list[dict[str, str]] = []
    target_native: Any | None = None
    story_before: HeaderStoryBinding | None = None
    if op == "set":
        resolved_path = _resolve_alias(command["path"], aliases)
        story_path = try_parse_header_story_path(resolved_path)
        if story_path is not None:
            story_before = view._resolve_header_story(story_path, expected_revision=input_revision)
            changed = _apply_header_story_set(story_before, command["properties"])
        else:
            record = view.resolve_record(resolved_path, expected_revision=input_revision)
            changed = _apply_set(document, record, command["properties"])
            target_native = record.native
    elif op == "add":
        parent_path = _resolve_alias(command["parent"], aliases)
        parent = view.resolve_record(parent_path, expected_revision=input_revision)
        position = _resolved_position(command["position"], aliases)
        target_native = _add(document, view, parent, command["kind"], command["properties"], position)
        created_view = HwpxAgentDocument.from_document(document, revision=input_revision)
        created_record = _record_for_native(created_view, target_native)
        changed = _apply_create_properties(document, created_record, command["properties"])
    elif op == "remove":
        resolved_path = _resolve_alias(command["path"], aliases)
        record = view.resolve_record(resolved_path, expected_revision=input_revision)
        parent_path = record.parent_path
        _remove(document, record)
        target_native = None
    elif op == "move":
        resolved_path = _resolve_alias(command["path"], aliases)
        parent_path = _resolve_alias(command["parent"], aliases)
        source = view.resolve_record(resolved_path, expected_revision=input_revision)
        parent = view.resolve_record(parent_path, expected_revision=input_revision)
        position = _resolved_position(command["position"], aliases)
        target_native = _move(view, source, parent, position)
    else:  # copy
        resolved_path = _resolve_alias(command["path"], aliases)
        parent_path = _resolve_alias(command["parent"], aliases)
        source = view.resolve_record(resolved_path, expected_revision=input_revision)
        parent = view.resolve_record(parent_path, expected_revision=input_revision)
        position = _resolved_position(command["position"], aliases)
        target_native, generated = _copy_node(document, view, source, parent, position)
    return resolved_path, parent_path, changed, generated, target_native, story_before


def _finalize_command_result(
    view: HwpxAgentDocument,
    command: Mapping[str, Any],
    command_id: str,
    op: str,
    resolved_path: str | None,
    parent_path: str | None,
    target_native: Any,
    story_before: HeaderStoryBinding | None,
    story_expectations: dict[str, Mapping[str, str]],
) -> tuple[str, str, str | None]:
    """Return (result_path, result_parent, result_stable_id) for one applied command."""

    result_stable_id: str | None = None
    if story_before is not None and resolved_path is not None:
        target_story = view._resolve_header_story(resolved_path)
        if target_story.stable_id != story_before.stable_id:
            raise AgentContractError(
                "invariant_violation",
                "header story identity changed during text edit",
                target=resolved_path,
            )
        result_path = target_story.path
        result_parent = target_story.parent_path
        result_stable_id = target_story.stable_id
        story_expectations[target_story.binding_key] = {
            "commandId": command_id,
            "path": target_story.path,
            "stableId": target_story.stable_id,
            "pageType": target_story.page_type,
            "text": command["properties"]["text"],
        }
    elif op == "set" and resolved_path is not None:
        # Some native bindings (notably form fields) are request-local
        # match dictionaries.  A property edit is non-structural, so
        # its canonical path is the durable post-edit lookup key.
        target_record = view.resolve_record(resolved_path)
        result_path = target_record.path
        result_parent = target_record.parent_path or "/"
    elif target_native is not None:
        target_record = _record_for_native(view, target_native)
        result_path = target_record.path
        result_parent = target_record.parent_path or "/"
    else:
        result_path = resolved_path or parent_path or "/"
        result_parent = parent_path or "/"
    return result_path, result_parent, result_stable_id


def apply_document_commands(
    batch: Mapping[str, Any],
    *,
    idempotency_store: IdempotencyStore | None = None,
    fault_injector: FaultInjector | None = None,
    domain_verifier: DomainVerifier | None = None,
    save_pipeline: SavePipeline | None = None,
) -> AgentBatchResult:
    """Validate and atomically apply one ``hwpx.agent-batch/v1`` request.

    ``idempotency_store`` is explicitly caller-owned.  The core keeps no hidden
    resident state in Leap A; MCP/CLI adapters may supply their existing scoped
    stores.  Any failure returns a structured rolled-back result and leaves the
    declared output untouched.
    """

    normalized: Mapping[str, Any] | None = None
    input_revision = _EMPTY_REVISION
    command_results: list[Mapping[str, Any]] = []
    verification: dict[str, Any] = {}
    try:
        normalized = validate_agent_batch(batch)
        _preflight(normalized)
        verification.update(
            {
                "schemaVersion": normalized["schemaVersion"],
                "catalogHash": catalog_hash(),
                "requirements": list(normalized["verificationRequirements"]),
            }
        )
        request_hash = _request_hash(normalized)
        key = normalized["idempotencyKey"]
        cached_result = _apply_commands_idempotency_lookup(
            verification, idempotency_store, key=key, request_hash=request_hash
        )
        if cached_result is not None:
            return cached_result

        input_path = Path(normalized["input"]["filename"])
        output_path = Path(normalized["output"]["filename"])
        input_data = input_path.read_bytes()
        input_revision = _revision(input_data)
        _validate_apply_commands_input(normalized, verification, input_data, input_revision, output_path)

        aliases: dict[str, dict[str, str]] = {}
        identity_changes: list[Mapping[str, str]] = []
        semantic_changes: list[Mapping[str, Any]] = []
        story_expectations: dict[str, Mapping[str, str]] = {}
        _call_fault(fault_injector, "before_open")
        with HwpxDocument.open(input_data) as document:
            view = HwpxAgentDocument.from_document(document, revision=input_revision)
            for index, command in enumerate(normalized["commands"]):
                _call_fault(fault_injector, "before_command", index)
                command_id = command["commandId"]
                op = command["op"]
                resolved_path, parent_path, changed, generated, target_native, story_before = _dispatch_command_op(
                    document, view, command, aliases, input_revision
                )
                identity_changes.extend(generated)

                _call_fault(fault_injector, "after_command", index)
                view = HwpxAgentDocument.from_document(document, revision=input_revision)
                result_path, result_parent, result_stable_id = _finalize_command_result(
                    view,
                    command,
                    command_id,
                    op,
                    resolved_path,
                    parent_path,
                    target_native,
                    story_before,
                    story_expectations,
                )
                aliases[command_id] = {"path": result_path, "parentPath": result_parent}
                result = {
                    "commandId": command_id,
                    "op": op,
                    "ok": True,
                    "path": result_path,
                    "parentPath": result_parent,
                    "changedProperties": changed,
                    "generatedIdentities": generated,
                    "warnings": [],
                }
                if result_stable_id is not None:
                    # Command results are already an untyped JSON mapping.  This
                    # story-only receipt carries the actual stable identity
                    # without changing AgentBatchResult or the ToolSpec schema.
                    result["stableId"] = result_stable_id
                command_results.append(result)
                semantic_changes.append(
                    {
                        "commandId": command_id,
                        "op": op,
                        "beforePath": resolved_path,
                        "afterPath": None if op == "remove" else result_path,
                        "changedProperties": changed,
                    }
                )

            _call_fault(fault_injector, "before_serialize")
            candidate_data = document.to_bytes()
            _call_fault(fault_injector, "after_serialize")

            candidate_revision, semantic_diff, safety, byte_report = _apply_commands_build_candidate_report(
                input_data,
                candidate_data,
                input_revision,
                semantic_changes,
                identity_changes,
                story_expectations,
                verification,
            )
            requirements = set(normalized["verificationRequirements"])
            _apply_commands_domain_verification(candidate_data, normalized, requirements, domain_verifier, verification)
            _require_candidate_structural_safety(safety, byte_report)

            _call_fault(fault_injector, "before_save")
            _apply_commands_run_save_pipeline(
                candidate_data,
                input_path,
                output_path,
                document,
                normalized,
                requirements,
                save_pipeline,
                verification,
            )

        result = AgentBatchResult(
            ok=True,
            rolled_back=False,
            dry_run=normalized["dryRun"],
            input_revision=input_revision,
            document_revision=candidate_revision,
            output_filename=str(output_path),
            command_results=tuple(command_results),
            semantic_diff=semantic_diff,
            verification_report=verification,
        )
        if key is not None and idempotency_store is not None:
            idempotency_store[key] = {"requestHash": request_hash, "result": result}
        return result
    except BaseException as exc:  # fail closed; caller receives a stable error contract
        return _failure_result(
            exc=exc,
            batch=normalized or batch,
            input_revision=input_revision,
            command_results=command_results,
            verification=verification,
        )


__all__ = [
    "DomainVerifier",
    "FaultInjector",
    "IdempotencyStore",
    "apply_document_commands",
]
