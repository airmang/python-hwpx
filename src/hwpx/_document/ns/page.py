# SPDX-License-Identifier: Apache-2.0
"""`doc.page` — 쪽 기하 — 용지·여백·단·머리말/꼬리말·쪽번호.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`setup`·`set_size`·`set_margins`·`set_columns`·`set_header`·`set_footer`·`set_page_number`·`remove_header`·`remove_footer`)은
WP-B2이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class PageNamespace(_Namespace):
    """쪽 기하 — 용지·여백·단·머리말/꼬리말·쪽번호."""

    __slots__ = ()
    _path = "doc.page"
