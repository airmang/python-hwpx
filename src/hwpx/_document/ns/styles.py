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

from ...errors import HwpxLookupError, HwpxValueError
from ...oxml._document_primitives import (
    FILL_GRADIENT_TYPES,
    FILL_IMAGE_EFFECTS,
    FILL_IMAGE_MODES,
    LINE_TYPE2_VALUES,
    MEMO_TYPE_VALUES,
)
from ._base import _Namespace

if TYPE_CHECKING:
    from ...objects import ListFormatResult, ParagraphFormatResult
    from ...objects.binary_item import BinaryItem
    from ...oxml import (
        Bullet,
        GenericElement,
        MemoShape,
        ParagraphProperty,
        RunStyle,
        Style,
        TabDefinition,
    )

__all__ = ["StylesNamespace"]

#: 제안에 나열할 최대 후보 수. 23개를 한 줄에 늘어놓으면 읽히지 않는다.
_MAX_SUGGESTIONS = 3


def _as_int(value: object, default: int) -> int:
    """Narrow an untyped mapping value before ``int()`` — mypy cannot see
    into a ``Mapping[str, object]`` value, so this is the one place that
    does."""

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _resolve_fill_image(
    value: "str | BinaryItem | Mapping[str, object] | None",
) -> dict[str, str] | None:
    """Normalize ``ensure_border_fill(fill_image=...)`` into the plain-string
    attribute dict ``hc:imgBrush``/``hc:img`` need (Core XML schema.xml:805-889).

    *value* is either a bare ``doc.media.add_image(...)`` result (or its
    ``item_id`` string) — real-corpus files (hwpxlib_corpus, 5 files) show
    ``mode="TOTAL"`` exclusively, so that is the default — or a mapping for
    the rarer cases (``mode``/``bright``/``contrast``/``effect``/``alpha``).
    """

    if value is None:
        return None
    if isinstance(value, Mapping):
        options: Mapping[str, object] = value
        item = value.get("item", value.get("binary_item_id"))
    else:
        options = {}
        item = value
    item_id = str(item) if item else ""
    if not item_id:
        raise HwpxValueError(
            "fill_image must reference a doc.media binary item",
            code="style-border-fill-image-missing",
            suggestion="Register the image with doc.media.add_image(...) first and pass its id.",
        )
    mode = str(options.get("mode", "TOTAL")).upper()
    if mode not in FILL_IMAGE_MODES:
        raise HwpxValueError(
            f"unsupported fill_image mode {mode!r}",
            code="style-border-fill-image-mode-invalid",
            context={"mode": mode, "allowed": sorted(FILL_IMAGE_MODES)},
            suggestion="Use one of: " + ", ".join(sorted(FILL_IMAGE_MODES)),
        )
    effect = str(options.get("effect", "REAL_PIC")).upper()
    if effect not in FILL_IMAGE_EFFECTS:
        raise HwpxValueError(
            f"unsupported fill_image effect {effect!r}",
            code="style-border-fill-image-effect-invalid",
            context={"effect": effect, "allowed": sorted(FILL_IMAGE_EFFECTS)},
            suggestion="Use one of: " + ", ".join(sorted(FILL_IMAGE_EFFECTS)),
        )
    return {
        "binaryItemIDRef": item_id,
        "mode": mode,
        "bright": str(_as_int(options.get("bright"), 0)),
        "contrast": str(_as_int(options.get("contrast"), 0)),
        "effect": effect,
        "alpha": str(options.get("alpha", "0")),
    }


