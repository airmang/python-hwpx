# SPDX-License-Identifier: Apache-2.0
"""`doc.media` — BinData 이진 항목과 그림 참조 관리.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`add_image`·`images`·`remove_image`·`replace_picture`·`picture_references`)은
WP-B3이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class MediaNamespace(_Namespace):
    """BinData 이진 항목과 그림 참조 관리."""

    __slots__ = ()
    _path = "doc.media"
