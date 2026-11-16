# SPDX-License-Identifier: Apache-2.0
"""`doc.tracking` — 변경추적(redline) 저작과 조회.

능력 레지스트리의 `redline` 영역이다. 5.x 는 저작 넷과 조회 넷을 루트에
여덟 칸으로 흩어 두었다.

`add_track_change` → `add_change` 는 **저수준 원시 동사**다. 변경 항목을
등록만 하고 본문은 건드리지 않는다. 대부분의 경우 `insert`/`delete`/`replace`
가 맞다.
"""

from __future__ import annotations

from ...model import Paragraph
from ...objects import TrackedChange, TrackedReplacement
from ...oxml import TrackChangeAuthor
from ._base import _Namespace

__all__ = ["TrackingNamespace"]


class TrackingNamespace(_Namespace):
    """변경추적(redline) 저작과 조회."""

    __slots__ = ()
    _path = "doc.tracking"

    # -- 저작 --------------------------------------------------------------

    def insert(
        self,
        paragraph: "Paragraph | int",
        text: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "TrackedChange":
        """삽입으로 표시된 텍스트를 문단 끝에 넣는다."""

        from .. import tracked as _tracked
        from .._resolve import resolve_paragraph

        return _tracked.add_tracked_insert(
            self._doc,
            paragraph=resolve_paragraph(
                self._doc, paragraph, caller="doc.tracking.insert"
            ),
            text=text,
            author=author,
            date=date,
            char_pr_id_ref=char_pr_id_ref,
        )

    def delete(
        self,
        paragraph: "Paragraph | int",
        *,
        match: str | None = None,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> "TrackedChange":
        """문단(또는 그 안의 *match*)을 삭제로 표시한다.

        글만 있는 문단을 통째로 지우고 뒤에 문단이 이어지면, 문단 나눔도
        삭제로 표시한다(`paraend="1"`). 그래서 한컴에서 빈 줄이 남지 않는다.
        """

        from .. import tracked as _tracked
        from .._resolve import resolve_paragraph

        return _tracked.add_tracked_delete(
            self._doc,
            paragraph=resolve_paragraph(
                self._doc, paragraph, caller="doc.tracking.delete"
            ),
            match=match,
            author=author,
            date=date,
        )

    def replace(
        self,
        paragraph: "Paragraph | int",
        old: str,
        new: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> "TrackedReplacement":
        """*old* 를 삭제로, *new* 를 삽입으로 표시한다.

        5.x 는 ``tuple[int, int]`` 를 돌려줘서 어느 쪽이 삽입인지 타입이
        말해주지 않았다. 이제 ``.insert`` / ``.delete`` 로 읽는다.
        """

        from .. import tracked as _tracked
        from .._resolve import resolve_paragraph

        return _tracked.add_tracked_replace(
            self._doc,
            paragraph=resolve_paragraph(
                self._doc, paragraph, caller="doc.tracking.replace"
            ),
            old=old,
            new=new,
            author=author,
            date=date,
        )

    def add_change(
        self,
        change_type: str,
        *,
        author: str = "AI Agent",
        date: str | None = None,
    ) -> "TrackedChange":
        """변경 항목만 등록한다(저수준 — 본문은 건드리지 않는다).

        본문을 건드리지 않으므로 결과의 ``paragraph`` 는 ``None`` 이다. *author* 는 작성자 이름으로,
        :meth:`insert`·:meth:`delete` 의 것과 같다. 글자·문단 모양 변경
        (``CharShape``·``ParaShape``)은 거부한다(``track-format-change-unconfirmed``): 스키마대로
        쓴 서식 변경을 한/글 2024가 다시 저장하면 그 항목과 ``charTcId``·``paraTcId`` 를 버린다.
        """

        from .. import tracked as _tracked

        return _tracked.add_track_change(
            self._doc, change_type=change_type, author=author, date=date
        )

    # -- 수락·거절 ----------------------------------------------------------

    def accept(
        self,
        change: "TrackedChange | int | str | None" = None,
        *,
        author: str | None = None,
    ) -> "tuple[TrackedChange, ...]":
        """변경을 수락하고 수락한 변경들을 돌려준다.

        넣은 글은 표시만 걷혀 남고, 지운 글은 실제로 지워진다(문단 나눔까지 지운
        변경이면 다음 문단이 붙는다). 아무것도 주지 않으면 문서의 모든 변경,
        ``change`` 는 그 변경 하나(id 또는 ``TrackedChange``), ``author`` 는 그
        작성자의 변경 전부. 머리의 변경·작성자 목록도 남은 것만 남는다.

        글자·문단 모양 변경(``CharShape``·``ParaShape``)은 본문(``charTcId``·``paraTcId``)이
        가리키지 않을 때만 수락한다(머리 목록에서만 빠지고 글은 지금 모양 그대로다). 본문이
        가리키면 아무것도 바꾸기 전에 거부한다(``track-format-change-unconfirmed``).
        """

        from .. import tracked as _tracked

        return _tracked.resolve_tracked_changes(self._doc, accept=True, change=change, author=author)

    def reject(
        self,
        change: "TrackedChange | int | str | None" = None,
        *,
        author: str | None = None,
    ) -> "tuple[TrackedChange, ...]":
        """변경을 거절하고 거절한 변경들을 돌려준다.

        넣은 글은 지워지고, 지운 글은 표시만 걷혀 되살아난다. 고르는 방법은
        :meth:`accept` 와 같다. 고른 것에 글자·문단 모양 변경이 있으면 되돌릴 옛 모양을 알 수
        없어(한/글 2024도 그런 변경을 저장 때 버린다) 아무것도 바꾸기 전에 거부한다
        (``track-format-change-unconfirmed``) — 넣기·지우기는 ``change=`` 로 하나씩 거절한다.
        """

        from .. import tracked as _tracked

        return _tracked.resolve_tracked_changes(self._doc, accept=False, change=change, author=author)

    # -- 조회 --------------------------------------------------------------

    @property
    def changes(self) -> tuple["TrackedChange", ...]:
        """문서의 변경 기록을 문서 순서로(:meth:`insert`·:meth:`delete` 가 돌려주는 것과 같은 ``TrackedChange``).

        본문에 표시가 있는 변경은 그 표시가 처음 나오는 순서로 오고 ``paragraph`` 가 그 문단이다.
        본문에 표시가 없는 변경(:meth:`add_change` 로 등록만 한 것)은 그 뒤에 머리(``hh:trackChanges``)의
        순서로 오고 ``paragraph`` 는 ``None`` 이다. ``kind`` 는 ``"INSERT"``·``"DELETE"`` …, ``author`` 는
        작성자 이름이다. 머리 정의 그대로는 ``doc.oxml.headers[0].track_changes``.
        """

        from .. import tracked as _tracked

        return _tracked.list_tracked_changes(self._doc)

    def change(self, change_id_ref: "int | str | None") -> "TrackedChange | None":
        """id 로 변경 기록 하나를 찾는다(:attr:`changes` 의 그 값). 없으면 ``None``."""

        from .. import tracked as _tracked

        return _tracked.find_tracked_change(self._doc, change_id_ref)

    @property
    def authors(self) -> dict[str, "TrackChangeAuthor"]:
        """변경 작성자 표(id → 작성자)."""

        return self._doc.oxml.track_change_authors

    def author(self, author_id_ref: "int | str | None") -> "TrackChangeAuthor | None":
        """id 로 작성자 하나를 찾는다."""

        return self._doc.oxml.track_change_author(author_id_ref)
