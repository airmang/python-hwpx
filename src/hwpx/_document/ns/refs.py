# SPDX-License-Identifier: Apache-2.0
"""`doc.refs` — 책갈피·하이퍼링크.

능력 레지스트리의 `toc-crossref` 영역이다. 지금은 두 멤버뿐이지만 이 자리는
Q3/Q4 의 네이티브 목차·상호참조(`hwpx.tools.toc_author`)가 들어올 곳이다 —
레지스트리가 이미 그 셋을 한 영역으로 묶어 두었기 때문에 경계는 정해져 있다.
"""

from __future__ import annotations

from ...model import Paragraph, Section, Table
from ...objects import Bookmark, CrossReference, Hyperlink, TableOfContents
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
        지금 보이는 글(``text``)을 적힌 그대로 읽는다. ``content_type``·``hyperlink`` 는 쓸 수 있고
        ``set_target()`` 은 가리키는 대상을 바꾸며, ``remove()`` 는 상호 참조만 걷고 글을 남긴다.
        """

        from .. import fields as _fields

        return _fields.list_cross_references(self._doc)

    @property
    def tables_of_contents(self) -> "tuple[TableOfContents, ...]":
        """문서의 모든 차례(``fieldBegin type="TABLEOFCONTENTS"``)를 문서 순서로.

        ``toc.title``·``toc.entries``(항목 글·수준·쪽 번호 글·링크 대상)·``levels`` 를 적힌 그대로
        읽는다. ``toc.rebuild()`` 는 개요가 바뀐 뒤 제목 항목을 다시 만든다 — 쪽 번호는 비워 두고
        ``refresh_on_open`` 을 켜서 한/글이 다음에 열 때 채우게 한다(한/글은 dirty 차례를 열면서
        항목·스타일·쪽 번호를 다시 만든다). ``toc.remove()`` 는 차례를 통째로 걷어 낸다.
        """

        from ...tools import toc_author

        return toc_author.list_tables_of_contents(self._doc)

    def add_table_of_contents(
        self,
        *,
        index: int = 0,
        section: "int | Section | None" = None,
        title: str = "<제목 차례>",
        levels: int = 2,
        leader: str = "DASH",
        hyperlink: bool = True,
    ) -> "TableOfContents":
        """개요 1~*levels* 수준 문단의 차례를 *section* 의 *index* 번째 문단 자리에 한/글이 쓰는
        모양으로 넣고 돌려준다(*section* 을 주지 않으면 첫 구역).

        항목은 개요 번호와 글, 수준의 '차례 N' 스타일로 쓰고 제목으로 링크한다(*hyperlink*). 쪽 번호는
        비워 두고 ``refresh_on_open`` 을 켠다: 한/글이 문서를 열 때 차례를 다시 만들며 쪽 번호를
        채운다. 개요 문단이 없으면 ``toc-no-headings``. *leader* 는 쪽 번호 앞 채움(``"DASH"`` 가
        한/글 차례의 점선, ``"NONE"`` 은 없음).
        """

        from ...tools import toc_author

        target = resolve_section(self._doc, 0 if section is None else section,
                                 caller="doc.refs.add_table_of_contents")
        return toc_author.add_table_of_contents(
            self._doc, index=index, section=self._doc.oxml.sections.index(target), title=title,
            levels=levels, leader=leader, hyperlink=hyperlink,
        )

    def add_cross_reference(
        self,
        target: "Paragraph | Table | Bookmark | str",
        *,
        content_type: str = "OBJECT_TYPE_PAGE",
        hyperlink: bool = False,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
    ) -> "CrossReference":
        """상호 참조를 *paragraph* 끝에(없으면 *section* 끝 새 문단에) 한/글이 쓰는 모양으로 넣는다.

        *target* 은 개요 문단(``TARGET_OUTLINE``)·책갈피(:class:`~hwpx.objects.Bookmark` 나 그 이름,
        ``TARGET_BOOKMARK``)·표(``TARGET_TABLE``)다. 한/글 파일에서 본 대상만 쓴다 — 그림·수식·각주를
        가리키는 상호 참조는 본 적이 없어 ``ref-cross-reference-target-unsupported`` 로 거부한다.
        *content_type* 은 보일 것(``OBJECT_TYPE_PAGE`` 쪽 번호, ``OBJECT_TYPE_NUMBER`` 번호,
        ``OBJECT_TYPE_CONTENTS`` 내용, ``OBJECT_TYPE_UPDOWNPOS`` 위/아래), *hyperlink* 는 누르면
        대상으로 가는지다. 보이는 글은 비워 둔다: 쪽 번호·번호는 한/글이 쪽을 배치하며 채운다
        (모르는 값은 쓰지 않는다).
        """

        from .. import fields as _fields

        return _fields.add_cross_reference(
            self._doc,
            target,
            content_type=content_type,
            hyperlink=hyperlink,
            paragraph=optional_paragraph(
                self._doc, paragraph, section=section, caller="doc.refs.add_cross_reference",
            ),
            section=resolve_section(self._doc, section, caller="doc.refs.add_cross_reference"),
        )

    def add_bookmark(
        self,
        name: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        offset: int | None = None,
    ) -> "Bookmark":
        """책갈피를 넣는다. 상호참조·목차의 앵커가 된다. :attr:`bookmarks` 가 읽는 :class:`Bookmark` 를 돌려준다.

        *offset* 을 주면 그 문단의 그 글자 자리(``paragraph.text`` 의 자리)에 둔다: 그 자리 컨트롤 뒤, 그 자리 글자 앞."""

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
            offset=offset,
        )

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
        field_char_pr_id_ref: str | int | None = None,
    ) -> "Hyperlink":
        """표시 문자열을 가진 하이퍼링크를 넣는다. :attr:`hyperlinks` 가 읽는 :class:`Hyperlink` 를 돌려준다.

        *char_pr_id_ref* 는 표시 글의 글자 모양, *field_char_pr_id_ref* 는 필드 시작·끝 컨트롤 런의 글자
        모양이다(주지 않으면 링크 앞 글의 모양, ``Paragraph.add_hyperlink`` 와 같다)."""

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
            field_char_pr_id_ref=field_char_pr_id_ref,
        )
