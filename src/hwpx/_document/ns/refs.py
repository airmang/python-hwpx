# SPDX-License-Identifier: Apache-2.0
"""`doc.refs` — 책갈피·하이퍼링크.

능력 레지스트리의 `toc-crossref` 영역이다. 지금은 두 멤버뿐이지만 이 자리는
Q3/Q4 의 네이티브 목차·상호참조(`hwpx.tools.toc_author`)가 들어올 곳이다 —
레지스트리가 이미 그 셋을 한 영역으로 묶어 두었기 때문에 경계는 정해져 있다.
"""

from __future__ import annotations

from ...model import Paragraph, Section
from ...objects import Bookmark, CrossReference, Hyperlink
from .._resolve import optional_paragraph, resolve_section
from ._base import _Namespace

__all__ = ["RefsNamespace"]


class RefsNamespace(_Namespace):
    """책갈피·하이퍼링크."""

    __slots__ = ()
    _path = "doc.refs"

    @property
    def bookmarks(self) -> "tuple[Bookmark, ...]":
        """문서의 모든 책갈피를 문서 순서로. 표 칸과 개체 안의 것도 본다.

        한/글이 책갈피를 저장하는 두 형태를 함께 낸다: ``hp:bookmark``(``kind="point"``)와
        ``fieldBegin type="BOOKMARK"``…``fieldEnd`` 짝(``kind="field"``). 필드 형태의 ``text``는
        시작과 끝 사이의 글이다(한/글은 흔히 사이를 비워 둔다).
        """

        from .. import fields as _fields

        return _fields.list_bookmarks(self._doc)

    @property
    def hyperlinks(self) -> "tuple[Hyperlink, ...]":
        """문서의 모든 하이퍼링크를 문서 순서로. 표 칸·글상자·각주·머리말 안의 것도 본다.

        ``link.url``·``link.text`` 는 읽고 쓸 수 있고, ``link.remove()`` 는 링크만
        걷어 내고 글은 남긴다.
        """

        from .. import fields as _fields

        return _fields.list_hyperlinks(self._doc)

    @property
    def cross_references(self) -> "tuple[CrossReference, ...]":
        """문서의 모든 상호 참조(``fieldBegin type="CROSSREF"``)를 문서 순서로.

        무엇을 가리키는지(``ref_type``·``target``), 무엇을 보이는지(``content_type``),
        지금 보이는 글(``text``)을 적힌 그대로 읽는다.
        """

        from .. import fields as _fields

        return _fields.list_cross_references(self._doc)

    def add_bookmark(
        self,
        name: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
    ) -> "Bookmark":
        """책갈피를 넣는다. 상호참조·목차의 앵커가 된다. :attr:`bookmarks` 가 읽는 :class:`Bookmark` 를 돌려준다."""

        from .. import layout as _layout

        return _layout.add_bookmark(
            self._doc,
            name=name,
            paragraph=optional_paragraph(
                self._doc, paragraph, section=section,
                caller="doc.refs.add_bookmark",
            ),
            section=resolve_section(
                self._doc, section, caller="doc.refs.add_bookmark"
            ),
        )

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "Hyperlink":
        """표시 문자열을 가진 하이퍼링크를 넣는다. :attr:`hyperlinks` 가 읽는 :class:`Hyperlink` 를 돌려준다."""

        from .. import layout as _layout

        return _layout.add_hyperlink(
            self._doc,
            url=url,
            display_text=display_text,
            paragraph=optional_paragraph(
                self._doc, paragraph, section=section,
                caller="doc.refs.add_hyperlink",
            ),
            section=resolve_section(
                self._doc, section, caller="doc.refs.add_hyperlink"
            ),
            char_pr_id_ref=char_pr_id_ref,
        )
