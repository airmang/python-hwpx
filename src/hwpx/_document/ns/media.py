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
        """패키지가 품은 이진 이미지 항목 목록.

        header의 ``binDataList``에 있는 항목이 먼저 오고, ``content.hpf``
        매니페스트에만 있는 이진 항목(href가 ``BinData/`` 아래이거나
        media-type이 ``image/*``)이 매니페스트 순서로 뒤따른다. 한컴이
        저장한 파일은 보통 ``binDataList``가 없어 뒤쪽만 나온다.
        ``isEmbeded="0"``이고 href가 ``BinData/`` 밖이라 바깥 파일을 잇는
        항목은 넣지 않는다. 한/글은 OLE에도 ``isEmbeded="0"``을 쓰지만 그
        파일은 ``BinData/``에 두므로 OLE 항목은 넣는다. 파트가 없는 내장
        항목은 ``size=0``으로 나온다."""

        from .. import media as _media

        return _media.list_images(self._doc)

    def remove_image(self, item_id: "str | BinaryItem", *, force: bool = False) -> bool:
        """이진 항목을 제거한다. 없으면 ``False``.

        매니페스트 id(``"image1"``), 파트 경로(``"BinData/image1.png"``),
        ``images``가 돌려준 ``BinaryItem`` 가운데 무엇이든 받는다.
        매니페스트 항목·파트·header의 ``binItem``(있으면)을 함께 지운다.
        구역·header처럼 이진 항목이 아닌 매니페스트 항목은 지우지 않고
        ``False``를 돌려준다.

        문서가 아직 그 항목을 가리키면(그림, header의 채우기 그림·그림
        글머리표, 바탕쪽, 동영상 파일·포스터, OLE, 내장 글꼴) 아무것도
        바꾸지 않고 ``HwpxValueError``(``media-item-in-use``)를 낸다.
        ``context["references"]``가 가리키는 곳이다. ``force=True``면
        그래도 지우고 그 참조는 끊긴 채 남는다."""

        from .. import media as _media

        return _media.remove_image(self._doc, item_id=item_id, force=force)

    def remove_unused_images(self) -> "tuple[BinaryItem, ...]":
        """문서가 어디서도 가리키지 않는 이진 항목을 모두 지우고, 지운 항목을 돌려준다.

        한/글은 문서를 저장할 때 쓰지 않는 이진 항목을 지운다. 본문에서 그림을 지우면
        (``section.clear_body()``, 문단 삭제) 그 그림의 이진 항목은 패키지에 남는다.
        :meth:`remove_image`가 확인하는 참조(그림, 채우기 그림·그림 글머리표, 바탕쪽,
        동영상, OLE, 내장 글꼴)가 하나라도 있으면 지우지 않는다."""

        from .. import media as _media

        return _media.remove_unused_images(self._doc)

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
