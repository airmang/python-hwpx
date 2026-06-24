# SPDX-License-Identifier: Apache-2.0
"""Conformance corpus model (plan §2 Phase G).

Phase G turns "docx-grade" into numbers. The corpus is the measured population:
a manifest (``corpus.json``) plus the ``.hwpx`` documents it points at, each
case declaring *which badge tiers apply* and *what passing means*.

Two visibilities, mirroring the §0.0 oracle boundary:

* ``public``  — committed, dependency-light docs (python-hwpx outputs). The
  structural tiers (Open-Safe / Semantic-Safe / Form-Safe measurement) run on
  these in any CI, with no Hancom and no imaging stack.
* ``private`` — real Hancom-saved docs (the 신청서/공문 originals) kept out of the
  repo. They carry layout caches and are the only honest input for the
  oracle-verified VisualComplete tier. A private corpus lives in a directory the
  runner is pointed at (``--corpus``), never bundled.

A case never claims a tier it cannot measure: :meth:`ConformanceCase.applies`
decides per tier, so the aggregate badge denominators only count cases that
actually exercised the tier (plan §0.0 "never blur the assurance tiers").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

BadgeTier = Literal["open_safe", "semantic_safe", "form_safe", "visual_complete"]
BADGE_TIERS: tuple[BadgeTier, ...] = (
    "open_safe",
    "semantic_safe",
    "form_safe",
    "visual_complete",
)
Visibility = Literal["public", "private"]


@dataclass(slots=True)
class FormSlot:
    """One value-in-a-slot fit check for the Form-Safe tier (plan §2 C/G).

    Selects a table cell by ``(table, row, col)`` index and asserts that
    ``value`` (or the cell's existing text when ``value`` is ``None``) fits the
    slot under FormFit measurement. ``max_lines`` is the slot's line budget.
    """

    table: int
    row: int
    col: int
    value: str | None = None
    max_lines: int = 1
    label: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FormSlot":
        return cls(
            table=int(data["table"]),
            row=int(data["row"]),
            col=int(data["col"]),
            value=data.get("value"),
            max_lines=int(data.get("maxLines", data.get("max_lines", 1))),
            label=data.get("label"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"table": self.table, "row": self.row, "col": self.col}
        if self.value is not None:
            out["value"] = self.value
        if self.max_lines != 1:
            out["maxLines"] = self.max_lines
        if self.label is not None:
            out["label"] = self.label
        return out


@dataclass(slots=True)
class ConformanceCase:
    """One measured document and the badge expectations declared for it.

    ``path`` is the document scored by every tier. ``before`` (optional) turns the
    VisualComplete tier into the oracle's **diff path** with real teeth: the
    before/after renders are compared and any change *outside* ``edit_mask`` (a
    fill spilling out of its slot, a stale-cache 글자 겹침) fails the case. Without
    ``before`` the visual tier is a conservative single-render pass (it only
    confirms the doc rasterizes with stable pagination — overlap/overflow needs a
    baseline, plan §2 Phase A/E). ``expect_visual_defect`` flips the sense so a
    deliberately-broken pair is a *positive control*: it passes when the oracle
    catches the defect, proving the gate is not rubber-stamping.
    """

    id: str
    path: str
    visibility: Visibility = "public"
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    form_slots: list[FormSlot] = field(default_factory=list)
    expect_open_safe: bool = True
    before: str | None = None
    edit_mask: dict[int, list[list[float]]] | None = None
    expect_visual_defect: bool = False
    note: str = ""

    def applies(self, tier: BadgeTier) -> bool:
        """Whether *tier* is measurable for this case (denominator membership).

        Open-Safe applies to every document; the others only apply when the case
        declares what would make them pass, so the corpus never inflates a badge
        with cases that never exercised the tier. VisualComplete is renderable for
        any document, so it always applies — but it can only be *verified* when an
        oracle is reachable (otherwise the runner records ``unverified``).
        """

        if tier == "open_safe":
            return True
        if tier == "semantic_safe":
            return bool(self.must_contain or self.must_not_contain)
        if tier == "form_safe":
            return bool(self.required_fields or self.form_slots)
        if tier == "visual_complete":
            return True
        return False

    def build_edit_mask(self) -> "Any | None":
        """Materialise ``edit_mask`` into a :class:`hwpx.visual.masks.EditMask`.

        Returns ``None`` when no mask is declared (strictest: nothing outside is
        allowed to change). Imported lazily so the structural tier never needs the
        visual package.
        """

        if not self.edit_mask:
            return None
        from hwpx.visual.masks import EditMask

        regions = {
            int(page): [tuple(float(v) for v in rect) for rect in rects]
            for page, rects in self.edit_mask.items()
        }
        return EditMask(regions=regions)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConformanceCase":
        raw_mask = data.get("editMask", data.get("edit_mask"))
        edit_mask = (
            {int(page): [list(rect) for rect in rects] for page, rects in raw_mask.items()}
            if raw_mask
            else None
        )
        return cls(
            id=str(data["id"]),
            path=str(data["path"]),
            visibility=data.get("visibility", "public"),
            must_contain=list(data.get("mustContain", data.get("must_contain", []))),
            must_not_contain=list(
                data.get("mustNotContain", data.get("must_not_contain", []))
            ),
            required_fields=list(
                data.get("requiredFields", data.get("required_fields", []))
            ),
            form_slots=[
                FormSlot.from_dict(slot)
                for slot in data.get("formSlots", data.get("form_slots", []))
            ],
            expect_open_safe=bool(
                data.get("expectOpenSafe", data.get("expect_open_safe", True))
            ),
            before=data.get("before"),
            edit_mask=edit_mask,
            expect_visual_defect=bool(
                data.get("expectVisualDefect", data.get("expect_visual_defect", False))
            ),
            note=str(data.get("note", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "path": self.path}
        if self.visibility != "public":
            out["visibility"] = self.visibility
        if self.must_contain:
            out["mustContain"] = list(self.must_contain)
        if self.must_not_contain:
            out["mustNotContain"] = list(self.must_not_contain)
        if self.required_fields:
            out["requiredFields"] = list(self.required_fields)
        if self.form_slots:
            out["formSlots"] = [slot.to_dict() for slot in self.form_slots]
        if not self.expect_open_safe:
            out["expectOpenSafe"] = False
        if self.before is not None:
            out["before"] = self.before
        if self.edit_mask:
            out["editMask"] = {
                str(page): [list(rect) for rect in rects]
                for page, rects in self.edit_mask.items()
            }
        if self.expect_visual_defect:
            out["expectVisualDefect"] = True
        if self.note:
            out["note"] = self.note
        return out


@dataclass(slots=True)
class ConformanceCorpus:
    """A manifest root + its cases. ``root`` resolves each case's ``path``."""

    root: Path
    cases: list[ConformanceCase] = field(default_factory=list)
    name: str = "corpus"

    def path_for(self, case: ConformanceCase) -> Path:
        return self.root / case.path

    def filter_visibility(self, visibility: Visibility) -> "ConformanceCorpus":
        return ConformanceCorpus(
            root=self.root,
            cases=[c for c in self.cases if c.visibility == visibility],
            name=self.name,
        )

    @classmethod
    def load(cls, manifest_path: str | Path) -> "ConformanceCorpus":
        """Read a ``corpus.json`` manifest. ``root`` defaults to its directory."""

        manifest_path = Path(manifest_path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        root = (
            manifest_path.parent / data["root"]
            if data.get("root")
            else manifest_path.parent
        )
        return cls(
            root=root,
            cases=[ConformanceCase.from_dict(c) for c in data.get("cases", [])],
            name=str(data.get("name", manifest_path.parent.name)),
        )

    @classmethod
    def bundled(cls) -> "ConformanceCorpus":
        """The packaged public corpus shipped under ``hwpx/conformance/corpus``."""

        corpus_dir = resources.files("hwpx.conformance") / "corpus"
        with resources.as_file(corpus_dir / "corpus.json") as manifest:
            return cls.load(manifest)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "cases": [c.to_dict() for c in self.cases]}


__all__ = [
    "BadgeTier",
    "BADGE_TIERS",
    "Visibility",
    "FormSlot",
    "ConformanceCase",
    "ConformanceCorpus",
]
