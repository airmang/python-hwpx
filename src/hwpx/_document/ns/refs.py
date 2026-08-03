# SPDX-License-Identifier: Apache-2.0
"""`doc.refs` — 책갈피·하이퍼링크. Q3/Q4의 목차·상호참조가 들어올 자리.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`add_bookmark`·`add_hyperlink`)은
WP-B3이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class RefsNamespace(_Namespace):
    """책갈피·하이퍼링크. Q3/Q4의 목차·상호참조가 들어올 자리."""

    __slots__ = ()
    _path = "doc.refs"