def _resolve_fill_gradient(value: "Mapping[str, object] | None") -> dict[str, object] | None:
    """Normalize ``ensure_border_fill(fill_gradient=...)`` into the plain
    attribute dict ``hc:gradation`` needs (Core XML schema.xml:710-803).

    Defaults mirror the schema except *type* — real corpus (hwpxlib_corpus, 2
    files) observes only ``LINEAR``, so that stays the ergonomic default even
    though the schema itself defaults nothing (``type`` has no XSD default).
    """

    if value is None:
        return None
    raw_colors = value.get("colors")
    colors = (
        [str(color) for color in raw_colors]
        if isinstance(raw_colors, Sequence) and not isinstance(raw_colors, str)
        else []
    )
    if len(colors) < 2:
        raise HwpxValueError(
            "fill_gradient needs at least two colors",
            code="style-border-fill-gradient-colors-invalid",
            context={"colors": colors},
            suggestion="Pass colors=['#RRGGBB', '#RRGGBB', ...] with two or more entries.",
        )
    gradient_type = str(value.get("type", "LINEAR")).upper()
    if gradient_type not in FILL_GRADIENT_TYPES:
        raise HwpxValueError(
            f"unsupported fill_gradient type {gradient_type!r}",
            code="style-border-fill-gradient-type-invalid",
            context={"type": gradient_type, "allowed": sorted(FILL_GRADIENT_TYPES)},
            suggestion="Use one of: " + ", ".join(sorted(FILL_GRADIENT_TYPES)),
        )
    return {
        "type": gradient_type,
        "angle": str(_as_int(value.get("angle"), 90)),
        "centerX": str(_as_int(value.get("center_x"), 0)),
        "centerY": str(_as_int(value.get("center_y"), 0)),
        "step": str(_as_int(value.get("step"), 255)),
        "colorNum": str(len(colors)),
        "stepCenter": str(_as_int(value.get("step_center"), 50)),
        "alpha": str(value.get("alpha", "0")),
        "colors": colors,
    }


