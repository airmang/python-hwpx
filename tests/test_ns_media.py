# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.media`.

`picture` 능력 영역은 두 쪽으로 갈린다. 그림 개체를 **놓는** 것은 루트
(`doc.add_picture`), 패키지의 **이진 항목을 관리**하는 것이 여기다.
"""

from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


def test_add_image_registers_a_manifest_item(document: HwpxDocument) -> None:
    item = document.media.add_image(PNG, "png")
    item_id = str(item)  # 6.0: BinaryItem, str()이 매니페스트 id (이주 완충)
    assert item_id.startswith("BIN")
    # 목록의 ``id`` 는 매니페스트 순번이고, 항목 파일명이 BinData 다.
    listed = document.media.images
    assert len(listed) == 1
    assert listed[0].href.endswith(f"{item_id}.png")
    assert listed[0].format == "png"


def test_remove_image_reports_whether_it_removed_anything(document: HwpxDocument) -> None:
    item = document.media.add_image(PNG, "png")
    assert document.media.remove_image(item.item_id) is True
    assert document.media.images == ()
    assert document.media.remove_image(item.item_id) is False


def test_picture_references_are_empty_until_a_picture_is_placed(
    document: HwpxDocument,
) -> None:
    document.media.add_image(PNG, "png")
    assert document.media.picture_references() == ()

    document.add_picture(PNG, "png", section=0)
    references = document.media.picture_references()
    assert len(references) == 1


def test_replace_picture_swaps_the_underlying_item(document: HwpxDocument) -> None:
    document.add_picture(PNG, "png", section=0)
    before = document.media.picture_references()[0]
    result = document.media.replace_picture(PNG + b"x", "png")
    after = document.media.picture_references()[0]
    assert result.previous_item_id == before.binary_item_id_ref
    assert result.item_id != result.previous_item_id
    assert after.binary_item_id_ref == result.item_id
    # 기하는 보존된다 — 같은 자리에 다른 이미지가 들어갈 뿐이다.
    assert (after.width, after.height) == (before.width, before.height)
    assert result.previous_item_id in result.removed_orphans


def test_the_binary_axis_is_separate_from_the_object_axis(document: HwpxDocument) -> None:
    """개체를 지워도 이진 항목은 남는다 — 그래서 축이 둘이다."""

    document.add_picture(PNG, "png", section=0)
    assert len(document.media.images) == 1
    document.paragraphs[-1].remove()
    assert document.media.picture_references() == ()
    assert len(document.media.images) == 1


def test_the_return_contract_is_domain_objects(document: HwpxDocument) -> None:
    """WP-C 조인 완료 — 5.x 의 str/list[dict] 가 도메인 객체가 됐다."""

    from hwpx.objects import BinaryItem, PictureRef

    item = document.media.add_image(PNG, "png")
    assert isinstance(item, BinaryItem)
    assert (item.item_id, item.format, item.size) == ("BIN0001", "png", len(PNG))
    assert item.href.endswith("BIN0001.png")
    # 이주 완충: f-string·경로 조립이 5.x 처럼 계속 동작한다.
    assert f"{item}" == item.item_id

    assert isinstance(document.media.images, tuple)
    assert all(isinstance(entry, BinaryItem) for entry in document.media.images)

    document.add_picture(PNG, "png", section=0)
    references = document.media.picture_references()
    assert isinstance(references, tuple)
    assert all(isinstance(entry, PictureRef) for entry in references)
