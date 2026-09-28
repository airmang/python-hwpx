# SPDX-License-Identifier: Apache-2.0
"""`doc.fields` — 누름틀·셀 필드·글상자 필드·체크박스 양식개체.

능력 레지스트리의 `form-field-create` 와 `check-box` 두 영역이 여기로 온다.
5.x 는 여섯 이름(`add_form_field`·`list_form_fields`·`fill_form_field`·
`add_check_box`·`list_check_boxes`·`set_check_box`)을 루트에 흩어 두었다.

## 반환은 도메인 객체다

5.x 는 여기서 dict 를 돌려줬다. `add_form_field` 의 dict 는 **20키**였고 그중
`field_id`/`id`/`fieldid` 셋이 같은 값의 별칭, `prompt`/`instruction` 과
`field_type`/`control_type` 이 각각 중복, 위치가 5키로 흩어져 있었다.

6.0 은 `FormField`·`CheckBox` 라이브 뷰와 `FieldFillResult` 를 돌려준다.
id 별칭은 `field_id` 하나로, 위치 5키는 `location` 하나로 접혔다.

`CheckBox.checked` 가 쓰기 가능한 속성이므로 `set_check_box` 는 사실상
`doc.fields.check_box(...).checked = False` 로 대체된다. 5.x 이름은 shim 으로
살아 있고, 이 네임스페이스에도 같은 이름을 남겨 이주 중 양쪽이 겹치게 했다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._resolve import resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...form_fit.policy import FitPolicy
    from ...objects import CellField, CheckBox, FieldFillResult, FormField, TextBoxField
    from ...oxml import HwpxOxmlParagraph, HwpxOxmlSection

__all__ = ["FieldsNamespace"]


class FieldsNamespace(_Namespace):
    """누름틀·체크박스 양식개체."""

    __slots__ = ()
    _path = "doc.fields"

    # -- 누름틀 ------------------------------------------------------------

    def add(
        self,
        name: str,
        *,
        prompt: str = "",
        memo: str = "",
        editable: bool = True,
        paragraph: "HwpxOxmlParagraph | None" = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "FormField":
        """누름틀(form field)을 만들고 그 라이브 뷰를 돌려준다."""

        from .. import fields as _fields

        return _fields.add_form_field(
            self._doc,
            name=name,
            prompt=prompt,
            memo=memo,
            editable=editable,
            paragraph=paragraph,
            section=resolve_section(
                self._doc, section, section_index, caller="doc.fields.add"
            ),
        )

    @property
    def all(self) -> "tuple[FormField, ...]":
        """문서의 누름틀을 문서 순서로.

        이름이 빈 누름틀(``name=""``)은 한/글의 필드 목록처럼 빠진다. 그런 누름틀도
        ``fill(field_index=)``·``fill(field_id=)``로는 채울 수 있다.
        """

        from .. import fields as _fields

        return _fields.list_form_fields(self._doc)

    def fill(
        self,
        value: str,
        *,
        field_index: int | None = None,
        field_id: str | None = None,
        name: str | None = None,
        fit_policy: "FitPolicy | None" = None,
        box_width: int | None = None,
        font_pt: float | None = None,
    ) -> "FieldFillResult":
        """누름틀 하나를 채우고 채움 결과를 돌려준다.

        내용이 여러 문단에 걸친 누름틀은 한/글처럼 채운다. 걸친 문단(그 안의 표 포함)을 지우고,
        값과 누름틀 끝을 시작 문단에 둔다. 끝 문단에서 누름틀 끝 뒤에 있던 글은 시작 문단으로 합친다.
        끝(``hp:fieldEnd``)이 없는 누름틀은 바꿀 내용이 없으므로
        ``HwpxValueError(code="field-end-missing")``를 낸다.

        실패는 결과의 불리언 필드가 아니라 typed error 로 나간다 — 5.x 의
        ``ok`` 키는 없다(설계서 §2.4, 헌법 VI fail-closed).
        """

        from .. import fields as _fields

        return _fields.fill_form_field(
            self._doc,
            value=value,
            field_index=field_index,
            field_id=field_id,
            name=name,
            fit_policy=fit_policy,
            box_width=box_width,
            font_pt=font_pt,
        )

    # -- 셀 필드 -----------------------------------------------------------

    @property
    def cells(self) -> "tuple[CellField, ...]":
        """이름 붙은 표 칸(한/글 "셀 필드")을 문서 순서로. 본문 표와 그 칸 안의 표를 본다.

        칸에 이름을 붙이려면 ``table.cell(r, c).field_name = "이름"``을 쓴다.
        """

        from .. import fields as _fields

        return _fields.list_cell_fields(self._doc)

    def fill_cell(self, value: str, *, name: str, index: int | None = None) -> "tuple[CellField, ...]":
        """이름이 *name* 인 셀 필드의 글을 *value* 로 바꾸고, 바꾼 셀 필드들을 돌려준다.

        한/글 ``PutFieldText``처럼 같은 이름의 칸이 여럿이면 모두 채운다. *index*(0부터,
        문서 순서)를 주면 그 하나만 채운다(한/글의 ``이름{{n}}``). 누름틀은 건드리지 않는다
        (누름틀은 :meth:`fill`). 없으면 ``HwpxValueError(code="field-cell-not-found")``.
        """

        from .. import fields as _fields

        return _fields.fill_cell_fields(self._doc, value, name=name, index=index)

    # -- 글상자 필드 -------------------------------------------------------

    @property
    def text_boxes(self) -> "tuple[TextBoxField, ...]":
        """이름 붙은 글상자를 문서 순서로. 한/글은 이름(``hp:drawText@name``)이 있는 글상자를
        필드로 보고 필드 목록에 넣고 이름으로 채운다. 이름 없는 글상자는 뺀다.

        글상자에 이름을 붙이려면 ``shape.set_draw_text(글, name="이름")``을 쓴다.
        """

        from .. import fields as _fields

        return _fields.list_text_box_fields(self._doc)

    def fill_text_box(self, value: str, *, name: str, index: int | None = None) -> "tuple[TextBoxField, ...]":
        """이름이 *name* 인 글상자의 글을 *value* 로 바꾸고, 바꾼 글상자들을 돌려준다.

        한/글 ``PutFieldText``처럼 글상자의 글을 값 한 문단으로 바꾼다(첫 문단과 첫 run의
        모양은 그대로). 같은 이름의 글상자가 여럿이면 모두 채우고, *index*(0부터, 문서 순서)를
        주면 그 하나만 채운다. 없으면 ``HwpxValueError(code="field-text-box-not-found")``.
        """

        from .. import fields as _fields

        return _fields.fill_text_box_fields(self._doc, value, name=name, index=index)

    # -- 체크박스 ----------------------------------------------------------

    def add_check_box(
        self,
        caption: str,
        *,
        checked: bool = False,
        name: str | None = None,
        paragraph: "HwpxOxmlParagraph | None" = None,
        section: "int | HwpxOxmlSection | None" = None,
        section_index: int | None = None,
    ) -> "CheckBox":
        """체크박스 양식개체를 만들고 그 라이브 뷰를 돌려준다."""

        from .. import fields as _fields

        return _fields.add_check_box(
            self._doc,
            caption=caption,
            checked=checked,
            name=name,
            paragraph=paragraph,
            section=resolve_section(
                self._doc, section, section_index, caller="doc.fields.add_check_box"
            ),
        )

    @property
    def check_boxes(self) -> "tuple[CheckBox, ...]":
        """문서의 모든 체크박스를 문서 순서로."""

        from .. import fields as _fields

        return _fields.list_check_boxes(self._doc)

    def set_check_box(
        self,
        checked: bool,
        *,
        index: int | None = None,
        name: str | None = None,
    ) -> "CheckBox":
        """체크박스 상태를 바꾸고 그 라이브 뷰를 돌려준다.

        ``doc.fields.check_boxes[i].checked = False`` 와 같은 일을 한다 —
        선택자로 찾아야 할 때 쓴다.
        """

        from .. import fields as _fields

        return _fields.set_check_box(self._doc, checked=checked, index=index, name=name)
