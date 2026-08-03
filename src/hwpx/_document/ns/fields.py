# SPDX-License-Identifier: Apache-2.0
"""`doc.fields` — 누름틀·체크박스 양식개체.

능력 레지스트리의 `form-field-create` 와 `check-box` 두 영역이 여기로 온다.
5.x 는 여섯 이름(`add_form_field`·`list_form_fields`·`fill_form_field`·
`add_check_box`·`list_check_boxes`·`set_check_box`)을 루트에 흩어 두었다.

## 반환 타입은 WP-C 조인 대기

이 네임스페이스의 반환은 아직 5.x 의 dict/list[dict] 그대로다. 설계서 §2가
정한 `FormField`·`CheckBox`·`FieldFillResult` 도메인 객체는 WP-C 가
`hwpx.objects` 에 만들고 있고, 착지하면 여기 시그니처만 바꾸면 된다 —
위임 대상(`_document/fields.py`)은 그대로다.

특히 `set_check_box` 는 6.0 계획상 **메서드가 아니라 속성**이 된다
(`doc.fields.check_box(name=...).checked = False`). 그 형태는 라이브 객체가
있어야 성립하므로 지금은 5.x 와 같은 메서드로 둔다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._resolve import resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...form_fit.policy import FitPolicy
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
    ) -> dict[str, Any]:
        """누름틀(form field)을 만들고 그 서술을 돌려준다.

        Note:
            반환 타입은 WP-C 착지 후 ``FormField`` 객체가 된다.
        """

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
    def all(self) -> list[dict[str, Any]]:
        """문서의 모든 누름틀을 문서 순서로.

        Note:
            원소 타입은 WP-C 착지 후 ``FormField`` 가 된다.
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
    ) -> dict[str, Any]:
        """누름틀 하나를 채우고 채움 결과를 돌려준다.

        Note:
            반환 타입은 WP-C 착지 후 ``FieldFillResult`` 가 된다.
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
    ) -> dict[str, Any]:
        """체크박스 양식개체를 만든다.

        Note:
            반환 타입은 WP-C 착지 후 ``CheckBox`` 객체가 된다.
        """

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
    def check_boxes(self) -> list[dict[str, Any]]:
        """문서의 모든 체크박스를 문서 순서로.

        Note:
            원소 타입은 WP-C 착지 후 ``CheckBox`` 가 된다.
        """

        from .. import fields as _fields

        return _fields.list_check_boxes(self._doc)

    def set_check_box(
        self,
        checked: bool,
        *,
        index: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """체크박스 상태를 바꾼다.

        Note:
            WP-C 착지 후에는 ``doc.fields.check_box(name=...).checked = False``
            형태가 정본이 된다. 라이브 객체가 있어야 성립하는 형태라 지금은
            5.x 와 같은 메서드로 둔다.
        """

        from .. import fields as _fields

        return _fields.set_check_box(self._doc, checked=checked, index=index, name=name)
