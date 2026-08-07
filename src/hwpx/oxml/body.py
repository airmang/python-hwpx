# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from lxml import etree

from .common import GenericElement
from .namespaces import HP
from .utils import local_name, parse_bool, parse_int


_DEFAULT_HP = HP

INLINE_OBJECT_NAMES = {
    "line",
    "rect",
    "ellipse",
    "arc",
    "polyline",
    "polygon",
    "curve",
    "connectLine",
    "picture",
    "pic",
    "shape",
    "drawingObject",
    "container",
    "equation",
    "ole",
    "chart",
    "video",
    "audio",
    "textart",
}

_TRACK_CHANGE_MARK_NAMES = {
    "insertBegin",
    "insertEnd",
    "deleteBegin",
    "deleteEnd",
}

_TRACK_CHANGE_TYPES = {
    "insert": "insert",
    "delete": "delete",
}

PreservedElement = Union[
    GenericElement,
    "CommentElement",
    "LineSegArray",
    "LineSeg",
    "TransformMatrix",
    "FormEditControl",
    "FormComboBoxControl",
    "ListItem",
    "ComposedCharacter",
    "Dutmal",
    "ParameterList",
    "Label",
]
InlineMark = Union[PreservedElement, "TrackChangeMark"]
RunChild = Union[PreservedElement, "Control", "Table", "InlineObject", "TextSpan", "Tab"]
ParagraphChild = Union["Run", PreservedElement]


@dataclass(slots=True)
class TrackChangeMark:
    tag: str
    name: str
    change_type: str
    is_begin: bool
    para_end: Optional[bool]
    tc_id: Optional[int]
    id: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TextMarkup:
    element: InlineMark
    trailing_text: str = ""

    @property
    def name(self) -> str:
        if isinstance(self.element, TrackChangeMark):
            return self.element.name
        if isinstance(self.element, ParameterList):
            # Every sibling PreservedElement type's ``.name`` is its tag's
            # local name (always a plain ``str``). ``ParameterList.name`` is
            # a different thing entirely -- the OWPML ``name=`` attribute
            # value (nullable, e.g. the empty-string field-parameter case
            # seen 304/306 times in the real corpus) -- so it cannot be
            # proxied through like the others without breaking that
            # contract. Derive the local tag name directly instead.
            return self.element.tag.rsplit("}", 1)[-1]
        if isinstance(self.element, Label):
            # Label has no .name field at all (DEV-023's attributes are all
            # typed individually, unlike GenericElement's catch-all shape) --
            # same derivation as ParameterList above, for the same reason
            # (nothing to proxy through).
            return self.element.tag.rsplit("}", 1)[-1]
        return self.element.name


@dataclass(slots=True)
class TextSpan:
    tag: str
    leading_text: str
    marks: List[TextMarkup] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.leading_text + "".join(mark.trailing_text for mark in self.marks)

    @text.setter
    def text(self, value: str) -> None:
        self.leading_text = value
        for mark in self.marks:
            mark.trailing_text = ""


@dataclass(slots=True)
class Control:
    tag: str
    control_type: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class InlineObject:
    tag: str
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class Tab:
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Table:
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)


@dataclass(slots=True)
class Label:
    """``hp:label`` -- Avery-style label-sheet/nameplate print layout,
    always the *last* child of ``hp:tbl`` (real corpus: always after every
    ``hp:tr`` row, matching ``ParaList XML schema.xml``'s own sequence
    order -- DEV-023, ``docs/owpml-deviations.md``). Unlike most elements
    this registry has reverse-engineered, the schema and 75 real private
    documents agree completely: all 11 attributes here, no more, no fewer,
    ``landscape`` the only non-integer one (schema enum ``WIDELY``/
    ``NARROWLY``, only ``WIDELY`` observed in the reverse-engineering
    sample -- ``NARROWLY`` is schema-legal but unconfirmed against real
    output)."""

    tag: str
    topmargin: Optional[int] = None
    leftmargin: Optional[int] = None
    boxwidth: Optional[int] = None
    boxlength: Optional[int] = None
    boxmarginhor: Optional[int] = None
    boxmarginver: Optional[int] = None
    labelcols: Optional[int] = None
    labelrows: Optional[int] = None
    landscape: Optional[str] = None
    pagewidth: Optional[int] = None
    pageheight: Optional[int] = None
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LineSeg:
    tag: str
    name: str
    text_pos: Optional[int]
    vert_pos: Optional[int]
    vert_size: Optional[int]
    text_height: Optional[int]
    baseline: Optional[int]
    spacing: Optional[int]
    horz_pos: Optional[int]
    horz_size: Optional[int]
    flags: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class LineSegArray:
    tag: str
    name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    linesegs: List[LineSeg] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)
    content: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class TransformMatrix:
    tag: str
    name: str
    e1: Optional[str]
    e2: Optional[str]
    e3: Optional[str]
    e4: Optional[str]
    e5: Optional[str]
    e6: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class FormEditControl:
    tag: str
    name: str
    multi_line: Optional[str]
    password_char: Optional[str]
    max_length: Optional[int]
    scroll_bars: Optional[str]
    tab_key_behavior: Optional[str]
    num_only: Optional[str]
    read_only: Optional[str]
    align_text: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None


@dataclass(slots=True)
class ListItem:
    """``hp:listItem`` — comboBox/listBox 옵션 한 개(ParaList XML
    schema.xml:2760, ``ListItemType``: ``displayText``/``value`` 속성뿐).

    ``tag``/``name``은 형제 preserved-element 타입(:class:`TransformMatrix`
    등)과 같은 관용구 — ``name``은 로컬 태그명("listItem")이라
    ``GenericElement``였을 때와 같은 자리에서 같은 값을 읽을 수 있다."""

    tag: Optional[str]
    name: str
    display_text: Optional[str]
    value: Optional[str]


