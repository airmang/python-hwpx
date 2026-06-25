# SPDX-License-Identifier: Apache-2.0
"""Semantic (value-level) equality of two HWPX serializations.

The existing ``roundtrip_diff`` reports only a per-local-name element *count*
delta — it would pass even if every run in a paragraph were flattened into the
first run's formatting (the count is unchanged) or runs were reordered. This
module compares the *content sequence* instead: per paragraph, the ordered
sequence of run texts / inline-control kinds / nested tables, recursed into
table cells. Differences are reported with a localizing path.

Deliberately excluded from the comparison (no stable cross-serialization
counterpart): id values themselves (they renumber), attribute ordering, and
namespace-prefix spelling. Only meaning-bearing content sequence is compared.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

__all__ = [
    "IrEqualityReport",
    "project_section_xml",
    "project_document",
    "compare_documents_semantic",
]

_SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _project_paragraph(p_elem: ET.Element) -> list:
    """Project an ``<hp:p>`` into an ordered list of content items."""
    items: list = []
    for child in p_elem:
        if _local(child.tag) != "run":
            continue
        for node in child:
            ln = _local(node.tag)
            if ln == "t":
                items.append(("t", "".join(node.itertext())))
            elif ln == "tbl":
                items.append(("tbl", _project_table(node)))
            elif ln == "ctrl":
                first = next(iter(node), None)
                items.append(("ctrl", _local(first.tag) if first is not None else "ctrl"))
            else:
                items.append(("obj", ln))
    return items


def _project_table(tbl_elem: ET.Element) -> list:
    rows: list = []
    for tr in tbl_elem:
        if _local(tr.tag) != "tr":
            continue
        cells: list = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            sub = next((c for c in tc if _local(c.tag) == "subList"), None)
            cell_paras: list = []
            if sub is not None:
                cell_paras = [
                    _project_paragraph(p) for p in sub if _local(p.tag) == "p"
                ]
            cells.append(cell_paras)
        rows.append(cells)
    return rows


def project_section_xml(xml: str | bytes) -> list:
    """Project one section XML string into a list of paragraph projections."""
    root = ET.fromstring(xml)
    paras: list = []
    # Top-level paragraphs are direct <hp:p> children of the section root;
    # paragraphs nested in table cells are reached via recursion, not here.
    for child in root:
        if _local(child.tag) == "p":
            paras.append(_project_paragraph(child))
    return paras


def project_document(data: bytes) -> list:
    """Project a whole HWPX byte blob: paragraphs across all sections in order."""
    projection: list = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(
            (n for n in archive.namelist() if _SECTION_RE.match(n)),
            key=lambda n: int(_SECTION_RE.match(n).group(1)),
        )
        for name in names:
            projection.extend(project_section_xml(archive.read(name)))
    return projection


@dataclass(frozen=True)
class IrEqualityReport:
    ok: bool
    differences: tuple[str, ...] = ()

    def summary(self) -> str:
        if self.ok:
            return "semantically equal"
        return f"{len(self.differences)} difference(s): " + "; ".join(self.differences[:8])

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "differences": list(self.differences)}


def _diff(a, b, path: str, out: list) -> None:
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
    elif isinstance(a, tuple) and isinstance(b, tuple):
        if a[:1] != b[:1]:
            out.append(f"{path}: kind {a[:1]} != {b[:1]}")
            return
        _diff(a[1] if len(a) > 1 else None, b[1] if len(b) > 1 else None, path, out)
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")


def compare_documents_semantic(a: bytes, b: bytes) -> IrEqualityReport:
    """Compare two HWPX byte blobs at the content-sequence level."""
    out: list[str] = []
    _diff(project_document(a), project_document(b), "doc", out)
    return IrEqualityReport(ok=not out, differences=tuple(out))
