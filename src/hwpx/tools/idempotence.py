# SPDX-License-Identifier: Apache-2.0
"""Two-round (fixed-point) idempotence check for HWPX serialization.

Re-saving an already-saved document must reproduce the same part contents. A
drift between consecutive saves means the serializer is non-deterministic or
self-inconsistent (attribute/dict ordering, ID renumbering, whitespace, or
lineseg reflow), which the editor-open-safety classifier and the visual oracle
cannot see. This gate protects the core lossless read/edit guarantee and needs
neither Hancom nor a curated corpus.

The comparison is at the *part-content* level — the bytes of each ZIP entry —
deliberately ignoring ZIP container metadata (entry mtimes, compression method),
which are not byte-stable across saves and carry no document meaning.

Following the rhwp roundtrip doctrine: the *first* serializer output may
legitimately differ from the original input (we strip stale linesegarray,
normalize, etc.), but once through the serializer the representation must reach
a fixed point — so we compare round-1 output against round-2 output, not against
the original source.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from hwpx.document import HwpxDocument

__all__ = [
    "IdempotenceReport",
    "check_idempotent_pair",
    "check_save_idempotent",
]


@dataclass(frozen=True)
class IdempotenceReport:
    """Result of a two-round serialization fixed-point check."""

    ok: bool
    changed_parts: tuple[str, ...] = ()
    added_parts: tuple[str, ...] = ()
    removed_parts: tuple[str, ...] = ()

    def summary(self) -> str:
        if self.ok:
            return "idempotent: re-save reproduced identical part contents"
        bits: list[str] = []
        if self.changed_parts:
            bits.append(f"changed={list(self.changed_parts)}")
        if self.added_parts:
            bits.append(f"added={list(self.added_parts)}")
        if self.removed_parts:
            bits.append(f"removed={list(self.removed_parts)}")
        return "non-idempotent: " + "; ".join(bits)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "changed_parts": list(self.changed_parts),
            "added_parts": list(self.added_parts),
            "removed_parts": list(self.removed_parts),
        }


def _part_contents(data: bytes) -> tuple[dict[str, bytes], list[str]]:
    """Return ``(content_by_name, duplicate_names)`` for a HWPX byte blob.

    ``namelist()`` can legitimately repeat an entry name; a plain dict
    comprehension would silently collapse duplicates and let the fixed-point
    check false-pass. We surface any duplicate names so the caller can treat
    them as a divergence rather than ignore them.
    """

    contents: dict[str, bytes] = {}
    duplicates: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            name = info.filename
            if name in contents:
                duplicates.append(name)
            contents[name] = archive.read(info)
    return contents, duplicates


def check_idempotent_pair(first: bytes, second: bytes) -> IdempotenceReport:
    """Compare two serialized HWPX byte blobs at the part-content level.

    Any duplicate ZIP entry name (in either blob) is reported as a changed
    part so a structural anomaly can never be silently collapsed into a pass.
    """

    first_parts, first_dups = _part_contents(first)
    second_parts, second_dups = _part_contents(second)
    first_names = set(first_parts)
    second_names = set(second_parts)

    changed = tuple(
        sorted(
            {n for n in (first_names & second_names) if first_parts[n] != second_parts[n]}
            | set(first_dups)
            | set(second_dups)
        )
    )
    added = tuple(sorted(second_names - first_names))
    removed = tuple(sorted(first_names - second_names))
    ok = not (changed or added or removed)
    return IdempotenceReport(
        ok=ok,
        changed_parts=changed,
        added_parts=added,
        removed_parts=removed,
    )


def check_save_idempotent(
    source: HwpxDocument | str | bytes,
) -> IdempotenceReport:
    """Serialize *source* twice and assert the second-round part contents
    equal the first-round's.

    ``round1 = serialize(open(source))``  (the first serializer output)
    ``round2 = serialize(open(round1))``  (the second serializer output)

    The original input may legitimately differ from ``round1`` (we strip stale
    linesegarray, normalize, etc.); the invariant being checked is that the
    serializer reaches a fixed point from its own output onward.

    *source* may be an :class:`~hwpx.document.HwpxDocument`, a filesystem path,
    or raw HWPX bytes.
    """

    if isinstance(source, HwpxDocument):
        round1 = source.to_bytes()
    else:
        round1 = HwpxDocument.open(source).to_bytes()
    round2 = HwpxDocument.open(round1).to_bytes()
    return check_idempotent_pair(round1, round2)
