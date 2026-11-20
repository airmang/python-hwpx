# SPDX-License-Identifier: Apache-2.0
"""Paragraph content and inline-composition OXML service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence, cast
import warnings
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import (
    note_made_run,
    refused_appends_nothing,
    SameElement,
    _HP,
    _HP_NS,
    _append_child,
    _append_text_with_run_choice_atoms,
    _append_text_with_tabs,
    _child_tag_like,
    _children_by_local,
    _clear_paragraph_layout_cache,
    _is_tab_control_element,
    _text_element_content,
    _object_id,
    _require_nonempty_str,
    _require_text,
    _sanitize_text,
)
from .namespaces import XML_NS, tag_local_name
from .drop_cap import _paragraph_add_drop_cap
from .dutmal_compose import (
    _paragraph_add_composed_character,
    _paragraph_add_dutmal,
    paragraph_composed_characters,
    paragraph_rubies,
)
from .hyperlink_form import HYPERLINK_FIELD_ID, hyperlink_char_pr, hyperlink_parameters
from .field_marks import (
    field_type_id,
    _paragraph_add_date_field,
    _paragraph_add_mail_merge_field,
    _paragraph_add_path_field,
    _paragraph_add_proofreading_mark,
)
from .note_authoring import (
    renumber_notes_holding,
    _paragraph_add_endnote,
    _paragraph_add_footnote,
    _paragraph_add_number_restart,
    _paragraph_endnotes,
    _paragraph_footnotes,
)
from ._paragraph_text_edit import (
    ParagraphFormats,
    checked_tab_widths,
    LiveSection,
    insert_paragraph_beside,
    refuse_taken_out,
    paragraph_container,
    paragraph_line_segments,
    paragraph_line_texts,
    remove_paragraph,
    text_marks_as_elements_in,
    write_tab_widths,
)
from .objects import (
    HwpxOxmlEquation,
    HwpxOxmlInlineObject,
    _missing_shape_children,
    _paragraph_equations,
    _paragraph_objects,
    _paragraph_pictures,
    _paragraph_add_arc,
    _paragraph_add_container,
    _paragraph_add_ellipse,
    _paragraph_add_line,
    _paragraph_add_picture,
    _paragraph_add_polygon,
    _paragraph_add_rectangle,
    _paragraph_insert_shape_element,
    _paragraph_shapes,
)
from .curves import _paragraph_add_connector, _paragraph_add_curve
from .run import HwpxOxmlRun
from .section_format import column_shares, validate_column_gap
from .shape_position import (
    equation_base_unit, stack_new_object, unique_object_ids, validate_box_size, validate_equation_font,
    validate_equation_script, validate_shape_size,
)
from .table import HwpxOxmlTable
from .table_sizes import NEW_TABLE_COLUMN_FLOOR, cell_margins_of, check_new_table_height, new_table_width, validate_table_size
from .table_sizes import checked_in_margins, with_in_margins

if TYPE_CHECKING:
    from ..objects.checkbox import CheckBox
    from ..objects.form_field import Bookmark, FormField, Hyperlink
    from ..objects.highlight import Highlight
    from typing import Iterable, Iterator

    from ..objects.results import CellMargins, ClearBodyReport, ObjectPlace, PageHiding, ParagraphPlace
    from .section import HwpxOxmlSection


def _content_and_cache(node: "LET._Element") -> tuple[bytes, bytes]:
    """A serialized paragraph split into its content and its own line cache."""

    copy = LET.fromstring(LET.tostring(node))
    cache = b""
    for child in list(copy):
        if isinstance(child.tag, str) and tag_local_name(child.tag).lower() == "linesegarray":
            cache += LET.tostring(child, with_tail=False)
            copy.remove(child)
    return LET.tostring(copy), cache


def _column_width_of(settings: ET.Element, text_width: int) -> int | None:
    """The width of a column of the ``hp:colPr`` *settings* over *text_width* (the narrowest of
    unequal ones), or ``None`` for one column or unreadable sizes, as the page estimate reads them."""

    count = int(settings.get("colCount", "1"))
    if count <= 1:
        return None
    if settings.get("sameSz") not in ("1", "true"):
        shares = [int(size.get("width", 0)) for size in settings.findall(f"{_HP}colSz")]
        return min(share * text_width // 32768 for share in shares) if len(shares) == count else None
    gap = int(settings.get("sameGap", "0"))
    if gap >= 1 << 31:  # a signed 32-bit number written unsigned
        gap -= 1 << 32
    return (text_width - (count - 1) * gap) // count


@dataclass(eq=False)
class HwpxOxmlParagraph(SameElement, ParagraphFormats):
    """Lightweight wrapper around an ``<hp:p>`` element.

    A paragraph taken out of its document (one of a removed table, note, text box or section) no longer
    belongs to it. An edit that changes only its text and runs and writes nothing on the document's side
    still works: ``text =``, ``insert_text``, ``delete_range``, ``replace_range``,
    ``set_text_preserving_runs``, ``clear_text``, ``add_run`` and ``split_run`` without a new shape, a shape
    id the document has (``char_pr_id_ref =``). An edit that writes on the document's side is refused before
    anything changes (``paragraph-not-in-document``): one that may register a shape in the header (a format
    given to ``add_run``/``insert_text``, ``format_range``, paragraph formats such as ``alignment =``), one
    that numbers (notes, number restarts, page hiding, bullets), one that makes a mark or an object the
    document counts (highlights, bookmarks, fields, links, check boxes, pictures, charts, shapes, equations,
    tables), one that adds a paragraph beside it (``insert_before``/``insert_after``) and one that moves or
    copies text into or out of it. The same rule holds for its runs, and for a table, cell, note, text box
    or object taken out (see ``install_detached_guard`` in ``_paragraph_text_edit``)."""

    element: ET.Element
    section: HwpxOxmlSection = LiveSection()  # type: ignore[assignment]  # the section holding it now

    def __repr__(self) -> str:
        """Return a compact and safe summary of paragraph contents."""

        runs = self._run_elements()
        return (
            f"{self.__class__.__name__}("
            f"runs={len(runs)}, "
            f"tables={len(self.tables)}, "
            f"text_length={len(self.text)}"
            ")"
        )

    def to_model(self) -> "body.Paragraph":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_paragraph_element(node)

    @property
    def model(self) -> "body.Paragraph":
        return self.to_model()

    def apply_model(self, model: "body.Paragraph") -> None:
        """Write *model* back over this paragraph.

        When the model changes the paragraph (its text, its runs, what sits in
        them) and leaves the line cache as it was, the cache is dropped: Hancom
        would lay the new content into the old lines. A model that changes
        only the cache, or nothing, is written as given.
        """

        new_node = body.serialize_paragraph(model)
        xml_bytes = LET.tostring(new_node)
        # Compare through the same serializer, so only what the caller changed differs.
        before = _content_and_cache(body.serialize_paragraph(self.to_model()))
        after = _content_and_cache(new_node)
        content_changed, cache_changed = before[0] != after[0], before[1] != after[1]
        parent = paragraph_container(self.element, self.section.element)
        if parent is None:
            parent = self.section.element
        if isinstance(parent, LET._Element):
            replacement = LET.fromstring(xml_bytes)
        else:
            replacement = ET.fromstring(xml_bytes)
        text_marks_as_elements_in(replacement)  # "\n" set on a model span, as hp:lineBreak
        paragraph_children = list(parent)
        index = paragraph_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        if content_changed and not cache_changed:
            # The model changed the paragraph and brought its old line cache back
            # unchanged: those lines are the old content's.
            _clear_paragraph_layout_cache(replacement)
        self.section.mark_dirty()

    def _run_elements(self) -> list[ET.Element]:
        return _children_by_local(self.element, "run")

    def _ensure_run(self) -> ET.Element:
        runs = self._run_elements()
        if runs:
            return runs[0]

        run_attrs: dict[str, str] = {}
        default_char = self.char_pr_id_ref or "0"
        if default_char is not None:
            run_attrs["charPrIDRef"] = default_char
        run = self.element.makeelement(_child_tag_like(self.element, "run", _HP_NS), run_attrs)
        self.element.append(run)
        return run

    @property
    def runs(self) -> tuple[HwpxOxmlRun, ...]:
        """The runs contained in this paragraph, in order."""
        return tuple(HwpxOxmlRun(run, self) for run in self._run_elements())

    def _last_text_run_for_tracked_insert(
        self,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlRun:
        desired_char = None if char_pr_id_ref is None else str(char_pr_id_ref)
        runs = self.runs

        if desired_char is not None:
            for run in reversed(runs):
                if run.char_pr_id_ref != desired_char:
                    continue
                if run.to_model().text_spans:
                    return run
            return self.add_run("", char_pr_id_ref=desired_char)

        for run in reversed(runs):
            if run.to_model().text_spans:
                return run
        return self.add_run("", char_pr_id_ref=self.char_pr_id_ref or "0")

    def _add_tracked_insert(
        self,
        text: str,
        *,
        change_id: int,
        mark_id: int,
        char_pr_id_ref: str | int | None = None,
    ) -> None:
        sanitized = _sanitize_text(text)
        if not sanitized:
            raise ValueError("tracked insert text must be non-empty")

        run = self._last_text_run_for_tracked_insert(char_pr_id_ref=char_pr_id_ref)
        model = run.to_model()
        body.append_tracked_insert_to_run(
            model,
            sanitized,
            tc_id=change_id,
            mark_id=mark_id,
        )
        run.apply_model(model)

    def _add_tracked_delete(
        self,
        *,
        change_id: int,
        first_mark_id: int,
        match: str | None = None,
    ) -> int:
        if match == "":
            raise ValueError("match must be a non-empty string")

        next_mark_id = first_mark_id
        if match is not None:
            for run in self.runs:
                model = run.to_model()
                if match not in "".join(span.text for span in model.text_spans):
                    continue
                for span in model.text_spans:
                    if body.wrap_tracked_delete_in_span(
                        span,
                        tc_id=change_id,
                        mark_id=next_mark_id,
                        match=match,
                    ):
                        run.apply_model(model)
                        return next_mark_id + 1
                raise ValueError("match crosses inline markup and cannot be wrapped safely")
            raise ValueError("match text was not found in the paragraph")

        modified = False
        for run in self.runs:
            model = run.to_model()
            changed = False
            for span in model.text_spans:
                if not span.text:
                    continue
                body.wrap_tracked_delete_in_span(
                    span,
                    tc_id=change_id,
                    mark_id=next_mark_id,
                )
                next_mark_id += 1
                changed = True
            if changed:
                run.apply_model(model)
                modified = True

        if not modified:
            raise ValueError("paragraph contains no text to delete")
        return next_mark_id

    def _add_tracked_replace(
        self,
        old: str,
        new: str,
        *,
        delete_change_id: int,
        insert_change_id: int,
        first_mark_id: int,
    ) -> None:
        """Apply one replacement atomically to a single run model."""

        if old == "":
            raise ValueError("match must be a non-empty string")
        sanitized = _sanitize_text(new)
        if not sanitized:
            raise ValueError("tracked insert text must be non-empty")

        for run in self.runs:
            model = run.to_model()
            for span in model.text_spans:
                if old not in span.text:
                    continue
                if not body.wrap_tracked_delete_in_span(
                    span,
                    tc_id=delete_change_id,
                    mark_id=first_mark_id,
                    match=old,
                ):
                    raise ValueError(
                        "match crosses inline markup and cannot be wrapped safely"
                    )
                if not body.insert_tracked_text_after_delete(
                    span,
                    sanitized,
                    delete_tc_id=delete_change_id,
                    insert_tc_id=insert_change_id,
                    mark_id=first_mark_id + 1,
                ):
                    raise RuntimeError(
                        "tracked replacement lost its delete boundary"
                    )
                run.apply_model(model)
                return

        raise ValueError("match text was not found in the paragraph")

    def add_highlight(
        self,
        *,
        color: str,
        match: str | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> "Highlight":
        """Wrap the first occurrence of *match* -- or characters ``[start, end)`` of ``paragraph.text`` -- in
        ``hp:markpenBegin``/``markpenEnd`` and return it as the :class:`~hwpx.objects.Highlight`
        ``doc.text.highlights`` reads. A range may cross runs: the begin goes in the ``hp:t`` holding character
        *start*, the end in the one holding character ``end - 1``, as Hancom writes it (``highlight_across_runs``).

        Mirrors :meth:`_add_tracked_delete`'s substring branch: the first run
        whose spans concatenate to contain *match* is targeted, then the
        specific span holding it (contiguously) is wrapped.
        """

        from ..objects.highlight import Highlight

        if start is not None or end is not None or match is None:
            from .._document.highlight import add_highlight

            return add_highlight(None, self, match, color=color, start=start, end=end)  # type: ignore[arg-type]
        if not match:
            raise ValueError("match must be a non-empty string")

        for run in self.runs:
            model = run.to_model()
            if match not in "".join(span.text for span in model.text_spans):
                continue
            for span in model.text_spans:
                if body.wrap_highlight_in_span(span, color=color, match=match):
                    run.apply_model(model)
                    return Highlight(text=match, color=color, paragraph=self)
            raise ValueError("match crosses inline markup and cannot be wrapped safely")

        raise ValueError("match text was not found in the paragraph")

    @property
    def text(self) -> str:
        """Return the concatenated textual content of this paragraph."""
        texts: list[str] = []
        for run in self._run_elements():
            for child in run:
                if tag_local_name(child.tag) == "t":
                    texts.append(_text_element_content(child))
                elif tag_local_name(child.tag) == "tab" or _is_tab_control_element(child):
                    texts.append("\t")
        return "".join(texts)

    @text.setter
    def text(self, value: str) -> None:
        """Replace the textual contents of this paragraph.

        Style references (``paraPrIDRef``, ``styleIDRef`` on the paragraph and
        ``charPrIDRef`` on the surviving run) are preserved.  Empty runs that
        contained only text nodes are removed to keep the XML clean.  Setting
        the text the paragraph already has changes nothing: its runs and its
        line layout caches stay.
        """
        _require_text(value)  # before the old text goes
        if value == self.text:
            return
        runs = self._run_elements()

        # Identify first run — its charPrIDRef will be kept.
        first_run = self._ensure_run()

        # Remove existing text/tab nodes from all runs.
        for run in runs:
            for child in list(run):
                if tag_local_name(child.tag) in {"t", "tab"} or _is_tab_control_element(child):
                    run.remove(child)

        # Remove non-first runs that are now empty (only had text).
        # Runs with non-text children (tables, shapes, controls) are kept.
        for run in runs:
            if run is first_run:
                continue
            if len(list(run)) == 0:
                self.element.remove(run)

        # Write the new text into the first run, preserving tabs as <hp:tab/>.
        _append_text_with_tabs(first_run, value)
        _clear_paragraph_layout_cache(self.element)
        self.section.mark_dirty()

    def set_text_preserving_runs(self, value: str) -> None:
        """Replace one unambiguous text span without changing run boundaries.

        The edit must fit inside one ``hp:t`` node: a correction within a styled run, every other run and
        control kept. Tabs, line breaks and special spaces written inside ``hp:t`` (as Hancom writes them)
        count one character each and stay as they are outside the edit; a tab or a line break in *value*
        goes in the same way. Cross-style replacements require an explicit run target.
        """
        from .text_ranges import set_text_preserving_runs

        set_text_preserving_runs(self, value)

    def clear_content(self, *, keep_headers: bool = True, on_control_content: str = "raise") -> "ClearBodyReport":
        """Empty this paragraph of its body content -- text, tables, pictures, notes, bookmarks, fields -- and keep
        its section settings: ``hp:secPr`` with the page-level controls beside it (the column definition always,
        headers and footers as *keep_headers* says), as ``section.clear_body`` keeps the first paragraph's.
        Content inside what stays follows *on_control_content* (``"raise"``, ``"keep"``, ``"strip"``) as there.
        Returns the :class:`~hwpx.objects.ClearBodyReport` of what went."""

        from .section import clear_paragraph_content

        return clear_paragraph_content(self, keep_headers=keep_headers, on_control_content=on_control_content)

    def clear_text(self) -> None:
        """Remove all text content while preserving styles and non-text elements.

        Style references on the paragraph and surviving runs are kept intact.
        Empty runs are cleaned up.
        """
        runs = self._run_elements()
        for run in runs:
            for child in list(run):
                if child.tag == f"{_HP}t":
                    run.remove(child)
        # Remove runs that are now completely empty.
        for run in list(runs):
            if len(list(run)) == 0:
                self.element.remove(run)
        _clear_paragraph_layout_cache(self.element)
        self.section.mark_dirty()

    def remove(self) -> None:
        """Remove this paragraph from the section, table cell, header or footer holding it.

        After removal, the paragraph wrapper should no longer be used, and a
        second call does nothing. Raises :class:`~hwpx.errors.HwpxValueError`
        (a ``ValueError``, ``code="paragraph-remove-last"``) if that container
        would be left without a paragraph: HWPX needs at least one ``<hp:p>``
        per section, and Hancom cannot open a cell, header or footer whose
        paragraph list is empty.
        """
        remove_paragraph(self)

    def insert_after(self, text: str | None = None) -> "HwpxOxmlParagraph":
        """Put a new paragraph right after this one (in its section, cell, header or footer) and return it.

        With *text* the new paragraph holds it, in this paragraph's paragraph shape, style and
        first run's character shape. Without, it is a copy of this paragraph: its runs, tables
        and objects, with fresh ids (a form field's begin and end get a new pair; a memo anchored
        in it becomes a memo of its own with the next memo number) and no line layout cache, but
        not the section settings the first paragraph of a section holds. :meth:`move_after`
        moves the paragraph itself instead.
        """

        return HwpxOxmlParagraph(self._insert_beside(text, after=True), self.section)

    def insert_before(self, text: str | None = None) -> "HwpxOxmlParagraph":
        """Put a new paragraph right before this one and return it, as :meth:`insert_after` does.

        Before the first paragraph of a section, the new paragraph starts the section: the
        section's settings (paper, margins, columns, header, footer) move to it.
        """

        return HwpxOxmlParagraph(self._insert_beside(text, after=False), self.section)

    def _insert_beside(self, text: str | None, *, after: bool) -> ET.Element:
        if text is not None and not isinstance(text, str):
            from ..errors import HwpxTypeError

            raise HwpxTypeError(
                f"text must be a str or None, got {type(text).__name__}",
                code="paragraph-text-invalid-type",
                suggestion="Pass the new paragraph's text as a str, or nothing to copy this paragraph.",
            )
        element = insert_paragraph_beside(self.element, self.section.element, text, after=after, ids=self.section._ids)
        # In a table cell (or caption) the new line makes the cell taller, and so the line of the
        # paragraph holding the table: it loses its cache as when a cell's text changes.
        _clear_paragraph_layout_cache(element)
        if text is None:  # a copied memo anchor gets a memo of its own, as obj.copy_to gives one
            from .memo import renew_copied_memos

            document = self.section.document
            renew_copied_memos(element, list(document.sections) if document is not None else [self.section],
                               self.section)
            unique_object_ids(self.section, (element,))
            renumber_notes_holding(self.section, (element,))
        self.section.mark_dirty()
        return element

    def copy_to(self, paragraph: "HwpxOxmlParagraph", *, before: bool = False) -> "HwpxOxmlParagraph":
        """Put a copy of this paragraph right after *paragraph* (``before=True``: before it) and return it.

        *paragraph* may be a paragraph of another document -- in its body, a cell, a text box, a note,
        a header or a footer. The copy comes as ``hwpx.tools.document_merge.insert_document`` brings a
        paragraph over: the character and paragraph shapes, styles, borders and fills, tabs,
        numberings, bullets and fonts it uses become definitions of that document, its pictures and
        charts bring their images and parts, and its fields, bookmarks, objects and paragraphs get fresh
        ids. A memo anchored in it comes along as a memo of its own. The section settings of a section's
        first paragraph stay behind; put in front of a section's first paragraph, the copy starts that
        section and takes its settings. What ``insert_document`` cannot carry is refused the same way
        (``document-merge-unsupported-reference``). In the same document the copy is the one
        :meth:`insert_after` makes of a paragraph. No line layout cache comes along.
        """

        from ..tools.document_merge import copy_paragraph

        return cast("HwpxOxmlParagraph", copy_paragraph(self, paragraph, before=before))

    def move_after(self, paragraph: "int | HwpxOxmlParagraph") -> None:
        """Move this paragraph right after *paragraph* (a paragraph of the same document -- in the
        body, a cell, a text box, a note, a header or a footer -- or its index in ``doc.paragraphs``).

        The paragraph itself moves: it keeps its id, its runs, tables and objects, and this object
        stays valid. It loses its line layout cache, as do the paragraphs holding the cells and
        captions it left and joined. The first paragraph of a section hands the section's settings
        to the paragraph after it, as :meth:`remove` does; memos anchored in it go to its new
        section's memo group. Refused: the last paragraph of a section, cell, header or footer
        (``paragraph-remove-last``), a move into its own cells or text boxes
        (``paragraph-move-into-itself``), a memo's paragraph (``paragraph-move-place-unsupported``).
        :meth:`insert_after` makes a copy instead.
        """

        self._move_beside(paragraph, after=True)

    def move_before(self, paragraph: "int | HwpxOxmlParagraph") -> None:
        """Move this paragraph right before *paragraph*, as :meth:`move_after` does. In front of the
        first paragraph of a section it starts the section: the section's settings move to it."""

        self._move_beside(paragraph, after=False)

    def _move_beside(self, paragraph: "int | HwpxOxmlParagraph", *, after: bool) -> None:
        from ._paragraph_text_edit import move_paragraph_beside, resolve_paragraph_in

        caller = "move_after" if after else "move_before"
        own = resolve_paragraph_in(self, self, caller=caller)
        anchor = resolve_paragraph_in(own, paragraph, caller=caller)
        self.section = move_paragraph_beside(own, anchor, after=after)

    def _create_run_for_object(
        self,
        run_attributes: dict[str, str] | None = None,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> ET.Element:
        attrs = dict(run_attributes or {})
        if char_pr_id_ref is not None:
            attrs.setdefault("charPrIDRef", str(char_pr_id_ref))
        elif "charPrIDRef" not in attrs:
            default_char = self.char_pr_id_ref or "0"
            if default_char is not None:
                attrs["charPrIDRef"] = str(default_char)
        run = self.element.makeelement(f"{_HP}run", attrs)
        self.element.append(run)
        note_made_run(self, run)
        _clear_paragraph_layout_cache(self.element)  # its lines change: Hancom lays the paragraph out again
        return run

    def add_run(
        self,
        text: str = "",
        *,
        char_pr_id_ref: str | int | None = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
        attributes: dict[str, str] | None = None,
        expand_special_characters: bool = False,
        tab_widths: "Sequence[int] | None" = None,
    ) -> HwpxOxmlRun:
        """Append a new run to the paragraph and return its wrapper.

        A tab in *text* becomes an ``hp:tab`` and a line break (``"\\n"``,
        ``"\\r\\n"`` or ``"\\r"``) an ``hp:lineBreak`` inside the run's
        ``hp:t``, as Hancom writes them. *expand_special_characters* (default
        ``False``) also writes a no-break space (``"\\u00a0"``) as
        ``hp:nbSpace`` and a full-width space (``"\\u3000"``) as
        ``hp:fwSpace``; real corpus (``error__20230818__test.hwpx``,
        ``error__20251107__test.hwpx``, ``error__20250808__...hwpx``) has
        Hancom emit all of these as elements nested inside a single ``hp:t``.

        *tab_widths* (HWPUNIT, one for each tab of *text*, in order) writes each tab as Hancom saves
        it, ``<hp:tab width="N" leader="0" type="1"/>`` -- the width it takes up to the next tab stop,
        as a caller that laid the line out measured it. Without it a tab is written ``<hp:tab/>`` and
        Hancom works the width out. A count other than the number of tabs, or a width that is not a
        whole number from 0 to 2**31-1, is refused (``paragraph-tab-widths``) before anything changes.
        """

        _require_text(text)  # not text: refused before anything is written
        widths = checked_tab_widths(text, tab_widths)
        run_attrs = dict(attributes or {})
        self.element.makeelement(f"{_HP}run", run_attrs)  # attributes that cannot be written: refused before a shape is declared

        if "charPrIDRef" not in run_attrs:
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            else:
                document = self.section.document
                if document is not None:
                    style_id = document.ensure_run_style(
                        bold=bool(bold),
                        italic=bool(italic),
                        underline=bool(underline),
                        color=color,
                        font=font,
                        size=size,
                        highlight=highlight,
                        strike=strike,
                    )
                    run_attrs["charPrIDRef"] = style_id
                else:
                    default_char = self.char_pr_id_ref or "0"
                    if default_char is not None:
                        run_attrs["charPrIDRef"] = str(default_char)

        run_element = _append_child(self.element, f"{_HP}run", run_attrs)
        _clear_paragraph_layout_cache(self.element)  # its lines change: Hancom lays the paragraph out again
        if expand_special_characters:
            _append_text_with_run_choice_atoms(run_element, text)
        else:
            _append_text_with_tabs(run_element, text)
        write_tab_widths(run_element, widths)
        self.section.mark_dirty()
        return HwpxOxmlRun(run_element, self)

    @property
    def tables(self) -> tuple["HwpxOxmlTable", ...]:
        """The tables embedded within this paragraph, in order."""

        return tuple(
            HwpxOxmlTable(child, self) for run in self._run_elements() for child in run if child.tag == f"{_HP}tbl"
        )

    def clear_layout_cache(self) -> int:
        """Drop this paragraph's line layout cache (``hp:linesegarray``) so Hancom lays it out again.

        Also of the paragraphs holding it (the cell's or caption's table's paragraph,
        up to the body): their line is as tall as what they hold. Call it after changing
        the paragraph — its text, size or placement — through the XML (``.element``); the
        editing methods do it themselves. A cache left over from before makes Hancom draw
        lines over each other. It also marks the paragraph's part changed, so the edit is
        saved even when there was no cache to drop (a part nothing marked is written as
        it was read). Returns how many caches went (0 when there were none).
        """

        removed = _clear_paragraph_layout_cache(self.element)
        self.section.mark_dirty()
        return removed

    @property
    def available_width(self) -> int | None:
        """The width this paragraph's content can use, in HWPUNIT, before its own margins.

        In a table cell, the cell's width less its inner margins (``cell.margins``); in
        the body, the section's text width (the page as drawn less its left, right and
        gutter margins), or the column's width where a multi-column layout is in effect
        (the narrowest column when they differ). ``None`` when that cannot be read. This
        is the width a table added to the paragraph takes by default.
        """

        return self._context_table_width()

    def _context_table_width(self) -> int | None:
        """Hancom-like default table width for this paragraph's context.

        Inside a table cell the parent cell's usable width bounds the new
        (nested) table — the fidelity audit reproduced silent content loss
        when the fixed per-cell default exceeded it. At body level Hancom
        fits a new table to the text width (page width minus margins).
        Returns ``None`` when neither context is measurable.
        """

        # stdlib ET has no getparent; lxml-backed elements do. Guarded getattr
        # keeps both backends working (19 suite failures without the guard).
        get_parent = getattr(self.element, "getparent", None)
        ancestor = cast(
            "ET.Element | None", get_parent() if callable(get_parent) else None
        )
        while ancestor is not None:
            if tag_local_name(ancestor.tag) == "tc":
                cell_sz = ancestor.find(f"{_HP}cellSz")
                if cell_sz is not None:
                    try:
                        width = int(cell_sz.get("width", "0"))
                    except ValueError:
                        return None
                    # The cell's effective margins (``cell.margins``): the
                    # table's hp:inMargin unless hasMargin is on.
                    row = getattr(ancestor, "getparent")()
                    inner = cell_margins_of(
                        ancestor, row.getparent() if row is not None else None
                    )
                    pad = inner.left + inner.right if inner is not None else 0
                    usable = width - pad
                    return usable if usable > 0 else None
                return None
            next_parent = getattr(ancestor, "getparent", None)
            ancestor = cast(
                "ET.Element | None",
                next_parent() if callable(next_parent) else None,
            )

        try:
            properties = self.section.properties
            page = properties.page_size
            margins = properties.page_margins
        except Exception:
            return None
        sizes = (page.drawn_width, margins.left, margins.right, margins.gutter)
        if page.width is None or page.width <= 0 or any(size is None for size in sizes):
            return None  # a page size or margin the file does not give
        usable = cast(int, page.drawn_width) - cast(int, margins.left) - cast(int, margins.right) - cast(int, margins.gutter)
        if usable <= 0:
            return None
        column = self._column_width(usable)
        return column if column is not None and column > 0 else usable

    def _column_width(self, text_width: int) -> int | None:
        """The width of a column of the multi-column layout in effect at this body paragraph, or
        ``None`` for one column: a table or chart Hancom fits to the line fits to that column.

        The layout in effect is the last ``hp:colPr`` of the section (outside cells and text
        boxes) at or before this paragraph. Columns of unequal width give the narrowest.
        """

        top: Any = self.element
        if not callable(getattr(top, "getparent", None)):
            return None
        while (parent := top.getparent()) is not None and parent is not self.section.element:
            top = parent
        if parent is None:
            return None
        settings: ET.Element | None = None
        for paragraph in self.section.element.findall(f"{_HP}p"):
            found = paragraph.findall(f"{_HP}run/{_HP}ctrl/{_HP}colPr")
            settings = found[-1] if found else settings
            if paragraph is top:
                break
        if settings is None:
            return None
        try:
            return _column_width_of(settings, text_width)
        except ValueError:
            return None

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None, in_margins: "CellMargins | None" = None,
    ) -> HwpxOxmlTable:
        """Add a *rows* x *cols* table at the end of this paragraph and return it.

        *in_margins* (a :class:`~hwpx.objects.CellMargins`, HWPUNIT) gives the table's inner cell
        margins and every cell's ``hp:cellMargin`` at once, as ``table.set_in_margins`` does
        afterwards; checked before anything is added (``table-margin-value``).
        """

        validate_table_size(rows, cols)
        height = check_new_table_height(height)
        margins = checked_in_margins(in_margins)
        if width is not None:
            width = new_table_width(width, cols)  # checked, and floored as Hancom draws it, before its run is added
        elif (context := self._context_table_width()) is not None:  # a narrow cell's may be below the floor
            width = max(context, cols * NEW_TABLE_COLUMN_FLOOR)
        if border_fill_id_ref is None:
            document = self.section.document
            if document is not None:
                resolved_border_fill: str | int = document.ensure_basic_border_fill()
            else:
                resolved_border_fill = "0"
        else:
            resolved_border_fill = border_fill_id_ref

        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        table_element = HwpxOxmlTable.create(rows, cols, width=width, height=height,
                                             border_fill_id_ref=resolved_border_fill, ids=self.section._ids)
        if type(table_element) is not type(run):
            table_element = LET.fromstring(ET.tostring(table_element, encoding="utf-8"))

        run.append(table_element)
        stack_new_object(table_element, self.section)  # tables take their numbers too, as Hancom numbers them
        self.section.mark_dirty()
        return with_in_margins(HwpxOxmlTable(table_element, self), margins)

    @refused_appends_nothing
    def add_shape(
        self,
        shape_type: str,
        attributes: dict[str, str] | None = None,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a generic shape element -- an escape hatch outside the contract, like ``.element``
        (not in the public surface lock; it may change between releases).

        This is a low-level escape hatch: it writes the element and the
        attributes it is handed and nothing else, so the result is **not a
        document Hancom can open** until the caller supplies the required
        OWPML children (``offset``, ``orgSz``, ``curSz``, ``sz``, ``pos`` and
        the type-specific geometry).  A :class:`UserWarning` is raised while
        they are missing.

        For LINE / RECT / ELLIPSE shapes, prefer the dedicated ``add_line``,
        ``add_rectangle``, and ``add_ellipse`` methods, which build the full
        child structure.
        """
        refuse_taken_out(self, "add_shape")  # here, not wrapped: its warning names the caller's line
        if not shape_type:
            from ..errors import HwpxValueError

            raise HwpxValueError("shape_type must be a non-empty string", code="shape-raw-tag-empty",
                                 suggestion="Pass the local name of the hp: element to write, e.g. 'rect'.")
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = _append_child(run, f"{_HP}{shape_type}", dict(attributes or {}))
        missing = _missing_shape_children(element)
        if missing:
            warnings.warn(
                f"add_shape({shape_type!r}) produced a shape without "
                f"{', '.join(missing)}; Hancom refuses to open a document "
                "containing it. Use add_line/add_rectangle/add_ellipse, or "
                "append the missing OWPML children yourself.",
                UserWarning,
                stacklevel=3,  # the caller's line, past the wrapper that undoes a refused call
            )
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    # Lives in ``oxml/objects.py`` with the other object helpers (this owner file is at its line cap).
    add_picture = _paragraph_add_picture

    # ------------------------------------------------------------------
    # Spec-compliant drawing shape helpers
    # ------------------------------------------------------------------
    #
    # Implementations live in ``oxml/objects.py`` (this owner module sits at
    # the modularization line cap) and are attached here as plain class
    # attributes — a function assigned this way is a method like any other,
    # so ``paragraph.add_rectangle(...)`` etc. keep working unchanged.

    _insert_shape_element = _paragraph_insert_shape_element
    add_line = _paragraph_add_line
    add_rectangle = _paragraph_add_rectangle
    add_ellipse = _paragraph_add_ellipse
    add_polygon = _paragraph_add_polygon
    add_arc = _paragraph_add_arc
    add_curve = _paragraph_add_curve
    add_connector = _paragraph_add_connector
    add_container = _paragraph_add_container
    shapes = property(_paragraph_shapes)
    objects = property(_paragraph_objects)
    pictures = property(_paragraph_pictures)

    def iter_objects(
        self,
        *,
        kinds: "Iterable[str] | str | None" = None,
        where: "Iterable[str] | str | None" = None,
    ) -> "Iterator[ObjectPlace]":
        """Every object inside this paragraph, at any depth, in document order, with where it sits.

        :meth:`hwpx.document.HwpxDocument` ``.text.iter_objects()`` narrowed to this paragraph: its own
        objects and those in its tables' cells, text boxes, captions, groups, notes and memos.
        ``kinds``/``where`` and the :class:`~hwpx.objects.ObjectPlace` values are those of
        ``doc.text.iter_objects()``. Only the paragraph's own XML and its ancestors are read.
        """

        from .._document.text_blocks import paragraph_object_places

        return paragraph_object_places(self, kinds, where)

    def iter_paragraphs(self, *, where: "Iterable[str] | str | None" = None) -> "Iterator[ParagraphPlace]":
        """Every paragraph inside this paragraph, at any depth, in document order, with where it sits.

        :meth:`hwpx.document.HwpxDocument` ``.text.iter_paragraphs()`` narrowed to this paragraph: the
        paragraphs of its tables' cells (nested tables too), captions, text boxes, groups, notes and
        memos, each as a :class:`~hwpx.objects.ParagraphPlace` with the same fields that walk gives. The
        paragraph itself is not among them; one holding nothing gives nothing. *where* chooses places as
        that walk does (``where={"cell", "text_box"}``). Only the paragraph's own XML and its ancestors
        are read.
        """

        from .._document.text_blocks import paragraph_paragraph_places

        return paragraph_paragraph_places(self, where)

    def nested_text(self, *, where: "Iterable[str] | str | None" = None) -> str:
        """This paragraph's text with the text of every paragraph inside it, in document order.

        :attr:`text` is the paragraph's own text; this also reads the paragraphs of its tables'
        cells (nested tables too), text boxes, captions, groups, notes and memos. The paragraph's
        text is cut where an object holding paragraphs sits, each inner paragraph's text (read the
        same way) comes there, and the stretches that hold text are joined with ``"\\n"``. Each
        stretch is read as :attr:`text` reads it (a tab ``"\\t"``, a line break ``"\\n"``, special
        spaces as their characters); nothing is collapsed. *where* (the places of
        ``doc.text.iter_paragraphs()``) chooses the inner paragraphs whose own text is read, as
        ``where={"cell", "text_box"}``; the paragraph's own text is always read. A paragraph with
        nothing inside gives :attr:`text`.
        """

        from .._document.text_blocks import paragraph_nested_text

        return paragraph_nested_text(self, where)
    equations = property(_paragraph_equations)
    line_segments = property(paragraph_line_segments)  # read only; body in _paragraph_text_edit.py
    line_texts = property(paragraph_line_texts)  # each saved line's text; body in _paragraph_text_edit.py

    # Implementations live in ``oxml/dutmal_compose.py`` -- ``objects.py``
    # (the shape-helpers' own overflow destination above) itself has no
    # headroom left either (1526/1600 measured before this module existed),
    # so this is a second overflow module, same reasoning.
    add_composed_character = refused_appends_nothing(_paragraph_add_composed_character)
    add_dutmal = refused_appends_nothing(_paragraph_add_dutmal)
    rubies = property(paragraph_rubies, doc="The 덧말 of this paragraph's runs (hwpx.objects.Ruby), in order.")
    composed_characters = property(
        paragraph_composed_characters,
        doc="The 글자 겹치기 of this paragraph's runs (hwpx.objects.ComposedCharacter), in order.",
    )

    @refused_appends_nothing
    def add_control(
        self,
        attributes: dict[str, str] | None = None,
        *,
        control_type: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a generic ``<hp:ctrl>`` control element -- an escape hatch outside the contract, like
        ``.element`` (not in the public surface lock; it may change between releases).

        This is a low-level escape hatch: an ``<hp:ctrl>`` carries no meaning
        of its own — the control it represents is its child element (
        ``colPr``, ``bookmark``, ``fieldBegin``, …).  Until the caller appends
        one, the element is empty and **Hancom refuses to open the document**,
        so a :class:`UserWarning` is raised.

        For the controls this package builds, prefer the dedicated
        ``add_column_definition``, ``add_bookmark``, and ``add_hyperlink``
        methods, which write the full child structure.
        """
        refuse_taken_out(self, "add_control")  # here, not wrapped: its warning names the caller's line
        attrs = dict(attributes or {})
        if control_type is not None:
            attrs.setdefault("type", control_type)
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        # ``ET.SubElement``는 stdlib Element만 받는다. 이 트리는 lxml이라
        # 그대로 부르면 TypeError로 항상 실패했다 — add_control은 문서에
        # 예제까지 있으면서 한 번도 동작한 적이 없다. 이 패키지의 다른
        # 생성 지점처럼 부모에게 만들게 해서 구현체를 맞춘다.
        element = run.makeelement(f"{_HP}ctrl", attrs)
        run.append(element)
        if len(element) == 0:
            warnings.warn(
                "add_control() produced an <hp:ctrl> with no control child; "
                "Hancom refuses to open a document containing it. Use "
                "add_column_definition/add_bookmark/add_hyperlink, or append "
                "the control element yourself.",
                UserWarning,
                stacklevel=3,  # the caller's line, past the wrapper that undoes a refused call
            )
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    # ------------------------------------------------------------------
    # Column definition helpers
    # ------------------------------------------------------------------

    @refused_appends_nothing
    def add_column_definition(
        self,
        col_count: int = 2,
        *,
        col_type: str = "NEWSPAPER",
        layout: str = "LEFT",
        same_size: bool = True,
        same_gap: int = 1200,
        column_widths: Sequence[tuple[int, int]] | None = None,
        separator_type: str | None = None,
        separator_width: str | None = None,
        separator_color: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a column definition control ``<hp:ctrl><hp:colPr>…</hp:colPr></hp:ctrl>``.

        Args:
            col_count: Number of columns (1–255).
            col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
            layout: ``LEFT``, ``RIGHT``, or ``MIRROR``.
            same_size: If ``True`` all columns have equal width.
            same_gap: Gap between columns when *same_size* is ``True`` (HWPUNIT).
            column_widths: When *same_size* is ``False``, a ``(width, gap)``
                pair per column, in HWP units adding up to the text width or
                in plain proportions: they are written as the shares of 32768
                Hancom keeps (see :func:`~hwpx.oxml.section_format.column_shares`).
            separator_type: Line type for the column separator (e.g. ``SOLID``).
            separator_width: Line width (e.g. ``0.12 mm``).
            separator_color: Line colour (e.g. ``#000000``).
        """
        if not 1 <= col_count <= 255:
            raise ValueError("col_count must be between 1 and 255")
        if same_size:
            validate_column_gap(same_gap)  # before its run is added
        sizes = column_shares(column_widths) if column_widths and not same_size else []
        # A section's first paragraph: Hancom does not open one with a second definition beside its settings' own,
        # so that one is rewritten (the section's).
        if self.element.find(f"{_HP}run/{_HP}secPr") is not None and (ctrl := self.section.properties.set_columns(
            col_count, col_type=col_type, layout=layout, same_size=same_size, same_gap=same_gap,
            column_widths=column_widths, separator_type=separator_type,
            separator_width=separator_width, separator_color=separator_color,
        )) is not None:
            return HwpxOxmlInlineObject(ctrl, self)

        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref,
        )
        # Hancom starts the new columns only from a definition ahead of the paragraph's text (its own
        # documents give it the first run, after a section's settings): one behind the text is not applied.
        ahead = [r for r in self.element.findall(f"{_HP}run") if r is not run and r.find(f"{_HP}secPr") is None]
        if ahead:
            self.element.remove(run)
            self.element.insert(list(self.element).index(ahead[0]), run)
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        col_pr_attrs: dict[str, str] = {
            "id": "",
            "type": col_type,
            "layout": layout,
            "colCount": str(col_count),
            "sameSz": "1" if same_size else "0",
            "sameGap": str(same_gap) if same_size else "0",
        }
        col_pr = _append_child(ctrl, f"{_HP}colPr", col_pr_attrs)

        # Optional column separator line
        if separator_type or separator_width or separator_color:
            line_attrs: dict[str, str] = {}
            if separator_type:
                line_attrs["type"] = separator_type
            if separator_width:
                line_attrs["width"] = separator_width
            if separator_color:
                line_attrs["color"] = separator_color
            _append_child(col_pr, f"{_HP}colLine", line_attrs)

        # Individual column sizes when same_size=False, as shares of 32768
        for w, g in sizes:
            _append_child(col_pr, f"{_HP}colSz", {
                "width": str(w), "gap": str(g),
            })

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    # ------------------------------------------------------------------
    # Bookmark / Hyperlink helpers
    # ------------------------------------------------------------------

    def add_bookmark(
        self,
        name: str,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
        offset: int | None = None,
    ) -> "Bookmark":
        """Insert a bookmark marker ``<hp:ctrl><hp:bookmark name="..."/></hp:ctrl>`` and return it as the
        :class:`~hwpx.objects.Bookmark` ``doc.refs.bookmarks`` reads (``kind="point"``).

        At the end of the paragraph, or with *offset* at that character of ``paragraph.text``: after the
        controls already there, before the character -- in the middle of a run's text between two ``hp:t`` of
        that run, as Hancom writes one (``mid_text_bookmark``). The bookmark name can be referenced by
        hyperlinks or cross-references.
        """
        from ._paragraph_text_edit import require_in_document

        require_in_document(self, caller="add_bookmark")
        from .field_marks import bookmark_for

        _require_nonempty_str(
            "name", name, code="ref-bookmark-name-empty", suggestion="Pass the bookmark's name."
        )
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref,
        )
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        mark = _append_child(ctrl, f"{_HP}bookmark", {"name": name})
        if offset is not None:
            from .text_ranges import place_created

            place_created(self, offset, ctrl, run)
        self.section.mark_dirty()
        return bookmark_for(self, mark)

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> "Hyperlink":
        """Insert a hyperlink spanning three runs: fieldBegin, text, fieldEnd.

        Args:
            url: The target URL, a ``mailto:`` address, or ``#name`` for the
                bookmark ``name``. It is written where Hancom reads it, the
                field's ``Command``/``Path`` parameters (``hyperlink_form``),
                and kept in ``@name`` for older readers.
            display_text: The visible text in the paragraph's look, blue and underlined as Hancom writes links, unless char_pr_id_ref is given.

        Returns:
            The link as the :class:`~hwpx.objects.Hyperlink` ``paragraph.hyperlinks`` reads
            (``link.element`` is the ``<hp:fieldBegin>``).
        """
        from ._paragraph_text_edit import require_in_document

        require_in_document(self, caller="add_hyperlink")
        from ..objects.form_field import Hyperlink

        _require_nonempty_str(
            "url", url, code="ref-link-target-empty",
            suggestion="Pass a web address, a mailto: address or #bookmark.",
        )
        _require_text(display_text)
        field_id = _object_id(self.section._ids)

        # 실한컴 gold 관례: 링크 서식(charPr)은 표시 텍스트 런에만 싣고
        # fieldBegin/fieldEnd 런은 주변 서식을 유지한다 — 뒤에 추가되는
        # 문단이 링크 서식을 상속(파랑 전염)하지 않게 하는 조건이기도 하다.
        run1 = self._create_run_for_object()
        ctrl1 = _append_child(run1, f"{_HP}ctrl", {})
        fb_attrs: dict[str, str] = {
            "id": field_id,
            "type": "HYPERLINK",
            "name": url,
            "editable": "0",
            "dirty": "0",
            "zorder": "-1",
            "fieldid": HYPERLINK_FIELD_ID,
        }
        begin = _append_child(ctrl1, f"{_HP}fieldBegin", fb_attrs)
        params = hyperlink_parameters(url)
        holder = _append_child(begin, f"{_HP}parameters", {"cnt": str(len(params)), "name": ""})
        for kind, name, text in params:
            _append_child(holder, f"{_HP}{kind}", {"name": name}).text = text

        # Run 2: visible text content
        link_style = hyperlink_char_pr(self.section, char_pr_id_ref, self.char_pr_id_ref or "0")
        run2 = self._create_run_for_object(char_pr_id_ref=link_style)
        t = _append_child(run2, f"{_HP}t", {})
        t.text = _sanitize_text(display_text)

        # Run 3: fieldEnd
        run3 = self._create_run_for_object()
        ctrl3 = _append_child(run3, f"{_HP}ctrl", {})
        _append_child(ctrl3, f"{_HP}fieldEnd", {"beginIDRef": field_id, "fieldid": HYPERLINK_FIELD_ID})

        self.section.mark_dirty()
        return Hyperlink(begin, self)

    add_date_field = refused_appends_nothing(_paragraph_add_date_field)
    add_proofreading_mark = _paragraph_add_proofreading_mark
    add_path_field = _paragraph_add_path_field
    add_mail_merge_field = _paragraph_add_mail_merge_field

    def add_title_mark(self, *, in_toc: bool) -> HwpxOxmlInlineObject:
        """이 문단의 첫 run 첫 ``hp:t`` 맨 앞에 ``<hp:titleMark
        ignore="0|1"/>``를 끼워 넣는다 -- "차례 숨기기"/"제목 차례 표시"의
        실측 계약(DEV-044, 6.15 박스 COM `SetPos`+`MarkTitle`/`HideTitle`
        3변형이 캐럿 문단 타겟팅을 확정: 마크는 항상 캐럿이 있는 문단에
        들어간다, 이전 Mac 프로브의 p0 착지는 캐럿 이동 불가에 따른
        퇴화 현상이었다).

        *in_toc*: ``True``(제목 차례 표시)면 ``ignore="1"``,
        ``False``(차례 숨기기)면 ``ignore="0"`` -- 이름의 직관과 반대인
        폴라리티가 실측 그대로다(Mac GUI A/B·Windows COM 독립 재확인
        일치). 호출자가 대상 문단을 직접 지정하는 이 API 형태가 실
        편집기의 "캐럿이 있는 문단" 타겟팅과 정확히 대응한다.
        """
        target_run: ET.Element | None = None
        text_element: ET.Element | None = None
        for run in self._run_elements():
            candidates = _children_by_local(run, "t")
            if candidates:
                target_run, text_element = run, candidates[0]
                break
        if text_element is None or target_run is None:
            from ..errors import HwpxStateError

            raise HwpxStateError(
                "문단에 hp:t를 가진 run이 없어 titleMark를 넣을 자리가 없습니다.",
                code="paragraph-title-mark-no-text-run",
            )
        mark = text_element.makeelement(
            _child_tag_like(text_element, "titleMark", _HP_NS),
            {"ignore": "1" if in_toc else "0"},
        )
        mark.tail = text_element.text
        text_element.text = None
        text_element.insert(0, mark)
        _clear_paragraph_layout_cache(self.element)  # the mark takes text positions the cached lines do not count
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(mark, self)

    def add_index_mark(self, first: str, *, second: str | None = None) -> HwpxOxmlInlineObject:
        """이 문단의 첫 텍스트 run 안, 그 ``hp:t`` **바로 앞**에
        ``<hp:ctrl><hp:indexmark>…</hp:indexmark></hp:ctrl>``를 끼워
        넣는다 -- "색인 표시"의 실측 계약.

        타겟팅은 ``add_title_mark``와 같다(호출자가 대상 문단을 직접
        지정 = 실 편집기의 "캐럿이 있는 문단"). 배치는 다르다: titleMark는
        ``hp:t`` **안**에 들어가지만 indexmark는 같은 run 안의
        ``hp:ctrl`` 형제로, 텍스트 앞에 선다(실측 gold
        ``tests/fixtures/gui_probes/index_mark_first_only.hwpx``).

        *first*는 색인 1단계 키, *second*는 2단계(하위) 키다. **second가
        ``None``이면 ``hp:secondKey`` 자체를 방출하지 않는다** -- 스키마
        (``ParaList XML schema.xml:209-216``)는 ``firstKey``/``secondKey``를
        둘 다 필수 시퀀스로 선언하지만 실한컴은 1단계만 넣은 색인에서
        ``secondKey``를 생략한다(gold 실측). 실측 우선 원칙(``add_new_num``
        의 ``autoNumFormat`` 생략, DEV-043의 열거값 불일치와 같은 부류)에
        따라 스키마가 아니라 실물을 따른다.
        """
        target_run: ET.Element | None = None
        text_element: ET.Element | None = None
        for run in self._run_elements():
            candidates = _children_by_local(run, "t")
            if candidates:
                target_run, text_element = run, candidates[0]
                break
        if text_element is None or target_run is None:
            from ..errors import HwpxStateError

            raise HwpxStateError(
                "문단에 hp:t를 가진 run이 없어 indexmark를 넣을 자리가 없습니다.",
                code="paragraph-index-mark-no-text-run",
            )
        for label, value in (("first", first), ("second", second)):
            if value is not None and not value:
                from ..errors import HwpxValueError

                raise HwpxValueError(
                    f"index mark {label} key must be a non-empty string",
                    code="paragraph-index-mark-empty-key",
                    context={"key": label},
                    suggestion=(
                        "빈 키를 넣지 마세요 -- 2단계 키가 없으면 second를 생략하면 됩니다"
                        "(생략과 빈 문자열은 방출되는 XML이 다릅니다)."
                    ),
                )

        ctrl = target_run.makeelement(_child_tag_like(target_run, "ctrl", _HP_NS), {})
        mark = _append_child(ctrl, _child_tag_like(target_run, "indexmark", _HP_NS), {})
        first_key = _append_child(mark, _child_tag_like(target_run, "firstKey", _HP_NS), {})
        first_key.text = _sanitize_text(first)
        if second is not None:
            second_key = _append_child(mark, _child_tag_like(target_run, "secondKey", _HP_NS), {})
            second_key.text = _sanitize_text(second)
        target_run.insert(list(target_run).index(text_element), ctrl)
        _clear_paragraph_layout_cache(self.element)  # a control in front of the text moves every cached line start
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    add_number_restart = _paragraph_add_number_restart

    def add_page_hiding(
        self,
        *,
        header: bool = False,
        footer: bool = False,
        master_page: bool = False,
        border: bool = False,
        fill: bool = False,
        page_num: bool = False,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "PageHiding":
        """Insert ``<hp:ctrl><hp:pageHiding .../></hp:ctrl>`` and return it as the
        :class:`~hwpx.objects.PageHiding` ``doc.page.page_hidings`` reads.

        Hides the named page elements on this paragraph's page only
        (``ParaList XML schema.xml:148-163`` — six independent booleans, all
        default ``false``/unhidden). Matches real corpus (hwpxlib_corpus, 4
        files) sibling placement: its own dedicated ``hp:ctrl``, typically
        alongside a ``newNum``/``pageNum`` control in the section-opening
        paragraph's first run.
        """

        from ..objects.results import PageHiding

        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        _append_child(
            ctrl,
            f"{_HP}pageHiding",
            {
                "hideHeader": "1" if header else "0",
                "hideFooter": "1" if footer else "0",
                "hideMasterPage": "1" if master_page else "0",
                "hideBorder": "1" if border else "0",
                "hideFill": "1" if fill else "0",
                "hidePageNum": "1" if page_num else "0",
            },
        )
        self.section.mark_dirty()
        return PageHiding(header=bool(header), footer=bool(footer), master_page=bool(master_page),
                          border=bool(border), fill=bool(fill), page_num=bool(page_num), paragraph=self)

    def add_chart(
        self,
        chart_id_ref: str,
        *,
        treat_as_char: bool = False,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a native ``<hp:chart>`` anchor referencing a chartML part.

        Emits the real-Hancom chart anchor (contract inferred in
        specs/055-chart-authoring/evidence/p0/chart-contract.md): the chart
        content lives in an ECMA-376 chartML part addressed directly by
        ``chartIDRef`` (real Hancom registers the part in no manifest), and
        Hancom lays the chart out from the chartML alone — no OLE fallback or
        pre-rendered image is required.

        Args:
            chart_id_ref: Package path of the chartML part
                (e.g. ``Chart/chart1.xml``).
            width, height: The chart's box (``<hp:sz>``, HWPUNIT, both from 1);
                one left out is the gold document's 32250 x 18750.
            treat_as_char: ``True`` places the chart inline in the text flow;
                the default mirrors the gold float placement.
        """
        from ._paragraph_text_edit import require_in_document

        require_in_document(self, caller="add_chart")
        from ..errors import HwpxValueError, argument_type_error

        if not isinstance(chart_id_ref, str):
            raise argument_type_error("chart_id_ref", chart_id_ref, "str")
        reference = chart_id_ref.strip()
        if not reference:
            raise HwpxValueError(
                "chart_id_ref must be a non-empty package path",
                code="shape-chart-reference-empty",
                suggestion="Pass the chart part's path, e.g. 'Chart/chart1.xml' (doc.shapes.add_chart writes one).",
            )
        width, height = validate_box_size((32250 if width is None else width, 18750 if height is None else height),
                                          kind="chart")
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref
        )
        chart = _append_child(run, f"{_HP}chart", {
            "id": _object_id(self.section._ids),
            "zOrder": "0",
            "numberingType": "PICTURE",
            "textWrap": "TOP_AND_BOTTOM" if treat_as_char else "SQUARE",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "chartIDRef": reference,
        })
        _append_child(chart, f"{_HP}sz", {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(chart, f"{_HP}pos", {
            "treatAsChar": "1" if treat_as_char else "0",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "0",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "PARA" if treat_as_char else "COLUMN",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(chart, f"{_HP}outMargin", {
            "left": "0",
            "right": "0",
            "top": "0",
            "bottom": "0",
        })
        stack_new_object(chart, self.section)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(chart, self)

    add_drop_cap = _paragraph_add_drop_cap

    def add_equation(
        self,
        script: str,
        *,
        font_size: float = 11.0,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        font: str = "HancomEQN",
        width: int | None = None,
        height: int | None = None,
    ) -> HwpxOxmlEquation:
        """Insert an inline ``<hp:equation>`` carrying an EqEdit *script*.

        Emits the real-Hancom equation shape (contract inferred in
        specs/054-equation-authoring/evidence/p0/equation-contract.md): the
        EqEdit source lives in the ``<hp:script>`` child, no lineseg cache is
        written (Hancom re-lays-out on open), and the shape is inline
        (``treatAsChar="1"``) so it renders in the page flow.

        Args:
            script: EqEdit script stored verbatim (e.g. ``{a} over {b}``).
            font_size: Equation font size in pt (gold: 11/12), kept as ``baseUnit``
                (1/100 pt).
            width, height: The box (``<hp:sz>``, HWPUNIT, from 1); one left out is
                measured from the script at *font_size*. Hancom lays the page out
                with the stored box on open.
            font: Equation font name. ``HancomEQN`` is what Hangul's own
                equation editor writes; ``HYhwpEQ`` is the older, lighter
                face python-hwpx wrote before 7.0. The measured box is
                wide enough for either.
        """
        from ..errors import HwpxValueError, argument_type_error

        if not isinstance(script, str):
            raise argument_type_error("script", script, "str", suggestion="Pass the EqEdit script as a str.")
        text = script.strip()
        if not text:
            raise HwpxValueError(
                "equation script must be a non-empty string",
                code="shape-equation-script-empty",
                suggestion="Pass an EqEdit script (convert LaTeX with hwpx.equation).",
            )
        validate_equation_script(text)  # LaTeX or unpaired braces: Hancom would not draw it as an equation
        base_unit = equation_base_unit(font_size)
        font = validate_equation_font(font)
        from ..equation.measure import measure_equation

        measured = measure_equation(text, base_unit=base_unit)
        if width is not None or height is not None:
            width, height = validate_box_size((measured.width if width is None else width,
                                               measured.height if height is None else height), kind="equation")
        else:
            width, height = measured.width, measured.height
        validate_shape_size(width, height)
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref
        )
        equation = _append_child(run, f"{_HP}equation", {
            "id": _object_id(self.section._ids),
            "zOrder": "0",
            "numberingType": "EQUATION",
            "textWrap": "TOP_AND_BOTTOM",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "version": "Equation Version 60",
            "baseLine": str(measured.base_line),
            "textColor": "#000000",
            "baseUnit": str(base_unit),
            "lineMode": "CHAR",
            "font": font,
        })
        _append_child(equation, f"{_HP}sz", {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(equation, f"{_HP}pos", {
            "treatAsChar": "1",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "0",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "PARA",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(equation, f"{_HP}outMargin", {
            "left": "56",
            "right": "56",
            "top": "0",
            "bottom": "0",
        })
        comment = _append_child(equation, f"{_HP}shapeComment", {})
        comment.text = "수식입니다."
        script_element = _append_child(equation, f"{_HP}script", {})
        script_element.text = text
        stack_new_object(equation, self.section)
        self.section.mark_dirty()
        return HwpxOxmlEquation(equation, self)

    def add_form_field(
        self,
        name: str,
        *,
        prompt: str = "",
        memo: str = "",
        editable: bool = True,
        prompt_char_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> "FormField":
        """Insert a click-here (누름틀) form field at the end of this paragraph and return it as the
        :class:`~hwpx.objects.FormField` ``doc.fields.all`` reads.

        With *start* and *end* the field wraps the characters ``[start, end)`` of ``paragraph.text``, its
        value: the begin after the controls at *start*, the end before the character at *end*, each in the run
        it falls in. Around at least one character no prompt run is written -- the field holds a value -- and
        *prompt* stays the field's 안내문 (its ``Direction`` parameter), as Hancom keeps one in a filled
        click-here field (``field_value_shape_filled``). An empty range (*start* == *end*) holds no value, so
        a non-empty *prompt* is written as without a range: a prompt run between begin and end, as every
        empty Hancom-saved click-here field with an 안내문 has one (12 of 12 in the fixtures; Hancom adds it
        on saving one without). *memo* and *editable* are written as without a range. A field around
        at least one character is written as filled (``dirty="1"``, :attr:`FormField.filled`), the mark Hancom
        saves on a click-here field holding text. A range holding
        one end of another field is refused (``paragraph-range-splits-field``).

        Emits the real-Hancom CLICKHERE shape (inferred from Hancom
        Office 12.0.0.3288 gold documents):
        a ``fieldBegin`` ctrl run carrying the ``Prop``/``Command``/``Direction``/
        ``HelpState`` parameters, an optional prompt run showing *prompt* (the
        안내문, screen-only — Hancom does not print it), and a ``fieldEnd`` ctrl
        run. ``Command`` lengths count UTF-16 characters, so values may contain
        spaces. ``fieldid`` is the click-here control id (``%clk``) Hancom gives
        every click-here field; ``id`` is new.

        Args:
            name: Field name used by ``list_form_fields``/``fill_form_field``.
            prompt: 안내문 text shown while the field is empty (``Direction``).
            memo: Help text (``HelpState``). A tab or a line break in either is refused before anything
                is written (``field-text-control-unsupported``): no Hancom-saved click-here field holds one.
            prompt_char_pr_id_ref: charPr for the prompt run (callers normally
                pass a red-italic style; Hancom uses one).

        Returns:
            The field (``field.element`` is the ``<hp:fieldBegin>``).
        """
        _require_text(name)  # not text: refused before anything is written
        _require_text(prompt)
        _require_text(memo)
        from .field_marks import check_click_here_text, form_field_for
        from .text_ranges import check_field_range, wrap_in_field

        check_click_here_text(prompt=prompt, memo=memo)
        span = check_field_range(self, start, end)
        field_id = _object_id(self.section._ids)
        field_instance_id = field_type_id("CLICK_HERE", ids=self.section._ids)
        direction = _sanitize_text(prompt)
        help_state = _sanitize_text(memo)

        # Run 1: fieldBegin with the CLICKHERE parameter block
        run1 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl1 = _append_child(run1, f"{_HP}ctrl", {})
        field_begin = _append_child(ctrl1, f"{_HP}fieldBegin", {
            "id": field_id,
            "type": "CLICK_HERE",
            "name": _sanitize_text(name),
            "editable": "1" if editable else "0",
            # A field wrapped around text holds a value: Hancom saves such a field with dirty="1"
            # (a document written with "0" comes back "1" when Hancom saves it again).
            "dirty": "1" if span is not None and span[1] > span[0] else "0",
            "zorder": "-1",
            "fieldid": field_instance_id,
            "metaTag": "",
        })
        # Lengths count UTF-16 units, as Hancom writes them and as the field's prompt and memo setters
        # read and write them (a character outside the BMP is two).
        def units(value: str) -> int:
            return len(value.encode("utf-16-le")) // 2

        payload = (
            f"Direction:wstring:{units(direction)}:{direction} "
            f"HelpState:wstring:{units(help_state)}:{help_state} "
        )
        param_count = 2 + (1 if direction else 0) + (1 if help_state else 0)
        parameters = _append_child(
            field_begin, f"{_HP}parameters", {"cnt": str(param_count), "name": ""}
        )
        prop = _append_child(parameters, f"{_HP}integerParam", {"name": "Prop"})
        prop.text = "9"
        command = _append_child(parameters, f"{_HP}stringParam", {
            "name": "Command",
            f"{{{XML_NS}}}space": "preserve",
        })
        command.text = f"Clickhere:set:{units(payload)}:{payload} "
        if direction:
            direction_param = _append_child(
                parameters, f"{_HP}stringParam", {"name": "Direction"}
            )
            direction_param.text = direction
        if help_state:
            help_param = _append_child(
                parameters, f"{_HP}stringParam", {"name": "HelpState"}
            )
            help_param.text = help_state

        # Run 2: the prompt placeholder (only while a prompt exists and no text is wrapped)
        run2: ET.Element | None = None
        if direction and (span is None or span[0] == span[1]):
            run2 = self._create_run_for_object(
                char_pr_id_ref=(
                    prompt_char_pr_id_ref
                    if prompt_char_pr_id_ref is not None
                    else char_pr_id_ref
                ),
            )
            prompt_text = _append_child(run2, f"{_HP}t", {})
            prompt_text.text = direction

        # Run 3: fieldEnd + trailing empty text node (gold shape)
        run3 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl3 = _append_child(run3, f"{_HP}ctrl", {})
        _append_child(ctrl3, f"{_HP}fieldEnd", {
            "beginIDRef": field_id,
            "fieldid": field_instance_id,
        })
        _append_child(run3, f"{_HP}t", {})
        if span is not None:
            wrap_in_field(self, span, (ctrl1, run1), (ctrl3, run3), run2)
        self.section.mark_dirty()
        return form_field_for(self, field_begin)

    @refused_appends_nothing
    def add_check_box(
        self,
        caption: str,
        *,
        checked: bool = False,
        name: str | None = None,
        width: int = 9921,
        height: int = 1984,
        char_pr_id_ref: str | int | None = None,
    ) -> "CheckBox":
        """Insert a check-box form object (체크박스) at the end of this paragraph and return it as the
        :class:`~hwpx.objects.CheckBox` ``doc.fields.check_boxes`` reads.

        Emits the real-Hancom ``<hp:checkBtn>`` shape. Unlike the click-here
        field this is **not** wrapped in ``<hp:ctrl>`` — it is a direct child of
        the run, beside the ``<hp:t>`` node.

        Hancom refuses to open a document whose ``checkBtn`` lacks
        ``<hp:formCharPr>`` (measured: the same file with the element present
        opens, without it Hancom reports a read error and produces nothing), so
        the child block is always emitted. ``caption`` is drawn next to the box
        and appears in the rendered text layer; ``checked`` selects the
        ``CHECKED``/``UNCHECKED`` value that draws ☑ or □.

        Args:
            caption: Label drawn beside the box.
            checked: Initial state.
            name: Object name. Defaults to a generated ``CheckBox<N>``.
            width: Box + caption width in HWPUNIT.
            height: Box height in HWPUNIT.
        """
        _require_text(caption)  # not text: refused before anything is written
        if name is not None:
            _require_text(name)
        from ._paragraph_text_edit import require_in_document

        require_in_document(self, caller="add_check_box")

        run = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        check = _append_child(run, f"{_HP}checkBtn", {
            "caption": _sanitize_text(caption),
            "value": "CHECKED" if checked else "UNCHECKED",
            "radioGroupName": "",
            "triState": "0",
            "backStyle": "OPAQUE",
            "name": _sanitize_text(name) if name else f"CheckBox{_object_id(self.section._ids)}",
            "foreColor": "#000000",
            "backColor": "#FFFFFF",
            "groupName": "",
            "tabStop": "1",
            "editable": "1",
            "tabOrder": "0",
            "enabled": "1",
            "borderTypeIDRef": "0",
            "drawFrame": "1",
            "printable": "1",
            "command": "",
        })
        _append_child(check, f"{_HP}formCharPr", {
            "charPrIDRef": str(char_pr_id_ref if char_pr_id_ref is not None else 0),
            "followContext": "0",
            "autoSz": "0",
            "wordWrap": "0",
        })
        _append_child(check, f"{_HP}sz", {
            "width": str(int(width)),
            "widthRelTo": "ABSOLUTE",
            "height": str(int(height)),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(check, f"{_HP}pos", {
            "treatAsChar": "1",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "1",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "COLUMN",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(check, f"{_HP}outMargin", {
            "left": "0", "right": "0", "top": "0", "bottom": "0",
        })
        _append_child(run, f"{_HP}t", {})

        self.section.mark_dirty()
        from .field_marks import check_box_for

        return check_box_for(self, check)

    @property
    def bookmarks(self) -> "tuple[Bookmark, ...]":
        """The bookmarks that start in this paragraph, in order, as :class:`~hwpx.objects.Bookmark`
        (``bookmark.name``), the values ``doc.refs.bookmarks`` gives.

        Both forms Hancom saves a bookmark in count:
        ``<hp:ctrl><hp:bookmark name=".."/></hp:ctrl>`` (``kind="point"``) and
        ``<hp:fieldBegin type="BOOKMARK" name="..">`` paired with a fieldEnd (``kind="field"``).
        """
        from .field_marks import paragraph_bookmarks

        return paragraph_bookmarks(self)

    @property
    def hyperlinks(self) -> "tuple[Hyperlink, ...]":
        """The hyperlinks that start in this paragraph, as :class:`hwpx.objects.Hyperlink`.

        ``link.url`` is the target (``Path``, else ``Command``, else ``@name`` --
        see ``hyperlink_form.hyperlink_target``) and ``link.text`` the text it spans;
        both are settable. Before 7.0 this gave dicts: read ``link.url`` / ``link.field_id``
        (or ``link.to_dict()``) where ``link["url"]`` / ``link["id"]`` was read.
        """
        from ..objects.form_field import Hyperlink

        return tuple(
            Hyperlink(fb, self)
            for run in self._run_elements()
            for ctrl in run.findall(f"{_HP}ctrl")
            for fb in ctrl.findall(f"{_HP}fieldBegin")
            if fb.get("type") == "HYPERLINK"
        )

    # Footnote/endnote authoring lives in note_authoring.py (owner-file
    # headroom, see class-attribute assignments near the top of this class).
    add_footnote = _paragraph_add_footnote
    add_endnote = _paragraph_add_endnote
    footnotes = property(_paragraph_footnotes)
    endnotes = property(_paragraph_endnotes)

    @property
    def id(self) -> str | None:
        """The paragraph's id as written (``hp:p/@id``); ``None`` when it has none.

        Not a unique key: Hancom writes ``"0"`` on some paragraphs and a file can repeat an id
        (2,549 of the 80,545 paragraphs in ``tests/fixtures/hancom_saved`` say ``"0"``). To find a
        paragraph again compare the objects: ``doc.paragraphs.index(paragraph)``, or use it as a
        dict key; two paragraph objects are equal when they are the same paragraph."""

        return self.element.get("id")

    @property
    def para_pr_id_ref(self) -> str | None:
        """Return the paragraph property reference applied to this paragraph."""
        return self.element.get("paraPrIDRef")

    @para_pr_id_ref.setter
    def para_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "paraPrIDRef" in self.element.attrib:
                del self.element.attrib["paraPrIDRef"]
                _clear_paragraph_layout_cache(self.element)
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("paraPrIDRef") != new_value:
            self.element.set("paraPrIDRef", new_value)
            # A new paragraph shape changes line spacing, indents and alignment.
            # Hancom takes the line heights from the cached layout, so a kept
            # cache would draw the old line spacing.
            _clear_paragraph_layout_cache(self.element)
            self.section.mark_dirty()

    @property
    def style_id_ref(self) -> str | None:
        """Return the style reference applied to this paragraph."""
        return self.element.get("styleIDRef")

    @style_id_ref.setter
    def style_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "styleIDRef" in self.element.attrib:
                del self.element.attrib["styleIDRef"]
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("styleIDRef") != new_value:
            self.element.set("styleIDRef", new_value)
            self.section.mark_dirty()

    @property
    def column_break(self) -> bool:
        """Whether this paragraph forces a column break before it starts (Hancom's Ctrl+Shift+Enter, as
        ``page_break`` is its Ctrl+Enter); settable.

        This is ``hp:p``'s own ``columnBreak`` attribute -- a per-paragraph
        instance flag (default ``"0"``, always present on every parsed
        paragraph already), distinct from ``hh:breakSetting``'s
        ``pageBreakBefore`` (a shared paraPr *style* property that
        ``set_paragraph_format``'s ``page_break_before`` controls). The
        sibling ``pageBreak`` attribute uses the same "0"/"1" lexical form
        (real-corpus confirmed: 73/14266 paragraphs carry ``pageBreak="1"``,
        never ``"true"``/``"false"`` — 6.12 트레인㊸ 갭④).
        """
        return self.element.get("columnBreak") == "1"

    @column_break.setter
    def column_break(self, value: bool) -> None:
        new_value = "1" if value else "0"
        if self.element.get("columnBreak") != new_value:
            self.element.set("columnBreak", new_value)
            # As page_break: the paragraph's lines move to another column, so its old line layout goes.
            _clear_paragraph_layout_cache(self.element)
            self.section.mark_dirty()

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the shared character property reference across runs.

        If runs use multiple different references the value ``None`` is
        returned, indicating the paragraph does not have a uniform character
        style applied.
        """

        values: set[str] = set()
        for run in self._run_elements():
            value = run.get("charPrIDRef")
            if value is not None:
                values.add(value)

        if not values:
            return None
        if len(values) == 1:
            return next(iter(values))
        return None

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        new_value = None if value is None else str(value)
        runs = self._run_elements()
        if not runs:
            runs = [self._ensure_run()]

        changed = False
        for run in runs:
            if new_value is None:
                if "charPrIDRef" in run.attrib:
                    del run.attrib["charPrIDRef"]
                    changed = True
            else:
                if run.get("charPrIDRef") != new_value:
                    run.set("charPrIDRef", new_value)
                    changed = True

        if changed:
            # A style swap changes glyph metrics, so the cached line layout of
            # this paragraph no longer holds.
            _clear_paragraph_layout_cache(self.element)
            self.section.mark_dirty()

__all__ = ["HwpxOxmlParagraph"]
