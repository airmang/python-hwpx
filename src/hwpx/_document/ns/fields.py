# SPDX-License-Identifier: Apache-2.0
"""`doc.fields` — 누름틀·체크박스 양식개체.

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
    from ...objects import CheckBox, FieldFillResult, FormField
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
        """문서의 모든 누름틀을 문서 순서로."""

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