@dataclass(slots=True)
class FormComboBoxControl:
    tag: str
    name: str
    list_box_rows: Optional[int]
    list_box_width: Optional[int]
    edit_enable: Optional[str]
    selected_value: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[PreservedElement] = field(default_factory=list)
    text: Optional[str] = None

    @property
    def list_items(self) -> List["ListItem"]:
        """``hp:listItem`` 자식들(스키마 순서 그대로) — 읽기 전용 뷰.

        옵션을 바꾸려면 ``children``에서 :class:`ListItem` 인스턴스를 직접
        추가/삭제/재배치한다 — 실코퍼스(SimpleComboBox.hwpx) 순서는
        ``formCharPr``, ``listItem*``, ``sz``, ``pos``, ``outMargin`` 순으로
        섞여 있어, 별도 리스트로 뽑아내면 그 순서를 복원할 수 없다."""

        return [child for child in self.children if isinstance(child, ListItem)]


@dataclass(slots=True)
class Parameter:
    """OWPML ``ParameterList``(ParaList XML schema.xml:2764)의 잎 하나.

    ``kind``: "boolean"/"integer"/"unsignedinteger"/"float"/"string" 중 하나면
    ``value``에 타입에 맞는 파이썬 값을 담은 잎이고, "list"면 ``hp:listParam``
    ―같은 ``ParameterList`` 타입이 재귀한 것―이라 ``items``에 중첩
    ``Parameter``를 담는다. ``unsignedintegerParam``은 실코퍼스에서 관측됐지만
    이 리포의 스키마 사본(ParaList XML schema.xml)엔 없다 — 편차로 등재."""

    name: Optional[str]
    kind: str
    value: Optional[Union[bool, int, float, str]] = None
    items: List["Parameter"] = field(default_factory=list)


@dataclass(slots=True)
class ParameterList:
    """``hp:parameters``(필드 클릭 액션) / ``hp:parameterset``(도형 등 개체
    속성) 최상위 컨테이너 — 실코퍼스 실측: 이름만 다를 뿐 둘 다 같은
    ``ParameterList`` 복합타입이다. ``tag``가 어느 쪽이었는지 왕복 보존한다."""

    tag: str
    name: Optional[str]
    params: List[Parameter] = field(default_factory=list)


@dataclass(slots=True)
class ComposedCharacterSlot:
    """``hp:compose`` 안의 ``hp:charPr`` 하나 — 겹쳐 쓸 글자 한 슬롯의 서식
    참조(ParaList XML schema.xml:538-543, ``prIDRef`` 뿐)."""

    pr_id_ref: Optional[int]


@dataclass(slots=True)
class ComposedCharacter:
    """``hp:compose`` — 글자 겹치기(원문자·합자, ParaList XML
    schema.xml:535-588). ``hp:t``의 자식이 아니라 ``hp:run`` 직속(실코퍼스
    SimpleCompose.hwpx 확인 — ``hp:ctrl`` 다음, ``hp:t`` 형제)."""

    tag: str
    circle_type: Optional[str]
    char_sz: Optional[int]
    compose_type: Optional[str]
    char_pr_cnt: Optional[int]
    compose_text: Optional[str]
    slots: List[ComposedCharacterSlot] = field(default_factory=list)


@dataclass(slots=True)
class Dutmal:
    """``hp:dutmal`` — 덧말(본말 위/아래에 붙는 작은 주석 텍스트, 루비와
    같은 부류, ParaList XML schema.xml:585-621). ``hp:compose``와 같은 위치
    관례(``hp:t``의 자식이 아니라 ``hp:run`` 직속 -- 실코퍼스
    ``reader_writer__SimpleDutmal.hwpx`` 확인: 그 문서의 유일한 표본에서
    ``hp:secPr``·``hp:ctrl`` 다음, ``hp:t`` 형제였다).

    두 스키마 편차를 실측 그대로 왕복 보존한다(강제하지 않는다): 스키마는
    ``option``을 ``fixed="4"``로 선언하지만 실측 값은 ``"0"``이었고,
    ``szRatio``는 ``xs:positiveInteger``(1 이상)로 선언되지만 실측 값도
    ``"0"``이었다. 표본이 1건뿐이라(빈도 낮음, macOS 편집기 메뉴 스캔이
    1급 메뉴 항목으로 확인했을 뿐) 이 두 값이 그 문서만의 우연인지 실제
    관행인지는 모른다 -- 정직하게 실측값을 기본값으로 채택하고, 스키마의
    주장(4 고정·1 이상)을 검증 규칙으로 강제하지 않는다.
    """

    tag: str
    pos_type: Optional[str]
    sz_ratio: Optional[int]
    option: Optional[int]
    style_id_ref: Optional[int]
    align: Optional[str]
    main_text: Optional[str]
    sub_text: Optional[str]


@dataclass(slots=True)
class CommentElement:
    """Round-trips an XML comment or processing-instruction child node.

    Comment and processing-instruction nodes expose a callable ``tag``
    (``etree.Comment`` / ``etree.PI``) rather than a string, so the generic
    element model cannot represent them: feeding that callable to
    ``etree.Element`` raises ``TypeError``. This dedicated model captures the
    node faithfully so it can be reconstructed via :func:`etree.Comment` /
    :func:`etree.ProcessingInstruction`.
    """

    kind: str  # "comment" or "pi"
    text: Optional[str] = None
    target: Optional[str] = None  # processing-instruction target


@dataclass(slots=True)
class Run:
    tag: str
    char_pr_id_ref: Optional[int]
    section_properties: List[PreservedElement] = field(default_factory=list)
    controls: List[Control] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    inline_objects: List[InlineObject] = field(default_factory=list)
    tabs: List[Tab] = field(default_factory=list)
    text_spans: List[TextSpan] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    content: List[RunChild] = field(default_factory=list)


@dataclass(slots=True)
class Paragraph:
    tag: str
    id: Optional[int]
    para_pr_id_ref: Optional[int]
    style_id_ref: Optional[int]
    page_break: Optional[bool]
    column_break: Optional[bool]
    merged: Optional[bool]
    runs: List[Run] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    other_children: List[PreservedElement] = field(default_factory=list)
    content: List[ParagraphChild] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    tag: str
    attributes: Dict[str, str]
    paragraphs: List[Paragraph] = field(default_factory=list)
    other_children: List[PreservedElement] = field(default_factory=list)


def _qualified_tag(tag: Optional[str], name: str) -> str:
    if tag:
        return tag
    return f"{_DEFAULT_HP}{name}"


