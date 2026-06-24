# SPDX-License-Identifier: Apache-2.0
"""Compose a new document from a profile + plan (plan §2 Phase E, task 2/3).

``compose`` lowers a :class:`~hwpx.design.plan.DocumentPlan` onto a verified
Hancom-saved skeleton: it clones the harvested fragments (real ``<hp:p>``/
``<hp:tbl>`` with real styles), fills their text/cells, preserves the template's
``secPr``/page setup, checks ``styleCoverage``, and saves through the single
:class:`~hwpx.quality.SavePipeline`. Every byte of structure traces to a real
Hancom save — never imagined XML. Production mode forbids any minimal-XML fallback.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from os import PathLike
from typing import Any
from uuid import uuid4

from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.quality import QualityPolicy

from . import _support as S
from .plan import Block, DocumentPlan
from .profile import Profile, load_profile
from .validator import StyleCoverage, style_coverage

# Roles a paragraph block may request; unknown roles fall back to body.
_PARAGRAPH_ROLES = ("title", "heading", "subheading", "body")


class ProfileRequiredError(RuntimeError):
    """Production compose could not stay on the verified template + fragments."""


@dataclass(slots=True)
class ComposeResult:
    ok: bool
    profile: str
    output_path: str | None
    visual_complete: Any
    style_coverage: StyleCoverage
    block_count: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": self.profile,
            "outputPath": self.output_path,
            "blockCount": self.block_count,
            "styleCoverage": self.style_coverage.to_dict(),
            "visualComplete": self.visual_complete.to_dict() if self.visual_complete else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def compose(
    plan: DocumentPlan | dict,
    *,
    profile: Profile | None = None,
    output_path: str | PathLike[str] | None = None,
    quality: QualityPolicy | None = None,
    production: bool = True,
) -> ComposeResult:
    """Lower *plan* onto its profile and save (or gate) through the SavePipeline."""

    if isinstance(plan, dict):
        plan = DocumentPlan.from_dict(plan)
    prof = profile or load_profile(plan.profile)
    warnings: list[str] = []

    doc = HwpxDocument.open(prof.template_bytes)
    try:
        section = doc.sections[0]
        secpr = S.find_secpr(section.element)
        if secpr is None:
            raise ProfileRequiredError(f"profile {prof.id!r} skeleton has no secPr")
        secpr = deepcopy(secpr)

        new_paragraphs: list[etree._Element] = []
        for block in plan.iter_blocks():
            frag = _fragment_for(prof, block, production, warnings)
            if frag is None:
                continue
            new_paragraphs.append(frag)

        if not new_paragraphs:
            raise ProfileRequiredError(
                f"plan produced no content for profile {prof.id!r}"
            )

        S.move_secpr_into(new_paragraphs[0], secpr)
        S.replace_section_body(section.element, new_paragraphs)
        _reassign_paragraph_ids(new_paragraphs)
        section.mark_dirty()

        coverage = style_coverage(doc, new_paragraphs)
        errors: list[str] = []
        if production and not coverage.meets(prof.style_coverage_threshold):
            errors.append(
                f"STYLE_COVERAGE_TOO_LOW: {coverage.coverage:.3f} < "
                f"{prof.style_coverage_threshold} (missing {coverage.missing[:5]})"
            )
            return ComposeResult(
                ok=False, profile=prof.id, output_path=None, visual_complete=None,
                style_coverage=coverage, block_count=len(new_paragraphs),
                warnings=warnings, errors=errors,
            )

        policy = quality or _default_policy()
        try:
            report = doc.save_report(output_path, quality=policy)
        except ValueError as exc:
            # save_report raises (not returns) when the serialized bytes fail the
            # open-safety floor — convert to the structured ok=False contract.
            return ComposeResult(
                ok=False, profile=prof.id, output_path=None, visual_complete=None,
                style_coverage=coverage, block_count=len(new_paragraphs),
                warnings=warnings, errors=[f"OPEN_SAFETY_FAILED: {exc}"],
            )
    finally:
        doc.close()

    return ComposeResult(
        ok=report.ok and coverage.ok,
        profile=prof.id,
        output_path=report.output_path,
        visual_complete=report,
        style_coverage=coverage,
        block_count=len(new_paragraphs),
        warnings=warnings + list(report.warnings),
        errors=[str(e) for e in report.errors],
    )


def compose_bytes(plan: DocumentPlan | dict, **kwargs: Any) -> tuple[bytes, ComposeResult]:
    """Compose and return the serialized bytes (no file written).

    The bytes are non-empty only when ``result.ok`` — on a gate failure the
    SavePipeline withholds the output, so the returned bytes are ``b""``. Callers
    MUST check ``result.ok`` before using the bytes.
    """

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "composed.hwpx"
        result = compose(plan, output_path=out, **kwargs)
        data = out.read_bytes() if out.exists() else b""
    return data, result


def _default_policy() -> QualityPolicy:
    # Structural-tier strict (no render here; the oracle gate runs separately):
    # open-safety + reference + layout lint on, render off.
    return QualityPolicy(
        require_open_safety=True,
        require_reference_integrity=True,
        require_visual_complete=False,
        render_check="off",
        layout_lint="strict",
        overflow_policy="warn",
    )


def _fragment_for(
    prof: Profile, block: Block, production: bool, warnings: list[str]
) -> etree._Element | None:
    if block.type == "table":
        if not prof.has_role("info_table"):
            _forbid_fallback(production, f"profile {prof.id!r} has no info_table fragment", warnings)
            return None
        frag = prof.fragment("info_table")
        _fill_table(frag, block.columns, block.rows, prof.id, warnings, production)
        return frag

    role = block.role if prof.has_role(block.role) else "body"
    if not prof.has_role(role):
        _forbid_fallback(production, f"profile {prof.id!r} has no {role!r} fragment", warnings)
        return None
    frag = prof.fragment(role)
    S.set_paragraph_text(frag, block.text)
    return frag


def _forbid_fallback(production: bool, message: str, warnings: list[str]) -> None:
    if production:
        raise ProfileRequiredError("PROFILE_REQUIRED: " + message)
    warnings.append("debug fallback: " + message)


# --------------------------------------------------------------------------- #
# Table filling (row-fit the harvested fragment to the plan's rows).
# --------------------------------------------------------------------------- #
def _fill_table(
    paragraph_frag: etree._Element,
    columns: list[str],
    rows: list[list[str]],
    profile_id: str = "",
    warnings: list[str] | None = None,
    production: bool = True,
) -> None:
    warnings = warnings if warnings is not None else []
    tbl = next((el for el in paragraph_frag.iter() if S.ln(el.tag) == "tbl"), None)
    if tbl is None:
        return
    trs = [c for c in tbl if S.ln(c.tag) == "tr"]
    if not trs:
        return
    header = trs[0]
    data_template = deepcopy(trs[1]) if len(trs) > 1 else deepcopy(trs[0])
    col_count = len([c for c in header if S.ln(c.tag) == "tc"])

    # The harvested grid has a fixed width; a plan asking for MORE columns would
    # silently lose data (fewer just leaves blank trailing cells). Surface it —
    # and in production refuse the lossy case rather than drop the user's content.
    want = len(columns) or max((len(r) for r in rows), default=0)
    if want > col_count:
        message = (
            f"TABLE_COLUMN_MISMATCH: plan asks for {want} columns but the "
            f"{profile_id!r} info_table grid has {col_count}; extra columns dropped"
        )
        if production:
            raise ProfileRequiredError("PROFILE_REQUIRED: " + message)
        warnings.append("debug fallback: " + message)
    elif 0 < want < col_count:
        warnings.append(
            f"table column-count mismatch: plan has {want} columns, "
            f"{profile_id!r} grid has {col_count}; trailing columns left blank"
        )

    # Always re-fill the header (even when columns is empty) so the harvested
    # {{cell}} placeholder never ships in the output.
    _fill_row(header, columns, col_count, row_addr=0)
    for tr in trs[1:]:
        tbl.remove(tr)

    header_index = list(tbl).index(header)
    data_rows = rows or [["" for _ in range(col_count)]]
    for offset, row in enumerate(data_rows):
        new_tr = deepcopy(data_template)
        _fill_row(new_tr, row, col_count, row_addr=offset + 1)
        tbl.insert(header_index + 1 + offset, new_tr)

    tbl.set("rowCnt", str(1 + len(data_rows)))
    S.strip_lineseg(paragraph_frag)


def _fill_row(tr: etree._Element, values: list[str], col_count: int, row_addr: int) -> None:
    tcs = [c for c in tr if S.ln(c.tag) == "tc"]
    for col_index, tc in enumerate(tcs):
        addr = next((c for c in tc if S.ln(c.tag) == "cellAddr"), None)
        if addr is not None:
            addr.set("rowAddr", str(row_addr))
            addr.set("colAddr", str(col_index))
        value = values[col_index] if col_index < len(values) else ""
        sublist = next((c for c in tc if S.ln(c.tag) == "subList"), None)
        target = sublist if sublist is not None else tc
        cell_paras = S.children_local(target, "p")
        # Collapse the cell to a single paragraph — a source cell may hold several
        # (empty) paragraphs, which Hancom flags as a damaged table after cloning.
        for extra in cell_paras[1:]:
            target.remove(extra)
        if cell_paras:
            S.set_paragraph_text(cell_paras[0], value)


def _reassign_paragraph_ids(paragraphs: list[etree._Element]) -> None:
    """Give every <hp:p> a fresh id so clones don't collide (id integrity)."""

    for root in paragraphs:
        for para in root.iter():
            if S.ln(para.tag) == "p" and para.get("id") is not None:
                para.set("id", str(uuid4().int % (2**31)))


__all__ = ["compose", "compose_bytes", "ComposeResult", "ProfileRequiredError"]
