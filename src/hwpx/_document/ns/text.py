# SPDX-License-Identifier: Apache-2.0
"""`doc.text` — 텍스트 순회·검색·치환·내보내기.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`plain`·`markdown`·`html`·`runs`·`find_runs`·`replace`)은
WP-B1이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class TextNamespace(_Namespace):
    """텍스트 순회·검색·치환·내보내기."""

    __slots__ = ()
    _path = "doc.text"
