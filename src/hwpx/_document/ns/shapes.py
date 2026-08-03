# SPDX-License-Identifier: Apache-2.0
"""`doc.shapes` — 도형·차트·수식 등 인라인 개체 저작.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`add_line`·`add_rectangle`·`add_ellipse`·`add_chart`·`add_equation`·`add_raw`·`add_control`)은
WP-B3이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class ShapesNamespace(_Namespace):
    """도형·차트·수식 등 인라인 개체 저작."""

    __slots__ = ()
    _path = "doc.shapes"
