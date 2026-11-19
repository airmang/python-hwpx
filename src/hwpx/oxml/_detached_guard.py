"""Edits through an object taken out of its document.

A paragraph, run, table, cell, row, column, note, text box or object of a table, note or text box taken
out, of a removed section, or removed itself, is no longer in its document: nothing written into it is
saved. One rule decides what such an object still takes:

* an edit that changes only the object's own content and values, and writes nothing on the document's
  side, works -- a paragraph's text (``text =``, ``insert_text``, ``delete_range``, ``replace_range``,
  ``set_text_preserving_runs``, ``clear_text``), a run without a new shape (``add_run`` with no
  formatting, ``split_run``), an existing shape id (``char_pr_id_ref =``), sizes, margins, placement
  and values of a table, cell or object;
* an edit that writes on the document's side is refused before anything changes
  (``paragraph-not-in-document``, ``table-not-in-document``, ``shape-not-in-document``): one that may
  register a character, paragraph or border shape in the header (formatting), one that numbers
  (notes, number restarts, page hiding, bullets and numbering), one that makes a mark or an object the
  document counts (highlights, bookmarks, fields, links, check boxes, pictures, charts, shapes,
  equations, tables), one that adds a paragraph beside it or rows, columns and cells to its table, and
  one that moves or copies it into the document.

The second kind is wrapped here, on the classes, so every way of calling it is covered; the edits the
paragraph and range code already refuse are left as they are.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Iterable

from ..errors import HwpxValueError
from ._paragraph_text_edit import in_document

_SUGGESTION = (
    "Take it again from the document (doc.paragraphs, doc.tables, cell.paragraphs ...); an object taken out "
    "is no longer saved."
)

# add_run/insert_text arguments that ask for a character shape (one to find or make in the header)
_FORMAT_ARGUMENTS = ("bold", "italic", "underline", "color", "font", "size", "highlight", "strike", "attributes",
                     "tab_widths")


def _holder_and_element(obj: Any) -> tuple[Any, Any]:
    """The section (or master page) *obj* was taken from, and the element to look for in it."""

    element = getattr(obj, "element", None)
    table = getattr(obj, "table", None)
    if element is None and table is not None:  # a column has no element of its own
        element = table.element
    owner: Any = obj
    if table is not None and not hasattr(obj, "paragraph"):
        owner = table  # a cell, row or column: its table's
    holder = owner.__dict__.get("_held_section") if hasattr(owner, "__dict__") else None
    if holder is None:
        holder = getattr(owner, "section", None) if not hasattr(owner, "paragraph") else None
    if holder is None:
        paragraph = getattr(owner, "paragraph", None)
        holder = paragraph.section if paragraph is not None else getattr(owner, "_section", None)
    return holder, element


def taken_out(obj: Any) -> bool:
    """True when *obj* (a paragraph, run, table, cell, row, column, note, text box or object) is no longer
    in its document. ``False`` when that cannot be told (an object made without a section)."""

    holder, element = _holder_and_element(obj)
    if holder is None or element is None or not hasattr(element, "getparent"):
        return False
    return not in_document(element, holder)


def _refusal(code: str, role: str, caller: str) -> HwpxValueError:
    return HwpxValueError(
        f"the {role} is not in the document any more (it sits in a table, note or text box taken out, in a "
        f"removed section, or was removed); {caller} writes on the document's side",
        code=code,
        context={"caller": caller, "role": role},
        suggestion=_SUGGESTION,
    )


def refuse_taken_out(obj: Any, caller: str, code: str = "paragraph-not-in-document", role: str = "paragraph") -> None:
    """Refuse (*code*) the call *caller* on *obj* when it is taken out of its document. For a method that warns
    (its warning names its caller's line, which a wrapper would take): it calls this itself."""

    if taken_out(obj):
        raise _refusal(code, role, caller)


def _formatting(arguments: dict[str, Any]) -> bool:
    for name in _FORMAT_ARGUMENTS:
        value = arguments.get(name)
        if value is not None and value is not False:
            return True
    return False


def _guard_method(cls: type, name: str, code: str, role: str,
                  when: Callable[[dict[str, Any]], bool] | None = None) -> None:
    original = getattr(cls, name)
    signature = inspect.signature(original)

    @functools.wraps(original)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        if taken_out(self) and (when is None or when(signature.bind_partial(self, *args, **kwargs).arguments)):
            raise _refusal(code, role, name)
        return original(self, *args, **kwargs)

    setattr(cls, name, guarded)


def _guard_setter(cls: type, name: str, code: str, role: str) -> None:
    original = inspect.getattr_static(cls, name)
    setter = original.fset  # a settable property of the class (install() names them)

    @functools.wraps(setter)
    def guarded(self: Any, value: Any) -> None:
        if taken_out(self):
            raise _refusal(code, role, f"{name} =")
        setter(self, value)

    setattr(cls, name, property(original.fget, guarded, original.fdel, original.__doc__))


def _guard(cls: type, code: str, role: str, methods: Iterable[str] = (), setters: Iterable[str] = (),
           when: dict[str, Callable[[dict[str, Any]], bool]] | None = None) -> None:
    for name in methods:
        _guard_method(cls, name, code, role, (when or {}).get(name))
    for name in setters:
        _guard_setter(cls, name, code, role)


def install() -> None:
    """Wrap the writes on the document's side of the model classes (once)."""

    from .memo import HwpxOxmlNote
    from .objects import Caption, DrawText
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun
    from .table import HwpxOxmlTable, HwpxOxmlTableCell

    if getattr(HwpxOxmlParagraph, "_detached_guard_installed", False):
        return
    HwpxOxmlParagraph._detached_guard_installed = True  # type: ignore[attr-defined]

    paragraph = ("paragraph-not-in-document", "paragraph")
    _guard(
        HwpxOxmlParagraph, *paragraph,
        methods=(
            # a paragraph beside it
            "insert_before", "insert_after",
            # marks and objects the document counts (ids, z-order, doc.text.highlights ...)
            "add_highlight", "add_table", "add_rectangle", "add_ellipse", "add_line", "add_equation", "add_arc",
            "add_polygon", "add_curve", "add_container", "add_date_field",  # add_shape, add_control: in them
            "add_path_field", "add_mail_merge_field", "add_index_mark", "add_title_mark", "add_proofreading_mark",
            "add_drop_cap", "add_dutmal", "add_composed_character", "add_column_definition",
            # numbering
            "add_number_restart", "add_page_hiding", "set_bullet", "set_numbering",
            # a character shape to find or make in the header
            "format_range", "add_run",
        ),
        setters=(
            "alignment", "first_line_indent_mm", "indent_left_mm", "indent_right_mm", "keep_lines",
            "keep_with_next", "line_spacing", "outline_level", "page_break_before", "spacing_after_pt",
            "spacing_before_pt", "widow_orphan",
        ),
        when={"add_run": _formatting},
    )
    _guard(
        HwpxOxmlRun, "paragraph-not-in-document", "run",
        methods=("set_font", "set_format"),
        setters=("bold", "color", "font", "highlight", "italic", "letter_spacing", "ratio", "size", "strike",
                 "subscript", "superscript", "underline"),
    )
    table = ("table-not-in-document", "table")
    _guard(
        HwpxOxmlTable, *table,
        methods=(
            "copy_after", "insert_rows", "delete_rows", "insert_columns", "delete_columns", "merge_cells",
            "split_cell", "split_merged_cell", "set_borders", "set_cell_borders", "set_cell_border_fill",
            "set_cell_fill_gradient", "set_cell_fill_image", "set_cell_shading", "set_shading",
        ),
        setters=("alignment",),
    )
    _guard(HwpxOxmlTableCell, "table-not-in-document", "cell", methods=("add_paragraph", "add_table"))
    _guard(HwpxOxmlNote, "paragraph-not-in-document", "note", methods=("add_paragraph", "add_run"),
           when={"add_run": _formatting})
    _guard(DrawText, "shape-not-in-document", "text box", methods=("add_paragraph",))
    _guard(Caption, "shape-not-in-document", "caption", methods=("add_paragraph",))
