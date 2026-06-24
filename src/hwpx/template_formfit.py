# SPDX-License-Identifier: Apache-2.0
"""Baseline-driven template-preserving HWPX form-fit helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .document import HwpxDocument
from .tools.package_validator import validate_editor_open_safety, validate_package
from .tools.validator import validate_document

TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION = "hwpx.template-formfit.baseline.v1"
TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION = "hwpx.template-formfit.plan.v1"

_DEFAULT_RESIDUAL_MARKERS = ("작성 필요", "TODO", "□□□□", "○○", "(예시)")


def analyze_template_formfit(
    source: str | Path,
    *,
    baseline: Mapping[str, Any] | str | Path,
    content: Mapping[str, Any],
    destination: str | Path | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze a template-preserving generation run without mutating files."""

    source_path = Path(source)
    baseline_payload = _load_baseline(baseline)
    content_payload = copy.deepcopy(dict(content or {}))
    before_hash = _sha256_file(source_path)
    before_mtime = source_path.stat().st_mtime_ns
    doc = HwpxDocument.open(source_path)
    try:
        resolved, unresolved = _analyze_targets(doc, baseline_payload, content_payload)
        info = {
            "paragraph_count": len(doc.paragraphs),
            "table_count": _table_count(doc),
            "anchor_count": len(_anchors_from_baseline(baseline_payload)),
        }
    finally:
        doc.close()

    after_hash = _sha256_file(source_path)
    destination_path = Path(destination) if destination is not None else None
    return {
        "schemaVersion": TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION,
        "baseline": {
            "schemaVersion": baseline_payload.get("schemaVersion"),
            "baselineId": baseline_payload.get("baselineId"),
        },
        "source": {
            "path": str(source_path),
            "sha256": before_hash,
            "mtime_ns": before_mtime,
            "unchanged_after_analysis": after_hash == before_hash,
        },
        "destination": {
            "path": str(destination_path) if destination_path is not None else None,
            "required_for_apply": destination_path is not None,
        },
        "document": info,
        "content": content_payload,
        "resolved": resolved,
        "unresolved": unresolved,
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "mutated": False,
        "visual_review_required": bool(_visual_review_regions(baseline_payload)),
        "visual_review_regions": _visual_review_regions(baseline_payload),
        "residual_marker_policy": _residual_marker_policy(baseline_payload),
        "next_tool": "apply_template_formfit",
        "options": dict(options or {}),
    }


