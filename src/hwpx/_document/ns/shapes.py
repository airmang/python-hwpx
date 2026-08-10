# SPDX-License-Identifier: Apache-2.0
"""`doc.shapes` — 도형·차트·수식 등 인라인 개체 저작.

능력 레지스트리의 다섯 영역(`shape-authoring`·`shape-escape-hatch`·
`curve-objects`·`chart`·`equation`)이 여기 모인다. 전부 "문단 흐름 안에 놓이는
개체를 만든다"는 한 가지 일이다.

`add_shape` 는 `add_raw` 로 이름이 바뀌었다 — 그것이 하는 일은 임의의 도형
태그를 그대로 내보내는 **탈출구**이고, 이름이 그 사실을 말해야 한다.
5.x 이름은 shim 으로 살아 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from .._resolve import resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...model import InlineObject, Paragraph, Section, Shape
    from ...oxml import ContainerMember

__all__ = ["ShapesNamespace"]


class ShapesNamespace(_Namespace):
    """도형·차트·수식 등 인라인 개체 저작."""

    __slots__ = ()
    _path = "doc.shapes"

    def _section(self, section, section_index, caller: str) -> "Section":
        return resolve_section(
            self._doc, section, section_index, caller=f"doc.shapes.{caller}"
        )

    # -- 기본 도형 ---------------------------------------------------------

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
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """직선을 넣는다."""

        from .. import shapes as _shapes

        return _shapes.add_line(
            self._doc,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            line_color=line_color,
            line_width=line_width,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_line"),
        )

    # -- 덧말·글자 겹치기 ---------------------------------------------------

    def add_composed_character(
        self,
        compose_text: str,
        char_pr_id_refs: Sequence[str | int] | None = None,
        *,
        circle_type: str | None = None,
        char_sz: int | None = None,
        compose_type: str | None = None,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """글자 겹치기(원문자·합자)를 넣는다."""

        from .. import shapes as _shapes

        return _shapes.add_composed_character(
            self._doc,
            compose_text,
            char_pr_id_refs,
            circle_type=circle_type,
            char_sz=char_sz,
            compose_type=compose_type,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_composed_character"),
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_dutmal(
        self,
        main_text: str,
        sub_text: str,
        *,
        pos_type: str = "TOP",
        align: str = "CENTER",
        sz_ratio: int | None = 0,
        option: int | None = 0,
        style_id_ref: str | int | None = None,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """덧말(루비형 주석 텍스트)을 넣는다.

        낮은 확신 축(정직 고지): 실코퍼스 표본 1건에서 리버스엔지니어링했다
        (macOS 편집기 메뉴 스캔이 1급 메뉴 항목으로는 확인했다). 자세한
        근거는 ``hwpx.oxml.body.Dutmal``의 문서화 참조.
        """

        from .. import shapes as _shapes

        return _shapes.add_dutmal(
            self._doc,
            main_text,
            sub_text,
            pos_type=pos_type,
            align=align,
            sz_ratio=sz_ratio,
            option=option,
            style_id_ref=style_id_ref,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_dutmal"),
            char_pr_id_ref=char_pr_id_ref,
        )

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
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """사각형을 넣는다(`ratio` 로 모서리 둥글기)."""

        from .. import shapes as _shapes

        return _shapes.add_rectangle(
            self._doc,
            width=width,
            height=height,
            ratio=ratio,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_rectangle"),
        )

    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """타원을 넣는다."""

        from .. import shapes as _shapes

        return _shapes.add_ellipse(
            self._doc,
            width=width,
            height=height,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_ellipse"),
        )

    def add_arc(
        self,
        width: int = 14400,
        height: int = 14400,
        *,
        corner: str = "TOP_LEFT",
        arc_type: str = "NORMAL",
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """사분원(호)을 넣는다(`corner`로 꼭짓점 위치, `arc_type`으로 NORMAL/PIE/CHORD)."""

        from .. import shapes as _shapes

        return _shapes.add_arc(
            self._doc,
            width=width,
            height=height,
            corner=corner,
            arc_type=arc_type,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_arc"),
        )

    def add_polygon(
        self,
        points_mm: Sequence[tuple[float, float]],
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """다각형을 넣는다(꼭짓점은 mm, 자기 bbox 좌상단 원점 로컬 좌표계로 배치)."""

        from .. import shapes as _shapes

        return _shapes.add_polygon(
            self._doc,
            points_mm=points_mm,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_polygon"),
        )

    def add_container(
        self,
        members: "Sequence[ContainerMember]",
        *,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """도형을 그룹으로 묶는다(`ContainerMember.rect`/`.ellipse`/`.polygon`으로
        각 부재를 그룹 로컬 좌표로 만들어 넘긴다)."""

        from .. import shapes as _shapes

        return _shapes.add_container(
            self._doc,
            members,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_container"),
        )

    # -- 차트·수식 ---------------------------------------------------------

    def add_chart(
        self,
        chart_xml: bytes | str,
        *,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        size: tuple[int, int] | None = None,
        treat_as_char: bool = False,
        char_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """ECMA-376 `c:chartSpace` 를 차트 개체로 넣는다."""

        from .. import shapes as _shapes

        return _shapes.add_chart(
            self._doc,
            chart_xml=chart_xml,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_chart"),
            size=size,
            treat_as_char=treat_as_char,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_drop_cap(
        self,
        character: str,
        *,
        width: int,
        height: int,
        style: str = "TripleLine",
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """문단 첫 글자 장식(drop cap) — 실코퍼스 실측 기반, `style="TripleLine"`만
        지원(`hwpx.oxml.drop_cap` 독스트링 참조). *width*/*height*는 HWPUNIT,
        자동 계산 안 함(실측된 공식이 없음)."""

        from .. import shapes as _shapes

        return _shapes.add_drop_cap(
            self._doc,
            character,
            width=width, height=height, style=style,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_drop_cap"),
            char_pr_id_ref=char_pr_id_ref,
            para_pr_id_ref=para_pr_id_ref,
        )

    def add_equation(
        self,
        script: str,
        *,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        base_unit: int = 1100,
        size: tuple[int, int] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """EqEdit 스크립트를 수식 개체로 넣는다."""

        from .. import shapes as _shapes

        return _shapes.add_equation(
            self._doc,
            script=script,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_equation"),
            base_unit=base_unit,
            size=size,
            char_pr_id_ref=char_pr_id_ref,
        )

    # -- 탈출구 ------------------------------------------------------------

    def add_raw(
        self,
        shape_type: str,
        *,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> "InlineObject":
        """모델이 없는 도형 태그를 그대로 내보낸다(저수준 탈출구).

        Warning:
            필수 기하 자식(`offset`·`orgSz`·`curSz`·`sz`·`pos`)을 직접 채우지
            않으면 한컴이 문서 열기를 거부한다. 대부분의 경우
            `add_line`/`add_rectangle`/`add_ellipse` 가 맞다.
        """

        from .. import shapes as _shapes

        return _shapes.add_shape(
            self._doc,
            shape_type=shape_type,
            section=self._section(section, section_index, "add_raw"),
            # 명시하지 않으면 **extra_attrs 가 이 자리에 흘러들 수 있다.
            section_index=None,
            attributes=attributes,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )

    def add_control(
        self,
        *,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        control_type: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> "InlineObject":
        """모델이 없는 `hp:ctrl` 을 그대로 내보낸다(저수준 탈출구)."""

        from .. import shapes as _shapes

        return _shapes.add_control(
            self._doc,
            section=self._section(section, section_index, "add_control"),
            # 명시하지 않으면 **extra_attrs 가 이 자리에 흘러들 수 있다.
            section_index=None,
            attributes=attributes,
            control_type=control_type,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )
