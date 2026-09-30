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
        line_width: str = "33",
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
        line_width: str = "33",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        original_size: "tuple[int, int] | None" = None,
    ) -> "Shape":
        """사각형을 넣는다(`ratio` 로 모서리 둥글기).

        *original_size* `(w, h)`를 주면 `hp:orgSz`를 그리는 크기와 따로 쓴다.
        도형은 원래 크기로 만들고 `scaMatrix`로 *width* x *height*에 맞춘다.
        주지 않으면 `orgSz`는 `curSz`와 같다.
        """

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
            original_size=original_size,
        )

    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width: str = "33",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        original_size: "tuple[int, int] | None" = None,
    ) -> "Shape":
        """타원을 넣는다. *original_size*는 `add_rectangle`과 같다."""

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
            original_size=original_size,
        )

    def add_arc(
        self,
        width: int = 14400,
        height: int = 14400,
        *,
        corner: str = "TOP_LEFT",
        arc_type: str = "NORMAL",
        line_color: str = "#000000",
        line_width: str = "33",
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
        line_width: str = "33",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        closed: bool = True,
    ) -> "Shape":
        """다각형을 넣는다(꼭짓점은 mm, 자기 bbox 좌상단 원점 로컬 좌표계로 배치).

        첫 꼭짓점을 끝에 한 번 더 써서 닫는다(한컴이 다각형을 닫는 방식).
        `closed=False`면 꼭짓점을 잇는 열린 선이다."""

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
            closed=closed,
        )

    def add_curve(
        self,
        points_mm: Sequence[tuple[float, float]],
        *,
        closed: bool = False,
        line_color: str = "#000000",
        line_width: str = "33",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "Shape":
        """곡선을 넣는다(앵커는 mm, 2개 이상, 닫으면 3개 이상).

        한/글은 앵커를 지나는 곡선을 그리고 크기 상자는 스스로 다시 계산하지 않는다.
        그래서 한/글 곡선이 갖는 상자(구간마다 16단계 꺾은선으로 근사한 곡선의 상자)를 쓰고,
        앵커는 그 상자 좌상단 원점 로컬 좌표로 둔다."""

        from .. import shapes as _shapes

        return _shapes.add_curve(
            self._doc,
            points_mm=points_mm,
            closed=closed,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_curve"),
        )

    def add_connector(
        self,
        start: "Shape",
        end: "Shape",
        *,
        start_side: str = "right",
        end_side: str = "left",
        kind: str = "STRAIGHT",
        line_color: str = "#000000",
        line_width: str = "33",
        paragraph: "Paragraph | None" = None,
    ) -> "Shape":
        """두 도형을 잇는 연결선을 넣는다(각 도형 상자의 한 변 가운데: top/right/bottom/left).

        `kind`는 직선(`STRAIGHT`)이나 꺾인 선(`STROKE`)이다. 두 도형은 글자처럼 두지 않고
        같은 기준(종이·쪽, 또는 연결선 문단의 단·문단)에서 왼쪽·위로 놓여 있어야 한다. 한/글은
        붙은 연결선을 도형 상자로 다시 그리므로 도형을 옮기거나 키워도 선이 따라간다."""

        from .. import shapes as _shapes

        return _shapes.add_connector(
            self._doc,
            start,
            end,
            start_side=start_side,
            end_side=end_side,
            kind=kind,
            line_color=line_color,
            line_width=line_width,
            paragraph=paragraph,
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

    def remove_unused_charts(self) -> tuple[str, ...]:
        """어떤 차트도 가리키지 않는 차트 파트(``Chart/...``)를 모두 지우고, 지운 파트 이름을 돌려준다.

        한/글은 문서를 저장할 때 이런 파트를 지운다. 본문에서 차트를 지우면
        (``section.clear_body()``, 문단 삭제) 그 차트의 파트가 차트 자료와 함께
        패키지에 남는다. 문서 어디든(구역, 바탕쪽, header, 기록) ``hp:chart``가 그
        파일을 가리키면 지우지 않는다. 한/글 문서의 차트에 딸린 OLE 대체본
        (``BinData``)은 :meth:`doc.media.remove_unused_images`가 지운다."""

        from .. import shapes as _shapes

        return _shapes.remove_unused_charts(self._doc)

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
        """문단 첫 글자 장식(drop cap) — 실코퍼스 실측 기반, `style="TripleLine"`과
        `"DoubleLine"`을 지원(`hwpx.oxml.drop_cap` 독스트링 참조). *width*/*height*는 HWPUNIT,
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
