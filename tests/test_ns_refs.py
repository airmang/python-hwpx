# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.refs`."""

from __future__ import annotations

import pytest

from hwpx import model
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


def test_add_bookmark_lands_on_the_paragraph(document: HwpxDocument) -> None:
    created = document.refs.add_bookmark("앵커", section=0)
    assert isinstance(created, model.InlineObject)
    assert "앵커" in document.paragraphs[-1].bookmarks


def test_add_hyperlink_keeps_its_display_text(document: HwpxDocument) -> None:
    created = document.refs.add_hyperlink("https://example.invalid", "링크", section=0)
    assert isinstance(created, model.InlineObject)
    assert "링크" in document.text.plain()


@pytest.mark.parametrize(
    "name,args",
    [("add_bookmark", ("앵커",)), ("add_hyperlink", ("https://example.invalid", "링크"))],
)
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_bad_sections_are_typed_errors(name, args, kwargs, code, document) -> None:
    with pytest.raises(HwpxError) as excinfo:
        getattr(document.refs, name)(*args, **kwargs)
    assert excinfo.value.code == code


def test_this_is_where_toc_and_cross_reference_will_live() -> None:
    """경계 근거: 능력 레지스트리가 TOC/상호참조와 하이퍼링크/책갈피를 같은
    네임스페이스(doc.refs) 밑에 두되, 서로 다른 캐파빌리티 영역으로 분리해
    등록해 뒀다 (6.8 트레인㉚ -- 하이퍼링크/책갈피는 toc-crossref 영역에
    같이 있었으나, 그 영역의 실한컴 검증 근거는 TOC 얘기뿐이라 독립 영역
    hyperlink-bookmark로 분리했다. 네임스페이스 경계 자체는 안 바뀐다)."""

    from hwpx.capabilities import _CAPABILITY_AREAS

    toc_area = next(row for row in _CAPABILITY_AREAS if row["area"] == "toc-crossref")
    assert toc_area["authoring_methods"] == ()
    assert toc_area["entry_points"] == ("hwpx.tools.toc_author:add_native_toc",)
    assert toc_area["namespace"] == "doc.refs"

    link_area = next(row for row in _CAPABILITY_AREAS if row["area"] == "hyperlink-bookmark")
    assert set(link_area["authoring_methods"]) == {"add_bookmark", "add_hyperlink"}
    assert link_area["namespace"] == "doc.refs"


def test_the_moved_root_names_still_answer(document: HwpxDocument) -> None:
    with pytest.warns(DeprecationWarning):
        document.add_bookmark("앵커", section_index=0)
    with pytest.warns(DeprecationWarning):
        document.add_hyperlink("https://example.invalid", "링크", section_index=0)
