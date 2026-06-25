# SPDX-License-Identifier: Apache-2.0
"""Reconcile a produced HWPX package against the model that produced it.

The intrinsic package validator checks that the archive is internally
consistent (every spine section resolves to a part). This module adds the
complementary *output-vs-intent* check: the number of ``Contents/sectionN.xml``
parts in the produced bytes must equal the number of sections in the source
document model. An intrinsic check passes a package that silently dropped or
duplicated a section between the model and the written bytes (e.g. a save
pipeline post-processing step); this catches it.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

__all__ = ["PackageReconcileReport", "reconcile_package_with_document"]

_SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$")


@dataclass(frozen=True)
class PackageReconcileReport:
    ok: bool
    expected_sections: int
    produced_sections: int
    problems: tuple[str, ...] = ()

    def summary(self) -> str:
        if self.ok:
            return f"reconciled: {self.produced_sections} section part(s) == model"
        return "; ".join(self.problems)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "expected_sections": self.expected_sections,
            "produced_sections": self.produced_sections,
            "problems": list(self.problems),
        }


def _count_section_parts(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return sum(1 for name in archive.namelist() if _SECTION_RE.match(name))


def reconcile_package_with_document(
    produced_bytes: bytes, document: object
) -> PackageReconcileReport:
    """Assert the produced package's section-part count equals the model's.

    *document* is the in-memory source (a :class:`~hwpx.document.HwpxDocument`);
    its ``sections`` length is the intended count.
    """

    expected = len(getattr(document, "sections", ()) or ())
    produced = _count_section_parts(produced_bytes)
    problems: list[str] = []
    if produced != expected:
        problems.append(
            f"section part count mismatch: produced={produced} model={expected}"
        )
    return PackageReconcileReport(
        ok=not problems,
        expected_sections=expected,
        produced_sections=produced,
        problems=tuple(problems),
    )
