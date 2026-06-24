# SPDX-License-Identifier: Apache-2.0
"""``DocumentPlan`` — the model-facing description of a new document (Appendix B).

The LLM emits a plan (``hwpx.document_plan.v1``), never XML. Phase E lowers it
natively onto a verified Hancom-saved template + harvested fragments
(:mod:`hwpx.design.composer`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DOCUMENT_PLAN_SCHEMA = "hwpx.document_plan.v1"

BlockType = Literal["paragraph", "table"]
# Paragraph roles map to harvested fragments; table → the info-table fragment.
BlockRole = Literal["title", "heading", "subheading", "body", "info"]


@dataclass(slots=True)
class Block:
    """One block of a :class:`DocumentPlan`."""

    type: BlockType
    role: BlockRole = "body"
    text: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Block":
        return cls(
            type=data.get("type", "paragraph"),
            role=data.get("role", "body"),
            text=str(data.get("text", "")),
            columns=[str(c) for c in data.get("columns", [])],
            rows=[[str(c) for c in row] for row in data.get("rows", [])],
        )


@dataclass(slots=True)
class DocumentPlan:
    """A new-document plan (Appendix B ``hwpx.document_plan.v1``)."""

    profile: str
    title: str = ""
    blocks: list[Block] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentPlan":
        if not data.get("profile"):
            raise ValueError("DocumentPlan requires a 'profile'")
        return cls(
            profile=str(data["profile"]),
            title=str(data.get("title", "")),
            blocks=[Block.from_dict(b) for b in data.get("blocks", [])],
        )

    def iter_blocks(self) -> list[Block]:
        """Blocks with the title promoted to a leading title block."""

        blocks: list[Block] = []
        if self.title:
            blocks.append(Block(type="paragraph", role="title", text=self.title))
        blocks.extend(self.blocks)
        return blocks


__all__ = ["DocumentPlan", "Block", "BlockType", "BlockRole", "DOCUMENT_PLAN_SCHEMA"]
