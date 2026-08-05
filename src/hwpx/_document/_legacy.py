# SPDX-License-Identifier: Apache-2.0
"""6.0 이주 창(migration window)을 여는 레거시 파사드.

`HwpxDocument`의 공개 표면은 5.x에서 102개였다. 6.0은 그것을 루트 34개로
줄이고 나머지를 도메인 네임스페이스(`doc.styles`, `doc.page`, `doc.fields` …)로
옮긴다. 이 모듈은 **옮겨 간 79개 이름을 루트에 그대로 남겨 두는 위임 shim**이며,
호출하면 행선지를 담은 `DeprecationWarning`을 낸다.

왜 별도 클래스인가. `tests/test_document_facade_surface.py`의 락 생성기는
`vars(HwpxDocument)` — **클래스 자기 `__dict__`만** 본다(상속 멤버는 안 잡힌다).
shim을 베이스 클래스에 두면 루트 락은 34개로 정직하게 줄고, shim은 사라지지
않고 `tests/data/document_legacy_shims.json`이라는 **별도 락**에 계속 세어진다.
감추는 게 아니라 분리해서 센다 — 그래서 두 번째 락은 감소만 허용하는
ratchet이고 `describe_capabilities()`가 `legacyShimCount`로 노출한다.

7.0에서 이 모듈 전체가 삭제된다(`docs/stable-api.md`의 최소 deprecation window
— 한 major에서 경고, 그다음 major에서 제거).

shim 본문은 5.8.0 `document.py`의 것을 **그대로** 옮긴 것이다. 위임 대상
(`_document/*.py` 소유 모듈)도 바뀌지 않았다. 6.0에서 이 79개 호출의
동작은 경고가 하나 더 붙는 것 말고는 5.x와 동일하다.
"""

from __future__ import annotations

import functools
import inspect
import warnings
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterator,
    Mapping,
    Sequence,
    TypeVar,
    cast,
)

from ..oxml import (
    Bullet,
    GenericElement,
    HwpxOxmlInlineObject,
    HwpxOxmlMemo,
    HwpxOxmlNote,
    HwpxOxmlParagraph,
    HwpxOxmlRun,
    HwpxOxmlSection,
    HwpxOxmlSectionHeaderFooter,
    HwpxOxmlShape,
    HwpxOxmlTable,
    MemoShape,
    ParagraphProperty,
    RunStyle,
    Style,
    TrackChange,
    TrackChangeAuthor,
)
from ..errors import HwpxValueError
from . import _resolve
from . import fields as _fields
from . import layout as _layout
from . import media as _media
from . import memos as _memos
from . import persistence as _persistence
from . import shapes as _shapes
from . import tracked as _tracked

if TYPE_CHECKING:
    from ..form_fit.policy import FitPolicy
    from ..objects.binary_item import BinaryItem
    from ..oxml import (
        HwpxOxmlDocument,
        HwpxOxmlHeader,
        HwpxOxmlHistory,
        HwpxOxmlMasterPage,
        HwpxOxmlVersion,
    )
    from ..tools.table_navigation import (
        SearchDirection,
        TableFillResult,
        TableLabelSearchResult,
        TableMapResult,
    )

_F = TypeVar("_F", bound=Callable[..., Any])

#: shim이 가리키는 제거 예정 major. 락(`document_legacy_shims.json`)과
#: `describe_capabilities()`가 이 값을 읽는다.
LEGACY_REMOVED_IN = "7.0"


def _takes_section_pair(func: Callable[..., Any]) -> bool:
    """`section` / `section_index` 쌍을 받는 서명인가.

    `remove_section(section)` 처럼 짝이 없는 것은 제외한다 — 그쪽은 애초에
    ``HwpxOxmlSection | int`` 를 받는 다른 계약이다.
    """

    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):  # pragma: no cover - 내장/C 함수 방어
        return False
    return "section" in params and "section_index" in params


def _moved(replacement: str, *, removed_in: str = LEGACY_REMOVED_IN) -> Callable[[_F], _F]:
    """호출 시 행선지를 알려 주는 위임 shim으로 감싼다.

    `functools.wraps`가 `__wrapped__`를 남기므로 `inspect.signature`는 원본
    시그니처를 그대로 보고한다 — 락이 기록하는 시그니처가 5.x와 한 글자도
    달라지지 않는다.

    부수적으로 **`section=` 관대 수용의 초크포인트**이기도 하다. 5.x에서
    `doc.set_header_text("x", section=0)` 은 `AttributeError: 'int' object has
    no attribute 'properties'` 로 터졌다. 여기서 한 번 정규화하면 소유 모듈
    (`_document/layout.py` 등)은 항상 해석된 섹션 객체만 받는다. 경고와
    정규화가 한 데코레이터에 있는 것은 결합이지만, 대안은 28개 shim 본문에
    같은 두 줄을 복사하는 것이다 — 초크포인트가 하나인 쪽이 낫다.
    """

    def decorate(func: _F) -> _F:
        normalizes_section = _takes_section_pair(func)

        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            warnings.warn(
                f"HwpxDocument.{func.__name__}은(는) python-hwpx 6.0에서 "
                f"{replacement}(으)로 이동했습니다. {removed_in}에서 제거됩니다. "
                f"자세한 내용: docs/migration-6.0.md",
                DeprecationWarning,
                stacklevel=2,
            )
            if normalizes_section and (
                kwargs.get("section") is not None or kwargs.get("section_index") is not None
            ):
                kwargs["section"] = _resolve.resolve_section(
                    self,
                    kwargs.get("section"),
                    kwargs.get("section_index"),
                    caller=func.__name__,
                )
                kwargs["section_index"] = None
            return func(self, *args, **kwargs)

        wrapper.__hwpx_moved_to__ = replacement  # type: ignore[attr-defined]
        wrapper.__hwpx_removed_in__ = removed_in  # type: ignore[attr-defined]
        wrapper.__hwpx_resolves_section__ = normalizes_section  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


