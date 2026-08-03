# SPDX-License-Identifier: Apache-2.0
"""`doc.media` — BinData 이진 항목과 그림 참조 관리.

능력 레지스트리의 `picture` 영역은 두 쪽으로 갈린다. **그림 개체를 문단에
놓는 것**(`doc.add_picture`)은 python-docx 대응이라 루트에 남았고, **패키지가
품은 이진 항목을 관리하는 것**이 여기다 — 등록·목록·제거·치환·역참조.

둘이 다른 축인 이유: 하나는 본문 흐름의 개체이고, 하나는 OPC 패키지의 자산이다.
같은 그림을 두 문단이 참조할 수 있고, 개체를 지워도 항목은 남는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import _Namespace

if TYPE_CHECKING:
    from ...objects import BinaryItem, PictureRef, PictureReplacement

__all__ = ["MediaNamespace"]


class MediaNamespace(_Namespace):
    """BinData 이진 항목과 그림 참조 관리."""

    __slots__ = ()
    _path = "doc.media"

    def add_image(
        self, image_data: bytes, image_format: str, *, item_id: str | None = None
    ) -> "BinaryItem":
        """이미지를 패키지에 넣고 그 이진 항목을 돌려준다.

        5.x 는 매니페스트 id 문자열을 돌려줬다. ``str(item)`` 이 여전히 그
        id 라 f-string·경로 조립은 그대로 동작한다(이주 완충).
        """

        from .. import media as _media

        return _media.add_image(
            self._doc,
            image_data=image_data,
            image_format=image_format,
            item_id=item_id,
        )

    @property
    def images(self) -> "tuple[BinaryItem, ...]":
        """패키지가 품은 이진 이미지 항목 목록."""

        from .. import media as _media

        return _media.list_images(self._doc)

    def remove_image(self, item_id: str) -> bool:
        """이진 항목을 제거한다. 없으면 ``False``."""

        from .. import media as _media

        return _media.remove_image(self._doc, item_id=item_id)

    def picture_references(self) -> "tuple[PictureRef, ...]":
        """본문의 그림 개체가 어떤 이진 항목을 가리키는지의 역참조 표."""

        from .. import media as _media

        return _media.picture_references(self._doc)

    def replace_picture(
        self,
        image_data: bytes,
        image_format: str,
        *,
        picture_index: int = 0,
        binary_item_id_ref: str | None = None,
        remove_orphaned: bool = True,
        item_id: str | None = None,
    ) -> "PictureReplacement":
        """그림 개체가 가리키는 이진 항목을 새 이미지로 바꾼다."""

        from .. import media as _media

        return _media.replace_picture(
            self._doc,
            image_data=image_data,
            image_format=image_format,
            picture_index=picture_index,
            binary_item_id_ref=binary_item_id_ref,
            remove_orphaned=remove_orphaned,
            item_id=item_id,
        )
