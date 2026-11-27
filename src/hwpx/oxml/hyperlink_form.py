# SPDX-License-Identifier: Apache-2.0
"""Hancom's storage of a hyperlink field (``hp:fieldBegin type="HYPERLINK"``).

Hancom keeps a link's target in the field's ``hp:parameters``, not in
``@name`` (which its own links leave empty):

* ``Command`` holds the target, with ``:``, ``?``, ``;`` and ``#`` escaped by
  a backslash, followed by a tail that names
  the kind: ``;1;0;0;`` for a web address, ``;2;0;0`` for ``mailto:``,
  ``;0;0;0;`` for a bookmark written ``?<bookmark name>``. A ``|`` separates
  an optional tool tip before the tail.
* ``Path`` repeats the plain address (web and mail links only).
* ``Category`` / ``TargetType`` / ``DocOpenType`` name the kind and how the
  target opens.

A field that carries only ``@name`` -- what python-hwpx wrote before --
survives a Hancom save but points nowhere: Hancom adds
``Category=HWPHYPERLINK_TYPE_HWP`` and no ``Command``.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .namespaces import HH, tag_local_name

#: The ``fieldid`` Hancom gives every hyperlink field (control id ``%hlk``).
HYPERLINK_FIELD_ID = "627600491"

_ESCAPED = ":?;#"
_COMMAND_TAIL = re.compile(r";\d+;\d+;\d+;?$")
_ESCAPE = re.compile(r"\\(.)")


def _escape(text: str) -> str:
    return "".join("\\" + ch if ch in _ESCAPED else ch for ch in text)


def hyperlink_parameters(url: str) -> list[tuple[str, str, str]]:
    """``(element local name, parameter name, text)`` for *url*, in Hancom's order.

    ``#name`` is a link to the bookmark ``name``; ``mailto:`` addresses are mail
    links; anything else is a web address.
    """

    if url.startswith("#"):
        command, path, category = f"?{_escape(url[1:])};0;0;0;", None, "HWPHYPERLINK_TYPE_HWP"
    elif url.lower().startswith("mailto:"):
        command, path, category = f"{url};2;0;0", url, "HWPHYPERLINK_TYPE_EMAIL"
    else:
        command, path, category = f"{_escape(url)};1;0;0;", url, "HWPHYPERLINK_TYPE_URL"
    params = [("integerParam", "Prop", "0"), ("stringParam", "Command", command)]
    if path is not None:
        params.append(("stringParam", "Path", path))
    params += [
        ("stringParam", "Category", category),
        ("stringParam", "TargetType", "HWPHYPERLINK_TARGET_BOOKMARK"),
        ("stringParam", "DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB"),
    ]
    return params


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def hyperlink_target(field_begin: Any) -> str:
    """Where a HYPERLINK ``fieldBegin`` points: ``Path``, else ``Command``, else ``@name``.

    ``Command`` loses its kind tail and tool tip and is unescaped; a bookmark
    target (``?name``) comes back as ``#name``, the form ``add_hyperlink`` takes.
    """

    command: str | None = None
    for params in field_begin:
        if _local(params.tag) != "parameters":
            continue
        for param in params:
            name = param.get("name")
            if name == "Path" and (param.text or "").strip():
                return param.text or ""
            if name == "Command" and param.text:
                command = param.text
    if command:
        head = _COMMAND_TAIL.sub("", command).split("|", 1)[0]
        head = _ESCAPE.sub(r"\1", head)
        if head.startswith("?") and not head.startswith("?#"):
            return "#" + head[1:]
        return head
    return field_begin.get("name", "") or ""


_LINK_COLOR = "#0000FF"
# hh:charPr children that come after hh:underline
_AFTER_UNDERLINE = ("strikeout", "outline", "shadow", "emboss", "engrave", "supscript", "subscript")


def _give_link_look(char_pr: Any) -> None:
    """Blue text with a blue underline; everything else stays as it is."""

    char_pr.set("textColor", _LINK_COLOR)
    underline = char_pr.find(f"{HH}underline")
    if underline is None:
        underline = char_pr.makeelement(f"{HH}underline", {})
        children = list(char_pr)
        at = next((i for i, child in enumerate(children)
                   if isinstance(child.tag, str) and tag_local_name(child.tag) in _AFTER_UNDERLINE), len(children))
        char_pr.insert(at, underline)
    if underline.get("type", "NONE").upper() in ("NONE", "SOLID"):
        underline.set("type", "BOTTOM")
    underline.set("shape", underline.get("shape") or "SOLID")
    underline.set("color", _LINK_COLOR)


def _shape_key(element: Any, *, top: bool = True) -> tuple:
    attrs = tuple(sorted((k, v) for k, v in element.attrib.items() if not (top and k == "id")))
    return (element.tag, attrs, (element.text or "").strip(), tuple(_shape_key(child, top=False) for child in element))


def hyperlink_char_pr(
    section: Any, char_pr_id_ref: str | int | None, base_char_pr_id: str | int | None = None
) -> str | int | None:
    """The char property of a link's visible text: the one given, or Hancom's convention.

    Hancom writes link text blue (``#0000FF``) with a blue underline. The rest of
    the look (font, size, bold, ...) is that of ``base_char_pr_id``, the text the
    link sits in; an equal char property is reused, otherwise one is added.
    Without a document (a detached section) the text keeps the paragraph's style.
    """

    if char_pr_id_ref is not None:
        return char_pr_id_ref
    document = getattr(section, "document", None)
    if document is None or not document.headers:
        return None
    header = document.headers[0]
    char_props = header._char_properties_element(create=True)
    if char_props is None:
        return None
    base = None
    if base_char_pr_id is not None:
        base = char_props.find(f"{HH}charPr[@id='{base_char_pr_id}']")
    if base is None:
        base = char_props.find(f"{HH}charPr")
    if base is None:
        return document.ensure_run_style(underline=True, color=_LINK_COLOR, underline_color=_LINK_COLOR)
    wanted = deepcopy(base)
    _give_link_look(wanted)
    key = _shape_key(wanted)
    element = header.ensure_char_property(
        predicate=lambda candidate: _shape_key(candidate) == key,
        modifier=_give_link_look,
        base_char_pr_id=base.get("id"),
    )
    return element.get("id")


def hyperlink_field_shapes(paragraph: Any, field_char_pr_id_ref: str | int | None) -> tuple[str, str]:
    """The look around a link added at the end of *paragraph*, and its field runs' shape.

    The look around it is that of the text it follows (the paragraph's last run; Hangul writes
    the ``fieldBegin`` in that run), the paragraph's own when it has no run. The field runs take
    it unless *field_char_pr_id_ref* names a shape the header defines (``style-definition-not-found``
    otherwise)."""

    runs = paragraph._run_elements()
    surrounding = (runs[-1].get("charPrIDRef") if runs else None) or paragraph.char_pr_id_ref or "0"
    if field_char_pr_id_ref is None:
        return surrounding, surrounding
    from .formatting import find_definition

    headers = getattr(getattr(paragraph.section, "document", None), "headers", None) or []
    found = find_definition(headers[0], "charPr", field_char_pr_id_ref) if headers else None
    if found is None:
        from ..errors import HwpxLookupError

        raise HwpxLookupError(
            f"the header has no charPr with id {field_char_pr_id_ref!r}",
            code="style-definition-not-found",
            context={"kind": "charPr", "id": str(field_char_pr_id_ref)},
            suggestion="Make the shape with doc.styles.ensure_run(...) and pass its id.",
        )
    return surrounding, str(found.get("id"))


def set_hyperlink_target(field_begin: Any, url: str) -> None:
    """Point the HYPERLINK ``fieldBegin`` at *url*: its parameters are written anew in
    Hancom's form (:func:`hyperlink_parameters`), and an ``@name`` holding the old target
    (what python-hwpx wrote before) follows."""

    old = hyperlink_target(field_begin)
    namespace = field_begin.tag.rsplit("}", 1)[0] + "}" if "}" in field_begin.tag else ""
    holder = next((child for child in field_begin if _local(child.tag) == "parameters"), None)
    if holder is None:
        holder = field_begin.makeelement(f"{namespace}parameters", {"cnt": "0", "name": ""})
        field_begin.insert(0, holder)
    for child in list(holder):
        holder.remove(child)
    params = hyperlink_parameters(url)
    for kind, name, text in params:
        param = holder.makeelement(f"{namespace}{kind}", {"name": name})
        param.text = text
        holder.append(param)
    holder.set("cnt", str(len(params)))
    if field_begin.get("name") and field_begin.get("name") == old:
        field_begin.set("name", url)


def _runs(paragraph: Any) -> list[Any]:
    return [child for child in paragraph if _local(child.tag) == "run"]


def field_end_in_paragraph(paragraph: Any, field_begin: Any) -> Any:
    """The ``fieldEnd`` closing *field_begin* later in the same paragraph, or ``None``.

    An end names its begin by ``beginIDRef``; an end naming none closes the first
    open begin of the same ``fieldid``."""

    begin_id = field_begin.get("id")
    seen = False
    for run in _runs(paragraph):
        for child in run:
            if child is _ctrl_of(field_begin):
                seen = True
                continue
            if not seen or _local(child.tag) != "ctrl":
                continue
            for mark in child:
                if _local(mark.tag) != "fieldEnd":
                    continue
                if mark.get("beginIDRef"):
                    if mark.get("beginIDRef") == begin_id:
                        return mark
                elif mark.get("fieldid") == field_begin.get("fieldid"):
                    return mark
    return None


def _ctrl_of(mark: Any) -> Any:
    getparent = getattr(mark, "getparent", None)
    return getparent() if getparent is not None else None


def between_marks(paragraph: Any, begin: Any, end: Any) -> list[tuple[Any, Any]]:
    """``(run, child)`` for every run child between the controls holding *begin* and
    *end* in *paragraph*, in order."""

    begin_ctrl, end_ctrl = _ctrl_of(begin), _ctrl_of(end)
    inside: list[tuple[Any, Any]] = []
    started = False
    for run in _runs(paragraph):
        for child in run:
            if child is begin_ctrl:
                started = True
                continue
            if child is end_ctrl:
                return inside
            if started:
                inside.append((run, child))
    return inside


def remove_mark(mark: Any) -> Any:
    """Take a field mark (``fieldBegin``/``fieldEnd``/``bookmark``) out: the mark, the
    ``hp:ctrl`` it leaves empty and the run left empty by that while its paragraph keeps
    another run. Returns the paragraph it was in (``None`` when it was not in one)."""

    holder = _ctrl_of(mark)
    if holder is None:
        return None
    holder.remove(mark)
    run = holder
    if _local(holder.tag) == "ctrl":
        if len(holder):
            return _paragraph_of(holder)
        run = holder.getparent()
        if run is None:
            return None
        run.remove(holder)
    paragraph = run.getparent() if _local(run.tag) == "run" else None
    if paragraph is not None and not len(run) and len(_runs(paragraph)) > 1:
        paragraph.remove(run)
    return paragraph


def _paragraph_of(element: Any) -> Any:
    node = element.getparent()
    while node is not None and _local(node.tag) != "p":
        node = node.getparent()
    return node


__all__ = [
    "HYPERLINK_FIELD_ID",
    "between_marks",
    "field_end_in_paragraph",
    "hyperlink_char_pr",
    "hyperlink_parameters",
    "hyperlink_target",
    "remove_mark",
    "set_hyperlink_target",
]
