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
        ({"section_index": 0}, "hwpx-argument-removed"),
    ],
    ids=["out-of-range", "wrong-type", "removed-section-index"],
)
def test_bad_sections_are_typed_errors(name, args, kwargs, code, document) -> None:
    with pytest.raises(HwpxError) as excinfo:
        getattr(document.refs, name)(*args, **kwargs)
    assert excinfo.value.code == code


def test_toc_and_cross_reference_live_in_doc_refs() -> None:
    """경계 근거: 능력 레지스트리가 TOC/상호참조와 하이퍼링크/책갈피를 같은
    네임스페이스(doc.refs) 밑에 두되, 서로 다른 캐파빌리티 영역으로 분리해
    등록해 뒀다 (6.8 트레인㉚ -- 하이퍼링크/책갈피는 toc-crossref 영역에
    같이 있었으나, 그 영역의 실한컴 검증 근거는 TOC 얘기뿐이라 독립 영역
    hyperlink-bookmark로 분리했다). 7.0에서 차례·상호참조도 doc.refs에서 읽고 만든다."""

    from hwpx.capabilities import _CAPABILITY_AREAS

    toc_area = next(row for row in _CAPABILITY_AREAS if row["area"] == "toc-crossref")
    assert toc_area["authoring_methods"] == ()
    assert toc_area["entry_points"] == ("hwpx.tools.toc_author:add_native_toc",)
    # 레지스트리는 실제 자리를 적는다(ENG-33): 7.0부터 doc.refs.
    assert toc_area["namespace"] == "doc.refs"
    refs = HwpxDocument.new().refs
    for name in ("tables_of_contents", "add_table_of_contents", "cross_references", "add_cross_reference"):
        assert hasattr(refs, name)
    assert not hasattr(refs, "add_native_toc")

    link_area = next(row for row in _CAPABILITY_AREAS if row["area"] == "hyperlink-bookmark")
    # 7.0: the root add_bookmark/add_hyperlink are gone; the area lives in doc.refs only.
    assert link_area["authoring_methods"] == ()
    assert link_area["namespace"] == "doc.refs"


def test_the_removed_root_names_point_at_doc_refs(document: HwpxDocument) -> None:
    """7.0: 6.x 가 경고와 함께 남겨 둔 루트 이름은 없어졌고, 부르면 새 자리를 말한다."""

    from hwpx.errors import HwpxAttributeError

    for name, target in [
        ("add_bookmark", "doc.refs.add_bookmark"),
        ("add_hyperlink", "doc.refs.add_hyperlink"),
    ]:
        with pytest.raises(HwpxAttributeError) as excinfo:
            getattr(document, name)
        assert target in str(excinfo.value)
