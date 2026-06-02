# SPDX-License-Identifier: Apache-2.0
"""Structural diagnostics for HWPX open/save/reopen roundtrips."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _doc_local_counts(doc: HwpxDocument) -> Counter[str]:
    counts: Counter[str] = Counter()
    for part in list(doc.oxml.headers) + list(doc.oxml.sections):
        for el in part.element.iter():
            counts[_local(el.tag)] += 1
    return counts


def roundtrip_report(source: str | Path | bytes) -> dict[str, Any]:
    before = HwpxDocument.open(source)
    before_counts = _doc_local_counts(before)

    data = before.to_bytes()
    after = HwpxDocument.open(data)
    after_counts = _doc_local_counts(after)

    lost = {
        k: before_counts[k] - after_counts.get(k, 0)
        for k in before_counts
        if before_counts[k] > after_counts.get(k, 0)
    }
    added = {
        k: after_counts[k] - before_counts.get(k, 0)
        for k in after_counts
        if after_counts[k] > before_counts.get(k, 0)
    }

    return {
        "reopened": True,
        "before_counts": dict(before_counts),
        "after_counts": dict(after_counts),
        "lost_elements": lost,
        "added_elements": added,
    }
