# SPDX-License-Identifier: Apache-2.0
"""`doc.styles` — 서식 정의(스타일·문단모양·글자모양·테두리·글머리표).

WP-A는 이 네임스페이스의 **호환 골격**만 만든다. 5.x의 `doc.styles`는
`dict[str, Style]`을 반환하는 속성이었고, 그 이름을 네임스페이스가 물려받는다.
그래서 이 클래스는 `Mapping[str, Style]`이다 — `doc.styles["0"]`,
`doc.styles.items()`, `if doc.styles:` 가 5.x와 똑같이 동작한다.

이건 호환을 위한 편법이 아니라 이 축의 올바른 모양이다. `python-docx`의
`document.styles`도 정확히 이 형태(이름/키로 조회되는 컬렉션 객체)다.
그래서 `styles`는 shim 목록에 없다 — 이름이 옮겨간 게 아니라 **같은 이름의
의미가 넓어졌다**.

`ensure_run`·`apply_paragraph_format`·`resolve`(이름 해석) 등 나머지 메서드는
WP-B1이 채운다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Mapping

from ._base import _Namespace

if TYPE_CHECKING:
    from ...oxml import Style


class StylesNamespace(_Namespace, Mapping[str, "Style"]):
    """스타일 정의 컬렉션. 키는 스타일 id 문자열."""

    __slots__ = ()
    _path = "doc.styles"

    # -- Mapping 프로토콜: 5.x `doc.styles` (dict) 계약 보존 ----------------

    def __getitem__(self, key: str) -> "Style":
        return self._doc.oxml.styles[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._doc.oxml.styles)

    def __len__(self) -> int:
        return len(self._doc.oxml.styles)

    def __repr__(self) -> str:
        return f"<StylesNamespace {self._path} ({len(self)} styles)>"
