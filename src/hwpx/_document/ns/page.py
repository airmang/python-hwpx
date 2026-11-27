# SPDX-License-Identifier: Apache-2.0
"""`doc.page` — 쪽 기하(용지·여백·단·머리말/꼬리말·쪽번호·격자·줄번호).

5.x 는 이 축 하나로 루트를 **12칸** 먹었다. 전부 "인쇄되는 지면이 어떻게
생겼는가"라는 한 가지 일이라 한 네임스페이스로 모았다.

## 두 가지 정리

**① 머리말/꼬리말 동사 5개 → 2개.** 5.x 는 `set_header_text`,
`set_header_content`, `set_footer_text`, `set_footer_content`, 그리고 그 넷의
합집합인 `set_header_footer(kind=...)` 를 나란히 두었다. 문자열 디스패치는
6.0 이 없애려는 안티패턴이라 `set_header_footer` 는 강등하고, 나머지 넷은
입력 형태(`text=` / `content=`)를 파라미터로 받는 두 동사로 접었다.

**② `doc.headers` 는 여기 없다.** 그 이름은 쪽 머리말이 아니라
`Contents/header.xml` 파트였고 `doc.parts.headers` 로 갔다. 이 네임스페이스의
`set_header` 가 진짜 쪽 머리말이다.

## 단위가 다른 두 벌은 둘 다 남긴다

`setup()` 은 mm(사람 단위), `set_size()`/`set_margins()` 는 HWPUNIT(포맷 단위)
이다. 개념 중복처럼 보이지만 정밀도가 다르고 실사용도 갈린다 — 접지 않는다.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Mapping, Sequence, TypeVar, cast

from ...errors import HwpxValueError
from ...objects import PageSetup
from ...oxml import HwpxOxmlInlineObject, HwpxOxmlMasterPage, HwpxOxmlParagraph, HwpxOxmlSection
from ...oxml.section_format import (
    LineNumberShape,
    PageMargins,
    PageSize,
    SectionGrid,
    SectionVisibility,
)
from ...oxml.section_story import HwpxOxmlSectionHeaderFooter
from ...objects.results import (
    Alignment,
    AutoNumber,
    BorderLine,
    ColumnDefinition,
    NoteShapeInfo,
    NumberRestart,
    PageBorder,
    PageHiding,
    PageNumberControl,
    StartNumbers,
)
from ...oxml.namespaces import HP
from .._resolve import optional_paragraph, resolve_paragraph, resolve_section
from ._base import _Namespace

_T = TypeVar("_T")

__all__ = ["PageNamespace"]

#: 6.12 트레인㊸ 갭③ — 스키마 선언 열거값. 실코퍼스 67파일의 `hp:secPr` 74건은 모두
#: `HORIZONTAL`·`textVerticalWidthHead="0"`이었다(VERTICAL·VERTICALALL 실사용 0건 — 렌더는 v16 배치가 확인).
#: 표 칸의 `TableCell.text_direction` 과 같은 말(str)로 읽는다(7.0, N9).
_TEXT_DIRECTIONS = frozenset({"HORIZONTAL", "VERTICAL", "VERTICALALL"})


class PageNamespace(_Namespace):
    """쪽 기하 — 용지·여백·단·머리말/꼬리말·쪽번호·격자·줄번호.

    모든 메서드는 ``section=`` (구역 객체 또는 번호)을 받는다. 주지 않으면
    **마지막 구역**에만 적용된다. 구역이 여럿인 문서에서 ``section`` 없이 바꾸는
    호출(``setup``·``set_*``·``remove_*``)은 문서마다 한 번 ``UserWarning`` 을 낸다.
    모든 구역을 한 번에 바꾸려면 바꾸는 메서드에 ``section="all"`` 을 준다(돌려주는 값은
    마지막 구역의 것). 읽는 메서드는 구역 하나를 읽는다.
    """

    __slots__ = ()
    _path = "doc.page"

    def _section(
        self,
        section: "int | HwpxOxmlSection | None",
        caller: str,
    ) -> "HwpxOxmlSection":
        """The section a ``doc.page`` call works on: *section*, else the **last** section.

        A change (``setup``, ``set_*``, ``remove_*``) to a document of several sections
        without *section* touches only the last one, and warns once per document: the
        first sections keep their paper, margins, header and footer.
        """

        if (
            section is None
            and caller.startswith(("set", "remove_"))
            and len(self._doc.sections) > 1
            and not getattr(self._doc, "_page_last_section_warned", False)
        ):
            import warnings

            self._doc._page_last_section_warned = True  # type: ignore[attr-defined]
            warnings.warn(
                f"doc.page.{caller}() 에 section 을 주지 않아 구역 {len(self._doc.sections)}개 중 "
                "마지막 구역만 바뀝니다. 모든 구역을 바꾸려면 "
                f"doc.page.{caller}(..., section='all') 처럼 부르세요.",
                UserWarning,
                stacklevel=3,
            )
        return resolve_section(
            self._doc, section, caller=f"doc.page.{caller}"
        )

    def _apply(
        self,
        section: "int | HwpxOxmlSection | Literal['all'] | None",
        caller: str,
        change: "Callable[[HwpxOxmlSection], _T]",
        check: "Callable[[HwpxOxmlSection], object] | None" = None,
    ) -> "_T":
        """Run *change* on the section a setter names, or on every section for ``section="all"``.

        With ``"all"`` the result is what the last section's change returned, so a setter
        returns the same type whichever sections it changed. *check* is what *change* refuses for
        one section, without writing: with ``"all"`` it is asked of every section before the first
        one changes, so a section that refuses leaves the others as they were.
        """

        if section == ALL_SECTIONS:
            sections = list(self._doc.sections)
            if not sections:
                return change(self._section(None, caller))
            if check is not None:
                for target in sections:
                    check(target)
            result = change(sections[0])
            for target in sections[1:]:
                result = change(target)
            return result
        return change(self._section(cast(Any, section), caller))

    # -- 용지·여백·단 ------------------------------------------------------

    def setup(
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
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> "PageSetup":
        """용지·여백·단을 **mm 단위**로 한 번에 설정하고 결과를 돌려준다.

        ``section="all"`` 이면 모든 구역에 같은 값을 쓰고 마지막 구역의 결과를 돌려준다.
        """

        from .. import layout as _layout

        return self._apply(section, "setup", lambda target: _layout.set_page_setup(
            self._doc,
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
            section=target,
        ))

    def set_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """용지 크기를 **HWPUNIT** 으로 설정한다(정밀 변형)."""

        from .. import layout as _layout

        self._apply(section, "set_size", lambda target: _layout.set_page_size(
            self._doc,
            width=width,
            height=height,
            orientation=orientation,
            gutter_type=gutter_type,
            section=target,
        ))

    def set_margins(
        self,
        *,
        left: int | None = None,
        right: int | None = None,
        top: int | None = None,
        bottom: int | None = None,
        header: int | None = None,
        footer: int | None = None,
        gutter: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """여백을 **HWPUNIT** 으로 설정한다(정밀 변형)."""

        from .. import layout as _layout

        self._apply(section, "set_margins", lambda target: _layout.set_page_margins(
            self._doc,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            header=header,
            footer=footer,
            gutter=gutter,
            section=target,
        ))

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
        separator_width_mm: float | None = None,
        separator_color: str | None = None,
        paragraph: "HwpxOxmlParagraph | int | None" = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> "HwpxOxmlInlineObject":
        """단(段) 정의를 삽입한다. *paragraph* 는 문단 객체나 인덱스다.

        단 사이 구분선은 *separator_type*(``"SOLID"`` …)·*separator_width_mm*(mm, 한/글 굵기 목록의
        값만 — 없는 값은 ``style-line-width-invalid``)·*separator_color* 로 긋는다. 지금 단 설정은 :meth:`columns` 로 읽는다.
        ``section="all"`` 은 *paragraph* 와 함께 줄 수 없다.
        """

        from .. import layout as _layout

        if section == ALL_SECTIONS and paragraph is not None:
            raise HwpxValueError(
                "section='all' 과 paragraph 를 함께 줄 수 없습니다: 문단은 한 구역에만 있습니다.",
                code="page-section-all-invalid",
                context={"caller": "doc.page.set_columns"},
                suggestion="문단 중간에서 단을 바꾸려면 그 문단이 있는 구역을 section= 으로 주세요.",
            )
        target_paragraph = None
        if section != ALL_SECTIONS:
            target_paragraph = optional_paragraph(
                self._doc, paragraph, section=cast(Any, section),
                caller="doc.page.set_columns",
            )
        return self._apply(section, "set_columns", lambda target: _layout.set_columns(
            self._doc,
            col_count=col_count,
            col_type=col_type,
            layout=layout,
            same_size=same_size,
            same_gap=same_gap,
            column_widths=column_widths,
            separator_type=separator_type,
            separator_width_mm=separator_width_mm,
            separator_color=separator_color,
            paragraph=target_paragraph,
            section=target,
        ))

    # -- 머리말 / 꼬리말 ---------------------------------------------------

    def set_header(
        self,
        *,
        text: str | None = None,
        content: "Sequence[Mapping[str, Any]] | None" = None,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 머리말을 설정한다. ``text=`` 또는 ``content=`` 중 하나.

        같은 *page_type* 의 머리말이 이미 있으면(한/글이 만든 문서의 것도) 그것을
        바꾼다. 새로 쓰는 내용이 있던 쪽 번호나 문구를 지우면 ``UserWarning`` 을
        낸다. 문구와 쪽 번호를 함께 두려면 ``content=`` 로 한 번에 쓴다::

            doc.page.set_header(content=[
                {"align": "RIGHT", "children": [
                    {"type": "run", "text": "2026 업무 계획 · "},
                    {"type": "page_number", "page_number": "page"},
                ]},
            ])

        문단 하나가 ``{"align": ..., "children": [...]}`` 이고, 자식은
        ``{"type": "run", "text": ..., "bold": ...}`` 또는
        ``{"type": "page_number", "page_number": "page" | "page/total"}`` 다.
        *section* 을 주지 않으면 **마지막 구역**만 바뀐다(구역이 둘 이상이면 경고).
        """

        return self._set_header_footer(
            "header",
            text=text,
            content=content,
            page_type=page_type,
            section=section,
        )

    def set_footer(
        self,
        *,
        text: str | None = None,
        content: "Sequence[Mapping[str, Any]] | None" = None,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 꼬리말을 설정한다. ``text=`` 또는 ``content=`` 중 하나.

        같은 *page_type* 의 꼬리말이 이미 있으면(한/글이 만든 문서의 것도) 그것을
        바꾼다. ``set_page_number()`` 로 넣은 쪽 번호도 꼬리말의 내용이라
        ``set_footer(text=...)`` 는 그것을 지운다(경고를 낸다). 반대 순서도 같다.
        문구와 쪽 번호를 함께 두려면 ``content=`` 로 한 번에 쓴다::

            doc.page.set_footer(content=[
                {"align": "CENTER", "children": [
                    {"type": "run", "text": "대외비 - "},
                    {"type": "page_number", "page_number": "page"},
                ]},
            ])

        또는 ``set_page_number(prefix="대외비 - ")``.
        *section* 을 주지 않으면 **마지막 구역**만 바뀐다(구역이 둘 이상이면 경고).
        """

        return self._set_header_footer(
            "footer",
            text=text,
            content=content,
            page_type=page_type,
            section=section,
        )

    def _set_header_footer(
        self,
        kind: str,
        *,
        text: str | None,
        content: "Sequence[Mapping[str, Any]] | None",
        page_type: str,
        section: "int | HwpxOxmlSection | Literal['all'] | None",
    ) -> "HwpxOxmlSectionHeaderFooter":
        from .. import layout as _layout

        caller = f"set_{kind}"
        if text is not None and content is not None:
            raise HwpxValueError(
                "text 와 content 를 동시에 지정할 수 없습니다.",
                code="page-argument-conflict",
                context={"caller": f"doc.page.{caller}"},
                suggestion=(
                    "문자열 한 줄이면 text=, 여러 문단·정렬이 필요하면 content= 를 쓰세요."
                ),
            )
        if text is None and content is None:
            raise HwpxValueError(
                "text 또는 content 중 하나는 지정해야 합니다.",
                code="page-argument-missing",
                context={"caller": f"doc.page.{caller}"},
                suggestion=f"내용을 지우려면 doc.page.remove_{kind}() 를 쓰세요.",
            )

        return self._apply(section, caller, lambda target: _layout.set_header_footer(
            self._doc,
            kind=kind,
            text=text,
            content=content,
            section=target,
            page_type=page_type,
        ))

    def remove_header(
        self,
        *,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """쪽 머리말을 제거한다."""

        from .. import layout as _layout

        self._apply(section, "remove_header", lambda target: _layout.remove_header(
            self._doc,
            section=target,
            page_type=page_type,
        ))

    def remove_footer(
        self,
        *,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """쪽 꼬리말을 제거한다."""

        from .. import layout as _layout

        self._apply(section, "remove_footer", lambda target: _layout.remove_footer(
            self._doc,
            section=target,
            page_type=page_type,
        ))

    def headers(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[HwpxOxmlSectionHeaderFooter, ...]":
        """구역의 머리말을 모두(쪽 종류마다 하나: ``BOTH``·``ODD``·``EVEN``) 모델 객체로.

        한/글이 저장한 문서의 머리말도, python-hwpx 가 쓴 머리말도 하나씩 나온다. 각 객체의
        ``page_type`` 이 쪽 종류, ``paragraphs`` 가 그 안의 문단이다. 문단을 고치거나
        ``add_paragraph(text)`` 로 더한 뒤 저장하면 한/글이 읽는 쪽에 반영된다. 첫 쪽에서만
        감추는 것은 쪽 종류가 아니라 ``visibility().hide_first_header`` 다.
        """

        return tuple(self._section(section, "headers").properties.headers)

    def footers(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[HwpxOxmlSectionHeaderFooter, ...]":
        """구역의 꼬리말을 모두 모델 객체로(:meth:`headers` 와 같다)."""

        return tuple(self._section(section, "footers").properties.footers)

    def header(
        self, *, page_type: str = "BOTH", section: "int | HwpxOxmlSection | None" = None
    ) -> "HwpxOxmlSectionHeaderFooter | None":
        """*page_type* 쪽의 머리말, 없으면 None. ``set_header(page_type=...)`` 의 읽기 짝."""

        return self._section(section, "header").properties.header(page_type)

    def footer(
        self, *, page_type: str = "BOTH", section: "int | HwpxOxmlSection | None" = None
    ) -> "HwpxOxmlSectionHeaderFooter | None":
        """*page_type* 쪽의 꼬리말, 없으면 None. ``set_footer(page_type=...)`` 의 읽기 짝."""

        return self._section(section, "footer").properties.footer(page_type)

    def set_page_number(
        self,
        *,
        target: str = "footer",
        page_type: str = "BOTH",
        format: str = "page",
        alignment: "Alignment | str" = "CENTER",
        position: str = "BOTTOM_CENTER",
        prefix: str = "",
        suffix: str = "",
        format_type: str | None = None,
        control: bool = True,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 번호를 머리말/꼬리말에 넣는다. *alignment* 는 번호 문단의 정렬(``Alignment`` 나 그 이름)이다.

        7.x는 자동 번호(``hp:autoNum``) 뒤에 쪽 번호 컨트롤(``hp:pageNum``)을 하나 더 쓴다.
        ``control=False``면 한/글이 머리말·꼬리말에 쪽 번호를 넣을 때처럼 자동 번호만 쓴다
        (*position* 은 그 컨트롤의 값이라 쓰이지 않는다). 8.0에서 이쪽을 기본으로 바꿀 예정이다.

        번호는 그 머리말/꼬리말의 내용을 바꾼 자동 번호 글이다. 한컴의 쪽 번호
        컨트롤("쪽 번호 매기기")이 아니어서 ``set_visibility(hide_first_page_num=True)``와
        ``add_page_hiding(page_num=True)``로는 숨지 않는다. 첫 쪽에서 감추려면
        ``set_visibility(hide_first_footer=True)``(머리말이면 ``hide_first_header``)를,
        한 쪽만 감추려면 ``add_page_hiding(paragraph, footer=True)``를 쓴다.
        """

        from .. import layout as _layout

        return self._apply(section, "set_page_number", lambda each: _layout.set_page_number(
            self._doc,
            target=target,
            page_type=page_type,
            format=format,
            align=str(alignment),
            position=position,
            prefix=prefix,
            suffix=suffix,
            format_type=format_type,
            control=control,
            section=each,
        ))

    def add_number_restart(
        self,
        paragraph: "HwpxOxmlParagraph | int",
        *,
        number: int = 1,
        kind: str = "PAGE",
    ) -> "NumberRestart":
        """*paragraph* 부터 *kind* 의 진행 번호를 *number* 로 다시 시작하는 새 번호 지정(`hp:newNum`)을 넣는다.

        `set_page_number` 가 머리말/꼬리말의 *표시* 필드를 다루는 것과 달리,
        이건 구역 중간의 재시작 지점을 문단에 심는다. :meth:`number_restarts` 가 읽는
        :class:`NumberRestart` 를 돌려준다(``paragraph.add_number_restart`` 와 같다).
        """

        from .. import layout as _layout

        return _layout.add_number_restart(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.page.add_number_restart"),
            number=number,
            kind=kind,
        )

    def add_page_hiding(
        self,
        paragraph: "HwpxOxmlParagraph | int",
        *,
        header: bool = False,
        footer: bool = False,
        master_page: bool = False,
        border: bool = False,
        fill: bool = False,
        page_num: bool = False,
    ) -> "PageHiding":
        """*paragraph* 가 있는 쪽에서만 지정한 요소를 숨기는 감추기(`hp:pageHiding`)를 넣는다.

        한컴의 "현재 쪽만 감추기"와 같아서 다음 쪽부터는 다시 보인다. *page_num* 은
        한컴 쪽 번호 컨트롤의 번호를 감춘다. ``set_page_number()`` 의 번호는
        머리말/꼬리말 글이라 *footer* (또는 *header*)로 감춘다. :meth:`page_hidings` 가 읽는
        :class:`PageHiding` 을 돌려준다(``paragraph.add_page_hiding`` 과 같다).
        """

        from .. import layout as _layout

        return _layout.add_page_hiding(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.page.add_page_hiding"),
            header=header,
            footer=footer,
            master_page=master_page,
            border=border,
            fill=fill,
            page_num=page_num,
        )

    # -- 읽기: 현재 지면 상태 ----------------------------------------------

    def size(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "PageSize":
        """현재 용지 크기."""

        return self._section(section, "size").properties.page_size

    def margins(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "PageMargins":
        """현재 여백."""

        return self._section(section, "margins").properties.page_margins

    # -- 격자·표시·줄번호 --------------------------------------------------
    #
    # ``hp:grid``·``hp:visibility``·``hp:lineNumberShape`` 는 실코퍼스 전 파일에
    # 있는데 5.x 코드가 Skeleton 상수로 박제해 두고 바꾸지 못하던 것들이다.
    # 저수준 API 는 ``HwpxOxmlSectionProperties`` 가 소유하고(Q3b), 여기서는 쪽
    # 기하 축의 나머지와 같은 자리에 노출하기만 한다.

    def master_page_refs(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> tuple[str, ...]:
        """이 절이 참조하는 바탕쪽 id(``hp:masterPage/@idRef``) 목록."""

        return self._section(
            section, "master_page_refs"
        ).properties.master_page_refs

    def set_master_page(
        self,
        master_page_id: "str | HwpxOxmlMasterPage",
        *,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """이 절이 바탕쪽(``doc.parts.add_master_page``가 돌려준 ``MasterPage`` 나 그 id)을
        참조하도록 등록한다(6.13 트레인㊻). 이미 참조 중이면 아무 일도
        안 한다(멱등). 연결을 끊는 쪽은 :meth:`remove_master_page_reference`."""

        self._apply(
            section, "set_master_page",
            lambda target: target.properties.add_master_page_reference(master_page_id),
            check=lambda target: target.properties._check_master_page_reference(master_page_id),
        )

    def grid(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "SectionGrid":
        """줄/글자 격자 설정."""

        return self._section(section, "grid").properties.grid

    def set_grid(
        self,
        *,
        line_grid: int | None = None,
        char_grid: int | None = None,
        wonggoji_format: bool | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """줄/글자 격자(원고지 형식 포함)를 설정한다."""

        self._apply(section, "set_grid", lambda target: target.properties.set_grid(
            line_grid=line_grid,
            char_grid=char_grid,
            wonggoji_format=wonggoji_format,
        ))

    def text_direction(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> str:
        """글자 방향: ``"HORIZONTAL"``(가로쓰기)·``"VERTICAL"``·``"VERTICALALL"``(세로쓰기).

        표 칸의 ``cell.text_direction`` 과 같은 말이다. 머리말/꼬리말 세로쓰기 여부는
        :meth:`vertical_header_footer`. (6.x 는 둘을 ``SectionTextDirection(direction,
        vertical_header_footer)`` 하나로 돌려주었다.)
        """

        return self._section(
            section, "text_direction"
        ).properties.text_direction

    def vertical_header_footer(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> bool:
        """머리말/꼬리말도 세로로 쓰는지(``hp:secPr/@textVerticalWidthHead``). 쓰기는
        ``set_text_direction(vertical_header_footer=...)``."""

        return self._section(
            section, "vertical_header_footer"
        ).properties.vertical_header_footer

    def set_text_direction(
        self,
        direction: str | None = None,
        *,
        vertical_header_footer: bool | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """글자 방향(세로쓰기 포함)을 설정한다.

        실코퍼스 67파일 전수에 `VERTICAL`/`VERTICALALL` 실사용 예가 없다
        (74/74 `HORIZONTAL`) — 스키마 열거값 자체는 명확해 저작을 막지
        않지만, 실한컴 렌더 검증 전까지는 "Create(experimental)"로만
        표기한다(``docs/support-matrix.md`` 참조).
        """

        if direction is not None and direction not in _TEXT_DIRECTIONS:
            raise HwpxValueError(
                f"unsupported text direction: {direction}",
                code="page-text-direction-unsupported",
                context={
                    "requested": direction,
                    "supported": sorted(_TEXT_DIRECTIONS),
                },
                suggestion=f"Supported: {', '.join(sorted(_TEXT_DIRECTIONS))}",
            )
        self._apply(section, "set_text_direction", lambda target: (
            target.properties.set_text_direction(direction, vertical_header_footer=vertical_header_footer)
        ))

    def visibility(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "SectionVisibility":
        """첫 쪽 숨김 플래그와 줄번호 표시 여부."""

        return self._section(section, "visibility").properties.visibility

    def set_visibility(
        self,
        *,
        hide_first_header: bool | None = None,
        hide_first_footer: bool | None = None,
        hide_first_master_page: bool | None = None,
        hide_first_page_num: bool | None = None,
        hide_first_empty_line: bool | None = None,
        show_line_number: bool | None = None,
        border: str | None = None,
        fill: str | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """첫 쪽 숨김 플래그와 줄번호 표시 여부를 설정한다.

        *hide_first_page_num* 은 한컴 쪽 번호 컨트롤의 첫 쪽 번호를 감춘다.
        ``set_page_number()`` 의 번호는 머리말/꼬리말 글이라 *hide_first_footer*
        (또는 *hide_first_header*)로 감춘다. 줄 번호는 *show_line_number* 가 참일
        때만 그려진다(모양은 ``set_line_numbers()``).
        """

        self._apply(section, "set_visibility", lambda target: target.properties.set_visibility(
            hide_first_header=hide_first_header,
            hide_first_footer=hide_first_footer,
            hide_first_master_page=hide_first_master_page,
            hide_first_page_num=hide_first_page_num,
            hide_first_empty_line=hide_first_empty_line,
            show_line_number=show_line_number,
            border=border,
            fill=fill,
        ))

    def line_numbers(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
    ) -> "LineNumberShape":
        """줄번호 표시 규칙."""

        return self._section(
            section, "line_numbers"
        ).properties.line_number_shape

    def set_line_numbers(
        self,
        *,
        restart_type: int | None = None,
        count_by: int | None = None,
        distance: int | None = None,
        start_number: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """줄번호 재시작·간격·시작값을 설정한다.

        모양만 정한다. 한컴은 ``set_visibility(show_line_number=True)`` 일 때만 줄
        번호를 그린다. *restart_type* 은 1이면 쪽마다 1부터 다시 세고, 0이면 이어
        센다.
        """

        self._apply(section, "set_line_numbers", lambda target: (
            target.properties.set_line_number_shape(
                restart_type=restart_type,
                count_by=count_by,
                distance=distance,
                start_number=start_number,
            )
        ))

    # -- 읽기 짝: 단·번호 컨트롤 ---------------------------------------------

    def columns(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[ColumnDefinition, ...]":
        """구역의 단 설정을 문서 순서로 돌려준다.

        첫 항목은 구역 첫머리의 단(``hp:secPr`` 옆의 ``hp:colPr``)이고, 본문 중간에서
        단을 바꾼 곳(``set_columns(paragraph=...)``, 한/글의 "단 정의 넣기")이 있으면
        그 뒤에 온다. 각 값의 ``paragraph`` 가 그 단 정의를 품은 본문 문단이다.
        """

        target = self._section(section, "columns")
        return tuple(_column_definition(node, paragraph, target) for node, paragraph in _body_column_nodes(target))

    def page_number_controls(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[PageNumberControl, ...]":
        """구역의 쪽 번호 컨트롤(``hp:pageNum``, 한/글 "쪽 번호 매기기")의 위치·형식을 문서 순서로.

        ``set_page_number()`` 가 머리말·꼬리말에 쓰는 번호는 컨트롤이 아니라 자동 번호라
        여기 없고 :meth:`auto_numbers` 에 나온다.
        """

        target = self._section(section, "page_number_controls")
        return tuple(page_number_control(node, paragraph) for node, paragraph in _controls(target, "pageNum"))

    def number_restarts(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[NumberRestart, ...]":
        """구역의 새 번호 컨트롤(``hp:newNum``, :meth:`add_number_restart` 가 넣는 것)을 문서 순서로."""

        target = self._section(section, "number_restarts")
        return tuple(number_restart(node, paragraph) for node, paragraph in _controls(target, "newNum"))

    def page_hidings(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[PageHiding, ...]":
        """구역의 감추기 컨트롤(``hp:pageHiding``, :meth:`add_page_hiding` 이 넣는 것)을 문서 순서로."""

        target = self._section(section, "page_hidings")
        return tuple(page_hiding(node, paragraph) for node, paragraph in _controls(target, "pageHiding"))

    def auto_numbers(
        self, *, section: "int | HwpxOxmlSection | None" = None
    ) -> "tuple[AutoNumber, ...]":
        """구역의 자동 번호(``hp:autoNum``)를 문서 순서로: 본문·표 칸·글상자·캡션·머리말·꼬리말·각주의 것.

        쪽 번호(``PAGE``)·전체 쪽 수(``TOTAL_PAGE``)·각주/미주 번호·그림·표·수식 번호가 여기 온다.
        """

        target = self._section(section, "auto_numbers")
        return tuple(auto_number(node, paragraph) for node, paragraph in _controls(target, "autoNum"))

    def start_numbers(self, *, section: "int | HwpxOxmlSection | None" = None) -> "StartNumbers":
        """구역의 시작 번호(``hp:startNum``): 쪽·그림·표·수식. 0이면 앞 구역에서 이어 센다."""

        return self._section(section, "start_numbers").properties.start_numbers

    def set_start_numbers(
        self,
        *,
        page_starts_on: str | None = None,
        page: int | None = None,
        picture: int | None = None,
        table: int | None = None,
        equation: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """구역의 시작 번호를 바꾼다. 주지 않은 값은 그대로 둔다.

        *page_starts_on* 은 ``BOTH``·``EVEN``·``ODD`` (구역이 어떤 쪽에서 시작하는지), 번호는
        0..65535 (0: 앞 구역에서 이어 센다).
        """

        if page_starts_on is not None:
            _one_of("page_starts_on", page_starts_on, ("BOTH", "EVEN", "ODD"), "page-start-numbers-invalid")
        self._apply(section, "set_start_numbers", lambda target: target.properties.set_start_numbers(
            page_starts_on=page_starts_on, page=page, picture=picture, table=table, equation=equation
        ))

    # -- 각주·미주 모양 ------------------------------------------------------

    def footnote_shape(self, *, section: "int | HwpxOxmlSection | None" = None) -> "NoteShapeInfo":
        """구역의 각주 모양(``hp:footNotePr``): 번호 형식, 구분선, 간격, 번호 매기기, 놓는 곳."""

        properties = self._section(section, "footnote_shape").properties
        return _note_shape_info(properties.footnote_shape, "footNotePr")

    def endnote_shape(self, *, section: "int | HwpxOxmlSection | None" = None) -> "NoteShapeInfo":
        """구역의 미주 모양(``hp:endNotePr``). :meth:`footnote_shape` 와 같은 값."""

        properties = self._section(section, "endnote_shape").properties
        return _note_shape_info(properties.endnote_shape, "endNotePr")

    def set_footnote_shape(
        self,
        *,
        number_format: str | None = None,
        user_char: str | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        superscript: bool | None = None,
        numbering: str | None = None,
        start: int | None = None,
        placement: str | None = None,
        beneath_text: bool | None = None,
        separator_type: str | None = None,
        separator_width_mm: float | None = None,
        separator_color: str | None = None,
        separator_length: int | None = None,
        between_notes: int | None = None,
        below_line: int | None = None,
        above_line: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """구역의 각주 모양을 바꾼다. 주지 않은 값은 그대로 둔다(:meth:`footnote_shape` 의 짝).

        *number_format* 은 번호 모양(``DIGIT``·``CIRCLED_DIGIT``·``ROMAN_SMALL``·``USER_CHAR`` …),
        *numbering* 은 ``CONTINUOUS``·``ON_SECTION``·``ON_PAGE``, *placement* 는 ``EACH_COLUMN``·
        ``MERGED_COLUMN``·``RIGHT_MOST_COLUMN``. 간격과 *separator_length* 는 HWPUNIT.
        """

        self._set_note_shape(
            "footNotePr", "set_footnote_shape", section,
            number_format=number_format, user_char=user_char, prefix=prefix, suffix=suffix,
            superscript=superscript, numbering=numbering, start=start, placement=placement,
            beneath_text=beneath_text, separator_type=separator_type, separator_width_mm=separator_width_mm,
            separator_color=separator_color, separator_length=separator_length, between_notes=between_notes,
            below_line=below_line, above_line=above_line,
        )

    def set_endnote_shape(
        self,
        *,
        number_format: str | None = None,
        user_char: str | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        superscript: bool | None = None,
        numbering: str | None = None,
        start: int | None = None,
        placement: str | None = None,
        beneath_text: bool | None = None,
        separator_type: str | None = None,
        separator_width_mm: float | None = None,
        separator_color: str | None = None,
        separator_length: int | None = None,
        between_notes: int | None = None,
        below_line: int | None = None,
        above_line: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """구역의 미주 모양을 바꾼다(:meth:`set_footnote_shape` 와 같은 인자).

        *numbering* 은 ``CONTINUOUS``·``ON_SECTION``, *placement* 는 ``END_OF_DOCUMENT``·``END_OF_SECTION``.
        """

        self._set_note_shape(
            "endNotePr", "set_endnote_shape", section,
            number_format=number_format, user_char=user_char, prefix=prefix, suffix=suffix,
            superscript=superscript, numbering=numbering, start=start, placement=placement,
            beneath_text=beneath_text, separator_type=separator_type, separator_width_mm=separator_width_mm,
            separator_color=separator_color, separator_length=separator_length, between_notes=between_notes,
            below_line=below_line, above_line=above_line,
        )

    def _set_note_shape(
        self,
        tag: str,
        caller: str,
        section: "int | HwpxOxmlSection | Literal['all'] | None",
        *,
        number_format: str | None,
        user_char: str | None,
        prefix: str | None,
        suffix: str | None,
        superscript: bool | None,
        numbering: str | None,
        start: int | None,
        placement: str | None,
        beneath_text: bool | None,
        separator_type: str | None,
        separator_width_mm: float | None,
        separator_color: str | None,
        separator_length: int | None,
        between_notes: int | None,
        below_line: int | None,
        above_line: int | None,
    ) -> None:
        from ...oxml.color import normalize_color
        from ...oxml.numbering_kinds import number_format as _number_format
        from ...oxml.utils import line_width_text

        code = "page-note-shape-invalid"
        # Everything is checked before anything changes: a refused value leaves the shape as it was.
        if number_format is not None:
            number_format = _number_format(number_format, note=True)
        if numbering is not None:
            allowed = _NOTE_NUMBERINGS[tag]
            _one_of("numbering", numbering, allowed, code)
        if placement is not None:
            _one_of("placement", placement, _NOTE_PLACEMENTS[tag], code)
        if start is not None:
            _int_in("start", start, 1, 0xFFFF, code)
        if separator_length is not None:
            _int_in("separator_length", separator_length, -1, 0x7FFFFFFF, code)
        for name, value in (("between_notes", between_notes), ("below_line", below_line), ("above_line", above_line)):
            if value is not None:
                _int_in(name, value, 0, 0x7FFFFFFF, code)
        width = None
        if separator_width_mm is not None:
            width = line_width_text(separator_width_mm, argument="separator_width_mm")
        color = normalize_color(separator_color) if separator_color is not None else None

        def change(target: "HwpxOxmlSection") -> None:
            properties = target.properties
            if any(v is not None for v in (number_format, user_char, prefix, suffix, superscript)):
                properties._set_note_auto_num_format(
                    tag, type=number_format, user_char=user_char, prefix_char=prefix, suffix_char=suffix,
                    supscript=superscript,
                )
            if any(v is not None for v in (separator_type, width, color, separator_length)):
                properties._set_note_line(tag, length=separator_length, type=separator_type, width=width, color=color)
            if any(v is not None for v in (between_notes, below_line, above_line)):
                properties._set_note_spacing(
                    tag, between_notes=between_notes, below_line=below_line, above_line=above_line
                )
            if numbering is not None or start is not None:
                properties._set_note_numbering(tag, type=numbering, new_num=start)
            if placement is not None or beneath_text is not None:
                properties._set_note_placement(tag, place=placement, beneath_text=beneath_text)

        self._apply(section, caller, change)

    # -- 쪽 테두리·배경 ------------------------------------------------------

    def page_border(
        self, *, page_type: str = "BOTH", section: "int | HwpxOxmlSection | None" = None
    ) -> "PageBorder | None":
        """구역의 쪽 테두리·배경(``hp:pageBorderFill``) 하나. 그 쪽 종류(``BOTH``·``EVEN``·``ODD``)의 것이 없으면 None."""

        _one_of("page_type", page_type, ("BOTH", "EVEN", "ODD"), "page-border-fill-invalid")
        value = self._section(section, "page_border").properties.page_border_fill(page_type)
        if value is None:
            return None
        return PageBorder(
            page_type=value.page_type,
            border_fill_id_ref=value.border_fill_id_ref,
            text_border=value.text_border,
            header_inside=value.header_inside,
            footer_inside=value.footer_inside,
            fill_area=value.fill_area,
            offset_left=value.offset_left,
            offset_right=value.offset_right,
            offset_top=value.offset_top,
            offset_bottom=value.offset_bottom,
        )

    def set_page_border(
        self,
        *,
        page_type: str = "BOTH",
        border_fill_id_ref: str | int | None = None,
        text_border: str | None = None,
        header_inside: bool | None = None,
        footer_inside: bool | None = None,
        fill_area: str | None = None,
        offset_left: int | None = None,
        offset_right: int | None = None,
        offset_top: int | None = None,
        offset_bottom: int | None = None,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> None:
        """구역의 쪽 테두리·배경을 바꾸거나 만든다. 주지 않은 값은 그대로 둔다(:meth:`page_border` 의 짝).

        *border_fill_id_ref* 는 ``doc.styles.ensure_border_fill(...)`` 이 돌려준 id, *text_border* 는
        ``PAPER``·``CONTENT`` (간격을 종이에서 재는지 본문에서 재는지), *fill_area* 는 ``PAPER``·``PAGE``·
        ``BORDER``. 간격은 HWPUNIT(0..32767).
        """

        if text_border is not None:
            _one_of("text_border", text_border, ("PAPER", "CONTENT"), "page-border-fill-invalid")
        self._apply(section, "set_page_border", lambda target: target.properties.set_page_border_fill(
            page_type=page_type,
            border_fill_id_ref=border_fill_id_ref,
            text_border=text_border,
            header_inside=header_inside,
            footer_inside=footer_inside,
            fill_area=fill_area,
            offset_left=offset_left,
            offset_right=offset_right,
            offset_top=offset_top,
            offset_bottom=offset_bottom,
        ))

    # -- 바탕쪽 연결 끊기 ----------------------------------------------------

    def remove_master_page_reference(
        self,
        master_page_id: "str | HwpxOxmlMasterPage",
        *,
        section: "int | HwpxOxmlSection | Literal['all'] | None" = None,
    ) -> bool:
        """이 구역과 바탕쪽 *master_page_id* (id 나 ``MasterPage``)의 연결을 끊는다. 끊은 연결이 있으면 True.

        :meth:`set_master_page` 의 짝이다. 바탕쪽 파트는 남는다. 어느 구역도 쓰지 않게 된 바탕쪽은
        ``doc.parts.remove_master_page(id)`` 로 지운다. ``section="all"`` 이면 모든 구역에서 끊는다.
        """

        removed: list[bool] = []

        def change(target: "HwpxOxmlSection") -> bool:
            removed.append(target.properties.remove_master_page_reference(master_page_id))
            return removed[-1]

        self._apply(section, "remove_master_page_reference", change)
        return any(removed)


#: ``section="all"``: a ``doc.page`` setter changes every section.
ALL_SECTIONS = "all"

_NOTE_NUMBERINGS = {
    "footNotePr": ("CONTINUOUS", "ON_SECTION", "ON_PAGE"),
    "endNotePr": ("CONTINUOUS", "ON_SECTION"),
}
_NOTE_PLACEMENTS = {
    "footNotePr": ("EACH_COLUMN", "MERGED_COLUMN", "RIGHT_MOST_COLUMN"),
    "endNotePr": ("END_OF_DOCUMENT", "END_OF_SECTION"),
}


def _one_of(argument: str, value: object, allowed: "Sequence[str]", code: str) -> None:
    if value not in allowed:
        raise HwpxValueError(
            f"{argument} 는 {', '.join(allowed)} 중 하나여야 합니다 — {value!r}.",
            code=code,
            context={"argument": argument, "value": repr(value), "allowed": list(allowed)},
            suggestion=f"{argument}= 에 {', '.join(allowed)} 중 하나를 주세요.",
        )


def _int_in(argument: str, value: object, low: int, high: int, code: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise HwpxValueError(
            f"{argument} 는 {low}..{high} 의 정수여야 합니다 — {value!r}.",
            code=code,
            context={"argument": argument, "value": repr(value), "low": low, "high": high},
            suggestion=f"{argument}= 에 {low}..{high} 의 정수를 주세요.",
        )


def page_number_control(node: Any, paragraph: "HwpxOxmlParagraph | None") -> "PageNumberControl":
    """The :class:`PageNumberControl` an ``hp:pageNum`` element writes (``doc.page.page_number_controls()``)."""

    return PageNumberControl(
        position=node.get("pos", "BOTTOM_CENTER"),
        format_type=node.get("formatType", "DIGIT"),
        side_char=node.get("sideChar", ""),
        paragraph=paragraph,
    )


def number_restart(node: Any, paragraph: "HwpxOxmlParagraph | None") -> "NumberRestart":
    """The :class:`NumberRestart` an ``hp:newNum`` element writes (``doc.page.number_restarts()``)."""

    return NumberRestart(kind=node.get("numType", "PAGE"), number=_int(node.get("num"), 1), paragraph=paragraph)


def page_hiding(node: Any, paragraph: "HwpxOxmlParagraph | None") -> "PageHiding":
    """The :class:`PageHiding` an ``hp:pageHiding`` element writes (``doc.page.page_hidings()``)."""

    return PageHiding(
        header=_flag(node, "hideHeader"),
        footer=_flag(node, "hideFooter"),
        master_page=_flag(node, "hideMasterPage"),
        border=_flag(node, "hideBorder"),
        fill=_flag(node, "hideFill"),
        page_num=_flag(node, "hidePageNum"),
        paragraph=paragraph,
    )


def auto_number(node: Any, paragraph: "HwpxOxmlParagraph | None") -> "AutoNumber":
    """The :class:`AutoNumber` an ``hp:autoNum`` element writes (``doc.page.auto_numbers()``)."""

    fmt = node.find(f"{HP}autoNumFormat")
    return AutoNumber(
        kind=node.get("numType", "PAGE"),
        number=_int(node.get("num"), 0),
        format_type=fmt.get("type", "DIGIT") if fmt is not None else "DIGIT",
        prefix=fmt.get("prefixChar") if fmt is not None else None,
        suffix=fmt.get("suffixChar") if fmt is not None else None,
        superscript=_flag(fmt, "supscript") if fmt is not None else False,
        paragraph=paragraph,
    )


def _int(value: "str | None", default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _flag(element: Any, name: str) -> bool:
    return str(element.get(name, "0")).strip().lower() in ("1", "true")


def _width_mm(text: "str | None") -> float:
    try:
        return float(str(text or "0").replace("mm", "").strip())
    except ValueError:
        return 0.0


def _controls(section: "HwpxOxmlSection", local: str) -> "list[tuple[Any, HwpxOxmlParagraph]]":
    """Every ``hp:ctrl/hp:<local>`` of *section*, with the paragraph holding it, in document order.

    Looks in body, table-cell, text-box, caption, header, footer and note paragraphs; skips memo
    bodies and the second copy python-hwpx keeps of a header or footer.
    """

    from ...oxml import HwpxOxmlParagraph
    from .text import _paragraphs_everywhere

    found = []
    for element, role, _key in _paragraphs_everywhere(section.element):
        if role == "mirror":
            continue
        paragraph = None
        for run in element.findall(f"{HP}run"):
            for ctrl in run.findall(f"{HP}ctrl"):
                for node in ctrl.findall(f"{HP}{local}"):
                    if paragraph is None:
                        paragraph = HwpxOxmlParagraph(element, section)
                    found.append((node, paragraph))
    return found


def _body_column_nodes(section: "HwpxOxmlSection") -> "list[tuple[Any, HwpxOxmlParagraph]]":
    found = []
    for paragraph in section.paragraphs:
        for run in paragraph.element.findall(f"{HP}run"):
            for ctrl in run.findall(f"{HP}ctrl"):
                for node in ctrl.findall(f"{HP}colPr"):
                    found.append((node, paragraph))
    return found


def _text_width(section: "HwpxOxmlSection") -> int:
    properties = section.properties
    size, margins = properties.page_size, properties.page_margins
    gutter = 0 if size.gutter_type == "TOP_BOTTOM" else margins.gutter
    sizes = (size.drawn_width, margins.left, margins.right, gutter)
    return 0 if None in sizes else max(sizes[0] - sizes[1] - sizes[2] - sizes[3], 0)  # type: ignore[operator]


def _column_definition(node: Any, paragraph: "HwpxOxmlParagraph", section: "HwpxOxmlSection") -> "ColumnDefinition":
    from ...oxml.section_format import COLUMN_SHARES

    count = max(_int(node.get("colCount"), 1), 1)
    same_size = _flag(node, "sameSz") if node.get("sameSz") is not None else True
    gap = _int(node.get("sameGap"), 0) if same_size else 0
    text_width = _text_width(section)
    sizes = [(_int(size.get("width"), 0), _int(size.get("gap"), 0)) for size in node.findall(f"{HP}colSz")]
    if same_size or not sizes:
        width = max((text_width - gap * (count - 1)) // count, 0)
        widths = tuple((width, gap if index < count - 1 else 0) for index in range(count))
    else:
        widths = tuple(
            (share * text_width // COLUMN_SHARES, between * text_width // COLUMN_SHARES) for share, between in sizes
        )
    line = node.find(f"{HP}colLine")
    separator = None
    if line is not None and line.get("type", "NONE") != "NONE":
        separator = BorderLine(
            type=line.get("type", "SOLID"), width_mm=_width_mm(line.get("width")), color=line.get("color", "#000000")
        )
    return ColumnDefinition(
        count=count,
        type=node.get("type", "NEWSPAPER"),
        layout=node.get("layout", "LEFT"),
        same_size=same_size,
        gap=gap,
        widths=widths,
        separator=separator,
        paragraph=paragraph,
    )


def _note_shape_info(shape: Any, tag: str) -> "NoteShapeInfo":
    from ...oxml.section_format import NoteAutoNumFormat, NoteLine, NoteNumbering, NotePlacement, NoteShape, NoteSpacing

    if shape is None:  # no hp:footNotePr/endNotePr: what Hancom uses then (the values a new one is made with)
        shape = NoteShape(
            auto_num_format=NoteAutoNumFormat(type="DIGIT", user_char=None, prefix_char=None, suffix_char=")",
                                              supscript=False),
            note_line=NoteLine(length=0, type="SOLID", width="0.12 mm", color="#000000"),
            note_spacing=NoteSpacing(between_notes=850, below_line=567, above_line=567),
            numbering=NoteNumbering(type="CONTINUOUS", new_num=1),
            placement=NotePlacement(place=_NOTE_PLACEMENTS[tag][0], beneath_text=False),
        )
    line = shape.note_line
    number = shape.auto_num_format
    length = line.length
    if length >= 1 << 31:  # stored unsigned: 4294967295 is -1 (the whole column)
        length -= 1 << 32
    return NoteShapeInfo(
        number_format=number.type,
        user_char=number.user_char,
        prefix=number.prefix_char,
        suffix=number.suffix_char,
        superscript=number.supscript,
        numbering=shape.numbering.type,
        start=shape.numbering.new_num,
        placement=shape.placement.place,
        beneath_text=shape.placement.beneath_text,
        separator=BorderLine(type=line.type, width_mm=_width_mm(line.width), color=line.color),
        separator_length=length,
        between_notes=shape.note_spacing.between_notes,
        below_line=shape.note_spacing.below_line,
        above_line=shape.note_spacing.above_line,
    )
