# SPDX-License-Identifier: Apache-2.0
"""Pure result payloads for the 6.0 return contract.

House convention (``hwpx.mutation_report``: ``ChangedPart``, ``PreservationSummary``):
``@dataclass(frozen=True)`` + ``to_dict()`` returning a ``camelCase`` dict for
callers that still want dict-shaped access. Unlike ``CheckBox``/``FormField``/
``TrackedChange``/``BinaryItem`` (living views over a document element), these
describe a *finished action* and do not point back at anything mutable, hence
frozen with no settable fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..form_fit.report import FitResult
    from ..model import InlineObject
    from .form_field import FormField


@dataclass(frozen=True)
class FieldFillResult:
    """The outcome of filling one form field (``doc.fields.fill``).

    5.x's dict carried an ``ok: bool`` key and kept going when it was
    ``False`` — a fit failure was reported, not refused, which is the shape
    the constitution's fail-closed rule (VI) rules out. 6.0 raises
    ``HwpxValueError(code="field-fit-failed")`` instead when a supplied
    ``FitPolicy`` cannot be satisfied, so reaching this dataclass at all means
    the fill already succeeded — there is no ``ok`` left to check.

    ``fit`` carries the FormFit engine's verdict when a ``fit_policy`` was
    supplied (``None`` otherwise): confidence, the font size actually applied,
    and any warnings. It is kept — trimming it would silently drop diagnostics
    the pre-existing FormFit integration suite asserts on — for the case where
    a value fit but only after being shrunk or wrapped.
    """

    field: "FormField"
    before: str
    after: str
    style_preserved: bool
    style_before: tuple[str, ...]
    style_after: tuple[str, ...]
    fit: "FitResult | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field.field_id,
            "before": self.before,
            "after": self.after,
            "stylePreserved": self.style_preserved,
            "styleBefore": list(self.style_before),
            "styleAfter": list(self.style_after),
            "fit": self.fit.to_dict() if self.fit is not None else None,
        }


@dataclass(frozen=True)
class PictureReplacement:
    """The outcome of swapping a body picture's image asset (``doc.media.replace_picture``).

    The existing ``<hp:pic>`` element is left in place — only its image
    reference changes — so geometry (size/position/crop/rotation/wrap) is
    untouched; this payload reports what moved, not what stayed.
    """

    picture: "InlineObject"
    item_id: str
    previous_item_id: str | None
    removed_orphans: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "previousItemId": self.previous_item_id,
            "removedOrphans": list(self.removed_orphans),
        }


@dataclass(frozen=True)
class Units:
    """Self-describing measurement units for a result's numeric fields.

    Only the axes the producing call actually measured are set; the rest stay
    ``None``. Each value is a short unit label (``"mm"``, ``"pt"``, ``"%"``).
    Shared by :class:`ParagraphFormatResult` and :class:`PageSetup`, which
    measure different axes — that is why every field is optional rather than
    each result defining its own single-purpose units type.
    """

    indent: str | None = None
    paragraph_spacing: str | None = None
    line_spacing: str | None = None
    page: str | None = None
    margins: str | None = None
    columns_gap: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in (
                ("indent", self.indent),
                ("paragraphSpacing", self.paragraph_spacing),
                ("lineSpacing", self.line_spacing),
                ("page", self.page),
                ("margins", self.margins),
                ("columnsGap", self.columns_gap),
            )
            if value is not None
        }


@dataclass(frozen=True)
class ListFormatResult:
    """The outcome of applying bullet/numbered formatting (``doc.styles.apply_list_format``)."""

    formatted: int
    paragraphs: tuple[int, ...]
    kind: str
    level: int
    para_pr_id_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "formatted": self.formatted,
            "paragraphs": list(self.paragraphs),
            "kind": self.kind,
            "level": self.level,
            "paraPrIDRef": self.para_pr_id_ref,
        }


@dataclass(frozen=True)
class ParagraphFormatResult:
    """The outcome of applying paragraph formatting (``doc.styles.apply_paragraph_format``)."""

    formatted: int
    paragraphs: tuple[int, ...]
    units: Units

    def to_dict(self) -> dict[str, Any]:
        return {
            "formatted": self.formatted,
            "paragraphs": list(self.paragraphs),
            "units": self.units.to_dict(),
        }


@dataclass(frozen=True)
class PageSize:
    """Page dimensions in millimetres, as measured by ``doc.page.setup``.

    5.x's dict labelled these ``"mm"`` in its ``units`` key while actually
    holding the HWPUNIT values already computed for the underlying
    ``set_page_size`` call — the number and its stated unit disagreed. This
    reports the millimetre inputs the call measured; ``hwpx.oxml`` section
    properties remain the HWPUNIT source of truth for what was written.
    """

    width_mm: float | None
    height_mm: float | None
    orientation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "widthMm": self.width_mm,
            "heightMm": self.height_mm,
            "orientation": self.orientation,
        }


@dataclass(frozen=True)
class PageMargins:
    """Page margins in millimetres, as measured by ``doc.page.setup``.

    Same honesty fix as :class:`PageSize` — millimetre inputs, not the
    HWPUNIT values the call converted them to before writing.
    """

    left: float | None
    right: float | None
    top: float | None
    bottom: float | None
    header: float | None
    footer: float | None
    gutter: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "top": self.top,
            "bottom": self.bottom,
            "header": self.header,
            "footer": self.footer,
            "gutter": self.gutter,
        }


@dataclass(frozen=True)
class ColumnLayout:
    """Column count/gap applied by ``doc.page.setup(columns=...)``."""

    count: int
    gap_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "gapMm": self.gap_mm}


@dataclass(frozen=True)
class PageSetup:
    """The outcome of ``doc.page.setup`` — page size, margins, and columns, in mm."""

    page_size: PageSize
    margins: PageMargins
    columns: ColumnLayout | None
    units: Units

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageSize": self.page_size.to_dict(),
            "margins": self.margins.to_dict(),
            "columns": self.columns.to_dict() if self.columns is not None else None,
            "units": self.units.to_dict(),
        }


__all__ = [
    "ColumnLayout",
    "FieldFillResult",
    "ListFormatResult",
    "PageMargins",
    "PageSetup",
    "PageSize",
    "ParagraphFormatResult",
    "PictureReplacement",
    "Units",
]
