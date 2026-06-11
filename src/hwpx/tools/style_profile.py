# SPDX-License-Identifier: Apache-2.0
"""Style profile extraction, transfer, and template registry helpers."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mail_merge import inspect_mail_merge_placeholders
from .template_analyzer import TemplateAnalysis, analyze_template

STYLE_PROFILE_SCHEMA_VERSION = "hwpx.style-profile.v1"
STYLE_PROFILE_COMPARISON_SCHEMA_VERSION = "hwpx.style-profile-comparison.v1"
TEMPLATE_REGISTRY_SCHEMA_VERSION = "hwpx.template-registry.v1"

_HWP_UNITS_PER_MM = 7200 / 25.4


def extract_style_profile(source: str | Path | TemplateAnalysis) -> dict[str, Any]:
    """Extract a compact, plan-applicable style profile from an HWPX document."""

    analysis = source if isinstance(source, TemplateAnalysis) else analyze_template(source)
    page = _page_profile(analysis)
    tables = [_table_profile(table) for table in analysis.table_summaries]
    return {
        "schemaVersion": STYLE_PROFILE_SCHEMA_VERSION,
        "sourceName": analysis.source_name,
        "page": page,
        "fonts": _font_profile(analysis),
        "runStyles": _run_style_profile(analysis),
        "tables": tables,
        "summary": {
            "sectionCount": len(analysis.section_layouts),
            "tableCount": len(tables),
            "charPropertyCount": len(analysis.char_properties),
            "bodyWidthHwp": page.get("bodyWidthHwp"),
        },
    }


def apply_style_profile_to_plan(
    document_plan: Mapping[str, Any],
    style_profile: Mapping[str, Any],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Return a copy of *document_plan* with page, margin, and table profile hints applied."""

    plan = copy.deepcopy(dict(document_plan))
    plan.setdefault("schemaVersion", "hwpx.document_plan.v2")
    plan["styleProfile"] = {
        "schemaVersion": style_profile.get("schemaVersion", STYLE_PROFILE_SCHEMA_VERSION),
        "sourceName": style_profile.get("sourceName"),
        "applied": True,
    }
    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        blocks = plan.pop("blocks", [])
        sections = [{"blocks": blocks if isinstance(blocks, list) else []}]
        plan["sections"] = sections

    page = style_profile.get("page") if isinstance(style_profile.get("page"), Mapping) else {}
    table_profiles = [table for table in style_profile.get("tables", []) if isinstance(table, Mapping)]
    table_index = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        if page:
            _apply_page_profile(section, page, overwrite=overwrite)
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or str(block.get("type")) != "table":
                continue
            profile = table_profiles[min(table_index, len(table_profiles) - 1)] if table_profiles else {}
            _apply_table_profile(block, profile, overwrite=overwrite)
            table_index += 1
    return plan


def compare_style_profiles(
    reference: str | Path | Mapping[str, Any],
    candidate: str | Path | Mapping[str, Any],
    *,
    margin_tolerance_mm: float = 1.0,
    table_weight_tolerance: float = 0.10,
) -> dict[str, Any]:
    """Compare two style profiles or HWPX files and return transfer evidence."""

    ref = _profile_arg(reference)
    got = _profile_arg(candidate)
    checks = [
        _check_orientation(ref, got),
        _check_margins(ref, got, tolerance_mm=margin_tolerance_mm),
        _check_table_weights(ref, got, tolerance=table_weight_tolerance),
    ]
    return {
        "schemaVersion": STYLE_PROFILE_COMPARISON_SCHEMA_VERSION,
        "pass": all(check["pass"] for check in checks),
        "checks": checks,
    }


