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


__all__ = ["HYPERLINK_FIELD_ID", "hyperlink_char_pr", "hyperlink_parameters", "hyperlink_target"]
