# SPDX-License-Identifier: Apache-2.0
"""``styleCoverage`` — every style a composed body references must be defined
(plan §2 Phase E, task 3).

Because fragments are harvested from the *same* Hancom save as their skeleton,
coverage is 1.0 by construction. The check exists to catch the failure mode the
plan forbids: a fragment (or minimal-XML fallback) that references a ``charPr`` /
``paraPr`` / ``style`` the header never defined — i.e. imagined structure. In
production mode that drops coverage below threshold and the compose fails.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from ._support import ln

_REF_TO_KIND = {
    "charPrIDRef": "charPr",
    "paraPrIDRef": "paraPr",
    "styleIDRef": "style",
    "borderFillIDRef": "borderFill",
}


@dataclass(slots=True)
class StyleCoverage:
    coverage: float
    referenced: int
    covered: int
    missing: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing

    def meets(self, threshold: float) -> bool:
        return self.coverage >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": round(self.coverage, 4),
            "referenced": self.referenced,
            "covered": self.covered,
            "missing": [{"kind": k, "id": i} for k, i in self.missing],
        }


def header_style_ids(doc: Any) -> dict[str, set[str]]:
    """Collect defined style ids from the document's header part(s)."""

    ids: dict[str, set[str]] = {"charPr": set(), "paraPr": set(), "style": set(), "borderFill": set()}
    package = doc._package
    try:
        header_paths = package.header_paths()
    except Exception:  # pragma: no cover - defensive
        header_paths = []
    for path in header_paths:
        try:
            root = package.get_xml(path)
        except Exception:  # pragma: no cover - defensive
            continue
        for element in root.iter():
            name = ln(element.tag)
            if name in ids and element.get("id") is not None:
                ids[name].add(element.get("id"))
    return ids


def collect_references(elements: list[etree._Element]) -> list[tuple[str, str]]:
    """Return (kind, id) for every style reference in *elements*."""

    refs: list[tuple[str, str]] = []
    for root in elements:
        for element in root.iter():
            for attr, kind in _REF_TO_KIND.items():
                value = element.get(attr)
                if value is not None:
                    refs.append((kind, value))
    return refs


def style_coverage(doc: Any, elements: list[etree._Element]) -> StyleCoverage:
    """Fraction of style references in *elements* defined by *doc*'s header."""

    defined = header_style_ids(doc)
    refs = collect_references(elements)
    if not refs:
        return StyleCoverage(coverage=1.0, referenced=0, covered=0)
    missing: list[tuple[str, str]] = []
    covered = 0
    for kind, value in refs:
        if value in defined.get(kind, set()):
            covered += 1
        else:
            missing.append((kind, value))
    return StyleCoverage(
        coverage=covered / len(refs),
        referenced=len(refs),
        covered=covered,
        missing=missing,
    )


__all__ = ["StyleCoverage", "style_coverage", "header_style_ids", "collect_references"]