def register_template(
    name: str,
    source: str | Path,
    *,
    registry_path: str | Path | None = None,
    description: str = "",
    tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Register a template path with its style profile and placeholder contract."""

    template_name = str(name or "").strip()
    if not template_name:
        raise ValueError("template name must be non-empty")
    source_path = Path(source).expanduser().resolve(strict=False)
    registry_file = _registry_path(registry_path)
    registry = _load_registry(registry_file)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    placeholders = inspect_mail_merge_placeholders(source_path)
    entry = {
        "name": template_name,
        "source": str(source_path),
        "description": str(description or ""),
        "tags": [str(tag) for tag in (tags or [])],
        "placeholderKeys": list(placeholders["keys"]),
        "placeholderCount": int(placeholders["placeholderCount"]),
        "styleProfile": extract_style_profile(source_path),
        "updatedAt": now,
    }
    existing = registry["templates"].get(template_name)
    entry["createdAt"] = existing.get("createdAt", now) if isinstance(existing, Mapping) else now
    registry["templates"][template_name] = entry
    _write_registry(registry_file, registry)
    return entry


def list_templates(*, registry_path: str | Path | None = None) -> dict[str, Any]:
    """List registered templates without returning full style profiles."""

    registry = _load_registry(_registry_path(registry_path))
    templates = []
    for entry in registry["templates"].values():
        if not isinstance(entry, Mapping):
            continue
        templates.append(
            {
                "name": entry.get("name"),
                "source": entry.get("source"),
                "description": entry.get("description", ""),
                "tags": list(entry.get("tags", [])),
                "placeholderKeys": list(entry.get("placeholderKeys", [])),
                "updatedAt": entry.get("updatedAt"),
            }
        )
    return {
        "schemaVersion": TEMPLATE_REGISTRY_SCHEMA_VERSION,
        "templates": sorted(templates, key=lambda item: str(item.get("name") or "")),
    }


def describe_template(
    name: str,
    *,
    registry_path: str | Path | None = None,
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one registered template and a placeholder fill report."""

    registry = _load_registry(_registry_path(registry_path))
    entry = registry["templates"].get(str(name))
    if not isinstance(entry, Mapping):
        raise KeyError(f"template is not registered: {name}")
    result = copy.deepcopy(dict(entry))
    result["placeholderReport"] = placeholder_fill_report(entry.get("placeholderKeys", []), values=values or {})
    return result


def placeholder_fill_report(
    source_or_keys: str | Path | Sequence[str],
    *,
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Report which standardized placeholders are unfilled by *values*."""

    if isinstance(source_or_keys, (str, Path)) and Path(source_or_keys).exists():
        keys = inspect_mail_merge_placeholders(source_or_keys)["keys"]
    else:
        keys = [str(key) for key in source_or_keys]  # type: ignore[arg-type]
    supplied = values or {}
    missing = [key for key in keys if supplied.get(key) in (None, "")]
    return {
        "schemaVersion": TEMPLATE_REGISTRY_SCHEMA_VERSION,
        "placeholderKeys": list(keys),
        "missingKeys": missing,
        "unfilledCount": len(missing),
        "ok": not missing,
    }


def _page_profile(analysis: TemplateAnalysis) -> dict[str, Any]:
    if not analysis.section_layouts:
        return {}
    layout = analysis.section_layouts[0]
    page: dict[str, Any] = {
        "widthHwp": layout.page_width,
        "heightHwp": layout.page_height,
        "bodyWidthHwp": layout.computed_body_width,
        "marginsHwp": dict(layout.margins),
        "marginsMm": {key: _hwp_to_mm(value) for key, value in layout.margins.items()},
    }
    if layout.page_width is not None:
        page["widthMm"] = _hwp_to_mm(layout.page_width)
    if layout.page_height is not None:
        page["heightMm"] = _hwp_to_mm(layout.page_height)
    if layout.page_width and layout.page_height:
        page["orientation"] = "LANDSCAPE" if layout.page_width > layout.page_height else "PORTRAIT"
    return page


def _font_profile(analysis: TemplateAnalysis) -> dict[str, Any]:
    faces: dict[str, list[str]] = {}
    for font_face in analysis.font_faces:
        values = []
        for font in font_face.fonts:
            face = font.get("face") or font.get("name")
            if face and face not in values:
                values.append(face)
        if values:
            faces[font_face.lang] = values
    primary = None
    for lang in ("hangul", "latin", "hanja", "japanese", "other"):
        if faces.get(lang):
            primary = faces[lang][0]
            break
    return {"primary": primary, "facesByLang": faces}


def _run_style_profile(analysis: TemplateAnalysis) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "flags": dict(item.flags),
            "fontRef": item.font_ref,
            "humanReadable": item.human_readable,
            "attributes": dict(item.attributes),
        }
        for item in analysis.char_properties
    ]


def _table_profile(table: Any) -> dict[str, Any]:
    widths = [int(width) if width is not None else None for width in table.column_widths.widths]
    numeric = [width or 0 for width in widths]
    total = sum(value for value in numeric if value > 0)
    if total > 0:
        weights = [round((value or 0) / total, 6) if value else 0 for value in widths]
    else:
        weights = [round(1 / max(len(widths), 1), 6) for _ in widths]
    margins = [cell.margin for cell in table.cells if cell.margin]
    return {
        "tableIndex": table.table_index,
        "rowCount": table.row_count,
        "columnCount": table.column_count,
        "columnWidthsHwp": widths,
        "columnWeights": weights,
        "completeColumnWidths": bool(table.column_widths.complete),
        "cellMarginHwp": _most_common_mapping(margins),
        "verticalAlignments": sorted({cell.vert_align for cell in table.cells if cell.vert_align}),
    }


def _apply_page_profile(section: dict[str, Any], page: Mapping[str, Any], *, overwrite: bool) -> None:
    if overwrite or "page" not in section:
        if page.get("widthMm") and page.get("heightMm"):
            section["page"] = {
                "widthMm": page["widthMm"],
                "heightMm": page["heightMm"],
                "orientation": page.get("orientation", "PORTRAIT"),
            }
    if overwrite or "margins" not in section:
        margins = page.get("marginsMm")
        if isinstance(margins, Mapping):
            section["margins"] = {
                f"{key}Mm": value
                for key, value in margins.items()
                if key in {"left", "right", "top", "bottom", "header", "footer", "gutter"}
            }


def _apply_table_profile(block: dict[str, Any], profile: Mapping[str, Any], *, overwrite: bool) -> None:
    weights = list(profile.get("columnWeights") or [])
    column_count = _block_column_count(block)
    if column_count <= 0 or not weights:
        return
    fitted = _fit_weights(weights, column_count)
    rows = block.get("rows") or []
    if "header" in block or any(isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)) for row in rows):
        if overwrite or "columnWidths" not in block:
            block["columnWidths"] = fitted
    elif isinstance(block.get("columns"), list):
        for column, weight in zip(block["columns"], fitted, strict=False):
            if isinstance(column, dict) and (overwrite or "widthWeight" not in column):
                column["widthWeight"] = max(int(round(weight * 100)), 1)


def _block_column_count(block: Mapping[str, Any]) -> int:
    if isinstance(block.get("header"), list) and block["header"]:
        return len(block["header"])
    if isinstance(block.get("columns"), list) and block["columns"]:
        return len(block["columns"])
    rows = block.get("rows") or []
    return max((len(row) for row in rows if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray))), default=0)


def _fit_weights(weights: Sequence[Any], count: int) -> list[float]:
    numeric = [max(float(weight or 0), 0.0) for weight in weights]
    if not numeric:
        numeric = [1.0]
    if len(numeric) < count:
        numeric.extend(numeric[-1] or 1.0 for _ in range(count - len(numeric)))
    numeric = numeric[:count]
    total = sum(numeric)
    if total <= 0:
        return [1.0 for _ in range(count)]
    return [round(value / total, 6) for value in numeric]


def _profile_arg(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return extract_style_profile(value)


def _check_orientation(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    expected = (reference.get("page") or {}).get("orientation") if isinstance(reference.get("page"), Mapping) else None
    actual = (candidate.get("page") or {}).get("orientation") if isinstance(candidate.get("page"), Mapping) else None
    return {"name": "page_orientation", "pass": expected == actual, "expected": expected, "actual": actual}


def _check_margins(reference: Mapping[str, Any], candidate: Mapping[str, Any], *, tolerance_mm: float) -> dict[str, Any]:
    ref_margins = _page_margins(reference)
    got_margins = _page_margins(candidate)
    deltas = {
        key: abs(float(ref_margins.get(key, 0)) - float(got_margins.get(key, 0)))
        for key in sorted(set(ref_margins) | set(got_margins))
    }
    return {"name": "page_margins", "pass": all(delta <= tolerance_mm for delta in deltas.values()), "toleranceMm": tolerance_mm, "deltasMm": deltas}


def _check_table_weights(reference: Mapping[str, Any], candidate: Mapping[str, Any], *, tolerance: float) -> dict[str, Any]:
    ref_tables = [table for table in reference.get("tables", []) if isinstance(table, Mapping)]
    got_tables = [table for table in candidate.get("tables", []) if isinstance(table, Mapping)]
    if not ref_tables and not got_tables:
        return {"name": "table_column_weights", "pass": True, "tablesCompared": 0, "maxDelta": 0}
    if not ref_tables or not got_tables:
        return {"name": "table_column_weights", "pass": False, "tablesCompared": 0, "maxDelta": None}
    ref = list(ref_tables[0].get("columnWeights") or [])
    got = list(got_tables[0].get("columnWeights") or [])
    count = min(len(ref), len(got))
    deltas = [abs(float(ref[index]) - float(got[index])) for index in range(count)]
    max_delta = max(deltas, default=0)
    return {
        "name": "table_column_weights",
        "pass": len(ref) == len(got) and max_delta <= tolerance,
        "tablesCompared": 1,
        "maxDelta": max_delta,
        "tolerance": tolerance,
    }


def _page_margins(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    page = profile.get("page")
    if not isinstance(page, Mapping):
        return {}
    margins = page.get("marginsMm")
    return margins if isinstance(margins, Mapping) else {}


def _registry_path(path: str | Path | None) -> Path:
    if path is None:
        return Path.home() / ".hwpx" / "template_registry.json"
    return Path(path).expanduser()


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": TEMPLATE_REGISTRY_SCHEMA_VERSION, "templates": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("template registry must be a JSON object")
    if not isinstance(payload.get("templates"), dict):
        payload["templates"] = {}
    payload["schemaVersion"] = TEMPLATE_REGISTRY_SCHEMA_VERSION
    return payload


def _write_registry(path: Path, registry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _most_common_mapping(values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for value in values:
        key = json.dumps(dict(value), sort_keys=True, ensure_ascii=False)
        current = counts.get(key)
        counts[key] = ((current[0] + 1) if current else 1, value)
    if not counts:
        return {}
    return dict(max(counts.values(), key=lambda item: item[0])[1])


def _hwp_to_mm(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / _HWP_UNITS_PER_MM, 3)


__all__ = [
    "STYLE_PROFILE_COMPARISON_SCHEMA_VERSION",
    "STYLE_PROFILE_SCHEMA_VERSION",
    "TEMPLATE_REGISTRY_SCHEMA_VERSION",
    "apply_style_profile_to_plan",
    "compare_style_profiles",
    "describe_template",
    "extract_style_profile",
    "list_templates",
    "placeholder_fill_report",
    "register_template",
]
