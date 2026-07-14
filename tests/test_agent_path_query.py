from __future__ import annotations

from dataclasses import dataclass

import pytest

from hwpx.agent.model import AgentContractError
from hwpx.agent.path import MAX_PATH_CHARS, canonicalize_path, parse_path
from hwpx.agent.query import evaluate_selector, normalize_search_text, parse_selector


@dataclass(frozen=True)
class Record:
    kind: str
    path: str
    parent_path: str | None
    attributes: dict[str, str]
    search_text: str


def test_path_round_trip_and_one_based_canonicalization() -> None:
    source = '/section[01]/paragraph[@id="문단\\\"1"]/run[0002]'
    canonical = '/section[1]/paragraph[@id="문단\\\"1"]/run[2]'

    assert parse_path(source).canonical == canonical
    assert canonicalize_path(canonical) == canonical
    assert parse_path("/").canonical == "/"
    assert canonicalize_path('/section[1]/form-field[@name="성명/이름"]') == (
        '/section[1]/form-field[@name="성명/이름"]'
    )


@pytest.mark.parametrize(
    "value",
    [
        "section[1]",
        "/section[0]",
        "/section[-1]",
        "/section[*]",
        "/section[1]//paragraph[1]",
        "/section[1]/../paragraph[1]",
        '/section[@style="x"]',
        "/unknown[1]",
        "/section[1]/",
    ],
)
def test_malformed_paths_fail_without_xpath_features(value: str) -> None:
    with pytest.raises(AgentContractError):
        parse_path(value)


def test_path_resource_limit_is_bounded() -> None:
    with pytest.raises(AgentContractError) as error:
        parse_path("/" + "x" * MAX_PATH_CHARS)
    assert error.value.code == "resource_limit"


def test_selector_parse_and_direct_child_evaluation() -> None:
    records = [
        Record("document", "/", None, {"type": "document"}, ""),
        Record("section", "/section[1]", "/", {"type": "section"}, ""),
        Record(
            "paragraph",
            '/section[1]/paragraph[@id="1"]',
            "/section[1]",
            {"id": "1", "style": "개요 1", "type": "PARA"},
            "  수행   평가  ",
        ),
        Record(
            "paragraph",
            '/section[1]/paragraph[@id="2"]',
            "/section[1]",
            {"id": "2", "style": "바탕글", "type": "PARA"},
            "다른 문단",
        ),
    ]
    selector = parse_selector('section > paragraph[style="개요 1"]:contains("수행 평가")')

    matches, truncated = evaluate_selector(records, selector, limit=10)

    assert [record.attributes["id"] for record in matches] == ["1"]
    assert truncated is False
    assert normalize_search_text("Ａ  B") == "a b"


def test_selector_order_and_truncation_are_deterministic() -> None:
    records = [
        Record("paragraph", f"/section[1]/paragraph[{index}]", "/section[1]", {}, "평가")
        for index in range(1, 5)
    ]

    matches, truncated = evaluate_selector(records, parse_selector('paragraph:contains("평가")'), limit=2)

    assert [record.path for record in matches] == [
        "/section[1]/paragraph[1]",
        "/section[1]/paragraph[2]",
    ]
    assert truncated is True


@pytest.mark.parametrize(
    "selector",
    [
        "",
        "*",
        "paragraph//run",
        "paragraph > > run",
        "paragraph[xml=x]",
        "paragraph:contains(x)",
        "paragraph:matches(\"x\")",
        "paragraph[id=1][id=2]",
        "unknown",
    ],
)
def test_malformed_selectors_fail_closed(selector: str) -> None:
    with pytest.raises(AgentContractError):
        parse_selector(selector)


def test_selector_fuzz_has_only_structured_failures() -> None:
    alphabet = "abc[]()@=/:>*.'\\\"012가"
    for size in range(1, 40):
        candidate = "".join(alphabet[(size * 7 + index * 11) % len(alphabet)] for index in range(size))
        try:
            parsed = parse_selector(candidate)
        except AgentContractError:
            continue
        assert 1 <= len(parsed.steps) <= 8
