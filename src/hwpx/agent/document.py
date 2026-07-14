# SPDX-License-Identifier: Apache-2.0
"""Bounded semantic projection over one HWPX document revision."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlShape

from .model import (
    MAX_CHILDREN_PER_NODE,
    MAX_TEXT_CHARS,
    MAX_VIEW_DEPTH,
    AgentContractError,
    AgentNode,
    NODE_PROPERTY_CATALOG_V1,
)
from .path import SemanticPath, canonicalize_path, identified_segment, indexed_segment
from .query import QueryResult, evaluate_selector, parse_selector

_HWP_UNITS_PER_MM = 7200 / 25.4
_SHAPE_KINDS = frozenset({"line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine"})
_IGNORED_INLINE_KINDS = frozenset({"t", "tab", "lineBreak", "secPr", "fieldEnd"})


def _local_name(element: Any) -> str:
    tag = getattr(element, "tag", "")
    return str(tag).rsplit("}", 1)[-1]


def _bounded_text(value: object, *, limit: int = 512) -> str:
    limit = min(limit, MAX_TEXT_CHARS)
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _mm(value: object) -> float | None:
    try:
        units = int(str(value))
    except (TypeError, ValueError):
        return None
    return round(units / _HWP_UNITS_PER_MM, 3)


def _first_child(element: Any, local_name: str) -> Any | None:
    for child in element:
        if _local_name(child) == local_name:
            return child
    return None


def _child_text(element: Any, local_name: str) -> str | None:
    child = _first_child(element, local_name)
    if child is None:
        return None
    value = "".join(str(part) for part in child.itertext()).strip()
    return _bounded_text(value) if value else None


def _identity(element: Any, *names: str) -> str | None:
    for name in names:
        value = element.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


@dataclass(slots=True)
class NodeRecord:
    """Request-local native binding; never serialized directly."""

    kind: str
    path: str
    stable_id: str | None
    stability: str
    summary: dict[str, Any]
    native: Any
    parent_path: str | None
    attributes: dict[str, str] = field(default_factory=dict)
    search_text: str = ""
    child_paths: list[str] = field(default_factory=list)
    unsupported_child_count: int = 0
    unsupported_child_kinds: Counter[str] = field(default_factory=Counter)

    def mark_unsupported(self, local_name: str, count: int = 1) -> None:
        self.unsupported_child_kinds[local_name] += count
        self.unsupported_child_count += count


class HwpxAgentDocument:
    """A revision-bound semantic view with request-local native bindings."""

    def __init__(self, document: HwpxDocument, revision: str, *, owns_document: bool = False) -> None:
        if not revision.startswith("sha256:") or len(revision) != 71:
            raise AgentContractError("invalid_syntax", "revision must be sha256", target="revision")
        self.document = document
        self.revision = revision
        self._owns_document = owns_document
        self._records: dict[str, NodeRecord] = {}
        self._ordered_paths: list[str] = []
        self._ambiguous_paths: set[str] = set()
        self._form_fields_by_paragraph: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        self._form_control_positions: set[tuple[int, int, int, int]] = set()
        self._id_counts: Counter[tuple[str, str]] = Counter()
        self._field_name_counts: Counter[str] = Counter()
        self._collect_identities()
        self._collect_form_fields()
        self._project()

    @classmethod
    def open(cls, source: str | PathLike[str] | bytes) -> "HwpxAgentDocument":
        if isinstance(source, bytes):
            data = source
        else:
            data = Path(source).read_bytes()
        revision = "sha256:" + hashlib.sha256(data).hexdigest()
        return cls(HwpxDocument.open(data), revision, owns_document=True)

    @classmethod
    def from_document(cls, document: HwpxDocument, *, revision: str) -> "HwpxAgentDocument":
        return cls(document, revision, owns_document=False)

    def __enter__(self) -> "HwpxAgentDocument":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._owns_document:
            self.document.close()
            self._owns_document = False

    @property
    def records(self) -> tuple[NodeRecord, ...]:
        return tuple(self._records[path] for path in self._ordered_paths)

    def _collect_identities(self) -> None:
        tag_to_kind = {
            "p": "paragraph",
            "tbl": "table",
            "pic": "picture",
            "memo": "memo",
            "footNote": "footnote",
            "endNote": "endnote",
            **{name: "shape" for name in _SHAPE_KINDS},
        }
        for section in self.document.sections:
            for element in section.element.iter():
                kind = tag_to_kind.get(_local_name(element))
                if kind is None:
                    continue
                value = _identity(element, "id", "instId", "instid")
                if value:
                    self._id_counts[(kind, value)] += 1

    def _collect_form_fields(self) -> None:
        # This private iterator is deliberately consumed inside python-hwpx so
        # later mutation can reuse its already-safe field matching semantics.
        matches = self.document._iter_form_field_matches()  # type: ignore[attr-defined]
        for match in matches:
            section_index = int(match["section_index"])
            paragraph_index = int(match["paragraph_index_in_section"])
            self._form_fields_by_paragraph[(section_index, paragraph_index)].append(match)
            self._form_control_positions.add(
                (
                    section_index,
                    paragraph_index,
                    int(match["run_index"]),
                    int(match["child_index"]),
                )
            )
            field_id = str(match.get("field_id") or match.get("id") or "").strip()
            if field_id:
                self._id_counts[("form-field", field_id)] += 1
            name = str(match.get("name") or "").strip()
            if name:
                self._field_name_counts[name] += 1

    def _add_record(self, record: NodeRecord) -> None:
        if record.path in self._records:
            raise AgentContractError(
                "invariant_violation", f"duplicate canonical path: {record.path}", target=record.path
            )
        self._records[record.path] = record
        self._ordered_paths.append(record.path)
        if record.parent_path is not None:
            self._records[record.parent_path].child_paths.append(record.path)

    def _segment_for(
        self,
        *,
        kind: str,
        index: int,
        identity: str | None,
        name: str | None = None,
    ) -> tuple[Any, str | None, str]:
        if identity:
            candidate = identified_segment(kind, identity)
            if self._id_counts[(kind, identity)] == 1:
                return candidate, f"{kind}:{identity}", "native"
            self._ambiguous_paths.add(SemanticPath((candidate,)).canonical)
            return indexed_segment(kind, index), None, "positional"
        if kind == "form-field" and name and self._field_name_counts[name] == 1:
            return identified_segment(kind, name, attribute="name"), f"form-field-name:{name}", "derived"
        if kind == "form-field" and name:
            name_segment = identified_segment(kind, name, attribute="name")
            self._ambiguous_paths.add(SemanticPath((name_segment,)).canonical)
        return indexed_segment(kind, index), None, "positional"

    def _register_ambiguous_relative(
        self,
        parent: SemanticPath,
        kind: str,
        identity: str,
        *,
        attribute: str = "id",
    ) -> None:
        segment = identified_segment(kind, identity, attribute=attribute)
        self._ambiguous_paths.add(parent.child(segment).canonical)

    def _project(self) -> None:
        root = NodeRecord(
            kind="document",
            path="/",
            stable_id="document",
            stability="derived",
            summary={},
            native=self.document,
            parent_path=None,
            attributes={"type": "document"},
        )
        self._add_record(root)
        for section_index, section in enumerate(self.document.sections, start=1):
            section_path = SemanticPath().child(indexed_segment("section", section_index))
            page_size = section.properties.page_size
            section_record = NodeRecord(
                kind="section",
                path=section_path.canonical,
                stable_id=None,
                stability="positional",
                summary={
                    "index": section_index,
                    "partId": Path(section.part_name).name,
                    "paragraphCount": len(section.paragraphs),
                    "pageWidthMm": _mm(page_size.width),
                    "pageHeightMm": _mm(page_size.height),
                },
                native=section,
                parent_path="/",
                attributes={"type": "section"},
            )
            self._add_record(section_record)
            for child in section.element:
                local = _local_name(child)
                if local not in {"p", "memogroup"}:
                    section_record.mark_unsupported(local)
            for paragraph_index, paragraph in enumerate(section.paragraphs, start=1):
                self._project_paragraph(
                    paragraph,
                    section_path,
                    paragraph_index,
                    section_index=section_index - 1,
                    paragraph_index_in_section=paragraph_index - 1,
                )
            for memo_index, memo in enumerate(section.memos, start=1):
                identity = memo.id
                segment, stable_id, stability = self._segment_for(
                    kind="memo", index=memo_index, identity=identity
                )
                if identity and stability == "positional":
                    self._register_ambiguous_relative(section_path, "memo", identity)
                memo_path = section_path.child(segment)
                self._add_record(
                    NodeRecord(
                        kind="memo",
                        path=memo_path.canonical,
                        stable_id=stable_id,
                        stability=stability,
                        summary={
                            "text": _bounded_text(memo.text),
                            "author": memo.attributes.get("author"),
                        },
                        native=memo,
                        parent_path=section_path.canonical,
                        attributes={"id": identity or "", "type": "memo"},
                        search_text=memo.text,
                    )
                )
        kinds = Counter(record.kind for record in self.records)
        root.summary.update(
            {
                "sectionCount": kinds["section"],
                "paragraphCount": kinds["paragraph"],
                "tableCount": kinds["table"],
            }
        )

    def _paragraph_summary(self, paragraph: Any) -> tuple[dict[str, Any], dict[str, str]]:
        style_ref = paragraph.element.get("styleIDRef")
        style = self.document.style(style_ref)
        style_name = style.name if style is not None and style.name else style_ref
        para_pr = self.document.paragraph_property(paragraph.element.get("paraPrIDRef"))
        summary: dict[str, Any] = {"text": _bounded_text(paragraph.text), "style": style_name}
        if para_pr is not None:
            summary["alignment"] = para_pr.align.horizontal if para_pr.align is not None else None
            summary["breakBefore"] = (
                para_pr.break_setting.page_break_before if para_pr.break_setting is not None else None
            )
            summary["keepWithNext"] = (
                para_pr.break_setting.keep_with_next if para_pr.break_setting is not None else None
            )
            summary["lineSpacingPercent"] = (
                para_pr.line_spacing.value if para_pr.line_spacing is not None else None
            )
        attributes = {
            "id": paragraph.element.get("id", ""),
            "style": style_name or "",
            "type": style.type if style is not None and style.type else "paragraph",
        }
        return summary, attributes

    def _project_paragraph(
        self,
        paragraph: Any,
        parent: SemanticPath,
        index: int,
        *,
        section_index: int,
        paragraph_index_in_section: int | None = None,
    ) -> None:
        identity = _identity(paragraph.element, "id")
        segment, stable_id, stability = self._segment_for(kind="paragraph", index=index, identity=identity)
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, "paragraph", identity)
        path = parent.child(segment)
        summary, attributes = self._paragraph_summary(paragraph)
        record = NodeRecord(
            kind="paragraph",
            path=path.canonical,
            stable_id=stable_id,
            stability=stability,
            summary=summary,
            native=paragraph,
            parent_path=parent.canonical,
            attributes=attributes,
            search_text=paragraph.text,
        )
        self._add_record(record)
        for child in paragraph.element:
            local = _local_name(child)
            if local not in {"run", "lineSegArray", "linesegarray"}:
                record.mark_unsupported(local)
        fields_by_position: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        if paragraph_index_in_section is not None:
            for match in self._form_fields_by_paragraph[(section_index, paragraph_index_in_section)]:
                fields_by_position[(int(match["run_index"]), int(match["child_index"]))].append(match)

        object_indexes: Counter[str] = Counter()
        for run_index, run in enumerate(paragraph.runs, start=1):
            run_path = path.child(indexed_segment("run", run_index))
            style = run.style
            child_attrs = style.child_attributes if style is not None else {}
            run_summary = {
                "text": _bounded_text(run.text),
                "bold": "bold" in child_attrs,
                "italic": "italic" in child_attrs,
                "underline": child_attrs.get("underline", {}).get("type", "NONE").upper() != "NONE",
                "fontSizePt": (
                    round(int(style.attributes["height"]) / 100, 2)
                    if style is not None and str(style.attributes.get("height", "")).isdigit()
                    else None
                ),
                "color": style.text_color() if style is not None else None,
            }
            self._add_record(
                NodeRecord(
                    kind="run",
                    path=run_path.canonical,
                    stable_id=None,
                    stability="positional",
                    summary=run_summary,
                    native=run,
                    parent_path=path.canonical,
                    attributes={"type": "run"},
                    search_text=run.text,
                )
            )
            for child_index, child in enumerate(run.element):
                local = _local_name(child)
                if local == "tbl":
                    object_indexes["table"] += 1
                    self._project_table(paragraph, child, path, object_indexes["table"])
                elif local == "pic":
                    object_indexes["picture"] += 1
                    self._project_picture(child, paragraph, path, object_indexes["picture"])
                elif local in _SHAPE_KINDS:
                    object_indexes["shape"] += 1
                    self._project_shape(child, paragraph, path, object_indexes["shape"])
                elif local in {"footNote", "endNote"}:
                    kind = "footnote" if local == "footNote" else "endnote"
                    object_indexes[kind] += 1
                    notes = paragraph.footnotes if kind == "footnote" else paragraph.endnotes
                    note = next(candidate for candidate in notes if candidate.element is child)
                    self._project_note(note, path, kind, object_indexes[kind])
                elif local == "ctrl":
                    matches = fields_by_position.get((run_index - 1, child_index), [])
                    if matches:
                        for match in matches:
                            object_indexes["form-field"] += 1
                            self._project_form_field(match, path, object_indexes["form-field"])
                    else:
                        record.mark_unsupported("ctrl")
                elif local not in _IGNORED_INLINE_KINDS:
                    record.mark_unsupported(local)

    def _project_table(self, paragraph: Any, element: Any, parent: SemanticPath, index: int) -> None:
        table = next(candidate for candidate in paragraph.tables if candidate.element is element)
        identity = _identity(element, "id")
        segment, stable_id, stability = self._segment_for(kind="table", index=index, identity=identity)
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, "table", identity)
        path = parent.child(segment)
        size = _first_child(element, "sz")
        pos = _first_child(element, "pos")
        table_record = NodeRecord(
            kind="table",
            path=path.canonical,
            stable_id=stable_id,
            stability=stability,
            summary={
                "rowCount": table.row_count,
                "columnCount": table.column_count,
                "caption": _child_text(element, "caption"),
                "widthMm": _mm(size.get("width")) if size is not None else None,
                "alignment": pos.get("horzAlign") if pos is not None else None,
            },
            native=table,
            parent_path=parent.canonical,
            attributes={"id": identity or "", "type": element.get("numberingType", "table")},
            search_text=paragraph.text,
        )
        self._add_record(table_record)
        for child in element:
            local = _local_name(child)
            if local not in {"sz", "pos", "caption", "outMargin", "inMargin", "tr"}:
                table_record.mark_unsupported(local)
        for row_index, row in enumerate(table.rows, start=1):
            row_path = path.child(indexed_segment("row", row_index))
            heights = [cell.height for cell in row.cells]
            self._add_record(
                NodeRecord(
                    kind="row",
                    path=row_path.canonical,
                    stable_id=None,
                    stability="positional",
                    summary={
                        "index": row_index,
                        "cellCount": len(row.cells),
                        "heightMm": _mm(max(heights)) if heights else None,
                    },
                    native=row,
                    parent_path=path.canonical,
                    attributes={"type": "row"},
                )
            )
            for cell_index, cell in enumerate(row.cells, start=1):
                cell_path = row_path.child(indexed_segment("cell", cell_index))
                address_row, address_column = cell.address
                row_span, column_span = cell.span
                sublist = _first_child(cell.element, "subList")
                cell_record = NodeRecord(
                    kind="cell",
                    path=cell_path.canonical,
                    stable_id=None,
                    stability="positional",
                    summary={
                        "text": _bounded_text(cell.text),
                        "row": address_row + 1,
                        "column": address_column + 1,
                        "rowSpan": row_span,
                        "columnSpan": column_span,
                        "verticalAlignment": (
                            sublist.get("vertAlign") if sublist is not None else None
                        ),
                    },
                    native=cell,
                    parent_path=row_path.canonical,
                    attributes={"type": "cell"},
                    search_text=cell.text,
                )
                self._add_record(cell_record)
                for child in cell.element:
                    local = _local_name(child)
                    if local not in {
                        "subList",
                        "cellAddr",
                        "cellSpan",
                        "cellSz",
                        "cellMargin",
                    }:
                        cell_record.mark_unsupported(local)
                for paragraph_index, nested in enumerate(cell.paragraphs, start=1):
                    self._project_paragraph(
                        nested,
                        cell_path,
                        paragraph_index,
                        section_index=-1,
                        paragraph_index_in_section=None,
                    )

    def _project_picture(
        self, element: Any, paragraph: Any, parent: SemanticPath, index: int
    ) -> None:
        identity = _identity(element, "id", "instid", "instId")
        segment, stable_id, stability = self._segment_for(kind="picture", index=index, identity=identity)
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, "picture", identity)
        path = parent.child(segment)
        image = next((child for child in element.iter() if _local_name(child) == "img"), None)
        size = _first_child(element, "sz")
        name = element.get("name") or (image.get("binaryItemIDRef") if image is not None else None)
        self._add_record(
            NodeRecord(
                kind="picture",
                path=path.canonical,
                stable_id=stable_id,
                stability=stability,
                summary={
                    "name": name,
                    "altText": (
                        _child_text(element, "shapeComment")
                        or element.get("altText")
                        or element.get("title")
                    ),
                    "widthMm": _mm(size.get("width")) if size is not None else None,
                    "heightMm": _mm(size.get("height")) if size is not None else None,
                },
                native=element,
                parent_path=parent.canonical,
                attributes={"id": identity or "", "name": name or "", "type": "picture"},
                search_text=name or "",
            )
        )

    def _project_shape(
        self, element: Any, paragraph: Any, parent: SemanticPath, index: int
    ) -> None:
        shape = HwpxOxmlShape(element, paragraph)
        identity = shape.inst_id
        segment, stable_id, stability = self._segment_for(kind="shape", index=index, identity=identity)
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, "shape", identity)
        path = parent.child(segment)
        pos = _first_child(element, "pos")
        name = element.get("name")
        self._add_record(
            NodeRecord(
                kind="shape",
                path=path.canonical,
                stable_id=stable_id,
                stability=stability,
                summary={
                    "shapeType": shape.shape_type,
                    "name": name,
                    "altText": (
                        _child_text(element, "shapeComment")
                        or element.get("altText")
                        or element.get("title")
                    ),
                    "xMm": _mm(pos.get("horzOffset")) if pos is not None else None,
                    "yMm": _mm(pos.get("vertOffset")) if pos is not None else None,
                    "widthMm": _mm(shape.width),
                    "heightMm": _mm(shape.height),
                },
                native=shape,
                parent_path=parent.canonical,
                attributes={"id": identity or "", "name": name or "", "type": shape.shape_type},
                search_text=name or "",
            )
        )

    def _project_note(self, note: Any, parent: SemanticPath, kind: str, index: int) -> None:
        identity = note.inst_id
        segment, stable_id, stability = self._segment_for(kind=kind, index=index, identity=identity)
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, kind, identity)
        path = parent.child(segment)
        self._add_record(
            NodeRecord(
                kind=kind,
                path=path.canonical,
                stable_id=stable_id,
                stability=stability,
                summary={"text": _bounded_text(note.text)},
                native=note,
                parent_path=parent.canonical,
                attributes={"id": identity or "", "type": kind},
                search_text=note.text,
            )
        )

    def _project_form_field(
        self, match: dict[str, Any], parent: SemanticPath, index: int
    ) -> None:
        identity = str(match.get("field_id") or match.get("id") or "").strip() or None
        name = str(match.get("name") or "").strip() or None
        segment, stable_id, stability = self._segment_for(
            kind="form-field", index=index, identity=identity, name=name
        )
        if identity and stability == "positional":
            self._register_ambiguous_relative(parent, "form-field", identity)
        elif name and stability == "positional":
            self._register_ambiguous_relative(parent, "form-field", name, attribute="name")
        path = parent.child(segment)
        runs = match.get("_runs") or []
        ctrl = None
        begin = None
        try:
            ctrl = list(runs[int(match["run_index"])])[int(match["child_index"])]
            begin = next(child for child in ctrl if _local_name(child) == "fieldBegin")
        except (IndexError, KeyError, StopIteration, TypeError, ValueError):
            pass
        read_only = None
        if begin is not None:
            editable = begin.get("editable")
            if editable is not None:
                read_only = str(editable).strip().lower() in {"0", "false", "no"}
        self._add_record(
            NodeRecord(
                kind="form-field",
                path=path.canonical,
                stable_id=stable_id,
                stability=stability,
                summary={
                    "name": name,
                    "value": _bounded_text(match.get("current_value")),
                    "fieldType": match.get("field_type"),
                    "readOnly": read_only,
                },
                native=match,
                parent_path=parent.canonical,
                attributes={
                    "id": identity or "",
                    "name": name or "",
                    "type": str(
                        match.get("field_type") or match.get("control_type") or "form-field"
                    ),
                },
                search_text=" ".join(
                    str(match.get(key) or "")
                    for key in ("name", "current_value", "prompt", "instruction")
                ),
            )
        )

    def resolve_record(
        self,
        path: str,
        *,
        expected_revision: str | None = None,
        require_stable: bool = False,
    ) -> NodeRecord:
        if expected_revision is not None and expected_revision != self.revision:
            raise AgentContractError("stale_revision", "document revision does not match", target=path)
        canonical = canonicalize_path(path)
        if canonical in self._ambiguous_paths:
            raise AgentContractError("ambiguous_target", "path identity is duplicated", target=canonical)
        record = self._records.get(canonical)
        if record is None:
            raise AgentContractError("not_found", f"semantic path not found: {canonical}", target=canonical)
        if require_stable and record.stability == "positional":
            raise AgentContractError("volatile_target", "target has a positional path", target=canonical)
        return record

    def _public_node(self, record: NodeRecord, *, depth: int, child_limit: int) -> AgentNode:
        supported_total = len(record.child_paths)
        selected_paths = record.child_paths[:child_limit] if depth > 0 else []
        children = tuple(
            self._public_node(self._records[path], depth=depth - 1, child_limit=child_limit)
            for path in selected_paths
        )
        truncated = supported_total - len(selected_paths)
        catalog = NODE_PROPERTY_CATALOG_V1[record.kind]
        return AgentNode(
            kind=record.kind,
            path=record.path,
            stable_id=record.stable_id,
            stability=record.stability,
            summary=record.summary,
            child_count=supported_total + record.unsupported_child_count,
            children=children,
            unsupported_child_count=record.unsupported_child_count,
            truncated_child_count=truncated,
            readable_properties=tuple(catalog["readable"]),
            editable_properties=tuple(catalog["editable"]),
            operations=tuple(catalog["operations"]),
            revision=self.revision,
        )

    def get(
        self,
        path: str = "/",
        *,
        depth: int = 1,
        child_limit: int = 50,
        expected_revision: str | None = None,
    ) -> AgentNode:
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= MAX_VIEW_DEPTH:
            raise AgentContractError(
                "resource_limit", f"depth must be 0..{MAX_VIEW_DEPTH}", target="depth"
            )
        if (
            isinstance(child_limit, bool)
            or not isinstance(child_limit, int)
            or not 1 <= child_limit <= MAX_CHILDREN_PER_NODE
        ):
            raise AgentContractError(
                "resource_limit",
                f"childLimit must be 1..{MAX_CHILDREN_PER_NODE}",
                target="childLimit",
            )
        record = self.resolve_record(path, expected_revision=expected_revision)
        return self._public_node(record, depth=depth, child_limit=child_limit)

    def query(
        self,
        selector: str,
        *,
        limit: int,
        node_depth: int = 0,
        child_limit: int = 20,
        expected_revision: str | None = None,
    ) -> QueryResult:
        if expected_revision is not None and expected_revision != self.revision:
            raise AgentContractError("stale_revision", "document revision does not match", target="selector")
        parsed = parse_selector(selector)
        matches, truncated = evaluate_selector(self.records, parsed, limit=limit)
        if not 0 <= node_depth <= MAX_VIEW_DEPTH:
            raise AgentContractError("resource_limit", "nodeDepth is out of bounds", target="nodeDepth")
        if not 1 <= child_limit <= MAX_CHILDREN_PER_NODE:
            raise AgentContractError("resource_limit", "childLimit is out of bounds", target="childLimit")
        return QueryResult(
            selector=selector,
            revision=self.revision,
            nodes=tuple(
                self._public_node(record, depth=node_depth, child_limit=child_limit) for record in matches
            ),
            truncated=truncated,
        )


__all__ = ["HwpxAgentDocument", "NodeRecord"]
