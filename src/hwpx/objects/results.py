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

from dataclasses import dataclass, field as _field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..form_fit.report import FitResult
    from ..model import InlineObject, Paragraph, Section, Table
    from .form_field import FormField


def _section_number(section: "Section | None") -> int | None:
    """The number of *section* in its document (what ``to_dict()`` writes), ``None`` without one."""

    document = getattr(section, "document", None) if section is not None else None
    if document is None:
        return None
    return next((index for index, candidate in enumerate(document.sections) if candidate is section), None)


@dataclass(frozen=True)
class FieldFillResult:
    """The outcome of filling one form field (``doc.fields.fill``).

    5.x's dict carried an ``ok: bool`` key and kept going when it was
    ``False`` — a fit failure was reported, not refused, which is the shape
    the constitution's fail-closed rule (VI) rules out. 6.0 raises
    ``HwpxValueError(code="field-fit-failed")`` instead when a supplied
    ``FitPolicy`` cannot be satisfied, so reaching this dataclass at all means
    the fill already succeeded — there is no ``ok`` left to check.

    ``fit`` carries the FormFit engine's verdict when a ``FitPolicy`` was
    supplied (``doc.fields.fill(fit=...)``, ``None`` otherwise): confidence, the font size actually applied,
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
class ObjectPosition:
    """Where an object (picture, equation, shape, chart, table...) sits, as ``obj.position`` reads it.

    The names are the ones ``obj.set_position(...)`` takes. *treat_as_char*: one character in its
    line (``True``) or floating (``False``). *text_wrap* (the object's ``textWrap``: ``SQUARE``,
    ``TIGHT``, ``THROUGH``, ``TOP_AND_BOTTOM``, ``BEHIND_TEXT``, ``IN_FRONT_OF_TEXT``) and
    *text_flow* (``textFlow``: ``BOTH_SIDES``, ``LEFT_ONLY``, ``RIGHT_ONLY``, ``LARGEST_ONLY``) say
    how the body text goes around it. *horizontal_relative_to*/*vertical_relative_to* are the frames
    the offsets count from (``PAPER``, ``PAGE``, ``COLUMN``, ``PARA``),
    *horizontal_alignment*/*vertical_alignment* the alignment in them, and *horizontal_offset*/*vertical_offset* the offsets in HWPUNIT (signed: Hancom stores a
    negative one in its unsigned 32-bit form). *flow_with_text* keeps it inside the page body and
    *allow_overlap* lets it overlap other objects. A value the object does not carry is ``None``
    (an object without ``hp:pos`` -- a member of a group -- reads ``None`` throughout but
    *treat_as_char*, which is then ``False``). *treat_as_char* is ``False`` both when ``treatAsChar``
    says ``0`` and when nothing says it; *has_position* (the object carries ``hp:pos``) and
    *treat_as_char_written* (its ``hp:pos`` writes ``treatAsChar``) tell those apart. Hancom's saved
    documents write ``treatAsChar`` on every ``hp:pos``. A snapshot: it does not follow later edits.
    """

    treat_as_char: bool
    text_wrap: str | None
    text_flow: str | None
    horizontal_relative_to: str | None
    vertical_relative_to: str | None
    horizontal_alignment: str | None
    vertical_alignment: str | None
    horizontal_offset: int | None
    vertical_offset: int | None
    flow_with_text: bool | None
    allow_overlap: bool | None
    has_position: bool = True
    treat_as_char_written: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "treatAsChar": self.treat_as_char,
            "textWrap": self.text_wrap,
            "textFlow": self.text_flow,
            "horizontalRelativeTo": self.horizontal_relative_to,
            "verticalRelativeTo": self.vertical_relative_to,
            "horizontalAlignment": self.horizontal_alignment,
            "verticalAlignment": self.vertical_alignment,
            "horizontalOffset": self.horizontal_offset,
            "verticalOffset": self.vertical_offset,
            "flowWithText": self.flow_with_text,
            "allowOverlap": self.allow_overlap,
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
    ``width_mm``/``height_mm`` describe the page as drawn (a landscape page is
    wider than tall) and ``orientation`` is the ``landscape`` value written:
    ``WIDELY`` for portrait, ``NARROWLY`` for landscape.
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
class CellMargins:
    """A table cell's inner margins in HWPUNIT, as ``cell.margins`` reads them.

    These are the margins Hancom lays the cell out with: the table's
    ``hp:inMargin`` unless the cell turns its own ``hp:cellMargin`` on.
    """

    left: int
    right: int
    top: int
    bottom: int

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left, "right": self.right, "top": self.top, "bottom": self.bottom}


@dataclass(frozen=True)
class CellZone:
    """One cell zone of a table (``hp:cellzone``, ``table.cell_zones``): the rectangle of cells from
    (``row``, ``col``) to (``end_row``, ``end_col``), both included, drawn with the border fill
    ``border_fill_id_ref`` over the cells' own. Values as the file stores them."""

    row: int
    col: int
    end_row: int
    end_col: int
    border_fill_id_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row, "col": self.col, "endRow": self.end_row, "endCol": self.end_col,
                "borderFillIDRef": self.border_fill_id_ref}


@dataclass(frozen=True)
class LineSegment:
    """One line of a paragraph as it was last laid out and saved (``hp:lineseg``), as
    ``paragraph.line_segments`` reads it. Read only: values as the file stores them.

    *text_position* is where the line starts in the paragraph's text, counted as Hancom counts it
    (a tab or another inline control takes 8 places, a character outside the basic plane 2). **That is
    Hancom's count, not a place in** ``paragraph.text``: every other place python-hwpx reads or takes
    (``replace_range``, ``obj.offset``, ``move_to(offset=)``, ``TextMatch``) counts a tab as one and a
    control or an object as none. ``paragraph.line_texts`` gives each line's text cut at these places.
    *vertical_position* is the line's top from the top of its paragraph list (the page body, a
    cell or a text box), *height* the line's height, *text_height* the height of its tallest
    characters, *baseline* the distance from the line's top to its base line and *spacing* the
    room below it before the next line. *horizontal_position* is where the line starts from the
    left of its column (a hanging indent or an object beside it moves it right) and *width* how
    much room the line has. Lengths are HWPUNIT. *flags* is Hancom's bit set for the line as
    written (first line of a page or column and the like).
    """

    text_position: int
    vertical_position: int
    height: int
    text_height: int
    baseline: int
    spacing: int
    horizontal_position: int
    width: int
    flags: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "textPosition": self.text_position,
            "verticalPosition": self.vertical_position,
            "height": self.height,
            "textHeight": self.text_height,
            "baseline": self.baseline,
            "spacing": self.spacing,
            "horizontalPosition": self.horizontal_position,
            "width": self.width,
            "flags": self.flags,
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


@dataclass(frozen=True)
class ClearBodyReport:
    """The outcome of blanking a section down to a template (``Section.clear_body``).

    ``removed_paragraphs`` counts the section paragraphs after the first,
    ``removed_runs`` the first paragraph's runs after its first, and
    ``stripped_run_children`` the first run's children other than
    ``hp:secPr``/``hp:ctrl``. ``control_content`` lists the content tags
    (``"hp:t"``, ``"hp:tbl"``, ...) found inside the kept ``hp:secPr``/``hp:ctrl``
    children, in first-seen order. With ``on_control_content="strip"``,
    ``stripped_controls`` counts the ``hp:ctrl`` children removed for holding
    such content and ``stripped_section_stories`` the ``hp:header``/``hp:footer``
    story copies removed from inside ``hp:secPr`` (the ``hp:headerApply``/
    ``hp:footerApply`` elements pointing at them go too and are not counted).
    With ``keep_column_changes=True``, ``kept_column_paragraphs`` counts the later
    paragraphs kept for the column change they hold (not in ``removed_paragraphs``).
    """

    removed_paragraphs: int
    removed_runs: int
    stripped_run_children: int
    control_content: tuple[str, ...]
    stripped_controls: int
    stripped_section_stories: int
    kept_column_paragraphs: int = 0

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "removedParagraphs": self.removed_paragraphs,
            "removedRuns": self.removed_runs,
            "strippedRunChildren": self.stripped_run_children,
            "controlContent": list(self.control_content),
            "strippedControls": self.stripped_controls,
            "strippedSectionStories": self.stripped_section_stories,
        }
        if self.kept_column_paragraphs:  # only with keep_column_changes: the report stays as it was without
            data["keptColumnParagraphs"] = self.kept_column_paragraphs
        return data


@dataclass(frozen=True)
class BorderLine:
    """One side of an ``hh:borderFill`` (``doc.styles.border_fill``).

    ``type`` and ``color`` are the stored attribute values, unnormalized;
    ``width_mm`` is the number in front of the stored ``"<n> mm"`` width.
    """

    type: str
    width_mm: float
    color: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "widthMm": self.width_mm, "color": self.color}


@dataclass(frozen=True)
class BorderFillInfo:
    """A typed read of one ``hh:borderFill`` (``doc.styles.border_fill``).

    ``fill`` is the solid ``hc:winBrush`` face colour, or ``None`` when there
    is no solid fill. ``fill_kinds`` names what the ``hc:fillBrush`` holds, in
    file order: ``"color"`` (``hc:winBrush``, 면 색·무늬 -- also when its face
    colour is ``"none"``, as Hancom often writes it), ``"gradation"``
    (``hc:gradation``), ``"image"`` (``hc:imgBrush``) and ``"unknown"`` for
    anything else; ``()`` when there is no ``hc:fillBrush`` at all (채움 없음).
    Like the action results above, it is a snapshot taken at call time and
    does not follow later edits to the header.
    """

    id: str
    left: BorderLine
    right: BorderLine
    top: BorderLine
    bottom: BorderLine
    diagonal: BorderLine
    fill: str | None
    fill_kinds: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "top": self.top.to_dict(),
            "bottom": self.bottom.to_dict(),
            "diagonal": self.diagonal.to_dict(),
            "fill": self.fill,
            "fillKinds": list(self.fill_kinds),
        }


@dataclass(frozen=True)
class FontReplaceReport:
    """The outcome of ``doc.styles.replace_font``.

    ``langs`` lists the ``hh:fontface`` blocks that changed, in document
    order; ``declared`` the blocks where the replacement face was newly
    added; ``repointed`` counts the ``hh:fontRef`` attributes moved from the
    old face to the new one.
    """

    src_face: str
    dst_face: str
    langs: tuple[str, ...]
    repointed: int
    declared: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "srcFace": self.src_face,
            "dstFace": self.dst_face,
            "langs": list(self.langs),
            "repointed": self.repointed,
            "declared": list(self.declared),
        }


class Alignment(str, Enum):
    """A paragraph's horizontal alignment (``hh:align/@horizontal``), read by
    ``paragraph.alignment``. A ``str`` too: ``p.alignment == "CENTER"`` holds."""

    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"
    JUSTIFY = "JUSTIFY"
    DISTRIBUTE = "DISTRIBUTE"
    DISTRIBUTE_SPACE = "DISTRIBUTE_SPACE"

    def __str__(self) -> str:
        return self.value


class LineSpacingType(str, Enum):
    """How a paragraph's line spacing is measured (``hh:lineSpacing/@type``)."""

    PERCENT = "PERCENT"
    FIXED = "FIXED"
    BETWEEN_LINES = "BETWEEN_LINES"
    AT_LEAST = "AT_LEAST"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class LineSpacing:
    """A paragraph's line spacing (``paragraph.line_spacing``).

    ``value`` is a percentage of the character size for ``PERCENT`` (160 is
    Hancom's default) and a length in HWPUNIT (1/7200 inch, 100 per point) for
    ``FIXED``, ``BETWEEN_LINES`` and ``AT_LEAST``: the value Hancom shows in its
    paragraph dialog, the ``hp:case`` branch of the paragraph shape.
    """

    type: LineSpacingType
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", LineSpacingType(str(getattr(self.type, "value", self.type)).upper()))
        object.__setattr__(self, "value", int(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, "value": self.value}


@dataclass(frozen=True)
class NumberingLevel:
    """One level (``hh:paraHead``) of a numbering definition.

    ``text`` is the level's number pattern as stored (``"^1."``: ``^n`` stands
    for the number of level *n*); ``number_format`` the digit style
    (``DIGIT``, ``HANGUL_SYLLABLE``, ``CIRCLED_DIGIT``, ...); ``alignment`` where
    the number sits in its width (``hh:paraHead/@align``, ``LEFT`` when unsaid);
    ``char_pr_id_ref`` the character shape of the number, ``None`` when it
    follows the text (Hancom writes 4294967295 for that). ``use_instance_width``
    (``useInstWidth``, 7.0) is whether the number takes the width of the text
    it shows rather than a fixed one; ``auto_indent`` whether the paragraph
    hangs from the number; ``width_adjust`` the number width's correction and
    ``text_offset`` the room before the text (``text_offset_type`` ``PERCENT``
    or ``HWPUNIT``). Every field is the paraHead's attribute as written; an
    attribute the file leaves out reads as the OWPML schema's default for it
    (``start`` 1, ``DIGIT``, ``LEFT``, ``use_instance_width`` and
    ``auto_indent`` true, ``width_adjust`` 0, ``text_offset`` 50 ``PERCENT``;
    ``checkable``, which has none, false).
    """

    level: int
    start: int
    number_format: str
    text: str
    alignment: Alignment
    char_pr_id_ref: str | None
    auto_indent: bool
    width_adjust: int
    text_offset: int
    text_offset_type: str
    checkable: bool
    use_instance_width: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "start": self.start,
            "numberFormat": self.number_format,
            "text": self.text,
            "alignment": str(self.alignment),
            "charPrIdRef": self.char_pr_id_ref,
            "autoIndent": self.auto_indent,
            "widthAdjust": self.width_adjust,
            "textOffset": self.text_offset,
            "textOffsetType": self.text_offset_type,
            "checkable": self.checkable,
            "useInstanceWidth": self.use_instance_width,
        }


@dataclass(frozen=True)
class NumberingInfo:
    """A typed read of one ``hh:numbering`` (``doc.styles.numbering``),
    its levels in document order. A snapshot: later header edits do not show."""

    id: str
    start: int
    levels: tuple[NumberingLevel, ...]

    def level(self, level: int) -> NumberingLevel | None:
        """The level numbered *level* (1 is the first), or ``None``."""

        return next((item for item in self.levels if item.level == level), None)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "start": self.start, "levels": [item.to_dict() for item in self.levels]}


# -- 쪽·구역 설정의 읽기 값 (doc.page.* / doc.parts.*) ------------------------
#
# Each is a snapshot taken at call time, like BorderFillInfo. Lengths without a
# suffix are HWPUNIT; ``paragraph`` (where a value has one) is the body paragraph
# holding the control, as a model object, and is left out of ``to_dict()``.


@dataclass(frozen=True)
class ColumnDefinition:
    """One column layout (``hp:colPr``), as ``doc.page.columns()`` reads it.

    ``type`` is ``NEWSPAPER``, ``BALANCED_NEWSPAPER`` or ``PARALLEL``; ``layout``
    is ``LEFT``, ``RIGHT`` or ``MIRROR``. ``gap`` is the gap between columns of
    the same width (0 when the widths differ). ``widths`` holds a
    ``(width, gap)`` pair per column in HWPUNIT, worked out from the shares the
    file keeps and the section's text width (paper width less the left and right
    margins and a left gutter); it is the shape ``doc.page.set_columns(
    column_widths=...)`` takes. ``separator`` is the line drawn between columns,
    or ``None``.
    """

    count: int
    type: str
    layout: str
    same_size: bool
    gap: int
    widths: tuple[tuple[int, int], ...]
    separator: "BorderLine | None"
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "type": self.type,
            "layout": self.layout,
            "sameSize": self.same_size,
            "gap": self.gap,
            "widths": [list(pair) for pair in self.widths],
            "separator": self.separator.to_dict() if self.separator is not None else None,
        }


@dataclass(frozen=True)
class PageNumberControl:
    """A page-number control (``hp:pageNum``, Hancom's 쪽 번호 매기기).

    ``position`` is where the number is drawn (``BOTTOM_CENTER``, ``TOP_LEFT``,
    ``NONE``, ...), ``format_type`` the number style (``DIGIT``, ``ROMAN_SMALL``,
    ...) and ``side_char`` the character drawn on both sides (``"-"``) or ``""``.
    """

    position: str
    format_type: str
    side_char: str
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position, "formatType": self.format_type, "sideChar": self.side_char}


@dataclass(frozen=True)
class NumberRestart:
    """A new-number control (``hp:newNum``): *kind*'s count restarts at *number*."""

    kind: str
    number: int
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "number": self.number}


@dataclass(frozen=True)
class PageHiding:
    """A hide-on-this-page control (``hp:pageHiding``, 현재 쪽만 감추기)."""

    header: bool
    footer: bool
    master_page: bool
    border: bool
    fill: bool
    page_num: bool
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header,
            "footer": self.footer,
            "masterPage": self.master_page,
            "border": self.border,
            "fill": self.fill,
            "pageNum": self.page_num,
        }


@dataclass(frozen=True)
class AutoNumber:
    """An automatic number in the text (``hp:autoNum``): a page, footnote,
    picture, table or equation number Hancom counts itself.

    ``number`` is the value stored with it (Hancom recounts on layout).
    """

    kind: str
    number: int
    format_type: str
    prefix: str | None
    suffix: str | None
    superscript: bool
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "number": self.number,
            "formatType": self.format_type,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "superscript": self.superscript,
        }


@dataclass(frozen=True)
class StartNumbers:
    """Where a section's counts start (``hp:startNum``); 0 goes on from the section before.

    ``page_starts_on`` is ``BOTH``, ``EVEN`` or ``ODD``: the kind of page the
    section starts on.
    """

    page_starts_on: str
    page: int
    picture: int
    table: int
    equation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageStartsOn": self.page_starts_on,
            "page": self.page,
            "picture": self.picture,
            "table": self.table,
            "equation": self.equation,
        }


@dataclass(frozen=True)
class BeginNumbers:
    """Where the document's counts start (``hh:beginNum`` in header.xml)."""

    page: int
    footnote: int
    endnote: int
    picture: int
    table: int
    equation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "footnote": self.footnote,
            "endnote": self.endnote,
            "picture": self.picture,
            "table": self.table,
            "equation": self.equation,
        }


@dataclass(frozen=True)
class NoteShapeInfo:
    """How a section draws its footnotes or endnotes (``hp:footNotePr``/``hp:endNotePr``).

    ``number_format`` is the number style (``DIGIT``, ``CIRCLED_DIGIT``,
    ``USER_CHAR``, ...), with ``user_char`` for ``USER_CHAR``; ``prefix`` and
    ``suffix`` are drawn around the number, raised when ``superscript``.
    ``numbering`` is ``CONTINUOUS``, ``ON_SECTION`` or ``ON_PAGE`` and ``start``
    the first number (Hancom uses it with ``ON_SECTION``). ``placement`` is
    where the notes go (``EACH_COLUMN``, ``MERGED_COLUMN``, ``RIGHT_MOST_COLUMN``
    for footnotes; ``END_OF_DOCUMENT``, ``END_OF_SECTION`` for endnotes).
    ``separator`` is the line above the notes and ``separator_length`` its
    length (0: Hancom's default, a third of the column; -1: the whole column).
    The spacings are HWPUNIT.
    """

    number_format: str
    user_char: str | None
    prefix: str | None
    suffix: str | None
    superscript: bool
    numbering: str
    start: int
    placement: str
    beneath_text: bool
    separator: "BorderLine"
    separator_length: int
    between_notes: int
    below_line: int
    above_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "numberFormat": self.number_format,
            "userChar": self.user_char,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "superscript": self.superscript,
            "numbering": self.numbering,
            "start": self.start,
            "placement": self.placement,
            "beneathText": self.beneath_text,
            "separator": self.separator.to_dict(),
            "separatorLength": self.separator_length,
            "betweenNotes": self.between_notes,
            "belowLine": self.below_line,
            "aboveLine": self.above_line,
        }


@dataclass(frozen=True)
class PageBorder:
    """A page border and fill (``hp:pageBorderFill``) for one kind of page.

    ``page_type`` is ``BOTH``, ``EVEN`` or ``ODD``. ``border_fill_id_ref`` names
    the ``hh:borderFill`` drawn (read it with ``doc.styles.border_fill``).
    ``text_border`` is what the offsets are measured from (``PAPER`` or
    ``CONTENT``); ``fill_area`` what is filled (``PAPER``, ``PAGE``, ``BORDER``).
    The offsets are HWPUNIT.
    """

    page_type: str
    border_fill_id_ref: str | None
    text_border: str | None
    header_inside: bool
    footer_inside: bool
    fill_area: str | None
    offset_left: int
    offset_right: int
    offset_top: int
    offset_bottom: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageType": self.page_type,
            "borderFillIDRef": self.border_fill_id_ref,
            "textBorder": self.text_border,
            "headerInside": self.header_inside,
            "footerInside": self.footer_inside,
            "fillArea": self.fill_area,
            "offset": {
                "left": self.offset_left,
                "right": self.offset_right,
                "top": self.offset_top,
                "bottom": self.offset_bottom,
            },
        }


@dataclass(frozen=True)
class DocumentOptions:
    """Document-wide options and compatibility settings in header.xml.

    ``target_program`` is ``hh:compatibleDocument/@targetProgram`` (Hancom
    writes ``HWP201X``) and ``layout_compatibility`` the names of the layout
    compatibility flags set (Hancom writes none). ``link_path``,
    ``page_inherit`` and ``footnote_inherit`` come from ``hh:docOption/
    hh:linkinfo``; the ``license_*`` fields from ``hh:licensemark`` (``None``
    when there is none). These are what ``doc.parts.set_*`` write.
    """

    target_program: str | None
    layout_compatibility: tuple[str, ...]
    link_path: str
    page_inherit: bool
    footnote_inherit: bool
    license_type: str | None
    license_flag: int | None
    license_lang: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetProgram": self.target_program,
            "layoutCompatibility": list(self.layout_compatibility),
            "linkPath": self.link_path,
            "pageInherit": self.page_inherit,
            "footnoteInherit": self.footnote_inherit,
            "licenseType": self.license_type,
            "licenseFlag": self.license_flag,
            "licenseLang": self.license_lang,
        }


@dataclass(frozen=True)
class ParagraphPlace:
    """One paragraph of the whole document and where it sits (``doc.text.iter_paragraphs()``).

    ``where`` is the innermost container: ``body``, ``cell``, ``text_box``,
    ``caption``, ``header``, ``footer``, ``footnote``, ``endnote``, ``memo``,
    ``master_page`` or ``hidden_comment`` (숨은 설명, ``hp:hiddenComment``). ``section`` is the section holding it, as a model object (``None`` on a
    master page; its number is ``doc.sections.index(place.section)``, and ``to_dict()`` writes
    that number).
    ``page_type`` is set in a header or footer (``BOTH``, ``ODD``, ``EVEN``).
    ``table``/``row``/``col`` name the innermost table cell holding the paragraph,
    when there is one, even inside a text box in that cell. ``owner`` is the
    innermost object (table, shape, picture...) holding it, and ``depth`` how many
    objects deep it is (0 in the body, a header, a note or a memo).
    """

    paragraph: "Paragraph"
    where: str
    section: "Section | None"
    page_type: str | None = None
    table: "Table | None" = None
    row: int | None = None
    col: int | None = None
    owner: Any = None
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "where": self.where,
            "section": _section_number(self.section),
            "pageType": self.page_type,
            "row": self.row,
            "col": self.col,
            "depth": self.depth,
            "text": self.paragraph.text,
        }


@dataclass(frozen=True)
class ObjectPlace:
    """One object of the whole document and where it sits (``doc.text.iter_objects()``).

    ``kind`` is ``table``, ``picture``, ``equation``, ``shape``, ``ole``,
    ``chart``, ``video`` or ``textart``; ``object`` is its model object, as
    ``paragraph.objects`` gives it: a table, a shape, a picture (``item_id``), an equation
    (``script``), or an inline object for the rest. Pictures and equations are inline objects
    too (earlier 7.0 development builds gave them as plain inline objects). The other fields describe the
    paragraph holding it, as in :class:`ParagraphPlace`.
    """

    object: Any
    kind: str
    where: str
    section: "Section | None"
    page_type: str | None = None
    table: "Table | None" = None
    row: int | None = None
    col: int | None = None
    owner: Any = None
    depth: int = 0

    @property
    def offset(self) -> int | None:
        """Where the object stands in the text of the paragraph holding it: ``object.offset`` (the
        characters before it, counted as ``paragraph.text`` counts)."""

        return getattr(self.object, "offset", None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "where": self.where,
            "section": _section_number(self.section),
            "pageType": self.page_type,
            "row": self.row,
            "col": self.col,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class SwitchChoice:
    """What an ``hp:switch`` written in a run holds (``run.content``'s ``"switch"`` piece ``object``): the
    objects of its ``hp:case`` -- the form Hancom reads when it knows the namespace the case requires
    (*required_namespace*), as Hancom 2024 knows ``ooxmlchart`` and draws the chart -- and those of its
    ``hp:default``, the form for a reader that does not. Each object is the model ``paragraph.objects``
    would give it. Read only: no writer of python-hwpx writes a switch.
    (``tests/fixtures/hancom_saved/pages_chart_case_*``, ``unused_chart_saved``.)"""

    required_namespace: str | None
    case: tuple[Any, ...]
    default: tuple[Any, ...]
    element: Any = _field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requiredNamespace": self.required_namespace,
            "case": [type(item).__name__ for item in self.case],
            "default": [type(item).__name__ for item in self.default],
        }


@dataclass(frozen=True)
class InlineItem:
    """One piece of a run's content, in the order the file writes it (``run.content``).

    ``kind`` says what the piece is; ``name`` is the XML element's local name (``""`` for
    plain characters); ``container`` is where the file writes it: ``"t"`` (inside an
    ``hp:t``), ``"ctrl"`` (inside an ``hp:ctrl``) or ``"run"`` (a child of the run itself).

    Inside ``hp:t``: ``"text"`` (characters), ``"tab"``, ``"line_break"``, ``"nb_space"``
    (묶음 빈칸), ``"fw_space"`` (고정폭 빈칸), ``"hyphen"``, ``"markpen_begin"``/``"markpen_end"``
    (형광펜), ``"title_mark"`` (차례 표시), ``"insert_begin"``/``"insert_end"``/``"delete_begin"``/
    ``"delete_end"`` (변경 추적 표시). ``text`` is the character a glyph stands for (``"\\t"``,
    ``"\\n"``, ``"\\xa0"``, ``"\\u3000"``, ``"\\xad"``) and ``""`` for a mark, so the ``text`` of the
    ``"t"`` pieces and of a ``"tab"`` written in the run, joined, is ``run.text``.

    Inside ``hp:ctrl``: ``"field_begin"``, ``"field_end"``, ``"footnote"``, ``"endnote"``,
    ``"bookmark"``, ``"auto_number"``, ``"page_number"`` (쪽 번호 매기기), ``"page_number_ctrl"``,
    ``"number_restart"``, ``"page_hiding"``, ``"column_definition"``, ``"header"``, ``"footer"``,
    ``"index_mark"``, ``"hidden_comment"``.

    Run children: objects by the kind ``doc.text.iter_objects()`` gives them (``"table"``,
    ``"picture"``, ``"equation"``, ``"shape"``, ``"textart"``, ``"ole"``, ``"chart"``,
    ``"video"``) and ``"form"`` (단추·선택 상자·입력 상자 …), ``"ruby"`` (덧말),
    ``"composed_character"`` (글자 겹치기), ``"section_properties"`` (``hp:secPr``),
    ``"switch"`` (``hp:switch``), and the marks and glyphs above when a writer puts them
    in the run instead of ``hp:t``.

    Anything else is ``"unknown"``, with its ``name``; nothing the file holds is left out
    (an empty ``hp:t`` or ``hp:ctrl`` holds nothing and gives no piece). ``attributes``
    are the element's attributes as written, in file order (``item.attribute("type")``).
    ``object`` is the model object for the piece when there is one: the table, picture,
    shape … (as ``paragraph.objects`` gives it), the note (``paragraph.footnotes``), the
    :class:`Hyperlink` of a ``HYPERLINK`` field, the memo of a ``MEMO`` field that holds its
    text, the :class:`Ruby` or :class:`ComposedCharacter`, and :class:`AutoNumber`,
    :class:`PageNumberControl`, :class:`NumberRestart`, :class:`PageHiding` or
    :class:`ColumnDefinition` for those controls, the header or footer (the model
    ``doc.page.headers()`` gives) for a ``"header"``/``"footer"`` control, and a
    :class:`FieldControl` (type, id, name, parameters) for any other field start (a hyperlink's
    and a memo field's object read ``parameters`` too); else ``None``. ``element`` is the XML
    element, the escape hatch (``None`` for characters). ``child_index`` tells which of the run's
    child elements the piece is written in: the place (from 0, comments not counted) of its
    ``hp:t`` or ``hp:ctrl``, or of the piece itself when it is a child of the run. Pieces of one
    ``hp:t`` (or one ``hp:ctrl``) share it, so two controls written in one ``hp:ctrl`` and in two
    can be told apart. ``offset`` is where the piece stands in its paragraph's text, counted as
    ``paragraph.text`` counts (a tab or a line break one, a control or an object none; for characters,
    where the first of them is): the place ``paragraph.replace_range`` or ``obj.move_to(offset=)`` takes.
    None of these four takes part in ``==`` or ``to_dict()``.
    """

    kind: str
    name: str
    container: str
    text: str = ""
    attributes: tuple[tuple[str, str], ...] = ()
    object: Any = _field(default=None, compare=False, repr=False)
    element: Any = _field(default=None, compare=False, repr=False)
    child_index: int = _field(default=0, compare=False)
    offset: int = _field(default=0, compare=False)

    def attribute(self, name: str, default: str | None = None) -> str | None:
        """The value of the attribute *name* as written, *default* when the element has none."""

        for key, value in self.attributes:
            if key == name:
                return value
        return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "container": self.container,
            "text": self.text,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class TextMatch:
    """One match of ``doc.text.find()``: where it is and what it matched.

    ``start``/``end`` are positions in ``paragraph.text`` (a tab or a line break is one
    character, a control or an object none), the ones ``paragraph.format_range(start, end, ...)``
    takes. ``text`` is the matched text, ``groups`` a regular expression's groups (``None`` for a
    group that took no part; ``()`` for a plain search). The other fields say where the paragraph
    sits, as in :class:`ParagraphPlace`.
    """

    paragraph: "Paragraph"
    start: int
    end: int
    text: str
    groups: tuple[str | None, ...]
    where: str
    section: "Section | None"
    page_type: str | None = None
    table: "Table | None" = None
    row: int | None = None
    col: int | None = None
    owner: Any = None
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "groups": list(self.groups),
            "where": self.where,
            "section": _section_number(self.section),
            "pageType": self.page_type,
            "row": self.row,
            "col": self.col,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class LanguageFonts:
    """The face a run's text uses in each language block (``run.fonts``).

    Hancom gives a character shape one face per language (``hh:fontRef``): Hangul, Latin,
    Hanja, Japanese, other scripts, symbols and the user block. A field is ``None`` when the
    shape names no face there (or the run has no character shape). ``run.font`` is ``hangul``.
    """

    hangul: str | None = None
    latin: str | None = None
    hanja: str | None = None
    japanese: str | None = None
    other: str | None = None
    symbol: str | None = None
    user: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "hangul": self.hangul,
            "latin": self.latin,
            "hanja": self.hanja,
            "japanese": self.japanese,
            "other": self.other,
            "symbol": self.symbol,
            "user": self.user,
        }


__all__ = [
    "Alignment",
    "LanguageFonts",
    "ObjectPlace",
    "ParagraphPlace",
    "TextMatch",
    "AutoNumber",
    "BeginNumbers",
    "ColumnDefinition",
    "DocumentOptions",
    "NoteShapeInfo",
    "NumberRestart",
    "PageBorder",
    "PageHiding",
    "PageNumberControl",
    "StartNumbers",
    "BorderFillInfo",
    "BorderLine",
    "CellMargins",
    "CellZone",
    "ClearBodyReport",
    "ColumnLayout",
    "FieldFillResult",
    "FontReplaceReport",
    "LineSpacing",
    "LineSpacingType",
    "ListFormatResult",
    "NumberingInfo",
    "NumberingLevel",
    "ObjectPosition",
    "PageMargins",
    "PageSetup",
    "PageSize",
    "ParagraphFormatResult",
    "PictureReplacement",
    "Units",
]
