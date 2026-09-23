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

import re
from typing import Any

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


__all__ = ["HYPERLINK_FIELD_ID", "hyperlink_parameters", "hyperlink_target"]
