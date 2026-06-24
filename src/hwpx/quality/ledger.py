# SPDX-License-Identifier: Apache-2.0
"""``DirtyLayoutLedger`` — a lightweight record of *what an edit changed*.

Its purpose in Phase B is **the edit mask for the visual gate** (what changed →
where the visual oracle should look), NOT driving lineseg invalidation. Stale
``<hp:linesegarray>`` stripping is already handled at save time
(``opc/package._strip_section_layout_caches`` for re-serialised sections and
``patch._strip_paragraph_layout_cache`` for the byte path) — see the plan §0.1 and
guardrail "Layout cache ≠ content". So this stays intentionally thin: it
accumulates ``DirtyLayoutRange`` entries and exposes them for masking/reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DirtyReason = Literal[
    "text_replaced",
    "text_inserted",
    "text_deleted",
    "style_changed",
    "paragraph_style_changed",
    "table_cell_changed",
    "table_structure_changed",
    "image_changed",
    "section_changed",
    "form_filled",
    "builder_generated",
]

StoryType = Literal[
    "body",
    "header",
    "footer",
    "footnote",
    "endnote",
    "table_cell",
    "textbox",
    "unknown",
]

DirtyPolicy = Literal["none", "paragraph", "following", "story", "document"]


@dataclass(frozen=True)
class DirtyLayoutRange:
    """One edited region — "what changed" for the edit mask (plan Appendix A)."""

    part: str
    story_id: str = "body"
    story_type: StoryType = "body"
    start_paragraph: int | None = None
    end_paragraph: int | None = None
    table_path: list[int] | None = None
    cell_path: list[tuple[int, int]] | None = None
    reason: DirtyReason = "text_replaced"
    policy: DirtyPolicy = "story"

    def to_dict(self) -> dict[str, Any]:
        return {
            "part": self.part,
            "storyId": self.story_id,
            "storyType": self.story_type,
            "startParagraph": self.start_paragraph,
            "endParagraph": self.end_paragraph,
            "tablePath": self.table_path,
            "cellPath": [list(pair) for pair in self.cell_path] if self.cell_path else None,
            "reason": self.reason,
            "policy": self.policy,
        }


@dataclass
class DirtyLayoutLedger:
    """An accumulator of :class:`DirtyLayoutRange` entries for one save."""

    ranges: list[DirtyLayoutRange] = field(default_factory=list)

    def note(self, range_or_part: DirtyLayoutRange | str, **kwargs: Any) -> DirtyLayoutRange:
        """Record an edited range. Accepts a ready ``DirtyLayoutRange`` or kwargs."""

        if isinstance(range_or_part, DirtyLayoutRange):
            entry = range_or_part
        else:
            entry = DirtyLayoutRange(part=range_or_part, **kwargs)
        self.ranges.append(entry)
        return entry

    @property
    def is_empty(self) -> bool:
        return not self.ranges

    @property
    def parts(self) -> set[str]:
        return {entry.part for entry in self.ranges}

    def to_dict(self) -> dict[str, Any]:
        return {"ranges": [entry.to_dict() for entry in self.ranges]}


__all__ = [
    "DirtyLayoutLedger",
    "DirtyLayoutRange",
    "DirtyReason",
    "StoryType",
    "DirtyPolicy",
]
