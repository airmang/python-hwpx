# SPDX-License-Identifier: Apache-2.0
"""Callable-level document-operation ownership and core 4.x compatibility."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import hwpx
from hwpx import HwpxDocument, tools
from hwpx.tools.doc_diff import doc_diff, inspect_reference_consistency
from hwpx.tools.mail_merge import merge_template_rows
from hwpx.tools.redline import author_demo_redline, inspect_redline_structure

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (
        ROOT / "tests" / "data" / "document_ops_runtime_4x_freeze.json"
    ).read_text(encoding="utf-8")
)
MODULES = {
    name: importlib.import_module(name)
    for name in (
        "hwpx.tools.doc_diff",
        "hwpx.tools.mail_merge",
        "hwpx.tools.redline",
    )
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _signature(value: Any) -> str | None:
    if not callable(value):
        return None
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return "<uninspectable>"


def _qualified_compatibility_projection() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expected in FREEZE["qualifiedExports"]:
        value = getattr(MODULES[expected["module"]], expected["name"])
        rows.append(
            {
                "module": expected["module"],
                "name": expected["name"],
                "kind": type(value).__name__,
                "origin": getattr(value, "__module__", None),
                "signature": _signature(value),
                "value": None if callable(value) else value,
            }
        )
    return rows


def _reexported_projection(module: Any) -> list[dict[str, Any]]:
    prefixes = tuple(MODULES)
    rows: list[dict[str, Any]] = []
    for name in module.__all__:
        value = getattr(module, name)
        origin = getattr(value, "__module__", "") or ""
        if not any(
            origin == prefix or origin.startswith(f"{prefix}.")
            for prefix in prefixes
        ):
            continue
        rows.append(
            {
                "name": name,
                "origin": origin,
                "kind": type(value).__name__,
                "signature": _signature(value),
            }
        )
    return rows


def _deterministic_payloads() -> dict[str, Any]:
    return {
        "diff": doc_diff(["a", "b"], ["a", "c", "d"]),
        "reference": inspect_reference_consistency(
            ["표 1 현황", "표 3 결과", "붙임 1. 자료 1부.", "붙임 2 참조"]
        ),
        "rows": MODULES["hwpx.tools.mail_merge"].load_mail_merge_rows(
            [{"name": "A", "score": 0}]
        ),
    }


def _template(path: Path) -> None:
    document = HwpxDocument.new()
    try:
        document.add_paragraph("student={{student}}")
        document.save_to_path(path)
    finally:
        document.close()


def test_released_document_ops_4x_surface_is_exact() -> None:
    qualified = _qualified_compatibility_projection()
    top_level = _reexported_projection(hwpx)
    tools_level = _reexported_projection(tools)

    assert len(qualified) == FREEZE["qualifiedExportCount"] == 11
    assert _sha256(_canonical(qualified)) == FREEZE["qualifiedSnapshotSha256"]
    assert len(top_level) == FREEZE["topLevelExportCount"] == 6
    assert _sha256(_canonical(top_level)) == FREEZE["topLevelSnapshotSha256"]
    assert len(tools_level) == FREEZE["toolsExportCount"] == 6
    assert _sha256(_canonical(tools_level)) == FREEZE["toolsSnapshotSha256"]
    assert _sha256(_canonical(_deterministic_payloads())) == FREEZE[
        "deterministicPayloadsSha256"
    ]


def test_generic_merge_uses_only_the_injected_sanitizer(tmp_path: Path) -> None:
    template = tmp_path / "template.hwpx"
    _template(template)

    report = merge_template_rows(
        template,
        [{"student": "private"}],
        output_dir=tmp_path / "out",
        value_sanitizer=lambda value: value.upper(),
    )

    assert report["ok"] is True
    assert report["rows"][0]["maskedFields"] == ["student"]
    merged = HwpxDocument.open(report["rows"][0]["filename"])
    try:
        assert "PRIVATE" in merged.export_text()
    finally:
        merged.close()

    source = inspect.getsource(merge_template_rows)
    assert "mask_pii" not in source
    assert "hwpx_automation" not in source


def test_merge_template_rows_does_not_use_a_deprecated_internal_api(
    tmp_path: Path,
) -> None:
    """Regression: found live while building the v13 openrate generator
    (cycle 6.9 cleanup train) -- ``_replace_token`` called the deprecated
    5.x ``HwpxDocument.replace_text_in_runs`` shim internally instead of
    the current ``doc.text.replace``. Functionally harmless (the shim still
    delegates correctly) but a genuine 6.x-migration defect the openrate
    generator family's own warnings-as-errors discipline exists to catch
    (every ``generate_openrate_corpus_v*.py`` escalates DeprecationWarning
    to an error) -- this test locks the same property in at the unit level
    rather than only when a generator script happens to exercise it. Also
    exercises the table-cell replacement path (``_replace_token``'s own
    docstring: body-only ``doc.text.replace`` does not descend into
    ``hp:tbl`` cells, so that path is handled separately and must not
    regress either)."""

    template = HwpxDocument.new()
    try:
        template.add_paragraph("body: {{org}}")
        table = template.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "cell: {{dept}}"
        template_path = tmp_path / "template.hwpx"
        template.save_to_path(template_path)
    finally:
        template.close()

    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = merge_template_rows(
            template_path,
            [{"org": "테스트조직", "dept": "테스트부서"}],
            output_dir=tmp_path / "out",
        )

    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert not deprecation_warnings, [str(w.message) for w in deprecation_warnings]

    assert report["ok"] is True
    merged = HwpxDocument.open(report["rows"][0]["filename"])
    try:
        text = merged.text.plain()
        assert "테스트조직" in text
        assert "테스트부서" in text
    finally:
        merged.close()


def test_redline_structure_is_renderer_neutral(tmp_path: Path) -> None:
    after = tmp_path / "after.hwpx"
    document = HwpxDocument.new()
    try:
        document.add_paragraph("baseline")
        author_demo_redline(document)
        document.save_to_path(after)
    finally:
        document.close()

    report = inspect_redline_structure(after)

    assert report["changeCount"] == 2
    assert report["marksLinked"] is True
    assert report["displayEnabled"] is True
    assert report["opensClean"] is True


def test_neutral_redline_import_does_not_activate_visual_runtime() -> None:
    script = """
import json
import sys
from hwpx.tools.redline import inspect_redline_structure
print(json.dumps({
    "callable": callable(inspect_redline_structure),
    # The old assertion watched hwpx.visual.oracle, which 5.0 removed — it would
    # now pass by watching nothing. The boundary that still exists is the
    # companion package, so watch that.
    "visual": any(name.startswith("hwpx_automation.office.rendering") for name in sys.modules),
    "mcp": any(name.startswith("hwpx_automation") for name in sys.modules),
}))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(process.stdout) == {
        "callable": True,
        "visual": False,
        "mcp": False,
    }
