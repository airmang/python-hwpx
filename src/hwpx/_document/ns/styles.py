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

from typing import Any, Iterator, Mapping, Sequence

from ...errors import HwpxLookupError, HwpxValueError
from ...objects import (
    BorderFillInfo,
    FontReplaceReport,
    LineSpacing,
    ListFormatResult,
    NumberingInfo,
    ParagraphFormatResult,
)
from ...objects.binary_item import BinaryItem
from ...oxml import (
    Bullet,
    Font,
    HwpxOxmlParagraph,
    MemoShape,
    ParagraphProperty,
    RunStyle,
    Style,
    TabDefinition,
)
from ...oxml.color import rgb_color
from ...oxml.header_part import HwpxOxmlHeader
from ...oxml._document_primitives import (
    FILL_GRADIENT_TYPES,
    FILL_IMAGE_EFFECTS,
    FILL_IMAGE_MODES,
    LINE_TYPE2_VALUES,
    MEMO_TYPE_VALUES,
)
from ._base import _Namespace

__all__ = ["StylesNamespace"]

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
        [rgb_color(color) for color in raw_colors]
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

    def __getitem__(self, key: "int | str") -> "Style":  # type: ignore[override]  # 이름·숫자 id 도 받는다
        """id·이름·영문 이름으로 찾는다(:meth:`resolve` 와 같은 순서).

        ``doc.styles["바탕글"]``·``doc.styles["Normal"]``·``doc.styles[0]``·``doc.styles["0"]``
        이 같은 스타일이다. 없으면 ``HwpxLookupError``(``KeyError`` 이기도 하다,
        ``style-not-found``) — 그래서 ``"바탕글" in doc.styles`` 도 이름으로 답한다.
        """

        return self.resolve(key)

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

    @property
    def names(self) -> tuple[str, ...]:
        """이 문서가 정의한 스타일 이름(한글 `name` 우선, 중복 제거)을 정의 순서로."""

        seen: dict[str, None] = {}
        for style in self._doc.oxml.styles.values():
            for label in ((style.name or "").strip(), (style.eng_name or "").strip()):
                if label:
                    seen.setdefault(label, None)
        return tuple(seen)

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

        from ...oxml.formatting import resolve_style

        # 해석 본체는 oxml 쪽에 있다 — paragraph.style = "개요 1" 도 같은 규칙으로 찾는다.
        return resolve_style(self._doc.oxml, spec)

    # -- 개요 스타일 -------------------------------------------------------

    def outline_style(self, level: int) -> "Style | None":
        """개요 *level* 수준(1~10)의 스타일. 이 문서에 없으면 ``None``.

        ``add_heading(level=)`` 이 고르는 스타일과 같다. 찾는 순서: 이름이
        ``개요 N`` → 영문 이름이 ``Outline N``(대소문자 무시) → 문단 모양이 그 수준의
        개요(``hh:heading type="OUTLINE"``)를 선언하는 스타일.

        Raises:
            HwpxValueError: *level* 이 1~10 의 정수가 아니다(``heading-level-invalid`` /
                ``heading-level-out-of-range``).
        """

        from ..headings import resolve_heading_style

        try:
            return resolve_heading_style(self._doc, level=level)
        except HwpxLookupError:
            return None

    def outline_level(self, style: "int | str | Style") -> int | None:
        """*style* 이 개요 스타일이면 그 수준(1~10), 아니면 ``None``.

        *style* 은 스타일 객체·숫자 id·이름(:meth:`resolve` 와 같다). 이름이
        ``개요 N``/``Outline N`` 이면 N, 아니면 스타일의 문단 모양이 선언한 개요
        수준이다 — :meth:`outline_style` 이 같은 규칙으로 찾으므로
        ``outline_level(outline_style(n)) == n`` 이다.

        Raises:
            HwpxLookupError: 그런 스타일이 없다(``style-not-found`` / ``style-ambiguous``).
        """

        from ...oxml.paragraph_heading import outline_style_level
        from ..headings import _OUTLINE_ENG_NAME, MAX_HEADING_LEVEL, MIN_HEADING_LEVEL

        resolved = self.resolve(style)
        level = outline_style_level(resolved.name)
        if level is None:
            match = _OUTLINE_ENG_NAME.match((resolved.eng_name or "").strip())
            level = int(match.group(1)) if match else None
        if level is None:
            from ...oxml.formatting import para_pr_outline_level

            level = para_pr_outline_level(self._doc.oxml, resolved.para_pr_id_ref)
        return level if level is not None and MIN_HEADING_LEVEL <= level <= MAX_HEADING_LEVEL else None

    # -- 서식 정의 테이블 --------------------------------------------------

    @property
    def char_properties(self) -> Mapping[str, "RunStyle"]:
        """글자 모양(``hh:charPr``) 전체, id(적힌 대로와 숫자로) → `RunStyle`. 읽을 때마다 머리를
        그때 모습으로 읽는 읽기 전용 보기다(``.element``로 고친 것도 보인다). id 하나 찾기는
        글자 모양 수와 상관없이 그 하나만 견주고, ``len``·차례로 훑기는 모두를 견준다. 그대로
        남는 사본은 ``dict(doc.styles.char_properties)``."""

        return self._doc.oxml.char_properties

    def char_property(self, char_pr_id_ref: "int | str | None") -> "RunStyle | None":
        from ...oxml.run import detached_style

        style = self._doc.oxml.char_property(char_pr_id_ref)
        return None if style is None else detached_style(style)

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
    def border_fills(self) -> dict[str, "BorderFillInfo"]:
        """테두리/배경 정의(`hh:borderFill`) 전체(id 문자열 → `BorderFillInfo`).

        id는 적힌 그대로와 앞의 0을 뗀 숫자 둘 다로 찾는다. 값 하나하나는
        :meth:`border_fill` 이 읽는 것과 같다. XML이 필요하면 ``doc.oxml.headers[0].element``.
        """

        mapping: dict[str, BorderFillInfo] = {}
        for header in self._doc.oxml.headers:
            mapping.update(header.border_fills)
        return mapping

    def border_fill(
        self, border_fill_id_ref: "int | str | None"
    ) -> "BorderFillInfo | None":
        """`hh:borderFill` 하나를 값으로 읽는다(없는 id면 `None`).

        네 변과 대각선은 `hh:borderFill`의 **직계** 자식
        `hh:leftBorder`·`hh:rightBorder`·`hh:topBorder`·`hh:bottomBorder`·
        `hh:diagonal`에서 읽는다. 요소가 없으면 `BorderLine("NONE", 0.0,
        "#000000")`, 속성이 없으면 `type="NONE"`·`width="0 mm"`·
        `color="#000000"`로 본다. 값은 저장된 그대로 돌려준다(대소문자·색
        표기를 바꾸지 않는다). `width_mm`는 `"0.12 mm"`의 앞 숫자이고, 숫자로
        읽을 수 없으면 `HwpxValueError(code="style-border-fill-width-invalid")`.

        `fill`은 첫 `hc:winBrush`의 `faceColor`이고, winBrush가 없거나
        `faceColor`가 `"none"`(대소문자 무시)이면 `None`이다. `fill_kinds`는
        `hc:fillBrush`가 담은 채움의 종류(`"color"`·`"gradation"`·`"image"`·
        `"unknown"`)를 적힌 차례로, `hc:fillBrush`가 없으면 `()`(채움 없음)다.
        그러데이션·그림의 자세한 값은 ``doc.oxml.headers[0].element`` 의 XML로 읽는다. 메모리의 헤더를 읽으므로
        `ensure_border_fill()`로 만든 id도 저장 없이 바로 읽힌다.
        """

        for header in self._doc.oxml.headers:
            found = header.border_fill(border_fill_id_ref)
            if found is not None:
                return found
        return None

    # -- 글꼴 표 -----------------------------------------------------------

    def fonts(self, lang: str = "HANGUL") -> dict[str, "Font"]:
        """`hh:fontface[@lang=lang]` 블록의 `hh:font` 목록(id 문자열 → `Font`).

        글꼴 id는 lang 블록마다 따로 매겨진다 — `hh:fontRef/@hangul`은 HANGUL
        블록의 id, `@latin`은 LATIN 블록의 id다. *lang*은 HANGUL·LATIN·HANJA·
        JAPANESE·OTHER·SYMBOL·USER 중 하나(대소문자 무시)이고, 그 밖이면
        `HwpxValueError(code="style-font-lang-invalid")`. 블록이 없으면 `{}`.
        메모리의 첫 헤더를 읽으므로 `ensure_font()` 직후에도 맞는다.
        """

        from ...oxml import header_fonts

        return header_fonts.fonts(self._primary_header(), lang)

    def font_face(
        self, char_pr_id_ref: "int | str | None", lang: str = "HANGUL"
    ) -> str | None:
        """글자 모양 *char_pr_id_ref*가 *lang* 블록에서 가리키는 글꼴 이름.

        `hh:charPr/hh:fontRef/@<lang 소문자>`의 id를 그 lang 블록에서 찾는다.
        글자 모양·`fontRef`·속성·글꼴 id 중 하나라도 없으면 `None`. id는
        `char_property()`처럼 정수와 문자열을 모두 받는다.
        """

        from ...oxml import header_fonts

        return header_fonts.font_face(self._primary_header(), char_pr_id_ref, lang)

    def replace_font(
        self,
        src_face: str,
        dst_face: str,
        *,
        langs: "Sequence[str] | None" = None,
        font_type: str | None = None,
    ) -> "FontReplaceReport":
        """글꼴 *src_face*를 문서 전체에서 *dst_face*로 바꾼다.

        읽는 쪽에 없는 장식 글꼴을 흔한 글꼴로 바꿀 때 쓴다. `hh:fontface`
        블록을 문서 순서대로(*langs*를 주면 그 lang 블록만) 하나씩 처리한다.

        1. 블록에 *src_face* 글꼴이 없으면 건너뛴다(오류 아님).
        2. *dst_face* 글꼴이 있으면 그 id를 쓰고, 없으면 블록 끝에 id가
           `{글꼴 수}`인 *dst_face* 글꼴을 더한다. 다른 블록에 *dst_face* 선언이
           있으면(바꾸기 전 문서 순서로 첫 선언) 그 `hh:font`를 id만 바꿔
           복사한다. 그래서 `type`·`isEmbedded`·자식 요소가 그 선언과 같다.
           어느 블록에도 없으면
           `<hh:font id="{글꼴 수}" face="{dst_face}" type="TTF" isEmbedded="0"/>`다.
           *font_type*(`REP`/`TTF`/`HFT`)을 주면 이 호출이 더하는 글꼴의
           `type`을 그 값으로 쓴다. 이미 있던 글꼴은 바꾸지 않는다.
        3. 헤더의 모든 `hh:charPr`에서 `fontRef/@<lang>`이 *src_face*를
           가리키면 *dst_face*를 가리키게 한다(`repointed`로 센다).
        4. *src_face* 글꼴을 지우고, 남은 글꼴의 id를 문서 순서대로 0..N-1로
           다시 매기고(옛 id 값이 아니라 순서 기준), `fontCnt`를 N으로 맞추고,
           모든 `fontRef/@<lang>`을 옛 id → 새 id로 옮긴다. 어떤 글꼴도
           가리키지 않던 값은 그대로 둔다. 2에서 더한 글꼴의 임시 id는 옛 id
           표에 넣지 않는다 — id가 0..N-1이 아닌 블록에서는 기존 id와 겹칠 수
           있고, 아무 글꼴도 가리키지 않던 값이 새 글꼴을 가리키게 되어서도
           안 된다.

        id가 0..N-1이고 모든 참조가 글꼴을 가리키는 블록에서는 위 단계를 그대로
        수행한 것과 바이트까지 같다. 망가진 입력 두 가지만 다르게 다룬다: id가
        0..N-1이 아닌 블록에서 임시 id가 기존 글꼴 id와 겹쳐도 그 글꼴의 참조가
        *dst_face*로 끌려가지 않고, 아무 글꼴도 가리키지 않던 참조(임시 id와 같은
        값 포함)는 계속 아무것도 가리키지 않는다.

        그래서 바뀐 참조 말고는 모든 `(charPr, lang)`이 전과 같은 글꼴 이름을
        가리킨다. `fontfaces/@itemCnt`는 건드리지 않는다. 무엇이든 바뀌면 헤더를
        dirty로 표시한다.

        인자는 바꾸기 전에 검사한다: 빈 이름은 `style-font-face-empty`, 같은
        이름 둘은 `style-font-replace-same-face`, 모르는 lang은
        `style-font-lang-invalid`, 모르는 *font_type*은
        `style-font-type-invalid`(`HwpxValueError`).

        Returns:
            `FontReplaceReport` — `langs`는 실제로 바뀐 블록(문서 순서),
            `declared`는 *dst_face*를 새로 더한 블록, `repointed`는
            *src_face*에서 *dst_face*로 옮긴 `fontRef` 속성 수.
        """

        from ...oxml import header_fonts

        return header_fonts.replace_font(
            self._primary_header(), src_face, dst_face, langs=langs, font_type=font_type
        )

    def _primary_header(self) -> "HwpxOxmlHeader | None":
        headers = self._doc.oxml.headers
        return headers[0] if headers else None

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

    @property
    def numberings(self) -> dict[str, "NumberingInfo"]:
        """번호 정의(`hh:numbering`) 전체(id 문자열 → `NumberingInfo`).

        첫 헤더의 `hh:refList/hh:numberings`를 읽는다. 문단 모양의
        `hh:heading@idRef`(종류가 NUMBER·OUTLINE일 때)가 가리키는 정의다. 값 하나하나는
        :meth:`numbering` 이 읽는 것과 같다. 헤더나 정의가 없으면 `{}`. 글머리표 정의는
        :attr:`bullets`.
        """

        from ...oxml.formatting import numbering_info

        header = self._primary_header()
        if header is None:
            return {}
        element = header._numberings_element()
        if element is None:
            return {}
        mapping: dict[str, NumberingInfo] = {}
        for definition in element:
            if not isinstance(definition.tag, str) or definition.tag.rsplit("}", 1)[-1] != "numbering":
                continue
            identifier = definition.get("id")
            if identifier is None or str(identifier) in mapping:
                continue
            info = numbering_info(header, identifier)
            if info is not None:
                mapping[str(identifier)] = info
        return mapping

    def numbering(self, numbering_id_ref: "int | str | None") -> "NumberingInfo | None":
        """번호 정의 하나를 값으로 읽는다(없는 id면 `None`, 정수와 문자열을 모두 받는다).

        `NumberingInfo.levels`는 수준마다 `NumberingLevel`(`level`·`start`·
        `number_format`(DIGIT·HANGUL_SYLLABLE·CIRCLED_DIGIT …)·`text`(번호 틀,
        `"^1."`의 `^n`은 n수준 번호)·`align`·`char_pr_id_ref`(번호 글자 모양, 본문을
        따르면 `None`) …)이다. `hp:switch`에 든 수준은 `hp:case` 쪽을 읽는다. 메모리의 첫
        헤더를 읽으므로 :meth:`ensure_numbering` 직후에도 맞는다. XML이 필요하면
        ``doc.oxml.headers[0].element``.
        """

        from ...oxml.formatting import numbering_info

        return numbering_info(self._primary_header(), numbering_id_ref)

    def add_numbering(self, levels: "Sequence[Mapping[str, object]] | None" = None) -> "NumberingInfo":
        """새 번호 정의(``hh:numbering``)를 만들고 그것을 읽은 값으로 돌려준다.

        한/글은 번호를 정의마다 센다. 같은 정의를 쓰는 문단은 사이에 다른 문단이 있어도 번호가
        이어지고, 정의가 다르면 따로 1부터 센다. 그래서 이것은 같은 모양의 정의가 있어도 늘 새로
        만든다(새 목록). 이어 갈 문단에는 돌려받은 정의를 다시 준다:
        ``p.set_numbering(numbering, level=1)``.

        정의는 열 수준이고 기본은 한/글 자신의 번호 모양이다(새 문서가 id 1로 갖고 새 번호 목록에
        쓰는 것: ``1.``·``가.``·``1)``·``가)``·``(1)``·``(가)``·``①``·``㉮``, 9·10수준은 번호를
        그리지 않는다). *levels* 의 i번째 매핑이 i+1수준을 바꾼다: ``text``(번호 틀, ``^n`` 이
        n수준의 번호, ``""`` 는 번호 없음), ``number_format``(DIGIT·HANGUL_SYLLABLE·
        CIRCLED_DIGIT·LATIN_SMALL·ROMAN_CAPITAL …), ``start``(그 수준의 시작 번호, 0~65535).
        번호와 글의 자리는 ``auto_indent``(첫 줄을 번호 너비만큼 들여 씀, ``autoIndent``)·
        ``use_instance_width``(번호가 그리는 너비를 씀, ``useInstWidth``)·``text_offset``(번호와 글 사이,
        0~32767)·``text_offset_type``(``"PERCENT"`` 글자 크기의 몫, ``"HWPUNIT"``)로 바꾼다. 한/글이 Word
        목록을 옮길 때 쓰는 값은 ``auto_indent=False, use_instance_width=True, text_offset=110,
        text_offset_type="PERCENT"`` 다(내어쓰기는 문단 모양이 맡는다).
        예: ``doc.styles.add_numbering([{"text": "^1)"}, {"text": "(^2)", "number_format":
        "LATIN_SMALL"}])``. 고칠 것은 바꾸기 전에 모두 검사한다(모르는 키·틀 아닌 글은
        ``style-numbering-level-invalid``, 열 수준 넘음은 ``style-list-level-invalid``, 번호 형식은
        ``style-number-format-invalid``, 시작 번호는 ``style-list-start-value``).
        """

        from ...oxml.formatting import numbering_info
        from ...oxml.numbering_kinds import add_numbering_definition

        header = self._require_header()
        numbering_id = add_numbering_definition(header, levels)
        info = numbering_info(header, numbering_id)
        if info is None:  # pragma: no cover - the definition was just added to this header
            from ...errors import HwpxStateError

            raise HwpxStateError("failed to read back the new numbering", code="style-list-property-failed")
        return info

    def ensure_bullet(
        self,
        char: str = "●",
        *,
        char_pr_id_ref: "str | int | None" = None,
        auto_indent: bool | None = None,
        use_instance_width: bool | None = None,
        text_offset: int | None = None,
        text_offset_type: str | None = None,
    ) -> str:
        """글머리표 *char* 의 정의(``hh:bullet``) id 를 보장하고 돌려준다(같은 정의가 있으면 그 id).

        글머리표는 번호를 세지 않으므로 같은 정의를 여러 목록이 함께 써도 된다. 새 정의는
        한/글이 저장하는 글머리표 모양 그대로다(문단 글의 글자 모양, 글머리표와 글 사이 50%).
        *char_pr_id_ref* 는 글머리표만의 글자 모양(``doc.styles.ensure_run(...)`` 의 id, 기호 글꼴
        같은 것)이고, 주지 않으면 문단 글의 모양을 따른다. 문단에 거는 것은
        ``p.set_bullet(bullet_id, level=1)``. 글자 하나가 아니면 ``style-bullet-char-invalid``,
        없는 글자 모양이면 ``style-definition-not-found``.

        *auto_indent*·*use_instance_width*·*text_offset*·*text_offset_type* 은 글머리표와 글의 자리로,
        :meth:`add_numbering` 의 같은 이름 키와 같다(``None`` 은 한/글의 새 글머리표 값). 한/글이 Word
        글머리표를 옮길 때는 ``auto_indent=False, use_instance_width=True, text_offset=110`` 이다. 값이
        맞지 않으면 ``style-numbering-level-invalid``.
        """

        from ...oxml.numbering_kinds import ensure_bullet_definition

        layout = {"auto_indent": auto_indent, "use_instance_width": use_instance_width,
                  "text_offset": text_offset, "text_offset_type": text_offset_type}
        return ensure_bullet_definition(self._require_header(), char, char_pr_id_ref, layout)

    def set_numbering_level(
        self,
        numbering: "NumberingInfo | int | str",
        level: int,
        *,
        text: str | None = None,
        number_format: str | None = None,
        start: int | None = None,
        auto_indent: bool | None = None,
        use_instance_width: bool | None = None,
        text_offset: int | None = None,
        text_offset_type: str | None = None,
    ) -> None:
        """번호 정의 *numbering* (``NumberingInfo`` 나 id)의 *level* 수준(1~10)을 고친다.

        ``text`` 는 번호 틀(``"^1."``, ``""`` 는 번호를 그리지 않는다), ``number_format`` 은 번호
        형식, ``start`` 는 시작 번호(0~65535; 1수준이면 정의의 시작 번호도)다. ``auto_indent``·
        ``use_instance_width``·``text_offset``·``text_offset_type`` 은 번호와 글의 자리로
        :meth:`add_numbering` 의 같은 이름 키와 같다. 준 것만 바뀐다. 그
        정의로 번호를 그리는 문단 — 그 정의의 번호 문단과, 구역이 그것으로 개요 번호를 그리면
        (``section.properties.outline_shape_id_ref``) 개요 문단 — 의 줄 배치 캐시를 지운다. 예:
        개요 번호를 그리지 않게 하려면 그 구역의 개요 번호 정의의 열 수준에 ``text=""`` 를 준다.
        한 정의를 여러 곳이 쓰면(한/글 새 문서는 개요와 새 번호 목록이 id 1을 함께 쓴다) 모두
        바뀐다. 없는 정의는 ``style-definition-not-found``, 그 수준이 없는 정의는
        ``style-numbering-level-missing``, 바꿀 것이 없으면 ``style-numbering-level-invalid``.
        """

        from ...oxml.numbering_kinds import set_numbering_level

        changes = {
            name: value
            for name, value in (("text", text), ("number_format", number_format), ("start", start),
                                ("auto_indent", auto_indent), ("use_instance_width", use_instance_width),
                                ("text_offset", text_offset), ("text_offset_type", text_offset_type))
            if value is not None
        }
        set_numbering_level(self._doc.oxml, numbering, level, changes)

    def ensure_tab_definition(
        self,
        *,
        tab_stops: "Sequence[Mapping[str, object]] | None" = None,
        auto_tab_left: bool = False,
        auto_tab_right: bool = False,
    ) -> str:
        """탭 정의(`hh:tabPr`) id 를 보장하고 돌려준다(같은 정의가 있으면 그 id).

        `tab_stops`는 `{"pos": HWPUNIT 또는 "pos_mm": mm, "type": "LEFT"|"RIGHT"|
        "CENTER"|"DECIMAL", "leader": "NONE"|…}`의 순서 있는 목록이다(`type`·
        `leader` 생략 시 "LEFT"·"NONE"). 한/글처럼 탭마다 `hp:switch`에 HWPUNIT 값과
        그 두 배(`hp:default`)를 쓴다. 돌려받은 id 는
        ``ensure_paragraph_format(tab_pr_id_ref=...)``에 넘긴다.
        """

        from ...oxml.formatting import tab_stops_in_hwpunit

        return self._require_header().ensure_tab_definition(
            tab_stops=tab_stops_in_hwpunit(tab_stops),
            auto_tab_left=bool(auto_tab_left),
            auto_tab_right=bool(auto_tab_right),
        )

    # -- 서식 id 를 mint 하는 동사 -----------------------------------------

    def ensure_run(
        self,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
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
        base_char_pr_id_ref: str | int | None = None,
        font_by_lang: "Mapping[str, str] | None" = None,
        letter_spacing_by_lang: "Mapping[str, int] | None" = None,
    ) -> str:
        """요청한 글자 서식의 `charPr` id 를 보장하고 그 id 를 돌려준다.

        돌려주는 글자 모양은 기준(`base_char_pr_id_ref`, 없으면 첫 `charPr`)에서 요청한
        값만 바꾼 것이다. 내용이 같은 글자 모양이 있으면 그것을 다시 쓴다.
        `bold`·`italic`·`underline`을 주지 않으면 `base_char_pr_id_ref`의 것을 따르고,
        기준을 주지 않았으면 끈다.

        `outline` (외곽선, OWPML `hc:LineType1` 어휘: NONE/SOLID/DOT/THICK/
        DASH/DASH_DOT/DASH_DOT_DOT), `emboss`/`engrave` (양각/음각)는 6.3
        추가분이다. `script="sup"/"sub"`는 한컴처럼 `hh:supscript`/`hh:subscript`
        요소만 쓴다(요소가 글자를 줄이고 올리거나 내린다. `relSz`/`offset`은 그대로).

        `font`는 모든 언어의 글꼴을, `font_by_lang`은 언어별 글꼴을 정한다.
        `font`는 일곱 언어 모두에 준다(한/글 저장본의 글자 모양 12,188개 가운데 12,187개가 일곱
        언어에 같은 글꼴을 쓴다). 그 글꼴이 없는 언어 블록에는 먼저 선언한다(그 언어의
        `hh:fontface` 블록이 아예 없으면 블록부터 만든다): 다른 블록에 선언이 있으면 그 `hh:font`를
        id만 바꿔 복사하고(`replace_font`와 같다. 글꼴 형식·대체 글꼴이 그대로다), 어디에도 없으면
        `ensure_font`의 기본 선언이다. `font_by_lang`이 댄 글꼴도 같다.
        `font_by_lang`은 언어(HANGUL·LATIN·HANJA·JAPANESE·OTHER·SYMBOL·USER,
        대소문자 무시) → 글꼴 이름 매핑이다. 예:
        `ensure_run(font_by_lang={"HANGUL": "함초롬바탕", "LATIN": "Arial"})`.

        - 언어마다 글꼴 id를 따로 매기므로, 각 글꼴을 그 언어 블록에 등록하고
          (없으면 더한다) 그 블록의 id를 `fontRef`의 그 언어 속성에 쓴다.
        - 이름을 대지 않은 언어는 기준 글자 모양의 `fontRef` 값을 그대로 둔다.
        - `font`와 함께 주면 `font`를 먼저 모든 언어에 적용하고, `font_by_lang`이
          댄 언어만 그 글꼴로 바꾼다(`font_by_lang`이 이긴다).
        - 기준 글자 모양은 바꾸지 않는다. 기준을 복사해 바꾼 결과와 내용이 같은
          글자 모양이 이미 있으면 그 id를, 없으면 새 id를 돌려준다.
        - 아무 글꼴도 등록하기 전에 모든 인자(색·크기 등 포함)를 검사한다. 거부한 호출은 문서를
          바꾸지 않는다. 모르는 언어는
          `style-font-lang-invalid`, 빈 글꼴 이름은 `style-font-face-empty`,
          매핑이 아니거나 문자열이 아닌 키·값, 대소문자만 다른 같은 언어 두 번은
          `style-run-font-by-lang-invalid`(`HwpxValueError`).

        `letter_spacing`은 모든 언어의 자간(%)을, `letter_spacing_by_lang`은 언어별 자간을
        정한다. 언어 키는 `font_by_lang`과 같고 값은 -50 ~ 100의 `int`다(`letter_spacing`과 같다.
        한/글 2024는 51 ~ 100을 다시 저장해도 그대로 둔다). 예: `ensure_run(base_char_pr_id_ref=7, letter_spacing_by_lang={"HANGUL": 0})`.

        - 이름을 대지 않은 언어는 기준 글자 모양의 `hh:spacing` 값을 그대로 둔다(기준에
          `hh:spacing`이 없으면 일곱 언어를 모두 적고, 대지 않은 언어는 스키마 기본값 0).
        - `letter_spacing`과 함께 주면 `letter_spacing`을 먼저 모든 언어에 적용하고,
          `letter_spacing_by_lang`이 댄 언어만 그 값으로 바꾼다.
        - 아무것도 바꾸기 전에 검사한다: 모르는 언어는 `style-font-lang-invalid`, 매핑이
          아니거나 문자열이 아닌 키, 같은 언어 두 번, `int`가 아니거나 범위 밖인 값은
          `style-run-letter-spacing-by-lang-invalid`(`HwpxValueError`).
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
            base_char_pr_id=base_char_pr_id_ref,
            font_by_lang=font_by_lang,
            letter_spacing_by_lang=letter_spacing_by_lang,
        )

    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width_mm: float = 0.12,
        fill_color: str | None = None,
        fill_image: "str | BinaryItem | Mapping[str, object] | None" = None,
        fill_gradient: "Mapping[str, object] | None" = None,
        active_borders: Sequence[str] | None = None,
        border_type: str = "SOLID",
        sides: "Mapping[str, Mapping[str, Any] | None] | None" = None,
        base_border_fill_id_ref: "str | int | None" = None,
    ) -> str:
        """요청한 테두리/채우기의 `borderFill` id 를 보장하고 돌려준다.

        `border_width_mm` 는 선 굵기(mm)이고, 한/글의 굵기 목록(0.1·0.12·0.15·0.2·0.25·0.3·
        0.4·0.5·0.6·0.7·1.0·1.5·2.0·3.0·4.0·5.0 mm)에 있는 값만 받는다. 목록에 없는 값은 문서를
        바꾸기 전에 `HwpxValueError(code="style-line-width-invalid")` 로 거부한다(가까운 값으로
        바꿔 쓰지 않는다. ``table.set_borders(border_width_mm=)`` 와 같다).

        `fill_color`/`fill_image`/`fill_gradient` 는 OWPML `hc:fillBrush` 의
        선택지(Core XML schema.xml:650) 그대로 상호 배타적이다 — 둘 이상
        주면 typed 거부한다. `fill_image` 는 `doc.media.add_image(...)` 가
        돌려준 `BinaryItem`(또는 그 id 문자열)을 그대로 받는다.

        `sides` 는 면마다 다른 선을 준다: `"left"`·`"right"`·`"top"`·`"bottom"` →
        `{"type", "width_mm", "color"}`(빠진 값은 `border_type`·`border_width_mm`·
        `border_color`; `width_mm` 는 굵기 목록의 mm 수), 또는 그 면에 선을 긋지 않는 `None`.
        대지 않은 면은 `active_borders` 를 따른다. 예: 위아래만 굵고 옆이 트인 칸은
        `sides={"top": {"width_mm": 0.4}, "bottom": {"width_mm": 0.4},
        "left": None, "right": None}`. 모르는 면이나 키(6.x 의 `"width": "0.4 mm"` 포함)는
        `HwpxValueError(code="style-border-side-invalid")`, 모르는 선 종류는 `ValueError`.

        `base_border_fill_id_ref` 를 주면 그 정의를 복사해 `sides` 가 댄 면과 `fill_color` 만
        바꾼다(한 변만 바꾸기). 면 매핑에서 뺀 값(`type`·`width_mm`·`color`)은 기준 면의
        값을 따르고, 대지 않은 면·대각선·채우기·그 밖의 속성은 기준 그대로다. 같은 내용의
        정의가 있으면 그 id, 기준과 같으면 기준 id 를 돌려준다. 이때 `border_color`·
        `border_width_mm`·`border_type`·`active_borders`·`fill_image`·`fill_gradient` 는
        함께 줄 수 없다(`style-border-base-conflict`). 예: 칸 테두리에서 아래 변만 굵게 —
        ``ensure_border_fill(base_border_fill_id_ref=cell.border_fill_id_ref,
        sides={"bottom": {"width_mm": 0.4}})``.
        """

        from .._units import _border_width_mm_text

        border_width = _border_width_mm_text(border_width_mm, argument="border_width_mm")
        if base_border_fill_id_ref is not None:
            uniform = (border_color, border_width, border_type) != ("#BFBFBF", "0.12 mm", "SOLID")
            if uniform or any(v is not None for v in (active_borders, fill_image, fill_gradient)):
                raise HwpxValueError(
                    "base_border_fill_id_ref changes only sides and fill_color",
                    code="style-border-base-conflict",
                    suggestion="Describe each changed side in sides={...}; the rest stays as the base has it.",
                )
            from ...oxml.formatting import derive_border_fill

            return derive_border_fill(
                self._require_header(), base_border_fill_id_ref, sides=sides, fill_color=fill_color
            )

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
            sides=sides,
        )

    def ensure_memo_shape(
        self,
        *,
        width: int = 15591,
        line_width_mm: float = 0.12,
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
        공유하는 조합. 만든 id 는 `doc.notes.set_memo_shape(id, section=i)`
        에 바로 넘길 수 있다(메모 모양은 한/글처럼 구역마다다).

        선 굵기는 *line_width_mm* (mm, 기본 0.12)로 준다. 한/글의 선 굵기(0.1·0.12·0.15·0.2·0.25·0.3·0.4·
        0.5·0.6·0.7·1.0·1.5·2.0·3.0·4.0·5.0 mm) 가운데 하나만 받고(테두리와 같다. 목록에 없는 값은
        ``style-line-width-invalid`` 로 거부), ``lineWidth`` 에는 그 순번(0.12 mm → ``1``)이 적힌다.
        한/글 2024 가 이 값을 1바이트 순번으로 다루는 것을 확인했다(다시 저장하면 283 은 27, "0.6mm" 은
        0 이 되고 목록 안의 순번은 그대로). 읽을 때는 ``doc.styles.memo_shape(id).line_width_mm``.
        6.x 의 ``line_width=``(XML 값을 그대로 적던 인자)는 7.0에서 없어졌다.
        """

        return self._doc.oxml.ensure_memo_shape(
            width=width,
            line_width_mm=line_width_mm,
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
        item_id: str | None = None,
        subst_face: str | None = None,
        subst_type: str | None = None,
        subst_is_embedded: bool = False,
        subst_item_id: str | None = None,
    ) -> str:
        """`hh:fontfaces` 에 *face* 를 선언하고(dedupe) 그 `hh:font` id 를 돌려준다.

        *lang* 을 생략하면 실문서 다수 관행대로 7개 lang 블록
        (HANGUL/LATIN/HANJA/JAPANESE/OTHER/SYMBOL/USER) 전부에 등록한다 —
        등록 뒤 ``ensure_run(font=face)`` 로 참조하면 ``fontRef`` 의 모든
        속성이 유효한 글꼴을 가리킨다. *subst_face*/*subst_type* 을 주면
        `hh:substFont` 대체 글꼴도 함께 선언한다. *item_id*(대체 글꼴은 *subst_item_id*)는
        내장 글꼴 파일의 이진 항목 id 다(``binaryItemIDRef``, ``Font.item_id`` 로 읽는다).
        """

        return self._doc.oxml.ensure_font(
            face,
            lang=lang,
            font_type=font_type,
            is_embedded=is_embedded,
            binary_item_id_ref=item_id,
            subst_face=subst_face,
            subst_type=subst_type,
            subst_is_embedded=subst_is_embedded,
            subst_binary_item_id_ref=subst_item_id,
        )

    def ensure_numbering(
        self, *, kind: str, levels: Sequence[dict[str, str]] | None = None
    ) -> tuple[str, ...]:
        """글머리표/번호 정의를 보장하고 수준마다 그 문단 모양 id 를 돌려준다."""

        return tuple(self._doc.oxml.ensure_numbering(kind=kind, levels=levels))

    def ensure_paragraph_format(
        self,
        *,
        base_para_pr_id_ref: str | int | None = None,
        alignment: str | None = None,
        margins: Mapping[str, int] | None = None,
        heading: Mapping[str, str | int] | None = None,
        border: Mapping[str, str | int] | None = None,
        break_setting: Mapping[str, bool | str] | None = None,
        tab_pr_id_ref: str | None = None,
        line_spacing: "LineSpacing | int | float | None" = None,
        condense: int | None = None,
    ) -> str:
        """요청한 문단 모양의 `paraPr` id 를 보장하고 그 id 를 돌려준다.

        :meth:`ensure_run` 의 문단 쪽 짝이다. 기준(`base_para_pr_id_ref`, 없으면 첫
        `paraPr`)을 복사해 요청한 값만 바꾸고, 내용이 같은 문단 모양이 있으면 그것을
        다시 쓴다. 문단에는 적용하지 않는다 — 돌려받은 id 를 문단의
        `para_pr_id_ref` 나 :meth:`ensure_style` 의 `para_pr_id_ref` 에 넘긴다.
        사람 단위(mm·pt)로 문단에 바로 적용하려면 :meth:`apply_paragraph_format`.

        값은 OWPML 그대로다: `margins` 는 HWPUNIT(`left`·`right`·`intent`·`prev`·
        `next`), `heading` 은 `hh:heading` 속성(`type`·`idRef`·`level`),
        `break_setting` 은 `keep_with_next`·`keep_lines`·`page_break_before`·
        `widow_orphan` 불리언과 줄 나눔 기준 `break_latin_word`·`break_non_latin_word`
        (`"KEEP_WORD"`·`"BREAK_WORD"`·`"HYPHENATION"`), `line_wrap`(`"BREAK"`·
        `"SQUEEZE"`·`"KEEP"`)이다. `line_spacing` 은 `LineSpacing`(종류와 값) 또는
        퍼센트 수(``160`` 은 160%)이고, `condense` 는 공백 최소값
        0~75(%)다. 헤더가 없으면 `HwpxStateError(code="document-header-missing")`.
        """

        return self._require_header().ensure_paragraph_format(
            base_para_pr_id=base_para_pr_id_ref,
            alignment=alignment,
            margins=margins,
            heading=heading,
            border=border,
            break_setting=break_setting,
            tab_pr_id_ref=tab_pr_id_ref,
            line_spacing=line_spacing,
            condense=condense,
        )

    def ensure_style(
        self,
        name: str,
        *,
        style_type: str | None = None,
        eng_name: str | None = None,
        para_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        next_style_id_ref: str | int | None = None,
        lang_id: int | None = None,
        lock_form: bool | None = None,
    ) -> str:
        """이름이 *name* 인 스타일(`hh:style`)의 id 를 보장하고 돌려준다.

        한/글은 스타일을 이름으로 구별하므로 *name* 이 중복 제거의 열쇠다. 같은
        이름의 스타일이 있으면 새로 만들지 않고 그 id 를 돌려주며, `None` 이 아닌
        키워드만 그 스타일에 덮어쓴다. 없으면 새 id 로 만들고(`style_type` 기본
        `"PARA"`), `hh:styles@itemCnt` 를 맞춘다. 같은 이름의 다른 스타일을 따로
        두고 싶으면 먼저 :attr:`names` 로 겹치지 않는 이름을 고른다.

        `next_style_id_ref` 를 자기 자신으로 두려면 한 번 만든 뒤 돌려받은 id 로
        다시 부른다. 헤더가 없으면 `HwpxStateError(code="document-header-missing")`.
        """

        return self._require_header().ensure_style(
            name,
            style_type=style_type,
            eng_name=eng_name,
            para_pr_id_ref=para_pr_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            next_style_id_ref=next_style_id_ref,
            lang_id=lang_id,
            lock_form=lock_form,
        )

    def set_style_format(
        self,
        style: "int | str | Style",
        *,
        size: float | None = None,
        font: str | None = None,
        font_by_lang: "Mapping[str, str] | None" = None,
        color: str | None = None,
        highlight: str | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strike: bool | None = None,
        superscript: bool | None = None,
        subscript: bool | None = None,
        letter_spacing: int | None = None,
        ratio: int | None = None,
        alignment: str | None = None,
        line_spacing: "LineSpacing | int | float | None" = None,
        indent_left_mm: float | None = None,
        indent_right_mm: float | None = None,
        first_line_indent_mm: float | None = None,
        spacing_before_pt: float | None = None,
        spacing_after_pt: float | None = None,
    ) -> None:
        """있는 스타일(이름·영문 이름·id)의 글자 모양·문단 모양을 고친다. 한/글의 스타일 고치기와 같다.

        글자 서식 인자는 ``run.set_format`` 과, 문단 서식 인자는 문단 속성
        (``paragraph.alignment`` …, 여백 mm·간격 pt)과 같다. 스타일은 고친 사본 모양을
        가리키게 되고, 그 스타일을 쓰는 문단 가운데 스타일의 옛 문단 모양을 쓰던 문단과
        그 문단에서 옛 글자 모양을 쓰던 run 이 새 모양을 따른다(그 문단의 줄 배치 캐시를
        지운다). 따로 서식을 준 run, 다른 스타일, 같은 모양을 함께 쓰던 다른 문단은
        그대로다. 아무것도 주지 않으면 ``style-format-empty``.
        """

        from ...oxml.formatting import para_shape_modifier, set_style_format

        char_changes = {
            name: value
            for name, value in (
                ("size", size), ("font", font), ("font_by_lang", font_by_lang), ("color", color),
                ("highlight", highlight), ("bold", bold), ("italic", italic), ("underline", underline),
                ("strike", strike), ("superscript", superscript), ("subscript", subscript),
                ("letter_spacing", letter_spacing), ("ratio", ratio),
            )
            if value is not None
        }
        modifier = para_shape_modifier(
            alignment=alignment,
            line_spacing=line_spacing,
            margins={
                "left": indent_left_mm, "right": indent_right_mm, "intent": first_line_indent_mm,
                "prev": spacing_before_pt, "next": spacing_after_pt,
            },
        )
        if not char_changes and modifier is None:
            raise HwpxValueError(
                "no style format to change",
                code="style-format-empty",
                suggestion="Pass a character format (size, bold, ...) or a paragraph format (alignment, ...).",
            )
        set_style_format(self._doc.oxml, style, char_changes, modifier)

    def set_char_property(
        self,
        char_pr_id_ref: "int | str",
        *,
        size: float | None = None,
        font: str | None = None,
        font_by_lang: "Mapping[str, str] | None" = None,
        color: str | None = None,
        highlight: str | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strike: bool | None = None,
        superscript: bool | None = None,
        subscript: bool | None = None,
        letter_spacing: int | None = None,
        ratio: int | None = None,
    ) -> int:
        """글자 모양 정의(``hh:charPr``) 하나를 **제자리에서** 고친다. 사본을 만들지 않는다.

        인자는 ``run.set_format`` 과 같다. ``run.set_format`` 은 그 run 만 바뀌도록 정의의 사본을
        만들지만, 이것은 정의 자체를 바꾸므로 그 id 를 가리키는 **모든** run·스타일·문단 번호·글머리표가
        함께 바뀐다(예: id 0 은 대개 바탕글과 많은 글이 같이 쓴다). 스타일에 딸린 모양만 고치려면
        :meth:`set_style_format` (한/글의 스타일 고치기)을 쓴다.

        글자 폭이 바뀌므로 그 id 를 쓰는 run 이 있는 문단(본문·표 칸·글상자·머리말·꼬리말·메모·
        바탕쪽)의 줄 배치 캐시를 지운다. 표 칸·캡션의 문단이면 그 표를 품은 문단 것도 지운다.
        문단 번호·글머리표가 이 모양으로 번호를 그리면 번호·글머리표가 있는 문단의 캐시도 지운다.
        캐시를 지운 문단 수를 돌려준다(값이 이미 같으면 0, 아무것도 바꾸지 않음).

        아무 인자도 없으면 ``style-run-format-empty``, 없는 id 는 ``style-definition-not-found``.
        """

        from ...oxml.formatting import set_char_property_in_place

        changes = {
            name: value
            for name, value in (
                ("size", size), ("font", font), ("font_by_lang", font_by_lang), ("color", color),
                ("highlight", highlight), ("bold", bold), ("italic", italic), ("underline", underline),
                ("strike", strike), ("superscript", superscript), ("subscript", subscript),
                ("letter_spacing", letter_spacing), ("ratio", ratio),
            )
            if value is not None
        }
        return set_char_property_in_place(self._doc.oxml, char_pr_id_ref, changes)

    def remove_unused_definitions(
        self,
        kinds: "Sequence[str] | None" = None,
    ) -> dict[str, tuple[str, ...]]:
        """목록 **끝에** 붙은, 아무도 가리키지 않는 서식 정의를 지우고 지운 id 를 돌려준다.

        *kinds* 는 ``"char_properties"``·``"paragraph_properties"``·``"border_fills"``·``"tab_properties"``
        (``doc.styles`` 의 목록 이름) 가운데 고른 것, ``None`` 이면 넷 다. 돌려주는 값은 그 이름마다 지운 id
        (앞에서부터 차례로)다.

        머리(스타일·문단 번호·다른 정의)·구역(머리말·꼬리말·각주·메모·표 칸 포함)·바탕쪽의 어느 요소도
        그 id 를 가리키지 않으면 쓰지 않는 정의다. 목록 끝에서부터 처음으로 쓰이는 정의를 만날 때까지만
        지우고 목록의 첫 정의는 남기므로, 다른 정의의 id 는 바뀌지 않는다(한/글처럼 id 가 빈틈없이 이어진다).
        가운데에 있는 쓰지 않는 정의는 그대로 둔다(한/글은 저장할 때 그것까지 지우고 id 를 다시 매긴다).

        ``run.set_format`` 으로 시험값 사본을 만들었다가 런을 원래 id 로 되돌린 뒤 사본을 걷어 내는
        쓰임에 맞다. 모르는 이름은 ``style-definition-kind-invalid``.
        """

        from ...oxml.formatting import UNUSED_DEFINITION_KINDS, remove_unused_definitions

        if kinds is None:
            chosen = tuple(UNUSED_DEFINITION_KINDS)
        else:
            chosen = (kinds,) if isinstance(kinds, str) else tuple(kinds)
            unknown = [kind for kind in chosen if kind not in UNUSED_DEFINITION_KINDS]
            if unknown or not chosen:
                raise HwpxValueError(
                    f"unknown definition list {unknown!r}" if unknown else "no definition list given",
                    code="style-definition-kind-invalid",
                    context={"kinds": list(chosen)},
                    suggestion="Pass some of " + ", ".join(UNUSED_DEFINITION_KINDS) + ", or leave kinds out.",
                )
        return remove_unused_definitions(self._doc.oxml, chosen)

    def remove_style(
        self, style: "int | str | Style", *, replacement: "int | str | Style | None" = None
    ) -> None:
        """스타일 하나를 지운다.

        그 스타일을 쓰는 문단이 있으면 *replacement* 가 있어야 한다(없으면
        ``HwpxValueError(code="style-in-use")``). 그 문단들은 *replacement* 스타일을
        한/글이 적용하듯 받는다(문단 모양·글자 모양 포함, ``paragraph.style`` 과 같다).
        첫 스타일(id 0, 바탕글)은 지울 수 없다(``style-remove-default``). 한/글처럼
        스타일 id 를 0..N-1 로 이어 두려고 뒤의 스타일 id 를 하나씩 당기고, 본문·바탕쪽
        문단의 ``styleIDRef`` 와 다른 스타일의 ``nextStyleIDRef`` 도 따라 옮긴다
        (지운 스타일을 다음 스타일로 두던 스타일은 *replacement*, 없으면 자기 자신).
        """

        from ...oxml.formatting import remove_style

        remove_style(self._doc.oxml, style, replacement)

    def _require_header(self) -> "HwpxOxmlHeader":
        header = self._primary_header()
        if header is None:
            from ...errors import HwpxStateError

            raise HwpxStateError(
                "document does not contain any headers",
                code="document-header-missing",
            )
        return header

    # -- 문단에 서식을 적용하는 동사 ---------------------------------------

    def apply_paragraph_format(
        self,
        *,
        paragraph: "HwpxOxmlParagraph | int | None" = None,
        paragraphs: "Sequence[HwpxOxmlParagraph | int] | None" = None,
        alignment: str | None = None,
        line_spacing: "LineSpacing | int | float | None" = None,
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
        border_width_mm: float = 0.12,
        tab_stops: Sequence[Mapping[str, object]] | None = None,
        auto_tab_left: bool | None = None,
        auto_tab_right: bool | None = None,
        border: Mapping[str, object] | None = None,
    ) -> "ParagraphFormatResult":
        """문단 서식을 사람 단위(mm·pt·%)로 적용한다.

        대상은 `paragraph`(문단 하나) 또는 `paragraphs`(여럿)이고, 둘 다 없으면 본문 문단
        전부다. 문단은 번호(본문 문단 몇 번째, ``doc.paragraphs`` 의 번호)나 이 문서의 문단
        객체로 준다. 객체로는 본문뿐 아니라 표 셀(중첩 표 포함)·머리말·꼬리말 문단에도
        적용한다 — 예: `paragraph=table.cell(0, 0).paragraphs[0]`,
        `paragraphs=header.paragraphs`. 다른 문서의 문단이나 지운 문단이 섞이면
        아무것도 바꾸기 전에 거부한다(`paragraph-not-in-document`). 결과의
        `paragraphs`에는 본문 문단의 번호만 담기고 `formatted`는 대상 수다.

        `line_spacing` 은 줄 간격 퍼센트 수(``160`` 은 160%) 또는 `LineSpacing`(종류와 값)이다.
        `bottom_border=True` 의 선은 `border_color`·`border_width_mm`(mm, 한/글 굵기 목록의
        값만 — 없는 값은 바꾸기 전에 ``style-line-width-invalid``)로 긋는다.

        `border`는 문단 테두리 매핑이다: `sides`(기본 네 면 "left"·"right"·
        "top"·"bottom"), `color`("#000000"), `width_mm`(0.12, 굵기 목록의 mm 수), `type`
        ("SOLID"), `offset_mm`(글과의 간격 mm, 수 하나 또는 `(왼쪽, 오른쪽, 위, 아래)`, 기본 0),
        `connect`·`ignore_margin`(기본 False). `connect=True`면 한컴이 같은 문단
        모양을 쓰는 연속 문단을 단·쪽을 넘는 상자 하나로 그린다(문단 테두리 연결).
        상자 안의 빈 문단에도 같은 서식을 주면 상자가 끊기지 않는다.
        `bottom_border=True`는 아래 한 면만 켜는 예전 형태다.

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
            paragraph=paragraph,
            paragraphs=paragraphs,
            alignment=alignment,
            line_spacing=line_spacing,
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
            border_width_mm=border_width_mm,
            tab_stops=tab_stops,
            auto_tab_left=auto_tab_left,
            auto_tab_right=auto_tab_right,
            border=border,
        )

    def apply_list_format(
        self,
        *,
        paragraph: "HwpxOxmlParagraph | int | None" = None,
        paragraphs: "Sequence[HwpxOxmlParagraph | int] | None" = None,
        kind: str = "bullet",
        level: int = 1,
        bullet_char: str | None = None,
        number_format: str | None = None,
        start: int | None = None,
        continue_list: bool = False,
    ) -> "ListFormatResult":
        """글머리표/번호 문단 서식을 적용한다.

        대상은 :meth:`apply_paragraph_format` 과 같다: `paragraph`(하나)나 `paragraphs`(여럿)에
        번호(본문 문단 몇 번째)나 문단 객체를 주고, 둘 다 없으면 본문 문단 전부다. 결과의
        `paragraphs` 에는 본문 문단의 번호만 담긴다.

        기본 모양은 한/글 새 목록과 다르다: 글머리표는 1수준 ``-``·2수준 ``○``(한/글은
        ``●``), 번호 2수준은 ``1.1.``(한/글은 ``가.``)·3수준은 ``1.1.1.``(한/글은 ``1)``).
        글머리표를 한/글처럼 하려면 ``bullet_char="●"``를 준다.

        번호 목록은 부를 때마다 새 번호 정의를 만들고, 한/글은 번호 정의마다 번호를
        센다. 그래서 문단마다 따로 부르면 목록이 매번 1부터 다시 시작한다. 이어지는
        목록은 ``paragraphs=[...]``로 한 번에 적용하거나 ``continue_list=True``를
        준다. 그러면 대상 문단 앞의 마지막 번호 목록(개요는 개요)에 이어 번호를 매긴다.
        앞에 그런 목록이 없으면 새 목록을 만든다. 앞 목록의 번호 정의에 없는 더 깊은
        수준이면 그 수준의 모양을 정의에 더한다(한/글은 없는 수준에 번호를 그리지 않는다).
        글머리표에는 번호가 없어 바뀌는 것이 없다. ``number_format``·``start``와 함께 주면 ``style-list-continue-conflict``로
        거부한다.
        """

        from .. import layout as _layout

        return _layout.set_list_format(
            self._doc,
            paragraph=paragraph,
            paragraphs=paragraphs,
            kind=kind,
            level=level,
            bullet_char=bullet_char,
            number_format=number_format,
            start=start,
            continue_list=continue_list,
        )

    @staticmethod
    def _label(style: "Style | None") -> str:
        if style is None:  # pragma: no cover - 방어
            return ""
        return (style.name or style.eng_name or "").strip()
