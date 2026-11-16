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

from typing import Sequence

from ...model import Equation, InlineObject, Paragraph, Section, Shape
from ...objects import Alignment, ComposedCharacter, Ruby
from ...oxml import ContainerMember, Style
from .._resolve import optional_paragraph, resolve_section
from ._base import _Namespace

__all__ = ["ShapesNamespace"]


class ShapesNamespace(_Namespace):
    """도형·차트·수식 등 인라인 개체 저작."""

    __slots__ = ()
    _path = "doc.shapes"

    def _section(self, section, caller: str) -> "Section":
        return resolve_section(
            self._doc, section, caller=f"doc.shapes.{caller}"
        )

    def _paragraph(self, paragraph, section) -> "Paragraph | None":
        """``paragraph=``: an index (in *section* when given, else in the whole document) or a
        paragraph of this document; ``None`` adds a new one."""

        return optional_paragraph(
            self._doc, paragraph, section=section, caller="doc.shapes"
        )

    # -- 기본 도형 ---------------------------------------------------------
    #
    # 선 굵기는 어디서나 ``line_width_mm`` (mm, float)다. 기본 0.12 mm 는 HWPUNIT 33 으로 쓰이고
    # (6.x 의 ``line_width="33"``), 0 은 선이 없다.

    def add_line(
        self,
        start_x: int = 0,
        start_y: int = 0,
        end_x: int = 14400,
        end_y: int = 0,
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
    ) -> "Shape":
        """직선을 넣는다. 좌표는 HWPUNIT, 선 굵기 *line_width_mm* 는 mm(0 은 선 없음)."""

        from .. import shapes as _shapes

        return _shapes.add_line(
            self._doc,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            line_color=line_color,
            line_width_mm=line_width_mm,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_line"),
        )

    # -- 덧말·글자 겹치기 ---------------------------------------------------

    def add_composed_character(
        self,
        text: str,
        char_pr_id_refs: Sequence[str | int] | None = None,
        *,
        frame: str | None = None,
        inner_size: int | None = None,
        arrangement: str | None = None,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "ComposedCharacter":
        """글자 겹치기(원문자·합자)를 넣고 :attr:`composed_characters` 가 읽는 :class:`ComposedCharacter` 를 돌려준다.

        *text* 는 겹칠 글자, *frame* 은 둘레(``"SHAPE_CIRCLE"`` 원·``"SHAPE_RECTANGLE"`` 사각형 …,
        ``"CHAR"`` 는 둘레 없음), *inner_size* 는 둘레 안 글자 크기 단계(0 은 그대로, 0보다 작으면 작게),
        *arrangement* 는 글자를 둘레 안에 펼칠지(``"SPREAD"``) 겹칠지(``"OVERLAP"``)다. 주지 않으면 한/글이
        새로 만드는 값(``SHAPE_CIRCLE``·``-4``·``SPREAD``)이다. *char_pr_id_refs* 는 겹친 글자 자리마다의
        글자 모양 id, *char_pr_id_ref* 는 이것을 담는 런의 글자 모양이다.
        """

        from .. import shapes as _shapes

        return _shapes.add_composed_character(
            self._doc,
            text,
            char_pr_id_refs,
            frame=frame,
            inner_size=inner_size,
            arrangement=arrangement,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_composed_character"),
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_ruby(
        self,
        text: str,
        ruby_text: str,
        *,
        position: str = "TOP",
        alignment: "Alignment | str" = "CENTER",
        size_ratio: int | None = 0,
        option: int | None = 0,
        style_id_ref: str | int | None = None,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "Ruby":
        """덧말을 넣고 :attr:`rubies` 가 읽는 :class:`Ruby` 를 돌려준다.

        *text* 는 본말, *ruby_text* 는 그 위(``position="TOP"``)나 아래(``"BOTTOM"``)에 작게 붙는
        덧말이다. *alignment* 는 덧말을 본말에 맞추는 방식(``Alignment`` 나 그 이름), *size_ratio* 는
        덧말 크기(본말의 %, 0 은 한/글 기본)다. *style_id_ref* 를 주지 않으면 덧말 스타일은 0 이다.

        낮은 확신 축(정직 고지): 실코퍼스 표본 1건에서 리버스엔지니어링했다
        (macOS 편집기 메뉴 스캔이 1급 메뉴 항목으로는 확인했다). 자세한
        근거는 ``hwpx.oxml.body.Dutmal``의 문서화 참조.
        """

        from .. import shapes as _shapes

        return _shapes.add_ruby(
            self._doc,
            text,
            ruby_text,
            position=position,
            alignment=alignment,
            size_ratio=size_ratio,
            option=option,
            style_id_ref=style_id_ref,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_ruby"),
            char_pr_id_ref=char_pr_id_ref,
        )

    @property
    def rubies(self) -> "tuple[Ruby, ...]":
        """문서의 모든 덧말(``hp:dutmal``)을 문서 순서로. 본문뿐 아니라 표 칸·글상자·머리말·
        꼬리말·각주·미주·바탕쪽의 것도 본다(메모 본문은 뺀다).

        ``ruby.text``(본말)·``ruby.ruby_text``(덧말)·``position``·``alignment`` 는 읽고 쓸 수
        있고, ``ruby.remove()`` 는 덧말만 걷고 본말을 글로 남긴다. 문단 하나의 것은
        ``paragraph.rubies``.
        """

        from ..text_blocks import iter_paragraph_places

        return tuple(
            ruby
            for place in iter_paragraph_places(self._doc)
            if place.where != "memo"
            for ruby in place.paragraph.rubies
        )

    @property
    def composed_characters(self) -> "tuple[ComposedCharacter, ...]":
        """문서의 모든 글자 겹치기(``hp:compose``)를 문서 순서로, :attr:`rubies` 와 같은 자리에서.

        ``text``·``frame``·``arrangement`` 는 읽고 쓸 수 있고, ``remove()`` 는 겹친 글자를
        보통 글로 남기고 걷어 낸다. 문단 하나의 것은 ``paragraph.composed_characters``.
        """

        from ..text_blocks import iter_paragraph_places

        return tuple(
            mark
            for place in iter_paragraph_places(self._doc)
            if place.where != "memo"
            for mark in place.paragraph.composed_characters
        )

    def add_rectangle(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
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
            line_width_mm=line_width_mm,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_rectangle"),
            original_size=original_size,
        )

    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        original_size: "tuple[int, int] | None" = None,
    ) -> "Shape":
        """타원을 넣는다. *original_size*는 `add_rectangle`과 같다."""

        from .. import shapes as _shapes

        return _shapes.add_ellipse(
            self._doc,
            width=width,
            height=height,
            line_color=line_color,
            line_width_mm=line_width_mm,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_ellipse"),
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
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
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
            line_width_mm=line_width_mm,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_arc"),
        )

    def add_polygon(
        self,
        points_mm: Sequence[tuple[float, float]],
        *,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
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
            line_width_mm=line_width_mm,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_polygon"),
            closed=closed,
        )

    def add_curve(
        self,
        points_mm: Sequence[tuple[float, float]],
        *,
        closed: bool = False,
        line_color: str = "#000000",
        line_width_mm: float = 0.12,
        fill_color: str | None = None,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
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
            line_width_mm=line_width_mm,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_curve"),
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
        line_width_mm: float = 0.12,
        paragraph: "Paragraph | int | None" = None,
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
            line_width_mm=line_width_mm,
            paragraph=self._paragraph(paragraph, None),
        )

    def add_container(
        self,
        members: "Sequence[ContainerMember]",
        *,
        treat_as_char: bool = True,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
    ) -> "Shape":
        """도형을 그룹으로 묶는다(`ContainerMember.rect`/`.ellipse`/`.polygon`/`.line`/
        `.text_box`/`.picture`/`.group`으로 각 부재를 그룹 로컬 좌표로 만들어 넘긴다)."""

        from .. import shapes as _shapes

        return _shapes.add_container(
            self._doc,
            members,
            treat_as_char=treat_as_char,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_container"),
        )

    # -- 차트·수식 ---------------------------------------------------------

    def add_chart(
        self,
        chart_xml: bytes | str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        treat_as_char: bool = False,
        char_pr_id_ref: str | int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> "InlineObject":
        """ECMA-376 `c:chartSpace` 를 차트 개체로 넣는다.

        *width*·*height* 는 차트 상자(HWPUNIT)다. 둘 다 주지 않으면 한/글 예제 문서의 크기
        (32250×18750)를 넣을 표 칸·본문 폭에 맞게 같은 비율로 줄여 쓰고, 하나만 주면 나머지는 그
        예제 문서의 값이다.
        """

        from .. import shapes as _shapes

        return _shapes.add_chart(
            self._doc,
            chart_xml=chart_xml,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_chart"),
            treat_as_char=treat_as_char,
            char_pr_id_ref=char_pr_id_ref,
            width=width,
            height=height,
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
        kind: str = "TripleLine",
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """문단 첫 글자 장식(drop cap) — 실코퍼스 실측 기반, 모양 `kind="TripleLine"`(세 줄)과
        `"DoubleLine"`(두 줄)을 지원(`hwpx.oxml.drop_cap` 독스트링 참조). *width*/*height*는 HWPUNIT,
        자동 계산 안 함(실측된 공식이 없음)."""

        from .. import shapes as _shapes

        return _shapes.add_drop_cap(
            self._doc,
            character,
            width=width, height=height, kind=kind,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_drop_cap"),
            char_pr_id_ref=char_pr_id_ref,
            para_pr_id_ref=para_pr_id_ref,
        )

    def add_equation(
        self,
        script: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        font_size: float = 11.0,
        char_pr_id_ref: str | int | None = None,
        font: str = "HancomEQN",
        width: int | None = None,
        height: int | None = None,
    ) -> "Equation":
        """EqEdit 스크립트를 수식 개체로 넣는다.

        ``font_size``는 수식 글자 크기(pt)다. ``width``·``height``는 수식 상자(HWPUNIT)이고, 주지 않은
        쪽은 스크립트를 *font_size* 로 재어 정한다. ``font``는 수식 글꼴이다. 기본값 ``HancomEQN``은
        한/글 수식 편집기가 쓰는 글꼴이고, 7.0 전의 모양을 원하면 ``font="HYhwpEQ"``를 준다.
        """

        from .. import shapes as _shapes

        return _shapes.add_equation(
            self._doc,
            script=script,
            paragraph=self._paragraph(paragraph, section),
            section=self._section(section, "add_equation"),
            font_size=font_size,
            char_pr_id_ref=char_pr_id_ref,
            font=font,
            width=width,
            height=height,
        )

    @property
    def equations(self) -> "tuple[Equation, ...]":
        """문서 본문의 수식 전부를 문서 순서로 돌려준다.

        표 칸·글상자·각주·미주·머리말·꼬리말 안의 수식도 든다. 하나하나가
        ``model.Equation``이라 ``script``를 읽고 쓰고(``equation.script = ...``) ``remove()``로 지운다.
        한 문단의 수식만 보려면 ``paragraph.equations``.
        """

        from .. import shapes as _shapes

        return _shapes.equations(self._doc)

    # -- 탈출구 ------------------------------------------------------------

    def add_raw(
        self,
        shape_type: str,
        *,
        section: "int | Section | None" = None,
        attributes: dict[str, str] | None = None,
        para_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> "InlineObject":
        """모델이 없는 도형 태그를 그대로 내보낸다 — 약속하지 않는 탈출구(계약 밖, ``.element`` 와 같은 자리).

        지정한 태그와 속성만 쓰고 엔진의 거부·인자 검사를 거치지 않는다. 공개 표면 잠금에 들지 않아 판 사이에
        바뀔 수 있다(docs/stable-api.md).

        Warning:
            필수 기하 자식(`offset`·`orgSz`·`curSz`·`sz`·`pos`)을 직접 채우지
            않으면 한컴이 문서 열기를 거부한다. 대부분의 경우
            `add_line`/`add_rectangle`/`add_ellipse` 가 맞다.
        """

        from .. import shapes as _shapes

        return _shapes.add_shape(
            self._doc,
            shape_type=shape_type,
            section=self._section(section, "add_raw"),
            # 명시하지 않으면 **extra_attrs 가 이 자리에 흘러들 수 있다.
            attributes=attributes,
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )

    def add_control(
        self,
        *,
        section: "int | Section | None" = None,
        attributes: dict[str, str] | None = None,
        control_type: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> "InlineObject":
        """모델이 없는 `hp:ctrl` 을 그대로 내보낸다 — 약속하지 않는 탈출구(계약 밖, ``.element`` 와 같은 자리).

        빈 ``hp:ctrl`` 은 한/글이 열지 못하므로 저장 전 열기 안전 검사가 막는다. 공개 표면 잠금에 들지 않는다.
        """

        from .. import shapes as _shapes

        return _shapes.add_control(
            self._doc,
            section=self._section(section, "add_control"),
            # 명시하지 않으면 **extra_attrs 가 이 자리에 흘러들 수 있다.
            attributes=attributes,
            control_type=control_type,
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            **extra_attrs,
        )
