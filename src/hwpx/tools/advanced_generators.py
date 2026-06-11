# SPDX-License-Identifier: Apache-2.0
"""Clean-room generators for common Korean office document blocks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence


def build_image_grid(
    images: Sequence[str | Mapping[str, Any]],
    *,
    columns: int = 2,
    image_width_mm: float | None = None,
) -> dict[str, Any]:
    """Return a plan-v2 image_grid block for a photo sheet."""

    normalized = _normalize_images(images)
    if not normalized:
        raise ValueError("images must contain at least one item")
    column_count = _positive_int(columns, field="columns")
    block: dict[str, Any] = {
        "type": "image_grid",
        "columns": column_count,
        "images": normalized,
    }
    if image_width_mm is not None:
        block["imageWidthMm"] = float(image_width_mm)
    return block


def build_meeting_nameplates(
    names: Sequence[str],
    *,
    size: str = "150x70",
    columns: int = 2,
) -> dict[str, Any]:
    """Return a plan-v2 table block for meeting nameplates."""

    clean_names = [str(name).strip() for name in names if str(name).strip()]
    if not clean_names:
        raise ValueError("names must contain at least one non-empty value")
    column_count = _positive_int(columns, field="columns")
    rows = _chunk(clean_names, column_count, fill="")
    return {
        "type": "table",
        "header": [f"명패 {index + 1}" for index in range(column_count)],
        "rows": rows,
        "columnWidths": [1 for _ in range(column_count)],
        "metadata": {"generator": "meeting_nameplates", "size": size},
    }


def build_organization_chart(
    hierarchy: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Return a table-based organization chart block for 2-3 level hierarchies."""

    depth = _positive_int(max_depth, field="max_depth")
    if depth not in {2, 3}:
        raise ValueError("max_depth must be 2 or 3")
    roots = list(hierarchy) if isinstance(hierarchy, Sequence) and not isinstance(hierarchy, Mapping) else [hierarchy]
    rows: list[list[str]] = []
    for root in roots:
        if not isinstance(root, Mapping):
            raise TypeError("organization chart nodes must be mappings")
        rows.extend(_flatten_org_node(root, depth=depth))
    if not rows:
        raise ValueError("hierarchy must contain at least one node")
    return {
        "type": "table",
        "header": [f"{index + 1}단계" for index in range(depth)],
        "rows": rows,
        "columnWidths": [1 for _ in range(depth)],
        "metadata": {"generator": "organization_chart", "maxDepth": depth},
    }


def _normalize_images(images: Sequence[str | Mapping[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in images:
        if isinstance(item, Mapping):
            path = str(item.get("path") or "").strip()
            caption = str(item.get("caption") or "").strip()
        else:
            path = str(item).strip()
            caption = ""
        if not path:
            raise ValueError("each image must define a non-empty path")
        normalized.append(
            {
                "path": path,
                "caption": caption or Path(path).stem,
            }
        )
    return normalized


def _positive_int(value: int | str, *, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _chunk(values: Sequence[str], columns: int, *, fill: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for offset in range(0, len(values), columns):
        row = list(values[offset : offset + columns])
        row.extend(fill for _ in range(columns - len(row)))
        rows.append(row)
    return rows


def _node_name(node: Mapping[str, Any]) -> str:
    value = node.get("name", node.get("title", node.get("label", "")))
    name = str(value or "").strip()
    if not name:
        raise ValueError("organization chart node must define name, title, or label")
    return name


def _flatten_org_node(
    node: Mapping[str, Any],
    *,
    depth: int,
    prefix: Sequence[str] = (),
) -> list[list[str]]:
    current = (*prefix, _node_name(node))
    children = node.get("children") or ()
    if len(current) >= depth or not children:
        row = list(current[:depth])
        row.extend("" for _ in range(depth - len(row)))
        return [row]
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes, bytearray)):
        raise TypeError("organization chart children must be a sequence")
    rows: list[list[str]] = []
    for child in children:
        if not isinstance(child, Mapping):
            raise TypeError("organization chart child nodes must be mappings")
        rows.extend(_flatten_org_node(child, depth=depth, prefix=current))
    return rows


__all__ = [
    "build_image_grid",
    "build_meeting_nameplates",
    "build_organization_chart",
]
