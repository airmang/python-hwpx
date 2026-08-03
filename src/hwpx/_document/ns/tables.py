# SPDX-License-Identifier: Apache-2.0
"""`doc.tables` — 표 탐색·매핑·병합·경로 채움.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`map`·`fill_by_path`·`find_cell_by_label`·`merge_cells`)은
WP-B2이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class TablesNamespace(_Namespace):
    """표 탐색·매핑·병합·경로 채움."""

    __slots__ = ()
    _path = "doc.tables"
