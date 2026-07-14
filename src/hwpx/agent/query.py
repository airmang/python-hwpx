# SPDX-License-Identifier: Apache-2.0
"""Bounded selector v1 parser and in-memory semantic-tree evaluator."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .model import (
    MAX_QUERY_RESULTS,
    MAX_SELECTOR_CHARS,
    AgentContractError,
    AgentNode,
    SELECTOR_ATTRIBUTES,
    SELECTOR_KINDS,
)

MAX_SELECTOR_STEPS = 8
MAX_SELECTOR_FILTERS = 4
_KIND_RE = re.compile(r"[a-z][a-z-]*")
_ATTR_RE = re.compile(r"\[([a-z]+)=(\"(?:[^\"\\]|\\.)*\"|[^\]\s]+)\]")
_CONTAINS_RE = re.compile(r":contains\((\"(?:[^\"\\]|\\.)*\")\)")


class QueryRecord(Protocol):
    kind: str
    path: str
    parent_path: str | None
    attributes: Mapping[str, str]
    search_text: str


@dataclass(frozen=True, slots=True)
class SelectorStep:
    kind: str
    attributes: tuple[tuple[str, str], ...] = ()
    contains: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticSelector:
    steps: tuple[SelectorStep, ...]


@dataclass(frozen=True, slots=True)
class QueryResult:
    selector: str
    revision: str
    nodes: tuple[AgentNode, ...]
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": "hwpx.agent-query-result/v1",
            "selector": self.selector,
            "revision": self.revision,
            "count": len(self.nodes),
            "truncated": self.truncated,
            "nodes": [node.to_dict() for node in self.nodes],
        }


def normalize_search_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def _split_steps(selector: str) -> list[str]:
    result: list[str] = []
    start = 0
    quoted = False
    escaped = False
    bracket_depth = 0
    paren_depth = 0
    for index, char in enumerate(selector):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == ">" and bracket_depth == 0 and paren_depth == 0:
            result.append(selector[start:index].strip())
            start = index + 1
        if bracket_depth < 0 or paren_depth < 0:
            raise AgentContractError("invalid_syntax", "unbalanced selector", target="selector")
    if quoted or bracket_depth or paren_depth:
        raise AgentContractError("invalid_syntax", "unbalanced selector", target="selector")
    result.append(selector[start:].strip())
    if any(not step for step in result):
        raise AgentContractError("invalid_syntax", "empty selector step", target="selector")
    return result


def _decode_literal(value: str) -> str:
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except (ValueError, json.JSONDecodeError) as exc:
            raise AgentContractError("invalid_syntax", "invalid selector string", target="selector") from exc
    else:
        decoded = value
    if not isinstance(decoded, str) or not decoded or len(decoded) > 256:
        raise AgentContractError("resource_limit", "selector value is invalid", target="selector")
    return decoded


def _parse_step(raw: str) -> SelectorStep:
    kind_match = _KIND_RE.match(raw)
    if kind_match is None:
        raise AgentContractError("invalid_syntax", "selector step requires a kind", target="selector")
    kind = kind_match.group(0)
    if kind not in SELECTOR_KINDS:
        raise AgentContractError("unknown_kind", f"unknown selector kind: {kind}", target="selector")
    cursor = kind_match.end()
    attributes: list[tuple[str, str]] = []
    contains: str | None = None
    while cursor < len(raw):
        attr_match = _ATTR_RE.match(raw, cursor)
        if attr_match is not None:
            name = attr_match.group(1)
            if name not in SELECTOR_ATTRIBUTES:
                raise AgentContractError(
                    "unknown_property", f"unsupported selector attribute: {name}", target="selector"
                )
            if any(existing == name for existing, _ in attributes):
                raise AgentContractError("invalid_syntax", "duplicate selector attribute", target="selector")
            attributes.append((name, _decode_literal(attr_match.group(2))))
            if len(attributes) > MAX_SELECTOR_FILTERS:
                raise AgentContractError("resource_limit", "too many selector filters", target="selector")
            cursor = attr_match.end()
            continue
        contains_match = _CONTAINS_RE.match(raw, cursor)
        if contains_match is not None and contains is None:
            contains = _decode_literal(contains_match.group(1))
            cursor = contains_match.end()
            continue
        raise AgentContractError(
            "invalid_syntax", f"invalid selector near {raw[cursor:]!r}", target="selector"
        )
    return SelectorStep(kind=kind, attributes=tuple(attributes), contains=contains)


def parse_selector(value: str) -> SemanticSelector:
    if not isinstance(value, str) or not value.strip():
        raise AgentContractError("invalid_syntax", "selector must be non-empty", target="selector")
    if len(value) > MAX_SELECTOR_CHARS:
        raise AgentContractError("resource_limit", "selector is too long", target="selector")
    raw_steps = _split_steps(value.strip())
    if len(raw_steps) > MAX_SELECTOR_STEPS:
        raise AgentContractError("resource_limit", "selector nesting exceeds limit", target="selector")
    return SemanticSelector(tuple(_parse_step(step) for step in raw_steps))


def _matches(record: QueryRecord, step: SelectorStep) -> bool:
    if record.kind != step.kind:
        return False
    for name, expected in step.attributes:
        actual = record.attributes.get(name)
        if actual is None or normalize_search_text(actual) != normalize_search_text(expected):
            return False
    if (
        step.contains is not None
        and normalize_search_text(step.contains) not in normalize_search_text(record.search_text)
    ):
        return False
    return True


def evaluate_selector(
    records: Sequence[QueryRecord] | Iterable[QueryRecord],
    selector: SemanticSelector,
    *,
    limit: int,
) -> tuple[list[QueryRecord], bool]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_QUERY_RESULTS:
        raise AgentContractError(
            "resource_limit", f"query limit must be 1..{MAX_QUERY_RESULTS}", target="limit"
        )
    ordered = list(records)
    by_path = {record.path: record for record in ordered}
    matches: list[QueryRecord] = []
    for record in ordered:
        if not _matches(record, selector.steps[-1]):
            continue
        cursor = record
        valid = True
        for step in reversed(selector.steps[:-1]):
            if cursor.parent_path is None:
                valid = False
                break
            parent = by_path.get(cursor.parent_path)
            if parent is None or not _matches(parent, step):
                valid = False
                break
            cursor = parent
        if valid:
            if len(matches) == limit:
                return matches, True
            matches.append(record)
    return matches, False


__all__ = [
    "MAX_SELECTOR_FILTERS",
    "MAX_SELECTOR_STEPS",
    "QueryRecord",
    "QueryResult",
    "SelectorStep",
    "SemanticSelector",
    "evaluate_selector",
    "normalize_search_text",
    "parse_selector",
]