def apply_template_formfit(
    *,
    analysis: Mapping[str, Any] | None = None,
    source: str | Path | None = None,
    baseline: Mapping[str, Any] | str | Path | None = None,
    content: Mapping[str, Any] | None = None,
    destination: str | Path | None = None,
    confirm: bool = True,
) -> dict[str, Any]:
    """Apply a resolved template form-fit plan to a copied destination."""

    if not confirm:
        raise ValueError("confirm must be true to apply template form-fit mutations")

    plan = copy.deepcopy(dict(analysis or {}))
    if not plan:
        if source is None or baseline is None or content is None:
            raise ValueError("provide analysis or source, baseline, and content")
        plan = analyze_template_formfit(
            source,
            baseline=baseline,
            content=content,
            destination=destination,
        )

    source_path = Path(str(source or plan.get("source", {}).get("path") or ""))
    destination_value = destination or plan.get("destination", {}).get("path")
    if not destination_value:
        raise ValueError("destination is required")
    destination_path = Path(str(destination_value))

    if source_path.resolve(strict=False) == destination_path.resolve(strict=False):
        return {
            "handoff_status": "blocked",
            "reason": "source-in-place edit refused",
            "source": {"path": str(source_path), "sha256": _sha256_file(source_path)},
            "destination": {"path": str(destination_path)},
        }

    unresolved = list(plan.get("unresolved") or [])
    if unresolved:
        return {
            "handoff_status": "blocked",
            "reason": "unresolved template targets remain",
            "unresolved": unresolved,
            "source": {"path": str(source_path), "sha256": _sha256_file(source_path)},
            "destination": {"path": str(destination_path)},
        }

    source_before_hash = _sha256_file(source_path)
    source_before_mtime = source_path.stat().st_mtime_ns
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(destination_path.parent),
        suffix=(destination_path.suffix or ".hwpx") + ".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        shutil.copy2(source_path, tmp_path)
        copied_hash = _sha256_file(tmp_path)

        applied: list[dict[str, Any]] = []
        doc = HwpxDocument.open(tmp_path)
        try:
            for target in plan.get("resolved", []):
                applied.append(_apply_target(doc, dict(target)))
            # Funnel the write through the single SavePipeline and keep its uniform
            # report (plan §2 Phase B). The serialized bytes reach disk only via the
            # pipeline; the os.replace below merely publishes that gated temp.
            visual_complete = doc.save_report(tmp_path)
        finally:
            doc.close()

        validation = _runtime_validation(tmp_path)
        if not validation["openSafety"]["ok"]:
            raise ValueError(
                "template form-fit output failed editor-open safety validation: "
                + validation["openSafety"]["summary"]
            )
        residual_markers = _residual_markers(
            tmp_path,
            plan.get("residual_marker_policy") or {},
        )
        destination_hash = _sha256_file(tmp_path)
        os.replace(tmp_path, destination_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    source_after_hash = _sha256_file(source_path)
    source_after_mtime = source_path.stat().st_mtime_ns
    ready = (
        bool(validation["validate_package"]["ok"])
        and bool(validation["validate_document"]["ok"])
        and bool(validation["openSafety"]["ok"])
        and not residual_markers["blocking"]
    )
    return {
        "handoff_status": "ready" if ready else "needs_revision",
        "source": {
            "path": str(source_path),
            "sha256_before": source_before_hash,
            "sha256_after": source_after_hash,
            "mtime_ns_before": source_before_mtime,
            "mtime_ns_after": source_after_mtime,
            "preserved": (
                source_before_hash == source_after_hash
                and source_before_mtime == source_after_mtime
            ),
        },
        "destination": {
            "path": str(destination_path),
            "sha256_after_copy": copied_hash,
            "sha256_after_apply": destination_hash,
            "changed": copied_hash != destination_hash,
        },
        "applied": applied,
        "validation": validation,
        "visual_complete": visual_complete.to_dict(),
        "residual_markers": residual_markers,
        "visual_review_required": bool(plan.get("visual_review_required", True)),
        "visual_review_regions": list(plan.get("visual_review_regions") or []),
        "persisted": True,
    }


def _load_baseline(baseline: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(baseline, Mapping):
        payload = copy.deepcopy(dict(baseline))
    else:
        baseline_path = Path(baseline)
        if baseline_path.exists():
            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        else:
            payload = json.loads(str(baseline))
    schema_version = payload.get("schemaVersion")
    if schema_version != TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION:
        raise ValueError(
            "baseline schemaVersion must be "
            f"{TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION!r}"
        )
    return payload


def _analyze_targets(
    doc: HwpxDocument,
    baseline: Mapping[str, Any],
    content: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for field in baseline.get("scalarFields") or []:
        if not isinstance(field, Mapping):
            continue
        source_path = str(field.get("sourcePath") or "")
        value, has_value = _content_value(content, source_path)
        if not has_value:
            if field.get("required"):
                unresolved.append(_unresolved(field, "missing content"))
            continue
        target = _analyze_anchor_target(doc, field)
        if target["ok"]:
            resolved.append(
                {
                    "id": field.get("id"),
                    "kind": "scalar-line",
                    "anchor": target["anchor"],
                    "paragraph_index": target["paragraph_index"],
                    "sourcePath": source_path,
                    "value": _stringify_value(value),
                }
            )
        else:
            unresolved.append({**_unresolved(field, target["reason"]), **target})

    for mapping in baseline.get("regionMappings") or []:
        if not isinstance(mapping, Mapping):
            continue
        source_path = str(mapping.get("sourcePath") or "")
        value, has_value = _content_value(content, source_path)
        if not has_value:
            if mapping.get("required"):
                unresolved.append(_unresolved(mapping, "missing content"))
            continue
        target = _analyze_anchor_target(doc, mapping)
        if target["ok"]:
            resolved.append(
                {
                    "id": mapping.get("id"),
                    "kind": mapping.get("kind"),
                    "anchor": target["anchor"],
                    "paragraph_index": target["paragraph_index"],
                    "sourcePath": source_path,
                    "value": copy.deepcopy(value),
                    "columns": list(mapping.get("columns") or []),
                }
            )
        else:
            unresolved.append({**_unresolved(mapping, target["reason"]), **target})
    return resolved, unresolved


def _analyze_anchor_target(doc: HwpxDocument, item: Mapping[str, Any]) -> dict[str, Any]:
    locator = item.get("locator") if isinstance(item.get("locator"), Mapping) else {}
    anchor = str(item.get("anchor") or locator.get("anchor") or "").strip()
    if not anchor:
        return {"ok": False, "reason": "missing anchor", "anchor": anchor}
    matches = _find_anchor_matches(doc, anchor)
    if not matches:
        return {"ok": False, "reason": "anchor not found", "anchor": anchor}
    if len(matches) > 1:
        return {
            "ok": False,
            "reason": "ambiguous anchor",
            "anchor": anchor,
            "candidate_count": len(matches),
            "candidates": matches,
        }
    return {"ok": True, "anchor": anchor, **matches[0]}


def _find_anchor_matches(doc: HwpxDocument, anchor: str) -> list[dict[str, int]]:
    matches: list[dict[str, int]] = []
    global_index = 0
    for section_index, section in enumerate(doc.sections):
        for local_index, paragraph in enumerate(section.paragraphs):
            if anchor in (paragraph.text or ""):
                matches.append(
                    {
                        "paragraph_index": global_index,
                        "section_index": section_index,
                        "section_paragraph_index": local_index,
                    }
                )
            global_index += 1
    return matches


def _content_value(content: Mapping[str, Any], source_path: str) -> tuple[Any, bool]:
    if source_path in content:
        value = content[source_path]
        return value, _has_value(value)
    path = source_path.replace("[]", "")
    parts = [part for part in path.split(".") if part]
    current: Any = content
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        return None, False
    return current, _has_value(current)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _stringify_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return "\n".join(f"{key}: {val}" for key, val in value.items())
    return str(value)


def _unresolved(item: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "kind": item.get("kind") or item.get("locator", {}).get("kind"),
        "anchor": item.get("anchor") or item.get("locator", {}).get("anchor"),
        "sourcePath": item.get("sourcePath"),
        "required": bool(item.get("required")),
        "reason": reason,
        "next_action": "provide content, unique anchor, or a narrower baseline locator",
    }


def _apply_target(doc: HwpxDocument, target: dict[str, Any]) -> dict[str, Any]:
    kind = target.get("kind")
    if kind == "scalar-line":
        return _apply_scalar_line(doc, target)
    if kind == "section-region":
        return _apply_section_region(doc, target)
    if kind == "table-region":
        return _apply_table_region(doc, target)
    return {**target, "applied": False, "reason": f"unsupported target kind: {kind}"}


def _apply_scalar_line(doc: HwpxDocument, target: Mapping[str, Any]) -> dict[str, Any]:
    match = _single_current_anchor(doc, str(target["anchor"]))
    paragraph = doc.sections[match["section_index"]].paragraphs[
        match["section_paragraph_index"]
    ]
    before = paragraph.text or ""
    paragraph.text = f"{target['anchor']} {target.get('value', '')}".rstrip()
    return {**dict(target), "applied": True, "before_text": before, "after_text": paragraph.text}


def _apply_section_region(doc: HwpxDocument, target: Mapping[str, Any]) -> dict[str, Any]:
    match = _single_current_anchor(doc, str(target["anchor"]))
    section = doc.sections[match["section_index"]]
    anchor_index = int(match["section_paragraph_index"])
    paragraphs = _paragraph_values(target.get("value"))
    removed = _remove_placeholder_paragraphs(section, anchor_index + 1)
    template = removed[0] if removed else section.paragraphs[anchor_index].element
    new_elements = [_paragraph_clone_with_text(template, text) for text in paragraphs]
    section.insert_paragraphs(anchor_index + 1, new_elements)
    return {
        **dict(target),
        "applied": True,
        "inserted_paragraphs": len(new_elements),
        "removed_placeholders": len(removed),
    }


def _apply_table_region(doc: HwpxDocument, target: Mapping[str, Any]) -> dict[str, Any]:
    match = _single_current_anchor(doc, str(target["anchor"]))
    section = doc.sections[match["section_index"]]
    anchor_index = int(match["section_paragraph_index"])
    removed = _remove_placeholder_paragraphs(section, anchor_index + 1)
    rows = _table_rows(target.get("value"))
    columns = [str(column) for column in target.get("columns") or []]
    if not columns and rows:
        columns = list(rows[0].keys())
    generated = _build_table_paragraph(doc, columns, rows)
    section.insert_paragraphs(anchor_index + 1, [generated])
    return {
        **dict(target),
        "applied": True,
        "inserted_tables": 1,
        "inserted_rows": len(rows),
        "removed_placeholders": len(removed),
    }


def _single_current_anchor(doc: HwpxDocument, anchor: str) -> dict[str, int]:
    matches = _find_anchor_matches(doc, anchor)
    if len(matches) != 1:
        raise ValueError(f"anchor must resolve once during apply: {anchor!r}")
    return matches[0]


def _paragraph_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()] or [value]
    if isinstance(value, Mapping):
        raw = value.get("paragraphs") or value.get("body") or value.get("text") or []
        return _paragraph_values(raw)
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _table_rows(value: Any) -> list[dict[str, str]]:
    if isinstance(value, Mapping):
        raw = value.get("rows", [])
    else:
        raw = value
    rows: list[dict[str, str]] = []
    if not isinstance(raw, (list, tuple)):
        return rows
    for row in raw:
        if isinstance(row, Mapping):
            rows.append({str(key): _stringify_value(val) for key, val in row.items()})
    return rows


def _build_table_paragraph(
    doc: HwpxDocument,
    columns: list[str],
    rows: list[dict[str, str]],
) -> Any:
    table = doc.add_table(len(rows) + 1, max(1, len(columns)))
    for col, label in enumerate(columns or ["내용"]):
        table.set_cell_text(0, col, label)
    for row_index, row in enumerate(rows, start=1):
        for col_index, column in enumerate(columns or list(row.keys()) or ["내용"]):
            table.set_cell_text(row_index, col_index, row.get(column, ""))
    generated_paragraph = doc.sections[-1].paragraphs[-1]
    cloned = copy.deepcopy(generated_paragraph.element)
    doc.sections[-1].remove_paragraph(len(doc.sections[-1].paragraphs) - 1)
    return cloned


def _remove_placeholder_paragraphs(section: Any, start_index: int) -> list[Any]:
    removed: list[Any] = []
    while start_index < len(section.paragraphs):
        paragraph = section.paragraphs[start_index]
        text = (paragraph.text or "").strip()
        if not _looks_like_placeholder(text):
            break
        removed.append(copy.deepcopy(paragraph.element))
        section.remove_paragraph(start_index)
    return removed


def _looks_like_placeholder(text: str) -> bool:
    if not text:
        return True
    return any(marker in text for marker in _DEFAULT_RESIDUAL_MARKERS)


def _paragraph_clone_with_text(template: Any, text: str) -> Any:
    cloned = copy.deepcopy(template)
    paragraph = _ParagraphElementAdapter(cloned)
    paragraph.text = text
    return cloned


def _remove_layout_cache(element: Any) -> None:
    for child in list(element):
        if _local_name(child.tag).lower() == "linesegarray":
            element.remove(child)
        else:
            _remove_layout_cache(child)


class _ParagraphElementAdapter:
    def __init__(self, element: Any):
        self.element = element

    @property
    def text(self) -> str:
        texts = [node.text or "" for node in self.element.iter() if _local_name(node.tag) == "t"]
        return "".join(texts)

    @text.setter
    def text(self, value: str) -> None:
        text_nodes = [node for node in self.element.iter() if _local_name(node.tag) == "t"]
        if text_nodes:
            text_nodes[0].text = value
            for node in text_nodes[1:]:
                node.text = ""
        _remove_layout_cache(self.element)


def _local_name(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _runtime_validation(path: Path) -> dict[str, Any]:
    package_report = validate_package(path)
    document_report = validate_document(path)
    open_safety = validate_editor_open_safety(path)
    return {
        "validate_package": _report_payload(package_report, "checked_parts"),
        "validate_document": _report_payload(document_report, "validated_parts"),
        "openSafety": open_safety.to_dict(),
    }


def _report_payload(report: Any, parts_attr: str) -> dict[str, Any]:
    return {
        "ok": bool(getattr(report, "ok", False)),
        parts_attr: list(getattr(report, parts_attr, ())),
        "issues": [
            {
                "part": getattr(issue, "part_name", None),
                "message": getattr(issue, "message", str(issue)),
                "level": getattr(issue, "level", "error"),
            }
            for issue in getattr(report, "issues", ())
        ],
    }


def _residual_markers(path: Path, policy: Mapping[str, Any]) -> dict[str, Any]:
    markers = [
        str(marker)
        for marker in policy.get("patterns", _DEFAULT_RESIDUAL_MARKERS)
        if _marker_is_actionable(str(marker))
    ]
    doc = HwpxDocument.open(path)
    try:
        full_text = doc.export_text()
    finally:
        doc.close()
    blocking = [
        {"marker": marker}
        for marker in markers
        if marker and marker in full_text
    ]
    return {
        "blockOutsideVisualReview": bool(policy.get("blockOutsideVisualReview", True)),
        "patterns": markers,
        "blocking": blocking,
    }


def _marker_is_actionable(marker: str) -> bool:
    if marker in {"□", "empty ㅇ bullet", "empty - bullet", "※ ... 기재"}:
        return False
    return bool(marker.strip())


def _residual_marker_policy(baseline: Mapping[str, Any]) -> dict[str, Any]:
    locator_policy = baseline.get("locatorPolicy")
    if not isinstance(locator_policy, Mapping):
        return {"blockOutsideVisualReview": True, "patterns": list(_DEFAULT_RESIDUAL_MARKERS)}
    markers = locator_policy.get("residualMarkers")
    if not isinstance(markers, Mapping):
        return {"blockOutsideVisualReview": True, "patterns": list(_DEFAULT_RESIDUAL_MARKERS)}
    return {
        "blockOutsideVisualReview": bool(markers.get("blockOutsideVisualReview", True)),
        "patterns": list(markers.get("patterns") or _DEFAULT_RESIDUAL_MARKERS),
    }


def _anchors_from_baseline(baseline: Mapping[str, Any]) -> list[str]:
    anchors: list[str] = []
    for collection in ("scalarFields", "regionMappings", "visualReviewRegions"):
        for item in baseline.get(collection) or []:
            if not isinstance(item, Mapping):
                continue
            anchor = item.get("anchor")
            locator = item.get("locator") if isinstance(item.get("locator"), Mapping) else {}
            value = str(anchor or locator.get("anchor") or "").strip()
            if value:
                anchors.append(value)
    return anchors


def _visual_review_regions(baseline: Mapping[str, Any]) -> list[dict[str, Any]]:
    regions = baseline.get("visualReviewRegions") or baseline.get("visualReview") or []
    return [dict(region) for region in regions if isinstance(region, Mapping)]


def _table_count(doc: HwpxDocument) -> int:
    return sum(len(getattr(paragraph, "tables", [])) for paragraph in doc.paragraphs)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
