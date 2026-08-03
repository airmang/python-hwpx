# SPDX-License-Identifier: Apache-2.0
"""`doc.refs` — 책갈피·하이퍼링크.

능력 레지스트리의 `toc-crossref` 영역이다. 지금은 두 멤버뿐이지만 이 자리는
Q3/Q4 의 네이티브 목차·상호참조(`hwpx.tools.toc_author`)가 들어올 곳이다 —
레지스트리가 이미 그 셋을 한 영역으로 묶어 두었기 때문에 경계는 정해져 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._resolve import resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...model import InlineObject, Paragraph, Section

__all__ = ["RefsNamespace"]


class RefsNamespace(_Namespace):
    """책갈피·하이퍼링크."""

    __slots__ = ()
    _path = "doc.refs"

    def add_bookmark(
        self,
        name: str,
        *,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
    ) -> "InlineObject":
        """책갈피를 넣는다. 상호참조·목차의 앵커가 된다."""

        from .. import layout as _layout

        return _layout.add_bookmark(
            self._doc,
            name=name,
            paragraph=paragraph,
            section=resolve_section(
                self._doc, section, section_index, caller="doc.refs.add_bookmark"
            ),
        )

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        paragraph: "Paragraph | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "InlineObject":
        """표시 문자열을 가진 하이퍼링크를 넣는다."""

        from .. import layout as _layout

        return _layout.add_hyperlink(
            self._doc,
            url=url,
            display_text=display_text,
            paragraph=paragraph,
            section=resolve_section(
                self._doc, section, section_index, caller="doc.refs.add_hyperlink"
            ),
            char_pr_id_ref=char_pr_id_ref,
        )