def _validate_memo_enum(value: str, allowed: frozenset[str], *, arg: str, code: str) -> str:
    normalized = str(value).upper()
    if normalized not in allowed:
        raise HwpxValueError(
            f"unsupported {arg} {value!r}",
            code=code,
            context={arg: normalized, "allowed": sorted(allowed)},
            suggestion="Use one of: " + ", ".join(sorted(allowed)),
        )
    return normalized


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
    def tab_properties(self) -> dict[str, "TabDefinition"]:
        """`hh:tabPr` 정의 전체(id → `TabDefinition`, `tab_stops`에 각
        `hh:tabItem`을 담는다). 문단의 탭 정의는
        `doc.styles.paragraph_property(p.para_pr_id_ref).tab_pr_id_ref`로
        참조 id를 얻은 뒤 이 매핑(또는 `tab_property()`)으로 해석한다 —
        `border_fill_id_ref`가 `border_fill()`로 해석되는 것과 같은 관용구."""

        return self._doc.oxml.tab_properties

    def tab_property(self, tab_pr_id_ref: "int | str | None") -> "TabDefinition | None":
        return self._doc.oxml.tab_property(tab_pr_id_ref)

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
        outline: str | None = None,
        emboss: bool | None = None,
        engrave: bool | None = None,
        base_char_pr_id: str | int | None = None,
    ) -> str:
        """요청한 글자 서식의 `charPr` id 를 보장하고 그 id 를 돌려준다.

        `outline` (외곽선, OWPML `hc:LineType1` 어휘: NONE/SOLID/DOT/THICK/
        DASH/DASH_DOT/DASH_DOT_DOT), `emboss`/`engrave` (양각/음각)는 6.3
        추가분이다. `script="sup"/"sub"`는 기존 `relSz`/`offset` 수치 근사에
        더해 실제 `hh:supscript`/`hh:subscript` 요소를 함께 방출한다.
        """

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
            outline=outline,
            emboss=emboss,
            engrave=engrave,
            base_char_pr_id=base_char_pr_id,
        )

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        fill_image: "str | BinaryItem | Mapping[str, object] | None" = None,
        fill_gradient: "Mapping[str, object] | None" = None,
        active_borders: Sequence[str] | None = None,
        border_type: str = "SOLID",
    ) -> str:
        """요청한 테두리/채우기의 `borderFill` id 를 보장하고 돌려준다.

        `fill_color`/`fill_image`/`fill_gradient` 는 OWPML `hc:fillBrush` 의
        선택지(Core XML schema.xml:650) 그대로 상호 배타적이다 — 둘 이상
        주면 typed 거부한다. `fill_image` 는 `doc.media.add_image(...)` 가
        돌려준 `BinaryItem`(또는 그 id 문자열)을 그대로 받는다.
        """

        given = sum(1 for v in (fill_color, fill_image, fill_gradient) if v is not None)
        if given > 1:
            raise HwpxValueError(
                "fill_color/fill_image/fill_gradient are mutually exclusive",
                code="style-border-fill-conflict",
                suggestion="Pass exactly one of fill_color, fill_image, fill_gradient.",
            )
        resolved_image = _resolve_fill_image(fill_image)
        resolved_gradient = _resolve_fill_gradient(fill_gradient)

        return self._doc.oxml.ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            fill_color=fill_color,
            fill_image=resolved_image,
            fill_gradient=resolved_gradient,
            active_borders=active_borders,
            border_type=border_type,
        )

    def ensure_memo_shape(
        self,
        *,
        width: int = 15591,
        line_width: int | str = 1,
        line_type: str = "SOLID",
        line_color: str = "#000000",
        fill_color: str = "#CCFF99",
        active_color: str = "#FFFF99",
        memo_type: str = "NOMAL",
    ) -> str:
        """요청한 메모 모양의 `memoPr` id 를 보장하고 돌려준다.

        기본값은 실코퍼스(hwpxlib_corpus, 6파일) 최빈 프로파일이다 —
        width=15591·lineWidth=1·lineType=SOLID·memoType=NOMAL(스키마 원문
        철자, 오타 아님)은 6파일 전량, 색 3종은 그 중 lineWidth=1인 절반이
        공유하는 조합. 만든 id 는 `doc.notes.add_memo(memo_shape_id_ref=...)`
        에 바로 넘길 수 있다.
        """

        return self._doc.oxml.ensure_memo_shape(
            width=width,
            line_width=line_width,
            line_type=_validate_memo_enum(
                line_type, LINE_TYPE2_VALUES, arg="line_type",
                code="style-memo-shape-line-type-invalid",
            ),
            line_color=line_color,
            fill_color=fill_color,
            active_color=active_color,
            memo_type=_validate_memo_enum(
                memo_type, MEMO_TYPE_VALUES, arg="memo_type",
                code="style-memo-shape-memo-type-invalid",
            ),
        )

    def ensure_font(
        self,
        face: str,
        *,
        lang: "Sequence[str] | str | None" = None,
        font_type: str = "TTF",
        is_embedded: bool = False,
        binary_item_id_ref: str | None = None,
        subst_face: str | None = None,
        subst_type: str | None = None,
        subst_is_embedded: bool = False,
        subst_binary_item_id_ref: str | None = None,
    ) -> str:
        """`hh:fontfaces` 에 *face* 를 선언하고(dedupe) 그 `hh:font` id 를 돌려준다.

        *lang* 을 생략하면 실문서 다수 관행대로 7개 lang 블록
        (HANGUL/LATIN/HANJA/JAPANESE/OTHER/SYMBOL/USER) 전부에 등록한다 —
        등록 뒤 ``ensure_run(font=face)`` 로 참조하면 ``fontRef`` 의 모든
        속성이 유효한 글꼴을 가리킨다. *subst_face*/*subst_type* 을 주면
        `hh:substFont` 대체 글꼴도 함께 선언한다.
        """

        return self._doc.oxml.ensure_font(
            face,
            lang=lang,
            font_type=font_type,
            is_embedded=is_embedded,
            binary_item_id_ref=binary_item_id_ref,
            subst_face=subst_face,
            subst_type=subst_type,
            subst_is_embedded=subst_is_embedded,
            subst_binary_item_id_ref=subst_binary_item_id_ref,
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
        column_break: bool | None = None,
        bottom_border: bool = False,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        tab_stops: Sequence[Mapping[str, object]] | None = None,
        auto_tab_left: bool | None = None,
        auto_tab_right: bool | None = None,
    ) -> "ParagraphFormatResult":
        """문단 서식을 사람 단위(mm·pt·%)로 적용한다.

        `tab_stops`는 `{"pos_mm": ..., "type": "LEFT"|"RIGHT"|"CENTER"|
        "DECIMAL", "leader": "NONE"|...}` 매핑의 순서 있는 시퀀스다(`type`·
        `leader` 생략 시 실코퍼스 다수 관행인 "LEFT"·"NONE"). 지정하면
        `hh:tabPr`를 보장(dedupe)하고 문단의 `tabPrIDRef`를 배선한다.

        `column_break`(6.12 트레인㊸ 갭④)은 `page_break_before`와 다른
        메커니즘이다 — 공유 paraPr 스타일 속성이 아니라 `hp:p` 자신의
        `columnBreak` 속성(문단 인스턴스별 강제 단 나눔)이라, 대상 문단에
        직접 적용된다.
        """

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
            column_break=column_break,
            bottom_border=bottom_border,
            border_color=border_color,
            border_width=border_width,
            tab_stops=tab_stops,
            auto_tab_left=auto_tab_left,
            auto_tab_right=auto_tab_right,
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