def _tag_namespace(tag: Optional[str]) -> Optional[str]:
    if not tag or not tag.startswith("{") or "}" not in tag:
        return None
    return tag[1:].split("}", 1)[0]


def _child_tag_like(parent_tag: Optional[str], name: str) -> str:
    namespace = _tag_namespace(parent_tag)
    if namespace:
        return f"{{{namespace}}}{name}"
    return _qualified_tag(None, name)


def _bool_to_str(value: bool) -> str:
    return "true" if value else "false"


def _bool_to_flag(value: bool) -> str:
    return "1" if value else "0"


def create_track_change_mark(
    change_type: str,
    *,
    is_begin: bool,
    tc_id: int,
    mark_id: int,
    para_end: bool | None = None,
) -> TrackChangeMark:
    """Create a typed inline tracked-change boundary mark."""

    normalized = _TRACK_CHANGE_TYPES.get(change_type.strip().lower())
    if normalized is None:
        raise ValueError("change_type must be 'insert' or 'delete'")
    name = f"{normalized}{'Begin' if is_begin else 'End'}"
    return TrackChangeMark(
        tag=_qualified_tag(None, name),
        name=name,
        change_type=normalized,
        is_begin=is_begin,
        para_end=para_end,
        tc_id=int(tc_id),
        id=int(mark_id),
    )


def append_tracked_insert_to_run(
    run: Run,
    text: str,
    *,
    tc_id: int,
    mark_id: int,
) -> None:
    """Append tracked inserted *text* to the last text span in *run*."""

    if not text:
        raise ValueError("tracked insert text must be non-empty")

    if run.text_spans:
        span = run.text_spans[-1]
    else:
        span = TextSpan(tag=_child_tag_like(run.tag, "t"), leading_text="")
        run.text_spans.append(span)
        run.content.append(span)

    span.marks.append(
        TextMarkup(
            create_track_change_mark("insert", is_begin=True, tc_id=tc_id, mark_id=mark_id),
            text,
        )
    )
    span.marks.append(
        TextMarkup(
            create_track_change_mark(
                "insert",
                is_begin=False,
                tc_id=tc_id,
                mark_id=mark_id,
                para_end=False,
            )
        )
    )


def insert_tracked_text_after_delete(
    span: TextSpan,
    text: str,
    *,
    delete_tc_id: int,
    insert_tc_id: int,
    mark_id: int,
) -> bool:
    """Insert tracked *text* immediately after one tracked deletion.

    A replacement must keep the inserted value at the deleted value's source
    position.  The text following ``deleteEnd`` belongs after the replacement,
    so move that suffix to ``insertEnd`` while splicing the insert marks between
    them.  Existing later marks retain their order.
    """

    if not text:
        raise ValueError("tracked insert text must be non-empty")

    for index, markup in enumerate(span.marks):
        mark = markup.element
        if not (
            isinstance(mark, TrackChangeMark)
            and mark.name == "deleteEnd"
            and mark.tc_id == delete_tc_id
        ):
            continue

        suffix = markup.trailing_text
        markup.trailing_text = ""
        begin = TextMarkup(
            create_track_change_mark(
                "insert",
                is_begin=True,
                tc_id=insert_tc_id,
                mark_id=mark_id,
            ),
            text,
        )
        end = TextMarkup(
            create_track_change_mark(
                "insert",
                is_begin=False,
                tc_id=insert_tc_id,
                mark_id=mark_id,
                para_end=False,
            ),
            suffix,
        )
        span.marks[index + 1 : index + 1] = [begin, end]
        return True

    return False


def wrap_tracked_delete_in_span(
    span: TextSpan,
    *,
    tc_id: int,
    mark_id: int,
    match: str | None = None,
) -> bool:
    """Wrap a whole span or a substring in tracked delete marks."""

    if match == "":
        raise ValueError("match must be a non-empty string")

    begin = TextMarkup(
        create_track_change_mark("delete", is_begin=True, tc_id=tc_id, mark_id=mark_id)
    )
    end = TextMarkup(
        create_track_change_mark(
            "delete",
            is_begin=False,
            tc_id=tc_id,
            mark_id=mark_id,
            para_end=False,
        )
    )

    if match is None:
        if not span.text:
            return False
        leading = span.leading_text
        span.leading_text = ""
        begin.trailing_text = leading
        span.marks.insert(0, begin)
        span.marks.append(end)
        return True

    index = span.leading_text.find(match)
    if index >= 0:
        before = span.leading_text[:index]
        after = span.leading_text[index + len(match) :]
        span.leading_text = before
        begin.trailing_text = match
        end.trailing_text = after
        span.marks[0:0] = [begin, end]
        return True

    for mark_index, markup in enumerate(span.marks):
        index = markup.trailing_text.find(match)
        if index < 0:
            continue
        before = markup.trailing_text[:index]
        after = markup.trailing_text[index + len(match) :]
        markup.trailing_text = before
        begin.trailing_text = match
        end.trailing_text = after
        span.marks[mark_index + 1 : mark_index + 1] = [begin, end]
        return True

    return False


def create_highlight_mark(*, is_begin: bool, color: str | None = None) -> GenericElement:
    """Create a ``markpenBegin``/``markpenEnd`` boundary element.

    Unlike :func:`create_track_change_mark`, there is no ``tc_id``/``mark_id``
    to allocate — the schema (``ParaList XML schema.xml``) gives
    ``markpenEnd`` no attributes at all, so begin/end pair positionally
    (first unmatched end closes the innermost open begin), the same rule
    :func:`hwpx.tools.text_extractor` already applies when it renders a
    ``hp:t`` for reading.
    """

    name = "markpenBegin" if is_begin else "markpenEnd"
    attributes: Dict[str, str] = {}
    if is_begin and color:
        attributes["color"] = color
    return GenericElement(name=name, tag=_qualified_tag(None, name), attributes=attributes)


