# SPDX-License-Identifier: Apache-2.0
"""Narrow typed native bridge used only by blueprint replay.

This module accepts validated blueprint records.  It deliberately exposes no
XML, namespace, package-part, or arbitrary-attribute input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlTable
from hwpx.oxml.namespaces import HH, HP

from ..commands import _add, _insert_direct_child, _insert_inline, _remove_inline_element, _table_caption
from ..document import HwpxAgentDocument, NodeRecord
from ..model import AgentContractError

_HWP_UNITS_PER_MM = 7200 / 25.4
_INLINE_KINDS = frozenset({"table", "picture", "shape", "footnote", "endnote"})


@dataclass(frozen=True, slots=True)
class CreatedBinding:
    kind: str
    native: Any
    native_id: str | None = None


def _local_name(element: Any) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _direct_child(element: Any, kind: str) -> Any | None:
    return next((child for child in element if _local_name(child) == kind), None)


def _mm_units(value: object, default: int) -> int:
    if value is None:
        return default
    return max(1, round(float(value) * _HWP_UNITS_PER_MM))


def _bool(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def create_paragraph_style(
    document: HwpxDocument, properties: dict[str, Any], *, source_key: str
) -> dict[str, str]:
    """Create one allow-listed paragraph style with a collision-free name."""

    if not document._root.headers:  # type: ignore[attr-defined]
        raise AgentContractError("unsupported_content", "target has no style header", target=source_key)
    header = document._root.headers[0]  # type: ignore[attr-defined]
    styles = header._styles_element()  # type: ignore[attr-defined]
    if styles is None:
        raise AgentContractError("unsupported_content", "target has no style registry", target=source_key)
    base_name = str(properties.get("name") or "Blueprint Style")[:200]
    existing_names = {str(style.name) for style in document.styles.values() if style.name}
    target_name = base_name
    if target_name in existing_names:
        target_name = f"{base_name}__bp_{source_key.rsplit(':', 1)[-1][:8]}"
    para_pr_id = header.ensure_paragraph_format(
        base_para_pr_id="0",
        alignment=properties.get("alignment"),
        line_spacing_percent=properties.get("lineSpacingPercent"),
        break_setting={
            key: value
            for key, value in {
                "keep_with_next": properties.get("keepWithNext"),
                "page_break_before": properties.get("breakBefore"),
            }.items()
            if isinstance(value, bool)
        }
        or None,
    )
    style_id = header._allocate_ref_id(styles, f"{HH}style")  # type: ignore[attr-defined]
    attrs = {
        "id": style_id,
        "type": str(properties.get("type") or "PARA"),
        "name": target_name,
        "engName": str(properties.get("englishName") or target_name)[:200],
        "paraPrIDRef": para_pr_id,
        "charPrIDRef": "0",
        "nextStyleIDRef": style_id,
        "langID": "0",
        "lockForm": "1" if properties.get("lockForm") else "0",
    }
    styles.append(styles.makeelement(f"{HH}style", attrs))
    header._update_item_count(styles, f"{HH}style")  # type: ignore[attr-defined]
    header.mark_dirty()
    return {"styleIDRef": style_id, "paraPrIDRef": para_pr_id, "name": target_name}


def create_character_format(document: HwpxDocument, properties: dict[str, Any]) -> str:
    return document.ensure_run_style(
        bold=_bool(properties.get("bold")),
        italic=_bool(properties.get("italic")),
        underline=_bool(properties.get("underline")),
        color=properties.get("color"),
        size=properties.get("fontSizePt"),
    )


def create_numbering(document: HwpxDocument, properties: dict[str, Any]) -> str:
    raw_type = str(properties.get("type") or "NUMBER").upper()
    kind = "bullet" if raw_type == "BULLET" else "number"
    level = max(0, int(properties.get("level") or 0))
    refs = document.ensure_numbering(kind=kind, levels=[{} for _ in range(level + 1)])
    return refs[level]


def _move_to_host_run(paragraph: Any, native: Any, host_run: Any) -> None:
    element = getattr(native, "element", native)
    temporary_run = None
    for run in list(paragraph.element):
        if _local_name(run) == "run" and any(child is element for child in run):
            temporary_run = run
            break
    if temporary_run is not None and temporary_run is not host_run.element:
        temporary_run.remove(element)
        if len(temporary_run) == 0:
            paragraph.element.remove(temporary_run)
        host_run.element.append(element)
        paragraph.section.mark_dirty()


class TypedNativeBridge:
    """Construct validated blueprint nodes through existing typed primitives."""

    def __init__(
        self,
        document: HwpxDocument,
        manifest: dict[str, Any],
        dependency_targets: dict[str, dict[str, Any]],
    ) -> None:
        self.document = document
        self.manifest = manifest
        self.nodes = {str(node["blueprintId"]): node for node in manifest["nodes"]}
        self.dependency_targets = dependency_targets
        self.created: dict[str, CreatedBinding] = {}
        self.references = {
            (str(item["from"]), str(item["field"])): str(item["to"])
            for item in manifest["references"]
        }
        self._identity_seed = self._max_numeric_identity()

    def _max_numeric_identity(self) -> int:
        maximum = 0
        for section in self.document.sections:
            for element in section.element.iter():
                for name in ("id", "instid", "instId"):
                    value = str(element.get(name) or "")
                    if value.isdigit():
                        maximum = max(maximum, int(value))
        return maximum

    def _identity(self) -> str:
        self._identity_seed += 1
        return str(self._identity_seed)

    def _dependency(self, node: dict[str, Any], field: str) -> dict[str, Any] | None:
        refs = list(node[field])
        if not refs:
            return None
        if len(refs) != 1:
            raise AgentContractError(
                "invariant_violation", f"{node['kind']} requires at most one {field}", target=node["blueprintId"]
            )
        return self.dependency_targets[str(refs[0])]

    def _apply_paragraph_dependencies(self, paragraph: Any, node: dict[str, Any]) -> None:
        style = self._dependency(node, "styleRefs")
        if style is not None:
            paragraph.style_id_ref = style["identity"]["styleIDRef"]
            paragraph.para_pr_id_ref = style["identity"]["paraPrIDRef"]
        numbering = self._dependency(node, "numberingRefs")
        if numbering is not None:
            definition = self.document.paragraph_property(numbering["identity"]["paraPrIDRef"])
            heading = definition.heading if definition is not None else None
            if heading is None or not self.document._root.headers:  # type: ignore[attr-defined]
                raise AgentContractError("invariant_violation", "mapped numbering has no heading")
            paragraph.para_pr_id_ref = self.document._root.headers[0].ensure_paragraph_format(  # type: ignore[attr-defined]
                base_para_pr_id=paragraph.para_pr_id_ref,
                heading={"type": heading.type or "NONE", "idRef": heading.id_ref or 0, "level": heading.level or 0},
            )

    def _populate_run(self, run: Any, node: dict[str, Any]) -> None:
        character = self._dependency(node, "styleRefs")
        if character is not None:
            run.char_pr_id_ref = character["identity"]["charPrIDRef"]
        run.text = str(node["properties"].get("text") or "")
        self.created[str(node["blueprintId"])] = CreatedBinding("run", run)

    def _create_runs(self, paragraph: Any, child_ids: list[str], *, reuse_existing: bool) -> None:
        run_ids = [child_id for child_id in child_ids if self.nodes[child_id]["kind"] == "run"]
        existing = list(paragraph.runs) if reuse_existing else []
        for index, run_id in enumerate(run_ids):
            node = self.nodes[run_id]
            if index < len(existing):
                run = existing[index]
            else:
                character = self._dependency(node, "styleRefs")
                char_ref = character["identity"]["charPrIDRef"] if character is not None else None
                run = paragraph.add_run("", char_pr_id_ref=char_ref)
            self._populate_run(run, node)
        for run in existing[len(run_ids) :]:
            # Newly created section/cell paragraphs may carry one structural
            # control run.  Preserve it only when it has non-text children.
            if all(_local_name(child) in {"t", "tab"} for child in run.element):
                paragraph.element.remove(run.element)

    def _host_run(self, node_id: str, paragraph: Any) -> Any:
        target_id = self.references.get((node_id, "hostRun"))
        if target_id is not None:
            try:
                return self.created[target_id].native
            except KeyError as exc:
                raise AgentContractError("invariant_violation", "host run was not constructed", target=node_id) from exc
        return paragraph.add_run("")

    def _create_paragraph(
        self,
        node_id: str,
        parent: Any,
        *,
        existing: Any | None = None,
        root_view: HwpxAgentDocument | None = None,
        root_parent: NodeRecord | None = None,
        position: dict[str, Any] | None = None,
    ) -> Any:
        node = self.nodes[node_id]
        if existing is not None:
            paragraph = existing
            paragraph.clear_text()
            reuse_existing = True
        elif hasattr(parent, "add_paragraph") and _local_name(parent.element) == "tc":
            paragraph = parent.add_paragraph("")
            paragraph.clear_text()
            reuse_existing = True
        else:
            paragraph = parent.add_paragraph("", include_run=False, inherit_style=False)
            reuse_existing = False
        self._apply_paragraph_dependencies(paragraph, node)
        if root_view is not None and root_parent is not None and position and position["mode"] != "append":
            paragraph.element.getparent().remove(paragraph.element)
            _insert_direct_child(root_view, root_parent, "paragraph", paragraph.element, position)
            root_parent.native.mark_dirty()
        self.created[node_id] = CreatedBinding("paragraph", paragraph)
        child_ids = list(node["children"])
        self._create_runs(paragraph, child_ids, reuse_existing=reuse_existing)
        non_runs = [child_id for child_id in child_ids if self.nodes[child_id]["kind"] != "run"]
        if not child_ids:
            paragraph.text = str(node["properties"].get("text") or "")
        for child_id in non_runs:
            self._create_inline_or_table(child_id, paragraph)
        return paragraph

    def _create_table(self, node_id: str, paragraph: Any, host_run: Any) -> Any:
        node = self.nodes[node_id]
        properties = node["properties"]
        table = paragraph.add_table(
            int(properties["rowCount"]),
            int(properties["columnCount"]),
            width=_mm_units(properties.get("widthMm"), 7200 * int(properties["columnCount"])),
        )
        _move_to_host_run(paragraph, table, host_run)
        if properties.get("caption") is not None:
            _table_caption(table, str(properties["caption"] or ""))
        pos = _direct_child(table.element, "pos")
        if pos is not None and properties.get("alignment"):
            pos.set("horzAlign", str(properties["alignment"]).upper())
        self.created[node_id] = CreatedBinding("table", table)
        row_ids = [child for child in node["children"] if self.nodes[child]["kind"] == "row"]
        if len(row_ids) != len(table.rows):
            raise AgentContractError("invariant_violation", "table row count does not match graph", target=node_id)
        cell_layout = self._table_cell_layout(row_ids, int(properties["columnCount"]))
        for cell_id, row_index, column_index, row_span, column_span in cell_layout:
            if row_span > 1 or column_span > 1:
                table.merge_cells(
                    row_index,
                    column_index,
                    row_index + row_span - 1,
                    column_index + column_span - 1,
                )
        for row_id, row in zip(row_ids, table.rows, strict=True):
            self._bind_row(row_id, row)
        for cell_id, row_index, column_index, _row_span, _column_span in cell_layout:
            self._populate_cell(cell_id, table.cell(row_index, column_index))
        return table

    def _table_cell_layout(
        self,
        row_ids: list[str],
        column_count: int,
    ) -> list[tuple[str, int, int, int, int]]:
        occupancy = [[False for _ in range(column_count)] for _ in row_ids]
        layout: list[tuple[str, int, int, int, int]] = []
        for row_index, row_id in enumerate(row_ids):
            column_index = 0
            cell_ids = [
                child
                for child in self.nodes[row_id]["children"]
                if self.nodes[child]["kind"] == "cell"
            ]
            for cell_id in cell_ids:
                while column_index < column_count and occupancy[row_index][column_index]:
                    column_index += 1
                properties = self.nodes[cell_id]["properties"]
                row_span = int(properties.get("rowSpan") or 1)
                column_span = int(properties.get("columnSpan") or 1)
                if (
                    column_index >= column_count
                    or row_index + row_span > len(row_ids)
                    or column_index + column_span > column_count
                ):
                    raise AgentContractError(
                        "invariant_violation",
                        "table cell spans exceed the declared grid",
                        target=cell_id,
                    )
                for occupied_row in range(row_index, row_index + row_span):
                    for occupied_column in range(column_index, column_index + column_span):
                        if occupancy[occupied_row][occupied_column]:
                            raise AgentContractError(
                                "invariant_violation",
                                "table cell spans overlap",
                                target=cell_id,
                            )
                        occupancy[occupied_row][occupied_column] = True
                layout.append((cell_id, row_index, column_index, row_span, column_span))
                column_index += column_span
        if any(not occupied for row in occupancy for occupied in row):
            raise AgentContractError(
                "invariant_violation",
                "table graph does not cover the declared grid",
            )
        return layout

    def _bind_row(self, node_id: str, row: Any) -> None:
        node = self.nodes[node_id]
        self.created[node_id] = CreatedBinding("row", row)
        height = node["properties"].get("heightMm")
        if height is not None:
            for cell in row.cells:
                cell.set_size(height=_mm_units(height, cell.height))

    def _populate_row(self, node_id: str, row: Any) -> None:
        node = self.nodes[node_id]
        self._bind_row(node_id, row)
        cell_ids = [child for child in node["children"] if self.nodes[child]["kind"] == "cell"]
        if len(cell_ids) != len(row.cells):
            raise AgentContractError("invariant_violation", "table cell count does not match graph", target=node_id)
        for cell_id, cell in zip(cell_ids, row.cells, strict=True):
            self._populate_cell(cell_id, cell)

    def _populate_cell(self, node_id: str, cell: Any) -> None:
        node = self.nodes[node_id]
        properties = node["properties"]
        cell.set_span(int(properties.get("rowSpan") or 1), int(properties.get("columnSpan") or 1))
        sublist = _direct_child(cell.element, "subList")
        if sublist is not None and properties.get("verticalAlignment"):
            sublist.set("vertAlign", str(properties["verticalAlignment"]).upper())
        self.created[node_id] = CreatedBinding("cell", cell)
        paragraph_ids = [child for child in node["children"] if self.nodes[child]["kind"] == "paragraph"]
        existing = list(cell.paragraphs)
        for index, paragraph_id in enumerate(paragraph_ids):
            paragraph = existing[index] if index < len(existing) else None
            self._create_paragraph(paragraph_id, cell, existing=paragraph)
        for paragraph in existing[len(paragraph_ids) :]:
            if sublist is not None:
                sublist.remove(paragraph.element)
                cell.table.mark_dirty()
        if not paragraph_ids:
            cell.text = str(properties.get("text") or "")

    def _create_picture(self, node_id: str, paragraph: Any, host_run: Any) -> Any:
        node = self.nodes[node_id]
        resource = self._dependency(node, "resourceRefs")
        if resource is None:
            raise AgentContractError("invariant_violation", "picture has no mapped resource", target=node_id)
        properties = node["properties"]
        picture = paragraph.add_picture(
            resource["identity"]["binaryItemIDRef"],
            width=_mm_units(properties.get("widthMm"), 14400),
            height=_mm_units(properties.get("heightMm"), 14400),
            align=properties.get("alignment"),
            treat_as_char=_bool(properties.get("treatAsChar"), True),
        )
        _move_to_host_run(paragraph, picture, host_run)
        if properties.get("altText"):
            picture.element.set("altText", str(properties["altText"]))
        if properties.get("name"):
            picture.element.set("name", str(properties["name"]))
        self.created[node_id] = CreatedBinding("picture", picture)
        return picture

    def _create_shape(self, node_id: str, paragraph: Any, host_run: Any) -> Any:
        node = self.nodes[node_id]
        properties = node["properties"]
        shape_type = str(properties.get("shapeType") or "")
        kwargs = {
            "width": _mm_units(properties.get("widthMm"), 14400),
            "height": _mm_units(properties.get("heightMm"), 7200),
            "line_color": str(properties.get("lineColor") or "#000000"),
            "line_width": str(properties.get("lineWidth") or "283"),
            "fill_color": properties.get("fillColor"),
            "treat_as_char": True,
        }
        if shape_type == "rect":
            shape = paragraph.add_rectangle(ratio=int(properties.get("ratio") or 0), **kwargs)
        elif shape_type == "ellipse":
            shape = paragraph.add_ellipse(**kwargs)
        else:
            raise AgentContractError("unsupported_content", "shape type is not replayable", target=node_id)
        _move_to_host_run(paragraph, shape, host_run)
        if properties.get("altText"):
            shape.element.set("altText", str(properties["altText"]))
        if properties.get("name"):
            shape.element.set("name", str(properties["name"]))
        self.created[node_id] = CreatedBinding("shape", shape)
        return shape

    def _create_note(self, node_id: str, paragraph: Any, host_run: Any) -> Any:
        node = self.nodes[node_id]
        text = str(node["properties"].get("text") or "")
        note = paragraph.add_footnote(text) if node["kind"] == "footnote" else paragraph.add_endnote(text)
        _move_to_host_run(paragraph, note, host_run)
        self.created[node_id] = CreatedBinding(str(node["kind"]), note)
        return note

    def _create_form_field(self, node_id: str, paragraph: Any) -> None:
        node = self.nodes[node_id]
        properties = node["properties"]
        if str(properties.get("fieldType") or "FORM").upper() != "FORM":
            raise AgentContractError("unsupported_content", "only FORM fields are replayable", target=node_id)
        host_id = self.references.get((node_id, "hostRun"))
        end_id = self.references.get((node_id, "endRun"))
        if host_id is None or end_id is None:
            raise AgentContractError("invariant_violation", "form field run references are incomplete", target=node_id)
        host_run = self.created[host_id].native
        end_run = self.created[end_id].native
        field_id = self._identity()
        ctrl = host_run.element.makeelement(f"{HP}ctrl", {"type": "FORM"})
        begin = ctrl.makeelement(
            f"{HP}fieldBegin",
            {
                "id": field_id,
                "fieldName": str(properties.get("name") or "")[:512],
                "type": "FORM",
                "editable": "false" if properties.get("readOnly") else "true",
            },
        )
        ctrl.append(begin)
        host_run.element.append(ctrl)
        end_ctrl = end_run.element.makeelement(f"{HP}ctrl", {"type": "FORM"})
        end_ctrl.append(
            end_ctrl.makeelement(
                f"{HP}fieldEnd", {"beginIDRef": field_id, "fieldid": field_id}
            )
        )
        end_run.element.append(end_ctrl)
        paragraph.section.mark_dirty()
        self.created[node_id] = CreatedBinding("form-field", None, field_id)

    def _create_inline_or_table(self, node_id: str, paragraph: Any) -> Any:
        node = self.nodes[node_id]
        kind = str(node["kind"])
        if kind == "form-field":
            self._create_form_field(node_id, paragraph)
            return None
        host_run = self._host_run(node_id, paragraph)
        if kind == "table":
            return self._create_table(node_id, paragraph, host_run)
        if kind == "picture":
            return self._create_picture(node_id, paragraph, host_run)
        if kind == "shape":
            return self._create_shape(node_id, paragraph, host_run)
        if kind in {"footnote", "endnote"}:
            return self._create_note(node_id, paragraph, host_run)
        raise AgentContractError("unsupported_content", f"unsupported paragraph child: {kind}", target=node_id)

    def _create_memo(self, node_id: str, section: Any) -> Any:
        node = self.nodes[node_id]
        properties = node["properties"]
        attrs = {"author": str(properties["author"])} if properties.get("author") else None
        memo = section.add_memo(str(properties.get("text") or ""), attributes=attrs)
        self.created[node_id] = CreatedBinding("memo", memo)
        return memo

    def _create_section(self, node_id: str) -> Any:
        node = self.nodes[node_id]
        section = self.document.add_section()
        properties = node["properties"]
        size: dict[str, int] = {}
        if properties.get("pageWidthMm") is not None:
            size["width"] = _mm_units(properties["pageWidthMm"], 59528)
        if properties.get("pageHeightMm") is not None:
            size["height"] = _mm_units(properties["pageHeightMm"], 84189)
        if size:
            section.properties.set_page_size(**size)
        self.created[node_id] = CreatedBinding("section", section)
        paragraph_ids = [child for child in node["children"] if self.nodes[child]["kind"] == "paragraph"]
        existing = list(section.paragraphs)
        for index, paragraph_id in enumerate(paragraph_ids):
            paragraph = existing[index] if index < len(existing) else None
            self._create_paragraph(paragraph_id, section, existing=paragraph)
        for child_id in node["children"]:
            if self.nodes[child_id]["kind"] == "memo":
                self._create_memo(child_id, section)
        return section

    def create_root(
        self,
        parent: NodeRecord,
        position: dict[str, Any],
        view: HwpxAgentDocument,
    ) -> dict[str, CreatedBinding]:
        root_id = str(self.manifest["root"]["blueprintId"])
        root = self.nodes[root_id]
        kind = str(root["kind"])
        if kind == "document":
            self.created[root_id] = CreatedBinding("document", self.document)
            for child_id in root["children"]:
                self._create_section(child_id)
        elif kind == "section":
            if position["mode"] != "append":
                raise AgentContractError("unsupported_operation", "section replay is append-only")
            self._create_section(root_id)
        elif kind == "paragraph":
            self._create_paragraph(
                root_id,
                parent.native,
                root_view=view,
                root_parent=parent,
                position=position,
            )
        elif kind == "run":
            character = self._dependency(root, "styleRefs")
            char_ref = character["identity"]["charPrIDRef"] if character is not None else None
            run = parent.native.add_run(str(root["properties"].get("text") or ""), char_pr_id_ref=char_ref)
            if position["mode"] != "append":
                parent.native.element.remove(run.element)
                _insert_direct_child(view, parent, "run", run.element, position)
            self.created[root_id] = CreatedBinding("run", run)
        elif kind in _INLINE_KINDS:
            native = self._create_inline_or_table(root_id, parent.native)
            if position["mode"] != "append":
                _remove_inline_element(native.element, parent.native)
                _insert_inline(view, parent, kind, native.element, position)
        elif kind == "memo":
            if position["mode"] != "append":
                raise AgentContractError("unsupported_operation", "memo replay is append-only")
            self._create_memo(root_id, parent.native)
        elif kind == "row":
            properties = root["properties"]
            created_element = _add(
                self.document,
                view,
                parent,
                "row",
                {"cellCount": int(properties["cellCount"]), "heightMm": properties.get("heightMm")},
                position,
            )
            row = next(
                (candidate for candidate in parent.native.rows if candidate.element is created_element),
                None,
            )
            if row is None:
                raise AgentContractError("not_found", "replayed row was not materialized", target=root_id)
            self._populate_row(root_id, row)
        else:
            raise AgentContractError("unsupported_content", f"root kind is not replayable: {kind}")
        return self.created


__all__ = [
    "CreatedBinding",
    "TypedNativeBridge",
    "create_character_format",
    "create_numbering",
    "create_paragraph_style",
]
