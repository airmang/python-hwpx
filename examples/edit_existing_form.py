# SPDX-License-Identifier: Apache-2.0
"""Fill unique labels' right-hand cells; verify a staged copy before publishing.

This core-only example is deliberately limited to body tables, labels written
exactly as given, and one move to the right. It reads cells as the file has
them and guesses nothing; label matching that ignores spacing or follows
``label > right > down`` paths lives in python-hwpx-automation
(``hwpx_automation.forms``). It is not a replacement for automation's
revision/session workflows. No visual or within-modified-part preservation
guarantee is inferred from a successful save. Call
``fill_existing_form(source, output, {label: value})``.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument


def _distinct_output(source: Path, output: Path) -> None:
    if source.resolve() == output.resolve() or (
        output.exists() and source.samefile(output)
    ):
        raise ValueError("source and output must be different files")


def _targets(document: HwpxDocument, values: Mapping[str, str]) -> dict[str, dict]:
    """``{label: {"table_index", "row", "col", "text"}}``: the cell right of each label."""

    found: dict[str, list[dict]] = {label: [] for label in values}
    for table_index, table in enumerate(document.tables):
        grid = table.get_cell_map()
        for position in table.iter_grid():
            label = position.cell.text.strip()
            if not position.is_anchor or label not in found:
                continue
            col = position.column + position.col_span
            if col >= table.column_count:
                continue
            row, col = grid[position.row][col].anchor
            found[label].append(
                {"table_index": table_index, "row": row, "col": col, "text": table.cell(row, col).text}
            )
    targets = {}
    occupied = set()
    for label, matches in found.items():
        if len(matches) != 1:
            raise ValueError(f"expected one target for {label!r}; got {len(matches)}")
        match = matches[0]
        coordinate = (match["table_index"], match["row"], match["col"])
        if coordinate in occupied:
            raise ValueError("multiple labels resolve to the same target")
        occupied.add(coordinate)
        targets[label] = match
    return targets


def fill_existing_form(
    source: str | Path, output: str | Path, values: Mapping[str, str],
    *, expected_values: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Publish only after every requested label/value is verified on reopen.

    On any failure before publication, source and existing output stay intact.
    ``values`` maps literal labels to replacement strings, not navigation paths.
    When supplied, ``expected_values`` must cover every requested label and
    match the current right-hand cell text. This detects stale or wrong targets
    such as a spacer cell before a date field; it never guesses a different cell.
    Long values may require reflow in Hancom; visual verification is not run.
    """
    source, output = Path(source), Path(output)
    values = dict(values)
    if not values or any(
        not isinstance(label, str) or not label.strip() or ">" in label
        or not isinstance(value, str)
        for label, value in values.items()
    ):
        raise ValueError("provide non-empty literal labels and string values")
    _distinct_output(source, output)
    if expected_values is not None:
        expected_values = dict(expected_values)
        if expected_values.keys() != values.keys():
            raise ValueError("expected_values must cover every requested label")
    original = source.read_bytes()

    # Same filesystem as output so the final replace remains atomic.
    with tempfile.TemporaryDirectory(prefix=".hwpx-edit-", dir=output.parent) as work:
        candidate = Path(work) / "candidate.hwpx"
        with HwpxDocument.open(original) as document:
            expected = _targets(document, values)
            if expected_values is not None:
                for label, value in expected_values.items():
                    if expected[label]["text"] != value:
                        raise ValueError(f"unexpected current value for {label!r}; inspect the target")
            tables = document.tables.all
            for label, value in values.items():
                target = expected[label]
                tables[target["table_index"]].set_cell_text(target["row"], target["col"], value, logical=True)
            report = document.save_to_path(
                candidate, mode="patch", fallback="error", return_report=True
            )
        if not report.ok:
            raise ValueError("save verification failed")
        with HwpxDocument.open(candidate) as reopened:
            actual = _targets(reopened, values)
            for label, value in values.items():
                before, after = expected[label], actual[label]
                if (before["table_index"] != after["table_index"]
                        or before["row"] != after["row"]
                        or before["col"] != after["col"]
                        or after["text"] != value):
                    raise ValueError(f"output content verification failed: {label!r}")
        payload = candidate.read_bytes()
        if source.read_bytes() != original:
            raise ValueError("source changed during editing; retry from current input")
        _distinct_output(source, output)
        os.replace(candidate, output)

    receipt = report.to_dict()
    receipt["path"] = str(output)  # the exact verified candidate was renamed
    return {
        "output": str(output),
        "sourceSha256": hashlib.sha256(original).hexdigest(),
        "outputSha256": hashlib.sha256(payload).hexdigest(),
        "content": {"requested": len(values), "verified": len(values)},
        "mutation": receipt,
        "withinModifiedParts": "not_performed",
        "visual": receipt["verification"]["visual"],
    }