class _LegacyFacade:
    """5.x 루트 표면 중 6.0에서 이동·강등된 79개 이름.

    `HwpxDocument`가 이 클래스를 상속한다. 본문은 `self._root` 등 구현
    상태를 쓰는데, 그 상태는 `HwpxDocument.__init__`이 만든다 — 이 클래스는
    단독으로 인스턴스화되지 않는다.
    """

    if TYPE_CHECKING:
        # `HwpxDocument`가 소유하는 구현 상태·비공개 헬퍼. 타입 검사기가
        # shim 본문을 검사할 수 있도록 여기서 선언만 한다.
        _root: HwpxOxmlDocument
        _package: Any
        _FORMAT_TO_MEDIA_TYPE: dict[str, str]

        def _iter_form_field_matches(self) -> list[dict[str, Any]]: ...

    @_moved("doc.refs.add_bookmark")
    def add_bookmark(
        self,
        name: str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a bookmark marker in the document.

        Returns the ``<hp:ctrl>`` wrapper element.
        """

        return _layout.add_bookmark(
            self,
            name=name,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.shapes.add_chart")
    def add_chart(
        self,
        chart_xml: bytes | str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        size: tuple[int, int] | None = None,
        treat_as_char: bool = False,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a native chart from ECMA-376 chartML. **Experimental contract.**

        Stores *chart_xml* as a ``Chart/chartN.xml`` package part and emits the
        real-Hancom ``<hp:chart>`` anchor referencing it via ``chartIDRef``
        (contract: ``specs/055-chart-authoring/evidence/p0/chart-contract.md``).
        Hancom draws the chart from the chartML alone — no OLE fallback or
        pre-rendered image is written. The chartML must parse and carry the
        ``c:chartSpace`` root (typed rejection otherwise), and the created
        anchor is re-read through the standard section scan — creation fails
        loudly if the standard consumer would not see it.

        Args:
            chart_xml: ECMA-376 chartML document (``c:chartSpace``).
            paragraph: Target paragraph (e.g. inside a table cell). When
                omitted a new paragraph is appended to *section*.
            size: Optional ``(width, height)`` HWPUNIT pair for the anchor.
            treat_as_char: ``True`` places the chart inline in the text flow;
                default mirrors the render-verified gold float placement.
        """

        return _shapes.add_chart(
            self,
            chart_xml,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            size=size,
            treat_as_char=treat_as_char,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.fields.add_check_box")
    def add_check_box(
        self,
        caption: str,
        *,
        checked: bool = False,
        name: str | None = None,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> dict[str, Any]:
        """Create a check-box form object (체크박스). **Experimental contract.**

        Real Hancom draws ☑ when *checked* and □ otherwise, with *caption* beside
        the box and present in the rendered text layer. The created object is
        read back through :meth:`list_check_boxes` with no special-casing.

        Note:
            Korean government forms specify a text ``[ ]`` + √ convention rather
            than this form object (시행규칙 별표 4 제10호), so this primitive is
            for forms that genuinely use Hancom check boxes — not for 공문서.

        Args:
            caption: Label drawn beside the box (non-empty).
            checked: Initial state.
            name: Object name; generated when omitted.
            paragraph: Target paragraph (e.g. a table cell). A new paragraph is
                appended to *section* when omitted.
        """

        return _fields.add_check_box(
            self,
            caption,
            checked=checked,
            name=name,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.shapes.add_control")
    def add_control(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        control_type: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert a control inline object into a new paragraph.

        This is a low-level escape hatch: an ``<hp:ctrl>`` carries no meaning
        of its own — the control it represents is its child element
        (``colPr``, ``bookmark``, ``fieldBegin``, …).  Until the caller
        appends one, the element is empty and **Hancom refuses to open the
        document**, so a :class:`UserWarning` is raised.

        For the controls this package builds, prefer :meth:`set_columns`,
        :meth:`add_bookmark`, and :meth:`add_hyperlink`, which write the full
        child structure.
        """

        return _shapes.add_control(
            self,
            section=section,
            section_index=section_index,
            attributes=attributes,
            control_type=control_type,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )

    @_moved("doc.shapes.add_ellipse")
    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert an ellipse drawing shape.

        Dimensions are in HWPUNIT.
        """

        return _shapes.add_ellipse(
            self,
            width=width,
            height=height,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.notes.add_endnote")
    def add_endnote(
        self,
        text: str,
        paragraph: HwpxOxmlParagraph | None = None,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Add an endnote to an existing paragraph, or create a new one."""

        return _shapes.add_endnote(
            self,
            text=text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.shapes.add_equation")
    def add_equation(
        self,
        script: str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        base_unit: int = 1100,
        size: tuple[int, int] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert an inline equation from an EqEdit script. **Experimental contract.**

        Emits the real-Hancom ``<hp:equation>`` shape (contract:
        ``specs/054-equation-authoring/evidence/p0/equation-contract.md``): the
        EqEdit source is stored verbatim in ``<hp:script>``, no layout cache is
        written (Hancom re-lays-out on open), and the shape is inline so it
        renders in the page flow. The created element is immediately re-read
        through the standard section scan — creation fails loudly if the
        standard consumer would not see it (no special-casing by design).

        To author from LaTeX, convert first (typed refusal outside the
        verified token set)::

            from hwpx.equation import latex_to_eqedit
            doc.add_equation(latex_to_eqedit(r"\\frac{a}{b}"))

        Args:
            script: EqEdit script stored as-is (e.g. ``{a} over {b}``).
            paragraph: Target paragraph (e.g. inside a table cell). When
                omitted a new paragraph is appended to *section*.
            base_unit: Equation base font size in 1/100 pt.
            size: Optional explicit ``(width, height)`` HWPUNIT pair;
                defaults to a proportional estimate (Hancom re-measures).
        """

        return _shapes.add_equation(
            self,
            script,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            base_unit=base_unit,
            size=size,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.notes.add_footnote")
    def add_footnote(
        self,
        text: str,
        paragraph: HwpxOxmlParagraph | None = None,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Add a footnote to an existing paragraph, or create a new one.

        When *paragraph* is ``None`` a new paragraph is appended to the given
        (or last) section.
        """

        return _shapes.add_footnote(
            self,
            text=text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.fields.add")
    def add_form_field(
        self,
        name: str,
        *,
        prompt: str = "",
        memo: str = "",
        editable: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> dict[str, Any]:
        """Create a click-here (누름틀) form field. **Experimental contract.**

        Emits the real-Hancom CLICKHERE shape (안내문 placeholder run included)
        so the created field is indistinguishable from a Hancom-authored one:
        ``list_form_fields``/``fill_form_field`` recognize it with no
        special-casing, and real Hancom Office enumerates and fills it.

        Args:
            name: Field name (non-empty).
            prompt: 안내문 shown while the field is empty. Screen-only —
                Hancom does not print it.
            memo: Help text (``HelpState``).
            paragraph: Target paragraph (e.g. inside a table cell). When
                omitted a new paragraph is appended to *section*.

        Returns:
            The created field's payload, same shape as a ``list_form_fields``
            entry.
        """

        return _fields.add_form_field(
            self,
            name,
            prompt=prompt,
            memo=memo,
            editable=editable,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.refs.add_hyperlink")
    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a hyperlink (fieldBegin + text + fieldEnd).

        The display text follows the Hancom convention (blue underlined)
        unless ``char_pr_id_ref`` overrides it.

        Returns the ``<hp:ctrl>`` wrapper containing the ``<hp:fieldBegin>``.
        """

        return _layout.add_hyperlink(
            self,
            url=url,
            display_text=display_text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.media.add_image")
    def add_image(
        self,
        image_data: bytes,
        image_format: str,
        *,
        item_id: str | None = None,
    ) -> str:
        """Embed an image file and return the manifest item id.

        Args:
            image_data: Raw image bytes.
            image_format: Image format extension (``jpg``, ``png``, …).
            item_id: Optional explicit manifest item id.  When omitted an
                     auto-generated ``BIN####`` id is used.

        Returns:
            The manifest item id that can be passed to
            ``binaryItemIDRef`` when constructing a ``<hp:pic>`` element.
        """

        return _media.add_image(
            self,
            image_data=image_data,
            image_format=image_format,
            item_id=item_id,
        )

    @_moved("doc.shapes.add_line")
    def add_line(
        self,
        start_x: int = 0,
        start_y: int = 0,
        end_x: int = 14400,
        end_y: int = 0,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a line drawing shape.

        Coordinates are in HWPUNIT (7200 per inch).
        """

        return _shapes.add_line(
            self,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            line_color=line_color,
            line_width=line_width,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.notes.add_memo")
    def add_memo(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlMemo:
        """Create a memo entry inside *section* (or the last section by default)."""

        return _memos.add_memo(
            self,
            text,
            section=section,
            section_index=section_index,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    @_moved("doc.notes.add_memo(anchor=...)")
    def add_memo_with_anchor(
        self,
        text: str = "",
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        paragraph_text: str | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        anchor_char_pr_id_ref: str | int | None = None,
    ) -> tuple[HwpxOxmlMemo, HwpxOxmlParagraph, str]:
        """Create a memo and ensure it is visible by anchoring a MEMO field."""

        return _memos.add_memo_with_anchor(
            self,
            text,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
            paragraph_text=paragraph_text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            anchor_char_pr_id_ref=anchor_char_pr_id_ref,
        )

    @_moved("doc.shapes.add_rectangle")
    def add_rectangle(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a rectangle drawing shape.

        Dimensions are in HWPUNIT.  *ratio* controls corner roundness
        (0 = sharp, 50 = semicircle).
        """

        return _shapes.add_rectangle(
            self,
            width=width,
            height=height,
            ratio=ratio,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.shapes.add_raw")
    def add_shape(
        self,
        shape_type: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert an inline shape into a new paragraph.

        This is a low-level escape hatch: it writes the element and the
        attributes it is handed and nothing else, so the result is **not a
        document Hancom can open** until the caller supplies the required
        OWPML children (``offset``, ``orgSz``, ``curSz``, ``sz``, ``pos`` and
        the type-specific geometry).  A :class:`UserWarning` is raised while
        they are missing.

        For LINE / RECT / ELLIPSE shapes, prefer :meth:`add_line`,
        :meth:`add_rectangle`, and :meth:`add_ellipse`, which build the full
        child structure.
        """

        return _shapes.add_shape(
            self,
            shape_type=shape_type,
            section=section,
            section_index=section_index,
            attributes=attributes,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )

    @_moved("doc.tracking.add_change")
    def add_track_change(
        self,
        change_type: str,
        *,
        author_name: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        """Add tracked-change header metadata and return the new change id."""

        return _tracked.add_track_change(
            self,
            change_type,
            author_name=author_name,
            date=date,
        )

    @_moved("doc.tracking.delete")
    def add_tracked_delete(
        self,
        paragraph: HwpxOxmlParagraph,
        *,
        match: str | None = None,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> int:
        """Wrap paragraph text or the first matching substring in delete marks."""

        return _tracked.add_tracked_delete(
            self,
            paragraph,
            match=match,
            author=author,
            date=date,
        )

    @_moved("doc.tracking.insert")
    def add_tracked_insert(
        self,
        paragraph: HwpxOxmlParagraph,
        text: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> int:
        """Append tracked inserted *text* to *paragraph* and return its change id."""

        return _tracked.add_tracked_insert(
            self,
            paragraph,
            text,
            author=author,
            date=date,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.tracking.replace")
    def add_tracked_replace(
        self,
        paragraph: HwpxOxmlParagraph,
        old: str,
        new: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> tuple[int, int]:
        """Represent a replacement as tracked delete of *old* plus tracked insert of *new*."""

        return _tracked.add_tracked_replace(
            self,
            paragraph,
            old,
            new,
            author=author,
            date=date,
        )

    @_moved("doc.notes.attach")
    def attach_memo_field(
        self,
        paragraph: HwpxOxmlParagraph,
        memo: HwpxOxmlMemo,
        *,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        char_pr_id_ref: str | int | None = None,
    ) -> str:
        """Attach a MEMO field control to *paragraph* so Hangul shows *memo*."""

        return _memos.attach_memo_field(
            self,
            paragraph,
            memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=char_pr_id_ref,
        )

    @_moved("doc.styles.border_fill")
    def border_fill(self, border_fill_id_ref: int | str | None) -> GenericElement | None:
        """Return the border fill definition referenced by *border_fill_id_ref*."""

        return self._root.border_fill(border_fill_id_ref)

    @property
    @_moved("doc.styles.border_fills")
    def border_fills(self) -> dict[str, GenericElement]:
        """Return border fill definitions declared in the headers."""

        return self._root.border_fills

    @_moved("doc.styles.bullet")
    def bullet(self, bullet_id_ref: int | str | None) -> Bullet | None:
        """Return the bullet definition referenced by *bullet_id_ref*."""

        return self._root.bullet(bullet_id_ref)

    @property
    @_moved("doc.styles.bullets")
    def bullets(self) -> dict[str, Bullet]:
        """Return bullet definitions declared in header reference lists."""

        return self._root.bullets

    @property
    @_moved("doc.styles.char_properties")
    def char_properties(self) -> dict[str, RunStyle]:
        """Return the resolved character style definitions available to the document."""

        return self._root.char_properties

    @_moved("doc.styles.char_property")
    def char_property(self, char_pr_id_ref: int | str | None) -> RunStyle | None:
        """Return the style referenced by *char_pr_id_ref* if known."""

        return self._root.char_property(char_pr_id_ref)

    @_moved("doc.styles.ensure_border_fill")
    def ensure_border_fill(
        self,
        *,
        border_color: str = "#BFBFBF",
        border_width: str = "0.12 mm",
        fill_color: str | None = None,
        fill_image: "str | BinaryItem | Mapping[str, object] | None" = None,
        fill_gradient: Mapping[str, object] | None = None,
        active_borders: Sequence[str] | None = None,
        border_type: str = "SOLID",
    ) -> str:
        """Return a borderFill id matching the requested border/fill attributes.

        ``border_type`` selects the OWPML line style (``SOLID``, ``DASH``,
        ``DOT``, ``DOUBLE_SLIM``, ``WAVE``, …); values outside the OWPML
        vocabulary are rejected. ``fill_color``/``fill_image``/``fill_gradient``
        are mutually exclusive (OWPML ``hc:fillBrush`` choice).
        """

        from .ns.styles import _resolve_fill_gradient, _resolve_fill_image

        given = sum(1 for v in (fill_color, fill_image, fill_gradient) if v is not None)
        if given > 1:
            raise HwpxValueError(
                "fill_color/fill_image/fill_gradient are mutually exclusive",
                code="style-border-fill-conflict",
                suggestion="Pass exactly one of fill_color, fill_image, fill_gradient.",
            )
        return self._root.ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            fill_color=fill_color,
            fill_image=_resolve_fill_image(fill_image),
            fill_gradient=_resolve_fill_gradient(fill_gradient),
            active_borders=active_borders,
            border_type=border_type,
        )

    @_moved("doc.styles.ensure_numbering")
    def ensure_numbering(
        self,
        *,
        kind: str,
        levels: Sequence[dict[str, str]] | None = None,
    ) -> list[str]:
        """Return paragraph property ids for bullet or numbered-list levels."""

        return self._root.ensure_numbering(kind=kind, levels=levels)

    @_moved("doc.styles.ensure_run")
    def ensure_run_style(
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
        """Return a ``charPr`` identifier matching the requested flags.

        5.4.0 additions (render-verified vocabulary; invalid values are
        rejected): ``underline_shape``/``underline_color``, ``strike_shape``,
        ``ratio`` (장평 %), ``letter_spacing`` (자간 %), ``shadow`` (drop
        shadow colour), ``script`` (``"sup"``/``"sub"``).
        """

        return self._root.ensure_run_style(
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

    @_moved("doc.text.html")
    def export_html(self, **kwargs: object) -> str:
        """Export content as HTML.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_html`."""

        return _persistence.export_html(
            self,
            **kwargs,
        )

    @_moved("doc.text.markdown")
    def export_markdown(self, **kwargs: object) -> str:
        """Export content as Markdown.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_markdown`."""

        return _persistence.export_markdown(
            self,
            **kwargs,
        )

    @_moved("doc.text.markdown(rich=True)")
    def export_rich_markdown(self, **kwargs: object) -> str:
        """Export rich Markdown preserving inline styles, tables, footnotes, hyperlinks, images, and shape text.

        Keyword args forwarded to :func:`~hwpx.tools.markdown_export.export_markdown`.
        """

        return _persistence.export_rich_markdown(
            self,
            **kwargs,
        )

    @_moved("doc.text.plain")
    def export_text(self, **kwargs: object) -> str:
        """Export content as plain text.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_text`."""

        return _persistence.export_text(
            self,
            **kwargs,
        )

    @_moved("doc.tables.fill_by_path")
    def fill_by_path(
        self,
        mappings: Mapping[str, str],
    ) -> TableFillResult:
        """Fill table cells using ``label > direction > ...`` navigation paths."""

        return _fields.fill_by_path(self, mappings)

    @_moved("doc.fields.fill")
    def fill_form_field(
        self,
        value: str,
        *,
        field_index: int | None = None,
        field_id: str | None = None,
        name: str | None = None,
        fit_policy: "FitPolicy | None" = None,
        box_width: int | None = None,
        font_pt: float | None = None,
    ) -> dict[str, Any]:
        """Fill a native form/click-here field while preserving surrounding runs.

        When *fit_policy* and *box_width* (the field's usable width, in HWPUNIT)
        are supplied, the value is run through the FormFit engine (plan §2 C): it
        is measured against the box and may be shrunk/​truncated, the inserted run
        is re-pointed at a smaller ``charPr`` for a real (oracle-visible) shrink,
        and the response carries a ``fit`` verdict with ``ok`` propagated from it.
        Without a box width a native field has no reliable geometry, so the fit is
        reported low-confidence and never hard-fails (measurement honesty).
        """

        return _fields.fill_form_field(
            self,
            value,
            field_index=field_index,
            field_id=field_id,
            name=name,
            fit_policy=fit_policy,
            box_width=box_width,
            font_pt=font_pt,
        )

    @_moved("doc.tables.find_cell_by_label")
    def find_cell_by_label(
        self,
        label_text: str,
        direction: str = "right",
    ) -> TableLabelSearchResult:
        """Return every label/target cell pair that matches *label_text*."""

        from ..tools.table_navigation import find_cell_by_label

        return find_cell_by_label(
            self,
            label_text,
            direction=cast("SearchDirection", direction),
        )

    @_moved("doc.text.find_runs")
    def find_runs_by_style(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> list[HwpxOxmlRun]:
        """Return runs matching the requested style criteria."""

        matches: list[HwpxOxmlRun] = []
        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None

        for run in self.iter_runs():
            if target_char is not None:
                run_char = (run.char_pr_id_ref or "").strip()
                if run_char != target_char:
                    continue
            style = run.style
            if text_color is not None:
                if style is None or style.text_color() != text_color:
                    continue
            if underline_type is not None:
                if style is None or style.underline_type() != underline_type:
                    continue
            if underline_color is not None:
                if style is None or style.underline_color() != underline_color:
                    continue
            matches.append(run)
        return matches

    @_moved("doc.tables.map")
    def get_table_map(self) -> TableMapResult:
        """Return compact metadata for every table in document order."""

        from ..tools.table_navigation import get_table_map

        return get_table_map(self)

    @property
    @_moved("doc.parts.headers")
    def headers(self) -> list[HwpxOxmlHeader]:
        """Return the header parts referenced by the document."""
        return self._root.headers

    @property
    @_moved("doc.parts.histories")
    def histories(self) -> list[HwpxOxmlHistory]:
        """Return document history parts referenced by the manifest."""
        return self._root.histories

    @_moved("doc.text.runs")
    def iter_runs(self) -> Iterator[HwpxOxmlRun]:
        """Yield every run element contained in the document."""

        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                yield run

    @_moved("doc.fields.check_boxes")
    def list_check_boxes(self) -> list[dict[str, Any]]:
        """Return check-box form objects (체크박스) in document order.

        Each entry carries ``index``/``name``/``caption``/``checked``.
        """

        return _fields.list_check_boxes(self)

    @_moved("doc.fields.all")
    def list_form_fields(self) -> list[dict[str, Any]]:
        """Return native form/click-here fields in document order.

        The result intentionally excludes memo and hyperlink fields because
        those are annotation/navigation mechanisms rather than fillable form
        slots.
        """

        return _fields.list_form_fields(self)

    @_moved("doc.media.images")
    def list_images(self) -> list[dict[str, str]]:
        """Return metadata dicts for all embedded binary data items.

        Each dict contains the ``<hh:binItem>`` attributes (``id``, ``Type``,
        ``BinData``, ``Format``, …).
        """

        return _media.list_images(self)

    @property
    @_moved("doc.parts.master_pages")
    def master_pages(self) -> list[HwpxOxmlMasterPage]:
        """Return the master-page parts declared in the manifest."""
        return self._root.master_pages

    @_moved("doc.styles.memo_shape")
    def memo_shape(self, memo_shape_id_ref: int | str | None) -> MemoShape | None:
        """Return the memo shape definition referenced by *memo_shape_id_ref*."""

        return self._root.memo_shape(memo_shape_id_ref)

    @property
    @_moved("doc.styles.memo_shapes")
    def memo_shapes(self) -> dict[str, MemoShape]:
        """Return memo shapes available in the header reference lists."""

        return self._root.memo_shapes

    @property
    @_moved("doc.notes.memos")
    def memos(self) -> list[HwpxOxmlMemo]:
        """Return all memo entries declared in every section."""

        memos: list[HwpxOxmlMemo] = []
        for section in self._root.sections:
            memos.extend(section.memos)
        return memos

    @_moved("doc.tables.merge_cells")
    def merge_table_cells(
        self,
        table: HwpxOxmlTable,
        cell_range: str,
    ) -> Any:
        """Merge a table cell range using spreadsheet notation such as ``A1:C1``."""

        return table.merge_cells(cell_range)

    @property
    @_moved("doc.styles.paragraph_properties")
    def paragraph_properties(self) -> dict[str, ParagraphProperty]:
        """Return paragraph property definitions declared in headers."""

        return self._root.paragraph_properties

    @_moved("doc.styles.paragraph_property")
    def paragraph_property(
        self, para_pr_id_ref: int | str | None
    ) -> ParagraphProperty | None:
        """Return the paragraph property referenced by *para_pr_id_ref*."""

        return self._root.paragraph_property(para_pr_id_ref)

    @_moved("doc.media.picture_references")
    def picture_references(self) -> list[dict[str, Any]]:
        """Return body picture references in document order."""

        return _media.picture_references(self)

    @_moved("doc.page.remove_footer")
    def remove_footer(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the footer linked to *page_type* from the requested section if present."""

        return _layout.remove_footer(
            self,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.page.remove_header")
    def remove_header(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the header linked to *page_type* from the requested section if present."""

        return _layout.remove_header(
            self,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.media.remove_image")
    def remove_image(self, item_id: str) -> bool:
        """Remove an embedded image by its manifest item id.

        This removes the binary data from the ZIP, the manifest entry, and
        the header binItem entry.

        Returns:
            ``True`` if any component was removed.
        """

        return _media.remove_image(
            self,
            item_id=item_id,
        )

    @_moved("doc.notes.remove_memo")
    def remove_memo(self, memo: HwpxOxmlMemo) -> None:
        """Remove *memo* from the section it belongs to."""

        return _memos.remove_memo(self, memo)

    @_moved("paragraph.remove()")
    def remove_paragraph(
        self,
        paragraph: HwpxOxmlParagraph | int,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Remove a paragraph from the document.

        *paragraph* may be a :class:`HwpxOxmlParagraph` instance or an
        integer index into the paragraphs of the specified (or last)
        section.

        Raises ``ValueError`` if the target section would become empty.
        """
        self._root.remove_paragraph(
            paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.media.replace_picture")
    def replace_picture(
        self,
        image_data: bytes,
        image_format: str,
        *,
        picture_index: int = 0,
        binary_item_id_ref: str | None = None,
        remove_orphaned: bool = True,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        """Replace a body picture's image asset while preserving its geometry.

        The existing ``<hp:pic>`` element is left in place.  Only the child
        ``<hc:img>`` ``binaryItemIDRef`` is changed, so size, position, crop,
        rotation, and wrapping geometry remain untouched.
        """

        return _media.replace_picture(
            self,
            image_data=image_data,
            image_format=image_format,
            picture_index=picture_index,
            binary_item_id_ref=binary_item_id_ref,
            remove_orphaned=remove_orphaned,
            item_id=item_id,
        )

    @_moved("doc.text.replace")
    def replace_text_in_runs(
        self,
        search: str,
        replacement: str,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
        limit: int | None = None,
    ) -> int:
        """Replace occurrences of *search* in runs matching the provided style filters."""

        if not search:
            raise HwpxValueError(
            "search must be a non-empty string",
            code="text-search-empty",
            context={"search": search},
            suggestion="Pass the substring to replace.",
        )

        replacements = 0
        runs = self.find_runs_by_style(
            text_color=text_color,
            underline_type=underline_type,
            underline_color=underline_color,
            char_pr_id_ref=char_pr_id_ref,
        )

        for run in runs:
            remaining = None
            if limit is not None:
                remaining = limit - replacements
                if remaining <= 0:
                    break
            original_char_pr = run.char_pr_id_ref
            replaced_here = run.replace_text(
                search,
                replacement,
                count=remaining,
            )
            if replaced_here and original_char_pr is not None:
                # Ensure the run retains its original formatting reference even
                # if XML nodes were rewritten during substitution.
                run.char_pr_id_ref = original_char_pr
            replacements += replaced_here
            if limit is not None and replacements >= limit:
                break
        return replacements

    @_moved("doc.fields.check_box(...).checked")
    def set_check_box(
        self,
        checked: bool,
        *,
        index: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Set a check box's state, selecting it by ``index`` or ``name``.

        Exactly one selector is required; an ambiguous name is refused rather
        than guessed.
        """

        return _fields.set_check_box(self, checked, index=index, name=name)

    @_moved("doc.page.set_columns")
    def set_columns(
        self,
        col_count: int = 2,
        *,
        col_type: str = "NEWSPAPER",
        layout: str = "LEFT",
        same_size: bool = True,
        same_gap: int = 1200,
        column_widths: "Sequence[tuple[int, int]] | None" = None,
        separator_type: str | None = None,
        separator_width: str | None = None,
        separator_color: str | None = None,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a column definition control.

        This adds a ``<hp:ctrl><hp:colPr>`` element to the specified paragraph.
        Text that follows will be laid out in the specified number of columns.

        Args:
            col_count: Number of columns (1–255).
            col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
            same_gap: Gap in HWPUNIT (7200 = 1 inch).
            separator_type: Optional column separator line type (e.g. ``SOLID``).
        """

        return _layout.set_columns(
            self,
            col_count=col_count,
            col_type=col_type,
            layout=layout,
            same_size=same_size,
            same_gap=same_gap,
            column_widths=column_widths,
            separator_type=separator_type,
            separator_width=separator_width,
            separator_color=separator_color,
            paragraph=paragraph,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.page.set_footer(content=...)")
    def set_footer_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich footer for *page_type*."""

        return _layout.set_footer_content(
            self,
            content=content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.page.set_footer(text=...)")
    def set_footer_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a footer for *page_type* and set its text."""

        return _layout.set_footer_text(
            self,
            text=text,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.page.set_header(content=...)")
    def set_header_content(
        self,
        content: Sequence[Mapping[str, Any]],
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a rich header for *page_type*."""

        return _layout.set_header_content(
            self,
            content=content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.page.set_header / doc.page.set_footer")
    def set_header_footer(
        self,
        *,
        kind: str,
        text: str | None = None,
        content: Sequence[Mapping[str, Any]] | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Set a header or footer using plain text or rich content specs."""

        return _layout.set_header_footer(
            self,
            kind=kind,
            text=text,
            content=content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.page.set_header(text=...)")
    def set_header_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a header for *page_type* and set its text."""

        return _layout.set_header_text(
            self,
            text=text,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    @_moved("doc.styles.apply_list_format")
    def set_list_format(
        self,
        *,
        paragraph_index: int | None = None,
        paragraph_indexes: Sequence[int] | None = None,
        kind: str = "bullet",
        level: int = 1,
        bullet_char: str | None = None,
        number_format: str | None = None,
        start: int | None = None,
    ) -> dict[str, Any]:
        """Apply bullet or numbered-list paragraph properties to paragraphs."""

        return _layout.set_list_format(
            self,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
            kind=kind,
            level=level,
            bullet_char=bullet_char,
            number_format=number_format,
            start=start,
        )

    @_moved("doc.page.set_margins")
    def set_page_margins(
        self,
        *,
        left: int | None = None,
        right: int | None = None,
        top: int | None = None,
        bottom: int | None = None,
        header: int | None = None,
        footer: int | None = None,
        gutter: int | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Set page margins on the requested section through the public facade."""

        return _layout.set_page_margins(
            self,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            header=header,
            footer=footer,
            gutter=gutter,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.page.set_page_number")
    def set_page_number(
        self,
        *,
        target: str = "footer",
        page_type: str = "BOTH",
        format: str = "page",
        align: str = "CENTER",
        position: str = "BOTTOM_CENTER",
        prefix: str = "",
        suffix: str = "",
        format_type: str | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> HwpxOxmlSectionHeaderFooter:
        """Replace header/footer content with an automatic page-number field."""

        return _layout.set_page_number(
            self,
            target=target,
            page_type=page_type,
            format=format,
            align=align,
            position=position,
            prefix=prefix,
            suffix=suffix,
            format_type=format_type,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.page.setup")
    def set_page_setup(
        self,
        *,
        paper_size: str | None = None,
        width_mm: float | None = None,
        height_mm: float | None = None,
        orientation: str | None = None,
        margins_mm: Mapping[str, float] | None = None,
        margin_left_mm: float | None = None,
        margin_right_mm: float | None = None,
        margin_top_mm: float | None = None,
        margin_bottom_mm: float | None = None,
        header_margin_mm: float | None = None,
        footer_margin_mm: float | None = None,
        gutter_mm: float | None = None,
        columns: int | None = None,
        column_gap_mm: float | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> dict[str, Any]:
        """Set page size, margins, orientation, and optional columns in human units."""

        return _layout.set_page_setup(
            self,
            paper_size=paper_size,
            width_mm=width_mm,
            height_mm=height_mm,
            orientation=orientation,
            margins_mm=margins_mm,
            margin_left_mm=margin_left_mm,
            margin_right_mm=margin_right_mm,
            margin_top_mm=margin_top_mm,
            margin_bottom_mm=margin_bottom_mm,
            header_margin_mm=header_margin_mm,
            footer_margin_mm=footer_margin_mm,
            gutter_mm=gutter_mm,
            columns=columns,
            column_gap_mm=column_gap_mm,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.page.set_size")
    def set_page_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
    ) -> None:
        """Set page dimensions on the requested section through the public facade."""

        return _layout.set_page_size(
            self,
            width=width,
            height=height,
            orientation=orientation,
            gutter_type=gutter_type,
            section=section,
            section_index=section_index,
        )

    @_moved("doc.styles.apply_paragraph_format")
    def set_paragraph_format(
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
    ) -> dict[str, Any]:
        """Apply paragraph-level formatting using human units.

        Millimetre inputs are converted to HWP units; paragraph spacing uses
        points; line spacing is stored as a percent value. ``keep_with_next`` /
        ``keep_lines`` / ``page_break_before`` set the paragraph's keep-together
        (``<hh:breakSetting>``) flags via a freshly minted paraPr.
        """

        return _layout.set_paragraph_format(
            self,
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

    @_moved("doc.styles.style")
    def style(self, style_id_ref: int | str | None) -> Style | None:
        """Return the style definition referenced by *style_id_ref*."""

        return self._root.style(style_id_ref)

    @_moved("doc.tracking.change")
    def track_change(self, change_id_ref: int | str | None) -> TrackChange | None:
        """Return tracked change metadata referenced by *change_id_ref*."""

        return self._root.track_change(change_id_ref)

    @_moved("doc.tracking.author")
    def track_change_author(
        self, author_id_ref: int | str | None
    ) -> TrackChangeAuthor | None:
        """Return tracked change author details referenced by *author_id_ref*."""

        return self._root.track_change_author(author_id_ref)

    @property
    @_moved("doc.tracking.authors")
    def track_change_authors(self) -> dict[str, TrackChangeAuthor]:
        """Return tracked change author metadata declared in the headers."""

        return self._root.track_change_authors

    @property
    @_moved("doc.tracking.changes")
    def track_changes(self) -> dict[str, TrackChange]:
        """Return tracked change metadata declared in the headers."""

        return self._root.track_changes

    @property
    @_moved("doc.parts.version")
    def version(self) -> HwpxOxmlVersion | None:
        """Return the version metadata part if present."""
        return self._root.version