def wrap_highlight_in_span(
    span: TextSpan,
    *,
    color: str,
    match: str,
) -> bool:
    """Wrap the first occurrence of *match* in *span* in markpen marks.

    Mirrors :func:`wrap_tracked_delete_in_span`'s substring branch exactly —
    a match must live entirely inside *span*'s ``leading_text`` or one
    existing mark's ``trailing_text``; a match that only appears once the
    span's pieces are concatenated straddles existing inline markup and is
    rejected by returning ``False`` (the caller distinguishes "not found" from
    "found but unsafe" the same way tracked-delete does).
    """

    if not match:
        raise ValueError("match must be a non-empty string")

    begin = TextMarkup(create_highlight_mark(is_begin=True, color=color))
    end = TextMarkup(create_highlight_mark(is_begin=False))

    index = span.leading_text.find(match)
    if index >= 0:
        before = span.leading_text[:index]
        after = span.leading_text[index + len(match) :]
        span.leading_text = before
        begin.trailing_text = match
        end.trailing_text = after
        span.marks[0:0] = [begin, end]
        return True

    for mark_index, markup in enumerate(span.marks):
        index = markup.trailing_text.find(match)
        if index < 0:
            continue
        before = markup.trailing_text[:index]
        after = markup.trailing_text[index + len(match) :]
        markup.trailing_text = before
        begin.trailing_text = match
        end.trailing_text = after
        span.marks[mark_index + 1 : mark_index + 1] = [begin, end]
        return True

    return False


def parse_track_change_mark(node: etree._Element) -> TrackChangeMark:
    attrs = {key: value for key, value in node.attrib.items()}
    para_end = parse_bool(attrs.pop("paraend", None))
    tc_id = parse_int(attrs.pop("TcId", None))
    mark_id = parse_int(attrs.pop("Id", None))
    name = local_name(node)
    change_type = "insert" if name.startswith("insert") else "delete"
    is_begin = name.endswith("Begin")
    return TrackChangeMark(
        tag=node.tag,
        name=name,
        change_type=change_type,
        is_begin=is_begin,
        para_end=para_end,
        tc_id=tc_id,
        id=mark_id,
        attributes=attrs,
    )


def _parse_int_attribute(attributes: Dict[str, str], name: str) -> Optional[int]:
    return parse_int(attributes.pop(name, None))


