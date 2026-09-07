# SPDX-License-Identifier: Apache-2.0
"""Fill unique labels' right-hand cells; verify a staged copy before publishing.

This core-only example is deliberately limited to labels followed by one right
move. It is not a replacement for automation's revision/session workflows.
No visual or within-modified-part preservation guarantee is inferred from a
successful save. Call ``fill_existing_form(source, output, {label: value})``.
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
    targets = {}
    occupied = set()
    for label in values:
        found = document.tables.find_cell_by_label(label, direction="right")
        if found["count"] != 1:
            raise ValueError(f"expected one target for {label!r}; got {found['count']}")
        match = found["matches"][0]
        cell = match["target_cell"]
        coordinate = (match["table_index"], cell["row"], cell["col"])
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
                    if expected[label]["target_cell"]["text"] != value:
                        raise ValueError(f"unexpected current value for {label!r}; inspect the target")
            mappings = {f"{label} > right": value for label, value in values.items()}
            result = document.tables.fill_by_path(mappings)
            if result["failed_count"] or result["applied_count"] != len(values):
                raise ValueError(f"incomplete fill: {result['failed']}")
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
                        or before["target_cell"]["row"] != after["target_cell"]["row"]
                        or before["target_cell"]["col"] != after["target_cell"]["col"]
                        or after["target_cell"]["text"] != value):
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
