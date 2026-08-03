# SPDX-License-Identifier: Apache-2.0
"""`doc.tracking` — 변경추적(redline) 저작과 조회.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`insert`·`delete`·`replace`·`add_change`·`changes`·`change`·`authors`·`author`)은
WP-B3이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class TrackingNamespace(_Namespace):
    """변경추적(redline) 저작과 조회."""

    __slots__ = ()
    _path = "doc.tracking"
