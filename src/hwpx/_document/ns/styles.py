# SPDX-License-Identifier: Apache-2.0
"""`doc.styles` — 서식 정의(스타일·문단모양·글자모양·테두리·글머리표).

## 5.x `doc.styles` 와의 관계

5.x에서 이 이름은 `dict[str, Style]`을 돌려주는 속성이었다. 6.0의
:class:`StylesNamespace`는 `Mapping[str, Style]`이라 `doc.styles["0"]`,
`doc.styles.items()`, `if doc.styles:` 가 그대로 동작한다. 이름이 옮겨간 것이
아니라 **같은 이름의 의미가 넓어졌다** — `python-docx`의 `document.styles`도
같은 형태의 컬렉션 객체다. 그래서 `styles`는 shim 목록에 없다.

## 이름 해석은 새 기능이 아니라 시점 이동이다

`style_id_ref="개요 1"`은 5.x에서도 **동작했다** —
`HwpxOxmlDocument._normalize_named_style_references()`가 serialize 시점에
이름을 id로 바꿔줬기 때문이다. 문제는 그 다음이었다(5.8.0 실측):

- `style_id_ref="개요1"`(공백 누락) → 호출 시점 무반응. 저장할 때 가서야
  `HwpxPackageError: Invalid integer value: '개요1'` 로 터진다. 스타일이라는
  말도, 가용 목록도, 제안도 없다.
- `style_id_ref=9999`(숫자지만 없는 id) → **아예 조용하다.** 기본 저장 정책
  `QualityPolicy.transparent()`(`require_reference_integrity=False`)가
  dangling 참조를 통과시켜 `styleIDRef="9999"` 가 그대로 나간다.

그래서 이 모듈이 하는 일은 새 해석기를 만드는 것이 아니라 **이미 있던 해석을
호출 시점으로 당기고, 두 경우 모두 말하게 하는 것**이다. serialize 시점
정규화기는 `doc.oxml`로 직접 만든 문서를 위한 backstop 으로 남는다.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Iterator, Mapping, Sequence

from ...errors import HwpxLookupError
from ._base import _Namespace

if TYPE_CHECKING:
    from ...objects import ListFormatResult, ParagraphFormatResult
    from ...oxml import (
        Bullet,
        GenericElement,
        MemoShape,
        ParagraphProperty,
        RunStyle,
        Style,
    )

__all__ = ["StylesNamespace"]

#: 제안에 나열할 최대 후보 수. 23개를 한 줄에 늘어놓으면 읽히지 않는다.
_MAX_SUGGESTIONS = 3


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

    @property
    def all(self) -> dict[str, "Style"]:
        """5.x `doc.styles` 와 같은 dict. 이 네임스페이스 자체도 매핑이다."""

        return self._doc.oxml.styles

    # -- 이름 해석 ---------------------------------------------------------

    def names(self) -> list[str]:
        """이 문서가 정의한 스타일 이름 목록(한글 `name` 우선, 중복 제거)."""

        seen: dict[str, None] = {}
        for style in self._doc.oxml.styles.values():
            for label in ((style.name or "").strip(), (style.eng_name or "").strip()):
                if label:
                    seen.setdefault(label, None)
        return list(seen)

    def get(  # type: ignore[override]  # Mapping.get 을 id·이름 겸용으로 넓힌다
        self,
        key: "int | str | Style | None",
        default: "Style | None" = None,
    ) -> "Style | None":
        """id 또는 이름으로 스타일을 찾고, 없으면 *default* 를 돌려준다.

        `Mapping.get` 계약(예외를 내지 않는다)을 지키면서 이름 조회를 얹었다.
        실패를 말하게 하려면 :meth:`resolve` 를 쓴다.
        """

        try:
            return self.resolve(key)
        except HwpxLookupError:
            return default

    def resolve(self, spec: "int | str | Style | None") -> "Style":
        """*spec* 을 스타일 하나로 해석한다. 실패하면 typed error 로 말한다.

        해석 순서: `Style` 인스턴스 → 숫자 id → `name` 정확 일치 →
        `eng_name` 정확 일치(대소문자 무시).

        Raises:
            HwpxLookupError: ``style-not-found`` (가용 목록·가장 가까운 이름
                포함) 또는 ``style-ambiguous`` (같은 이름의 후보 나열).
        """

        if spec is None:
            raise self._not_found(spec)
        if not isinstance(spec, (int, str)):
            return spec  # 이미 Style

        styles = self._doc.oxml.styles
        if isinstance(spec, int) or spec.strip().lstrip("-").isdigit():
            wanted = str(int(str(spec).strip()))
            for style_id, style in styles.items():
                if str(style_id) == wanted or str(style.id) == wanted:
                    return style
            raise self._not_found(spec)

        wanted = spec.strip()
        aliases = self._doc.oxml.style_name_aliases()
        ids = aliases.get(wanted)
        if ids is None:
            lowered = wanted.lower()
            for alias, candidate_ids in aliases.items():
                if alias.lower() == lowered:
                    ids = candidate_ids
                    break
        if ids is None:
            raise self._not_found(spec)
        if len(ids) > 1:
            raise HwpxLookupError(
                f"스타일 이름 {wanted!r} 이(가) 모호합니다 — {len(ids)}개가 같은 이름을 씁니다.",
                code="style-ambiguous",
                context={
                    "requested": wanted,
                    "candidates": [
                        {"id": style_id, "name": self._label(styles.get(style_id))}
                        for style_id in ids
                    ],
                },
                suggestion=f"숫자 id 로 지정하세요 — 후보: {', '.join(ids)}.",
            )
        resolved = styles.get(ids[0]) if ids else None
        if resolved is None:  # pragma: no cover - 별칭 표는 같은 헤더에서 나온다
            raise self._not_found(spec)
        return resolved

    def _not_found(self, spec: object) -> HwpxLookupError:
        requested = spec if isinstance(spec, (int, str)) else repr(spec)
        available = self.names()
        closest = difflib.get_close_matches(
            str(requested), available, n=_MAX_SUGGESTIONS, cutoff=0.6
        )
        hint = (
            f"가장 가까운 이름: {', '.join(repr(name) for name in closest)}. "
            if closest
            else ""
        )
        return HwpxLookupError(
            f"스타일 {requested!r} 을(를) 찾을 수 없습니다.",
            code="style-not-found",
            context={
                "requested": requested,
                "available": available,
                "availableCount": len(available),
                "closest": closest,
            },
            suggestion=f"{hint}전체 목록: doc.styles.names()",
        )

    # -- 서식 정의 테이블 --------------------------------------------------

    @property
    def char_properties(self) -> dict[str, "RunStyle"]:
        return self._doc.oxml.char_properties

    def char_property(self, char_pr_id_ref: "int | str | None") -> "RunStyle | None":
        return self._doc.oxml.char_property(char_pr_id_ref)

    @property
    def paragraph_properties(self) -> dict[str, "ParagraphProperty"]:
        return self._doc.oxml.paragraph_properties

    def paragraph_property(
        self, para_pr_id_ref: "int | str | None"
    ) -> "ParagraphProperty | None":
        return self._doc.oxml.paragraph_property(para_pr_id_ref)

    @property
    def border_fills(self) -> dict[str, "GenericElement"]:
        return self._doc.oxml.border_fills

    def border_fill(
        self, border_fill_id_ref: "int | str | None"
    ) -> "GenericElement | None":
        return self._doc.oxml.border_fill(border_fill_id_ref)

    @property
    def bullets(self) -> dict[str, "Bullet"]:
        return self._doc.oxml.bullets

    def bullet(self, bullet_id_ref: "int | str | None") -> "Bullet | None":
        return self._doc.oxml.bullet(bullet_id_ref)

    @property
    def memo_shapes(self) -> dict[str, "MemoShape"]:
        return self._doc.oxml.memo_shapes

    def memo_shape(self, memo_shape_id_ref: "int | str | None") -> "MemoShape | None":
        return self._doc.oxml.memo_shape(memo_shape_id_ref)

    # -- 서식 id 를 mint 하는 동사 -----------------------------------------

    def ensure_run(
        self,
        *,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
        underline_shape: str | None = None,
        underline_color: str | None = None,
        strike_shape: str | None = None,
        ratio: int | None = None,
        letter_spacing: int | None = None,
        shadow: str | None = None,
        script: str | None = None,
        base_char_pr_id: str | int | None = None,
    ) -> str:
        """요청한 글자 서식의 `charPr` id 를 보장하고 그 id 를 돌려준다."""

        return self._doc.oxml.ensure_run_style(
            bold=bold,
            italic=italic,
            underline=underline,
            color=color,
            font=font,
            size=size,
            highlight=highlight,
            strike=strike,
            underline_shape=underline_shape,
            underline_color=underline_color,
            strike_shape=strike_shape,
            ratio=ratio,
            letter_spacing=letter_spacing,
            shadow=shadow,
            script=script,
            base_char_pr_id=base_char_pr_id,
        )

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        active_borders: Sequence[str] | None = None,
        border_type: str = "SOLID",
    ) -> str:
        """요청한 테두리/채우기의 `borderFill` id 를 보장하고 돌려준다."""

        return self._doc.oxml.ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            fill_color=fill_color,
            active_borders=active_borders,
            border_type=border_type,
        )

    def ensure_numbering(
        self, *, kind: str, levels: Sequence[dict[str, str]] | None = None
    ) -> list[str]:
        """글머리표/번호 정의를 보장하고 참조 id 들을 돌려준다."""

        return self._doc.oxml.ensure_numbering(kind=kind, levels=levels)

    # -- 문단에 서식을 적용하는 동사 ---------------------------------------

    def apply_paragraph_format(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
        alignment: str | None = None,
        line_spacing_percent: int | float | None = None,
        indent_left_mm: float | None = None,
        indent_right_mm: float | None = None,
        first_line_indent_mm: float | None = None,
        spacing_before_pt: float | None = None,
        spacing_after_pt: float | None = None,
        outline_level: int | None = None,
        keep_with_next: bool | None = None,
        keep_lines: bool | None = None,
        page_break_before: bool | None = None,
        bottom_border: bool = False,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
    ) -> "ParagraphFormatResult":
        """문단 서식을 사람 단위(mm·pt·%)로 적용한다."""

        from .. import layout as _layout

        return _layout.set_paragraph_format(
            self._doc,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
            alignment=alignment,
            line_spacing_percent=line_spacing_percent,
            indent_left_mm=indent_left_mm,
            indent_right_mm=indent_right_mm,
            first_line_indent_mm=first_line_indent_mm,
            spacing_before_pt=spacing_before_pt,
            spacing_after_pt=spacing_after_pt,
            outline_level=outline_level,
            keep_with_next=keep_with_next,
            keep_lines=keep_lines,
            page_break_before=page_break_before,
            bottom_border=bottom_border,
            border_color=border_color,
            border_width=border_width,
        )

    def apply_list_format(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
        kind: str = "bullet",
        level: int = 1,
        bullet_char: str | None = None,
        number_format: str | None = None,
        start: int | None = None,
    ) -> "ListFormatResult":
        """글머리표/번호 문단 서식을 적용한다."""

        from .. import layout as _layout

        return _layout.set_list_format(
            self._doc,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
            kind=kind,
            level=level,
            bullet_char=bullet_char,
            number_format=number_format,
            start=start,
        )

    @staticmethod
    def _label(style: "Style | None") -> str:
        if style is None:  # pragma: no cover - 방어
            return ""
        return (style.name or style.eng_name or "").strip()
