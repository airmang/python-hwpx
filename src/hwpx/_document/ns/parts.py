# SPDX-License-Identifier: Apache-2.0
"""`doc.parts` — OPC 파트 접근 — header.xml·바탕쪽·이력·버전.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`headers`·`master_pages`·`histories`·`version`)은
WP-B1이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class PartsNamespace(_Namespace):
    """OPC 파트 접근 — header.xml·바탕쪽·이력·버전."""

    __slots__ = ()
    _path = "doc.parts"
