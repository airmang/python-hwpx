# SPDX-License-Identifier: Apache-2.0
"""`doc.fields` — 누름틀·체크박스 양식개체.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`add`·`all`·`fill`·`add_check_box`·`check_boxes`·`check_box`)은
WP-B2이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class FieldsNamespace(_Namespace):
    """누름틀·체크박스 양식개체."""

    __slots__ = ()
    _path = "doc.fields"
