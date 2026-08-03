# SPDX-License-Identifier: Apache-2.0
"""`doc.notes` — 각주·미주·메모 — 본문 흐름 밖 주석.

WP-A는 클래스 정의와 문서 결합만 만든다. 메서드 본문(`add_footnote`·`add_endnote`·`add_memo`·`attach`·`remove_memo`·`memos`)은
WP-B3이 채운다 — 설계서 §9의 배타적 파일 소유 규칙.
"""

from __future__ import annotations

from ._base import _Namespace


class NotesNamespace(_Namespace):
    """각주·미주·메모 — 본문 흐름 밖 주석."""

    __slots__ = ()
    _path = "doc.notes"
