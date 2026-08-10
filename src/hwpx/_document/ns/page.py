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

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from ...errors import HwpxValueError
from .._resolve import resolve_paragraph, resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...oxml import HwpxOxmlInlineObject, HwpxOxmlParagraph, HwpxOxmlSection
    from ...oxml.section_format import (
        LineNumberShape,
        PageMargins,
        PageSize,
        SectionGrid,
        SectionTextDirection,
        SectionVisibility,
    )
    from ...objects import PageSetup
    from ...oxml.section_story import HwpxOxmlSectionHeaderFooter

__all__ = ["PageNamespace"]

#: 6.12 트레인㊸ 갭③ — 스키마 선언 열거값(다른 어떤 값도 실코퍼스에 없음,
#: 실측 근거는 SectionTextDirection 독스트링 참조).
_TEXT_DIRECTIONS = frozenset({"HORIZONTAL", "VERTICAL", "VERTICALALL"})


class PageNamespace(_Namespace):
    """쪽 기하 — 용지·여백·단·머리말/꼬리말·쪽번호·격자·줄번호."""

    __slots__ = ()
    _path = "doc.page"

    def _section(
        self,
        section: "int | HwpxOxmlSection | None",
        section_index: int | None,
        caller: str,
    ) -> "HwpxOxmlSection":
        return resolve_section(
            self._doc, section, section_index, caller=f"doc.page.{caller}"
        )

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
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "PageSetup":
        """용지·여백·단을 **mm 단위**로 한 번에 설정하고 결과를 돌려준다."""

        from .. import layout as _layout

        return _layout.set_page_setup(
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
            section=self._section(section, section_index, "setup"),
        )

    def set_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """용지 크기를 **HWPUNIT** 으로 설정한다(정밀 변형)."""

        from .. import layout as _layout

        _layout.set_page_size(
            self._doc,
            width=width,
            height=height,
            orientation=orientation,
            gutter_type=gutter_type,
            section=self._section(section, section_index, "set_size"),
        )

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
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """여백을 **HWPUNIT** 으로 설정한다(정밀 변형)."""

        from .. import layout as _layout

        _layout.set_page_margins(
            self._doc,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            header=header,
            footer=footer,
            gutter=gutter,
            section=self._section(section, section_index, "set_margins"),
        )

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
        paragraph: "HwpxOxmlParagraph | None" = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "HwpxOxmlInlineObject":
        """단(段) 정의를 삽입한다."""

        from .. import layout as _layout

        return _layout.set_columns(
            self._doc,
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
            section=self._section(section, section_index, "set_columns"),
        )

    # -- 머리말 / 꼬리말 ---------------------------------------------------

    def set_header(
        self,
        *,
        text: str | None = None,
        content: "Sequence[Mapping[str, Any]] | None" = None,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 머리말을 설정한다. ``text=`` 또는 ``content=`` 중 하나."""

        return self._set_header_footer(
            "header",
            text=text,
            content=content,
            page_type=page_type,
            section=section,
            section_index=section_index,
        )

    def set_footer(
        self,
        *,
        text: str | None = None,
        content: "Sequence[Mapping[str, Any]] | None" = None,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 꼬리말을 설정한다. ``text=`` 또는 ``content=`` 중 하나."""

        return self._set_header_footer(
            "footer",
            text=text,
            content=content,
            page_type=page_type,
            section=section,
            section_index=section_index,
        )

    def _set_header_footer(
        self,
        kind: str,
        *,
        text: str | None,
        content: "Sequence[Mapping[str, Any]] | None",
        page_type: str,
        section: "int | HwpxOxmlSection | None",
        section_index: int | None,
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

        return _layout.set_header_footer(
            self._doc,
            kind=kind,
            text=text,
            content=content,
            section=self._section(section, section_index, caller),
            page_type=page_type,
        )

    def remove_header(
        self,
        *,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """쪽 머리말을 제거한다."""

        from .. import layout as _layout

        _layout.remove_header(
            self._doc,
            section=self._section(section, section_index, "remove_header"),
            page_type=page_type,
        )

    def remove_footer(
        self,
        *,
        page_type: str = "BOTH",
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """쪽 꼬리말을 제거한다."""

        from .. import layout as _layout

        _layout.remove_footer(
            self._doc,
            section=self._section(section, section_index, "remove_footer"),
            page_type=page_type,
        )

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
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "HwpxOxmlSectionHeaderFooter":
        """쪽 번호를 머리말/꼬리말에 넣는다."""

        from .. import layout as _layout

        return _layout.set_page_number(
            self._doc,
            target=target,
            page_type=page_type,
            format=format,
            align=align,
            position=position,
            prefix=prefix,
            suffix=suffix,
            format_type=format_type,
            section=self._section(section, section_index, "set_page_number"),
        )

    def restart_page_number(
        self,
        paragraph: "HwpxOxmlParagraph | int",
        *,
        number: int = 1,
        kind: str = "PAGE",
    ) -> "HwpxOxmlInlineObject":
        """*paragraph* 부터 *kind* 의 진행 번호를 *number* 로 재시작한다.

        `set_page_number` 가 머리말/꼬리말의 *표시* 필드를 다루는 것과 달리,
        이건 구역 중간의 재시작 지점(`hp:newNum`)을 문단에 심는다.
        """

        from .. import layout as _layout

        return _layout.restart_page_number(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.page.restart_page_number"),
            number=number,
            kind=kind,
        )

    def hide_page_elements(
        self,
        paragraph: "HwpxOxmlParagraph | int",
        *,
        header: bool = False,
        footer: bool = False,
        master_page: bool = False,
        border: bool = False,
        fill: bool = False,
        page_num: bool = False,
    ) -> "HwpxOxmlInlineObject":
        """*paragraph* 가 속한 쪽부터 지정한 요소를 숨긴다(`hp:pageHiding`)."""

        from .. import layout as _layout

        return _layout.hide_page_elements(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.page.hide_page_elements"),
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
        section_index: int | None = None,
    ) -> "PageSize":
        """현재 용지 크기."""

        return self._section(section, section_index, "size").properties.page_size

    def margins(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "PageMargins":
        """현재 여백."""

        return self._section(section, section_index, "margins").properties.page_margins

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
        section_index: int | None = None,
    ) -> tuple[str, ...]:
        """이 절이 참조하는 바탕쪽 id(``hp:masterPage/@idRef``) 목록."""

        return self._section(
            section, section_index, "master_page_refs"
        ).properties.master_page_refs

    def set_master_page(
        self,
        master_page_id: str,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """이 절이 바탕쪽(``doc.parts.add_master_page``가 만든 id)을
        참조하도록 등록한다(6.13 트레인㊻). 이미 참조 중이면 아무 일도
        안 한다(멱등)."""

        self._section(
            section, section_index, "set_master_page"
        ).properties.add_master_page_reference(master_page_id)

    def grid(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "SectionGrid":
        """줄/글자 격자 설정."""

        return self._section(section, section_index, "grid").properties.grid

    def set_grid(
        self,
        *,
        line_grid: int | None = None,
        char_grid: int | None = None,
        wonggoji_format: bool | None = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """줄/글자 격자(원고지 형식 포함)를 설정한다."""

        self._section(section, section_index, "set_grid").properties.set_grid(
            line_grid=line_grid,
            char_grid=char_grid,
            wonggoji_format=wonggoji_format,
        )

    def text_direction(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "SectionTextDirection":
        """글자 방향(가로쓰기/세로쓰기)과 머리말/꼬리말 세로쓰기 여부."""

        return self._section(
            section, section_index, "text_direction"
        ).properties.text_direction

    def set_text_direction(
        self,
        direction: str | None = None,
        *,
        vertical_header_footer: bool | None = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
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
        self._section(
            section, section_index, "set_text_direction"
        ).properties.set_text_direction(
            direction, vertical_header_footer=vertical_header_footer
        )

    def visibility(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "SectionVisibility":
        """첫 쪽 숨김 플래그와 줄번호 표시 여부."""

        return self._section(section, section_index, "visibility").properties.visibility

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
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """첫 쪽 숨김 플래그와 줄번호 표시 여부를 설정한다."""

        self._section(
            section, section_index, "set_visibility"
        ).properties.set_visibility(
            hide_first_header=hide_first_header,
            hide_first_footer=hide_first_footer,
            hide_first_master_page=hide_first_master_page,
            hide_first_page_num=hide_first_page_num,
            hide_first_empty_line=hide_first_empty_line,
            show_line_number=show_line_number,
            border=border,
            fill=fill,
        )

    def line_numbers(
        self,
        *,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "LineNumberShape":
        """줄번호 표시 규칙."""

        return self._section(
            section, section_index, "line_numbers"
        ).properties.line_number_shape

    def set_line_numbers(
        self,
        *,
        restart_type: int | None = None,
        count_by: int | None = None,
        distance: int | None = None,
        start_number: int | None = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> None:
        """줄번호 재시작·간격·시작값을 설정한다."""

        self._section(
            section, section_index, "set_line_numbers"
        ).properties.set_line_number_shape(
            restart_type=restart_type,
            count_by=count_by,
            distance=distance,
            start_number=start_number,
        )