def parse_line_seg_element(node: etree._Element) -> LineSeg:
    attrs = {key: value for key, value in node.attrib.items()}
    return LineSeg(
        tag=node.tag,
        name=local_name(node),
        text_pos=_parse_int_attribute(attrs, "textpos"),
        vert_pos=_parse_int_attribute(attrs, "vertpos"),
        vert_size=_parse_int_attribute(attrs, "vertsize"),
        text_height=_parse_int_attribute(attrs, "textheight"),
        baseline=_parse_int_attribute(attrs, "baseline"),
        spacing=_parse_int_attribute(attrs, "spacing"),
        horz_pos=_parse_int_attribute(attrs, "horzpos"),
        horz_size=_parse_int_attribute(attrs, "horzsize"),
        flags=_parse_int_attribute(attrs, "flags"),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_line_seg_array_element(node: etree._Element) -> LineSegArray:
    line_array = LineSegArray(
        tag=node.tag,
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        text=node.text if node.text is not None else None,
    )

    for child in node:
        element = parse_preserved_element(child)
        if isinstance(element, LineSeg):
            line_array.linesegs.append(element)
        else:
            line_array.other_children.append(element)
        line_array.content.append(element)

    return line_array


def parse_transform_matrix_element(node: etree._Element) -> TransformMatrix:
    attrs = {key: value for key, value in node.attrib.items()}
    return TransformMatrix(
        tag=node.tag,
        name=local_name(node),
        e1=attrs.pop("e1", None),
        e2=attrs.pop("e2", None),
        e3=attrs.pop("e3", None),
        e4=attrs.pop("e4", None),
        e5=attrs.pop("e5", None),
        e6=attrs.pop("e6", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_form_edit_element(node: etree._Element) -> FormEditControl:
    attrs = {key: value for key, value in node.attrib.items()}
    return FormEditControl(
        tag=node.tag,
        name=local_name(node),
        multi_line=attrs.pop("multiLine", None),
        password_char=attrs.pop("passwordChar", None),
        max_length=_parse_int_attribute(attrs, "maxLength"),
        scroll_bars=attrs.pop("scrollBars", None),
        tab_key_behavior=attrs.pop("tabKeyBehavior", None),
        num_only=attrs.pop("numOnly", None),
        read_only=attrs.pop("readOnly", None),
        align_text=attrs.pop("alignText", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def parse_list_item_element(node: etree._Element) -> ListItem:
    return ListItem(
        tag=node.tag,
        name=local_name(node),
        display_text=node.get("displayText"),
        value=node.get("value"),
    )


def parse_composed_character_element(node: etree._Element) -> ComposedCharacter:
    attrs = {key: value for key, value in node.attrib.items()}
    slots = [
        ComposedCharacterSlot(pr_id_ref=parse_int(child.get("prIDRef")))
        for child in node
        if isinstance(child.tag, str) and local_name(child) == "charPr"
    ]
    return ComposedCharacter(
        tag=node.tag,
        circle_type=attrs.pop("circleType", None),
        char_sz=_parse_int_attribute(attrs, "charSz"),
        compose_type=attrs.pop("composeType", None),
        char_pr_cnt=_parse_int_attribute(attrs, "charPrCnt"),
        compose_text=attrs.pop("composeText", None),
        slots=slots,
    )


def parse_dutmal_element(node: etree._Element) -> Dutmal:
    attrs = {key: value for key, value in node.attrib.items()}
    main_text: Optional[str] = None
    sub_text: Optional[str] = None
    for child in node:
        if not isinstance(child.tag, str):
            continue
        name = local_name(child)
        if name == "mainText":
            main_text = child.text
        elif name == "subText":
            sub_text = child.text
    return Dutmal(
        tag=node.tag,
        pos_type=attrs.pop("posType", None),
        sz_ratio=_parse_int_attribute(attrs, "szRatio"),
        option=_parse_int_attribute(attrs, "option"),
        style_id_ref=_parse_int_attribute(attrs, "styleIDRef"),
        align=attrs.pop("align", None),
        main_text=main_text,
        sub_text=sub_text,
    )


def parse_form_combo_box_element(node: etree._Element) -> FormComboBoxControl:
    attrs = {key: value for key, value in node.attrib.items()}
    return FormComboBoxControl(
        tag=node.tag,
        name=local_name(node),
        list_box_rows=_parse_int_attribute(attrs, "listBoxRows"),
        list_box_width=_parse_int_attribute(attrs, "listBoxWidth"),
        edit_enable=attrs.pop("editEnable", None),
        selected_value=attrs.pop("selectedValue", None),
        attributes=attrs,
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


#: OWPML 잎 파라미터 태그 ↔ :class:`Parameter` kind. ``unsignedintegerParam``
#: 은 실코퍼스(hwpxlib error__20230809 문서)에서 관측됐지만 이 리포 스키마
#: 사본엔 없다 — 관측을 정본으로 삼아 등재한다.
_PARAM_LEAF_KINDS = {
    "booleanParam": "boolean",
    "integerParam": "integer",
    "unsignedintegerParam": "unsignedinteger",
    "floatParam": "float",
    "stringParam": "string",
}
_PARAM_KIND_TAGS = {kind: tag for tag, kind in _PARAM_LEAF_KINDS.items()}


def _parsed_parameter_value(kind: str, text: Optional[str]) -> Optional[Union[bool, int, float, str]]:
    if text is None:
        return None
    if kind == "boolean":
        return parse_bool(text)
    if kind in ("integer", "unsignedinteger"):
        return parse_int(text)
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            return None
    return text


def parse_parameter_element(node: etree._Element) -> Parameter:
    tag = local_name(node)
    name = node.get("name")
    if tag == "listParam":
        return Parameter(
            name=name, kind="list", items=[parse_parameter_element(child) for child in node]
        )
    kind = _PARAM_LEAF_KINDS.get(tag, tag)
    return Parameter(name=name, kind=kind, value=_parsed_parameter_value(kind, node.text))


def parse_parameter_list_element(node: etree._Element) -> ParameterList:
    """``hp:parameters``/``hp:parameterset`` 최상위(둘 다 재사용 가능 — 이
    함수는 태그 이름을 강제하지 않고 ``node.tag`` 그대로 왕복한다)."""

    return ParameterList(
        tag=node.tag,
        name=node.get("name"),
        params=[parse_parameter_element(child) for child in node],
    )


def parse_comment_element(node: etree._Element) -> CommentElement:
    """Build a :class:`CommentElement` from a comment / PI *node*.

    Such nodes expose a callable ``tag`` instead of a string; ``node.tag is
    etree.PI`` distinguishes processing instructions (which carry a ``target``)
    from plain comments.
    """

    if node.tag is etree.PI:
        return CommentElement(kind="pi", text=node.text, target=node.target)
    return CommentElement(kind="comment", text=node.text)


def parse_preserved_element(node: etree._Element) -> PreservedElement:
    if not isinstance(node.tag, str):
        # Comment / processing-instruction node: ``local_name`` would return ""
        # and ``GenericElement`` cannot round-trip a callable tag.
        return parse_comment_element(node)
    name = local_name(node)
    if name == "linesegarray":
        return parse_line_seg_array_element(node)
    if name == "lineseg":
        return parse_line_seg_element(node)
    if name in {"transMatrix", "scaMatrix", "rotMatrix"}:
        return parse_transform_matrix_element(node)
    if name == "edit":
        return parse_form_edit_element(node)
    if name == "comboBox":
        return parse_form_combo_box_element(node)
    if name == "listItem":
        return parse_list_item_element(node)
    if name == "compose":
        return parse_composed_character_element(node)
    if name == "dutmal":
        return parse_dutmal_element(node)
    if name in {"parameters", "parameterset"}:
        return parse_parameter_list_element(node)
    if name == "label":
        return parse_label_element(node)
    if name in INLINE_OBJECT_NAMES:
        # 실코퍼스 실측(cycle-6.3 트레인⑫): hp:container(등)가 최상위
        # run 자식일 땐 InlineObject로 뜨지만, 그 컨테이너 *안에* 중첩된
        # 개체(pic/line/rect 등, reader_writer__SimpleContainer.hwpx)는
        # 이 함수로 재귀해 GenericElement로 강등돼 있었다 — 중첩 깊이와
        # 무관하게 같은 타입으로 뜨도록 통일한다.
        return parse_inline_object_element(node)
    return GenericElement(
        name=name,
        tag=node.tag,
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
        text=node.text if node.text is not None else None,
    )


def _parse_text_markup(node: etree._Element) -> InlineMark:
    name = local_name(node)
    if name in _TRACK_CHANGE_MARK_NAMES:
        return parse_track_change_mark(node)
    return parse_preserved_element(node)


def parse_text_span(node: etree._Element) -> TextSpan:
    leading = node.text or ""
    marks: List[TextMarkup] = []

    for child in node:
        mark = _parse_text_markup(child)
        trailing = child.tail or ""
        marks.append(TextMarkup(mark, trailing))

    return TextSpan(
        tag=node.tag,
        leading_text=leading,
        marks=marks,
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_control_element(node: etree._Element) -> Control:
    attrs = {key: value for key, value in node.attrib.items()}
    control_type = attrs.pop("type", None)
    children = [parse_preserved_element(child) for child in node]
    return Control(tag=node.tag, control_type=control_type, attributes=attrs, children=children)


def parse_inline_object_element(node: etree._Element) -> InlineObject:
    return InlineObject(
        tag=node.tag,
        name=local_name(node),
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
    )


def parse_table_element(node: etree._Element) -> Table:
    return Table(
        tag=node.tag,
        attributes={key: value for key, value in node.attrib.items()},
        children=[parse_preserved_element(child) for child in node],
    )


_LABEL_INT_ATTRS = (
    "topmargin", "leftmargin", "boxwidth", "boxlength", "boxmarginhor",
    "boxmarginver", "labelcols", "labelrows", "pagewidth", "pageheight",
)


def parse_label_element(node: etree._Element) -> Label:
    attrs = {key: value for key, value in node.attrib.items()}
    values = {name: parse_int(attrs.pop(name, None)) for name in _LABEL_INT_ATTRS}
    landscape = attrs.pop("landscape", None)
    return Label(tag=node.tag, landscape=landscape, attributes=attrs, **values)


def parse_tab_element(node: etree._Element) -> Tab:
    return Tab(tag=node.tag, attributes={key: value for key, value in node.attrib.items()})


def parse_run_element(node: etree._Element) -> Run:
    attributes = {key: value for key, value in node.attrib.items()}
    char_pr_id_ref = parse_int(attributes.pop("charPrIDRef", None))

    run = Run(tag=node.tag, char_pr_id_ref=char_pr_id_ref, attributes=attributes)

    for child in node:
        name = local_name(child)
        if name == "secPr":
            element = parse_preserved_element(child)
            run.section_properties.append(element)
            run.content.append(element)
        elif name == "ctrl":
            control = parse_control_element(child)
            run.controls.append(control)
            run.content.append(control)
        elif name == "t":
            span = parse_text_span(child)
            run.text_spans.append(span)
            run.content.append(span)
        elif name == "tab":
            tab = parse_tab_element(child)
            run.tabs.append(tab)
            run.content.append(tab)
        elif name == "tbl":
            table = parse_table_element(child)
            run.tables.append(table)
            run.content.append(table)
        elif name in INLINE_OBJECT_NAMES:
            obj = parse_inline_object_element(child)
            run.inline_objects.append(obj)
            run.content.append(obj)
        elif name == "compose":
            composed = parse_composed_character_element(child)
            run.other_children.append(composed)
            run.content.append(composed)
        elif name == "dutmal":
            dutmal = parse_dutmal_element(child)
            run.other_children.append(dutmal)
            run.content.append(dutmal)
        else:
            element = parse_preserved_element(child)
            run.other_children.append(element)
            run.content.append(element)

    return run


def parse_paragraph_element(node: etree._Element) -> Paragraph:
    attributes = {key: value for key, value in node.attrib.items()}

    paragraph = Paragraph(
        tag=node.tag,
        id=parse_int(attributes.pop("id", None)),
        para_pr_id_ref=parse_int(attributes.pop("paraPrIDRef", None)),
        style_id_ref=parse_int(attributes.pop("styleIDRef", None)),
        page_break=parse_bool(attributes.pop("pageBreak", None)),
        column_break=parse_bool(attributes.pop("columnBreak", None)),
        merged=parse_bool(attributes.pop("merged", None)),
        attributes=attributes,
    )

    for child in node:
        if local_name(child) == "run":
            run = parse_run_element(child)
            paragraph.runs.append(run)
            paragraph.content.append(run)
        else:
            element = parse_preserved_element(child)
            paragraph.other_children.append(element)
            paragraph.content.append(element)

    return paragraph


def parse_section_element(node: etree._Element) -> Section:
    section = Section(tag=node.tag, attributes={key: value for key, value in node.attrib.items()})

    for child in node:
        if local_name(child) == "p":
            section.paragraphs.append(parse_paragraph_element(child))
        else:
            section.other_children.append(parse_preserved_element(child))

    return section


def _generic_element_to_xml(element: GenericElement) -> etree._Element:
    node = etree.Element(_qualified_tag(element.tag, element.name))
    for key, value in element.attributes.items():
        node.set(key, value)
    if element.text:
        node.text = element.text
    for child in element.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _set_int_attr(attrs: Dict[str, str], name: str, value: Optional[int]) -> None:
    if value is not None:
        attrs[name] = str(value)


def _line_seg_to_xml(line_seg: LineSeg) -> etree._Element:
    attrs = dict(line_seg.attributes)
    _set_int_attr(attrs, "textpos", line_seg.text_pos)
    _set_int_attr(attrs, "vertpos", line_seg.vert_pos)
    _set_int_attr(attrs, "vertsize", line_seg.vert_size)
    _set_int_attr(attrs, "textheight", line_seg.text_height)
    _set_int_attr(attrs, "baseline", line_seg.baseline)
    _set_int_attr(attrs, "spacing", line_seg.spacing)
    _set_int_attr(attrs, "horzpos", line_seg.horz_pos)
    _set_int_attr(attrs, "horzsize", line_seg.horz_size)
    _set_int_attr(attrs, "flags", line_seg.flags)
    node = etree.Element(_qualified_tag(line_seg.tag, line_seg.name), attrs)
    if line_seg.text:
        node.text = line_seg.text
    for child in line_seg.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _line_seg_array_to_xml(line_array: LineSegArray) -> etree._Element:
    node = etree.Element(_qualified_tag(line_array.tag, line_array.name), dict(line_array.attributes))
    if line_array.text:
        node.text = line_array.text
    for child in line_array.content:
        node.append(_preserved_element_to_xml(child))
    return node


def _set_str_attr(attrs: Dict[str, str], name: str, value: Optional[str]) -> None:
    if value is not None:
        attrs[name] = value


def _transform_matrix_to_xml(matrix: TransformMatrix) -> etree._Element:
    attrs = dict(matrix.attributes)
    _set_str_attr(attrs, "e1", matrix.e1)
    _set_str_attr(attrs, "e2", matrix.e2)
    _set_str_attr(attrs, "e3", matrix.e3)
    _set_str_attr(attrs, "e4", matrix.e4)
    _set_str_attr(attrs, "e5", matrix.e5)
    _set_str_attr(attrs, "e6", matrix.e6)
    node = etree.Element(_qualified_tag(matrix.tag, matrix.name), attrs)
    if matrix.text:
        node.text = matrix.text
    for child in matrix.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _form_edit_to_xml(edit: FormEditControl) -> etree._Element:
    attrs = dict(edit.attributes)
    _set_str_attr(attrs, "multiLine", edit.multi_line)
    _set_str_attr(attrs, "passwordChar", edit.password_char)
    _set_int_attr(attrs, "maxLength", edit.max_length)
    _set_str_attr(attrs, "scrollBars", edit.scroll_bars)
    _set_str_attr(attrs, "tabKeyBehavior", edit.tab_key_behavior)
    _set_str_attr(attrs, "numOnly", edit.num_only)
    _set_str_attr(attrs, "readOnly", edit.read_only)
    _set_str_attr(attrs, "alignText", edit.align_text)
    node = etree.Element(_qualified_tag(edit.tag, edit.name), attrs)
    if edit.text:
        node.text = edit.text
    for child in edit.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _form_combo_box_to_xml(combo: FormComboBoxControl) -> etree._Element:
    attrs = dict(combo.attributes)
    _set_int_attr(attrs, "listBoxRows", combo.list_box_rows)
    _set_int_attr(attrs, "listBoxWidth", combo.list_box_width)
    _set_str_attr(attrs, "editEnable", combo.edit_enable)
    _set_str_attr(attrs, "selectedValue", combo.selected_value)
    node = etree.Element(_qualified_tag(combo.tag, combo.name), attrs)
    if combo.text:
        node.text = combo.text
    for child in combo.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _list_item_to_xml(item: ListItem) -> etree._Element:
    attrs: Dict[str, str] = {}
    _set_str_attr(attrs, "displayText", item.display_text)
    _set_str_attr(attrs, "value", item.value)
    return etree.Element(_qualified_tag(item.tag, item.name), attrs)


def _composed_character_slot_to_xml(slot: ComposedCharacterSlot) -> etree._Element:
    attrs: Dict[str, str] = {}
    _set_int_attr(attrs, "prIDRef", slot.pr_id_ref)
    return etree.Element(f"{HP}charPr", attrs)


def _composed_character_to_xml(composed: ComposedCharacter) -> etree._Element:
    attrs: Dict[str, str] = {}
    _set_str_attr(attrs, "circleType", composed.circle_type)
    _set_int_attr(attrs, "charSz", composed.char_sz)
    _set_str_attr(attrs, "composeType", composed.compose_type)
    _set_int_attr(attrs, "charPrCnt", composed.char_pr_cnt)
    _set_str_attr(attrs, "composeText", composed.compose_text)
    node = etree.Element(_qualified_tag(composed.tag, "compose"), attrs)
    for slot in composed.slots:
        node.append(_composed_character_slot_to_xml(slot))
    return node


def _dutmal_to_xml(dutmal: Dutmal) -> etree._Element:
    attrs: Dict[str, str] = {}
    _set_str_attr(attrs, "posType", dutmal.pos_type)
    _set_int_attr(attrs, "szRatio", dutmal.sz_ratio)
    _set_int_attr(attrs, "option", dutmal.option)
    _set_int_attr(attrs, "styleIDRef", dutmal.style_id_ref)
    _set_str_attr(attrs, "align", dutmal.align)
    node = etree.Element(_qualified_tag(dutmal.tag, "dutmal"), attrs)
    main = etree.SubElement(node, f"{_DEFAULT_HP}mainText")
    main.text = dutmal.main_text
    sub = etree.SubElement(node, f"{_DEFAULT_HP}subText")
    sub.text = dutmal.sub_text
    return node


def _parameter_value_text(kind: str, value: Union[bool, int, float, str]) -> str:
    if kind == "boolean":
        return "1" if value else "0"
    return str(value)


def parameter_to_xml(param: Parameter) -> etree._Element:
    if param.kind == "list":
        attrs: Dict[str, str] = {"cnt": str(len(param.items))}
        _set_str_attr(attrs, "name", param.name)
        node = etree.Element(f"{HP}listParam", attrs)
        for child in param.items:
            node.append(parameter_to_xml(child))
        return node
    leaf_attrs: Dict[str, str] = {}
    _set_str_attr(leaf_attrs, "name", param.name)
    # 원장 write 분류기가 태그 리터럴을 etree.Element( 인접으로만 인식한다
    # (2026-08-04 감사 §3-C2) — kind→태그 dict 조회로 조립하지 않고 알려진
    # 5종은 리터럴로 나열한다. 스키마 밖 kind만 방어적으로 조립 조회한다.
    if param.kind == "boolean":
        node = etree.Element(f"{HP}booleanParam", leaf_attrs)
    elif param.kind == "integer":
        node = etree.Element(f"{HP}integerParam", leaf_attrs)
    elif param.kind == "unsignedinteger":
        node = etree.Element(f"{HP}unsignedintegerParam", leaf_attrs)
    elif param.kind == "float":
        node = etree.Element(f"{HP}floatParam", leaf_attrs)
    elif param.kind == "string":
        node = etree.Element(f"{HP}stringParam", leaf_attrs)
    else:
        node = etree.Element(f"{HP}{param.kind}", leaf_attrs)
    if param.value is not None:
        node.text = _parameter_value_text(param.kind, param.value)
    return node


def parameter_list_to_xml(model: ParameterList) -> etree._Element:
    attrs: Dict[str, str] = {"cnt": str(len(model.params))}
    _set_str_attr(attrs, "name", model.name)
    node = etree.Element(model.tag, attrs)
    for param in model.params:
        node.append(parameter_to_xml(param))
    return node


def _comment_element_to_xml(element: CommentElement) -> etree._Element:
    if element.kind == "pi":
        return etree.ProcessingInstruction(element.target or "", element.text or "")
    return etree.Comment(element.text)


def _preserved_element_to_xml(element: PreservedElement) -> etree._Element:
    if isinstance(element, CommentElement):
        return _comment_element_to_xml(element)
    if isinstance(element, LineSegArray):
        return _line_seg_array_to_xml(element)
    if isinstance(element, LineSeg):
        return _line_seg_to_xml(element)
    if isinstance(element, TransformMatrix):
        return _transform_matrix_to_xml(element)
    if isinstance(element, FormEditControl):
        return _form_edit_to_xml(element)
    if isinstance(element, FormComboBoxControl):
        return _form_combo_box_to_xml(element)
    if isinstance(element, ListItem):
        return _list_item_to_xml(element)
    if isinstance(element, ComposedCharacter):
        return _composed_character_to_xml(element)
    if isinstance(element, Dutmal):
        return _dutmal_to_xml(element)
    if isinstance(element, ParameterList):
        return parameter_list_to_xml(element)
    if isinstance(element, Label):
        return _label_to_xml(element)
    if isinstance(element, InlineObject):
        return _inline_object_to_xml(element)
    return _generic_element_to_xml(element)


def _track_change_mark_to_xml(mark: TrackChangeMark) -> etree._Element:
    attrs: Dict[str, str] = {}
    if mark.id is not None:
        attrs["Id"] = str(mark.id)
    if mark.tc_id is not None:
        attrs["TcId"] = str(mark.tc_id)
    if mark.para_end is not None:
        attrs["paraend"] = _bool_to_flag(mark.para_end)
    attrs.update(mark.attributes)
    return etree.Element(_qualified_tag(mark.tag, mark.name), attrs)


def _inline_mark_to_xml(mark: InlineMark) -> etree._Element:
    if isinstance(mark, TrackChangeMark):
        return _track_change_mark_to_xml(mark)
    return _preserved_element_to_xml(mark)


def _text_span_to_xml(span: TextSpan) -> etree._Element:
    node = etree.Element(_qualified_tag(span.tag, "t"), dict(span.attributes))
    if span.leading_text:
        node.text = span.leading_text
    for mark in span.marks:
        child = _inline_mark_to_xml(mark.element)
        node.append(child)
        if mark.trailing_text:
            child.tail = mark.trailing_text
    return node


def _tab_to_xml(tab: Tab) -> etree._Element:
    return etree.Element(_qualified_tag(tab.tag, "tab"), dict(tab.attributes))


def _control_to_xml(control: Control) -> etree._Element:
    attrs = dict(control.attributes)
    if control.control_type is not None:
        attrs["type"] = control.control_type
    node = etree.Element(_qualified_tag(control.tag, "ctrl"), attrs)
    for child in control.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _table_to_xml(table: Table) -> etree._Element:
    node = etree.Element(_qualified_tag(table.tag, "tbl"), dict(table.attributes))
    for child in table.children:
        node.append(_preserved_element_to_xml(child))
    return node


def _label_to_xml(label: Label) -> etree._Element:
    # Attribute order matches ParaList XML schema.xml's declared sequence,
    # which every real occurrence (436/436, private reverse-engineering
    # sample) also follows -- see DEV-023.
    attrs: Dict[str, str] = {}
    _set_int_attr(attrs, "topmargin", label.topmargin)
    _set_int_attr(attrs, "leftmargin", label.leftmargin)
    _set_int_attr(attrs, "boxwidth", label.boxwidth)
    _set_int_attr(attrs, "boxlength", label.boxlength)
    _set_int_attr(attrs, "boxmarginhor", label.boxmarginhor)
    _set_int_attr(attrs, "boxmarginver", label.boxmarginver)
    _set_int_attr(attrs, "labelcols", label.labelcols)
    _set_int_attr(attrs, "labelrows", label.labelrows)
    if label.landscape is not None:
        attrs["landscape"] = label.landscape
    _set_int_attr(attrs, "pagewidth", label.pagewidth)
    _set_int_attr(attrs, "pageheight", label.pageheight)
    attrs.update(label.attributes)
    return etree.Element(_qualified_tag(label.tag, "label"), attrs)


def _inline_object_to_xml(obj: InlineObject) -> etree._Element:
    node = etree.Element(_qualified_tag(obj.tag, obj.name), dict(obj.attributes))
    for child in obj.children:
        node.append(_preserved_element_to_xml(child))
    return node


def serialize_run(run: Run) -> etree._Element:
    attrs = dict(run.attributes)
    if run.char_pr_id_ref is not None:
        attrs["charPrIDRef"] = str(run.char_pr_id_ref)
    node = etree.Element(_qualified_tag(run.tag, "run"), attrs)
    for child in run.content:
        if isinstance(child, TextSpan):
            node.append(_text_span_to_xml(child))
        elif isinstance(child, Control):
            node.append(_control_to_xml(child))
        elif isinstance(child, Tab):
            node.append(_tab_to_xml(child))
        elif isinstance(child, Table):
            node.append(_table_to_xml(child))
        elif isinstance(child, InlineObject):
            node.append(_inline_object_to_xml(child))
        else:
            node.append(_preserved_element_to_xml(child))
    return node


def serialize_paragraph(paragraph: Paragraph) -> etree._Element:
    attrs = dict(paragraph.attributes)
    if paragraph.id is not None:
        attrs["id"] = str(paragraph.id)
    if paragraph.para_pr_id_ref is not None:
        attrs["paraPrIDRef"] = str(paragraph.para_pr_id_ref)
    if paragraph.style_id_ref is not None:
        attrs["styleIDRef"] = str(paragraph.style_id_ref)
    if paragraph.page_break is not None:
        attrs["pageBreak"] = _bool_to_str(paragraph.page_break)
    if paragraph.column_break is not None:
        attrs["columnBreak"] = _bool_to_str(paragraph.column_break)
    if paragraph.merged is not None:
        attrs["merged"] = _bool_to_str(paragraph.merged)

    node = etree.Element(_qualified_tag(paragraph.tag, "p"), attrs)
    for child in paragraph.content:
        if isinstance(child, Run):
            node.append(serialize_run(child))
        else:
            node.append(_preserved_element_to_xml(child))
    return node


__all__ = [
    "CommentElement",
    "ComposedCharacter",
    "ComposedCharacterSlot",
    "Control",
    "Dutmal",
    "FormComboBoxControl",
    "FormEditControl",
    "InlineObject",
    "INLINE_OBJECT_NAMES",
    "LineSeg",
    "Label",
    "LineSegArray",
    "ListItem",
    "Paragraph",
    "Parameter",
    "ParameterList",
    "PreservedElement",
    "Run",
    "Section",
    "Table",
    "TextMarkup",
    "TextSpan",
    "TrackChangeMark",
    "TransformMatrix",
    "append_tracked_insert_to_run",
    "create_track_change_mark",
    "insert_tracked_text_after_delete",
    "parameter_list_to_xml",
    "parameter_to_xml",
    "parse_comment_element",
    "parse_composed_character_element",
    "parse_control_element",
    "parse_form_combo_box_element",
    "parse_form_edit_element",
    "parse_inline_object_element",
    "parse_label_element",
    "parse_line_seg_array_element",
    "parse_line_seg_element",
    "parse_list_item_element",
    "parse_paragraph_element",
    "parse_parameter_element",
    "parse_parameter_list_element",
    "parse_preserved_element",
    "parse_run_element",
    "parse_section_element",
    "parse_table_element",
    "parse_text_span",
    "parse_track_change_mark",
    "parse_transform_matrix_element",
    "serialize_paragraph",
    "serialize_run",
    "wrap_tracked_delete_in_span",
]

logger = logging.getLogger(__name__)
