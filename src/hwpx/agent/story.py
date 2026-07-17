# SPDX-License-Identifier: Apache-2.0
"""Private, contract-neutral bindings for existing non-body stories.

The public semantic path grammar intentionally remains frozen at the Feature
024 catalog.  This module recognizes one narrower command-only seam: an
existing section header selected by its native id or page type.  It does not
project headers into the public view, accept package paths, or expose XML.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .model import AgentContractError
from .path import MAX_PATH_CHARS

HEADER_STORY_KIND = "header"
HEADER_STORY_EDITABLE_PROPERTIES = frozenset({"text"})
HEADER_PAGE_TYPES = frozenset({"BOTH", "EVEN", "ODD"})

_HEADER_STORY_RE = re.compile(
    r"^/section\[(?P<section>0*[1-9][0-9]*)\]/header\["
    r"@(?P<attribute>id|page-type)=(?P<value>\"(?:[^\"\\]|\\.)*\")\]$"
)


@dataclass(frozen=True, slots=True)
class HeaderStoryPath:
    """Parsed command-only path for one existing section header."""

    section_index: int
    attribute: str
    value: str

    @property
    def kind(self) -> str:
        return HEADER_STORY_KIND

    @property
    def canonical(self) -> str:
        value = json.dumps(self.value, ensure_ascii=False, separators=(",", ":"))
        return (
            f"/section[{self.section_index}]/"
            f"header[@{self.attribute}={value}]"
        )

    @property
    def parent_path(self) -> str:
        return f"/section[{self.section_index}]"


@dataclass(frozen=True, slots=True)
class HeaderStoryBinding:
    """Request-local native binding for an existing logical header."""

    path: str
    parent_path: str
    stable_id: str
    native_id: str
    page_type: str
    section_index: int
    native: Any
    text: str

    @property
    def kind(self) -> str:
        return HEADER_STORY_KIND

    @property
    def binding_key(self) -> str:
        # Native ids are not promised to be document-global.  Section scope is
        # part of the logical binding even though the receipt exposes the same
        # kind:id stable-id convention used by projected semantic nodes.
        return f"{self.section_index}:{self.native_id}"


def try_parse_header_story_path(value: object) -> HeaderStoryPath | None:
    """Return a private header path, or ``None`` for the public path parser.

    Only exact supported forms are intercepted.  Unsupported forms such as
    ``header[1]`` deliberately continue through :func:`parse_path` and retain
    the frozen ``unknown_kind`` behavior.
    """

    if not isinstance(value, str) or "/header[@" not in value:
        return None
    if len(value) > MAX_PATH_CHARS:
        raise AgentContractError("resource_limit", "path is too long", target="path")
    match = _HEADER_STORY_RE.fullmatch(value)
    if match is None:
        return None
    try:
        decoded = json.loads(match.group("value"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentContractError(
            "invalid_syntax", "invalid header story path string", target="path"
        ) from exc
    if not isinstance(decoded, str) or not decoded or len(decoded) > 256:
        raise AgentContractError(
            "resource_limit", "header story selector is invalid", target="path"
        )
    attribute = match.group("attribute")
    if attribute == "page-type" and decoded not in HEADER_PAGE_TYPES:
        raise AgentContractError(
            "invalid_syntax",
            "header page type must be BOTH, EVEN, or ODD",
            target="path",
        )
    return HeaderStoryPath(
        section_index=int(match.group("section")),
        attribute=attribute,
        value=decoded,
    )


def parse_header_story_path(value: str) -> HeaderStoryPath:
    """Parse an exact private header path for focused internal tests."""

    parsed = try_parse_header_story_path(value)
    if parsed is None:
        raise AgentContractError(
            "invalid_syntax", "unsupported header story path", target="path"
        )
    return parsed


def resolve_header_story(document: Any, path: HeaderStoryPath) -> HeaderStoryBinding:
    """Resolve one unique direct logical header without scanning descendants."""

    try:
        sections = document.sections
    except (AttributeError, TypeError, ValueError) as exc:
        raise AgentContractError(
            "unsupported_content", "document section structure is unavailable", target=path.canonical
        ) from exc
    if path.section_index > len(sections):
        raise AgentContractError(
            "not_found", "header story section does not exist", target=path.canonical
        )
    section = sections[path.section_index - 1]
    try:
        headers = tuple(section.properties.headers)
        if path.attribute == "id":
            matches = [header for header in headers if header.id == path.value]
        else:
            matches = [
                header for header in headers if header.apply_page_type == path.value
            ]
    except (AttributeError, TypeError, ValueError) as exc:
        raise AgentContractError(
            "unsupported_content", "section header structure is invalid", target=path.canonical
        ) from exc

    if not matches:
        raise AgentContractError(
            "not_found", f"existing header story not found: {path.canonical}", target=path.canonical
        )
    if len(matches) > 1:
        raise AgentContractError(
            "ambiguous_target",
            f"header story selector is not unique: {path.canonical}",
            target=path.canonical,
        )

    header = matches[0]
    try:
        native_id = header.id
        page_type = header.apply_page_type
        text = header.text
    except (AttributeError, TypeError, ValueError) as exc:
        raise AgentContractError(
            "unsupported_content", "header story cannot be read safely", target=path.canonical
        ) from exc
    if not native_id or len(native_id) > 256:
        raise AgentContractError(
            "unsupported_content", "header story has no bounded native identity", target=path.canonical
        )
    if page_type not in HEADER_PAGE_TYPES:
        raise AgentContractError(
            "unsupported_content", "header story has an unsupported page type", target=path.canonical
        )

    return HeaderStoryBinding(
        path=path.canonical,
        parent_path=path.parent_path,
        stable_id=f"header:{native_id}",
        native_id=native_id,
        page_type=page_type,
        section_index=path.section_index,
        native=header,
        text=text,
    )


__all__ = [
    "HEADER_PAGE_TYPES",
    "HEADER_STORY_EDITABLE_PROPERTIES",
    "HEADER_STORY_KIND",
    "HeaderStoryBinding",
    "HeaderStoryPath",
    "parse_header_story_path",
    "resolve_header_story",
    "try_parse_header_story_path",
]
