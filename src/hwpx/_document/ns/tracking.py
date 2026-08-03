# SPDX-License-Identifier: Apache-2.0
"""`doc.tracking` — 변경추적(redline) 저작과 조회.

능력 레지스트리의 `redline` 영역이다. 5.x 는 저작 넷과 조회 넷을 루트에
여덟 칸으로 흩어 두었다.

`add_track_change` → `add_change` 는 **저수준 원시 동사**다. 변경 항목을
등록만 하고 본문은 건드리지 않는다. 대부분의 경우 `insert`/`delete`/`replace`
가 맞다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import _Namespace

if TYPE_CHECKING:
    from ...model import Paragraph
    from ...objects import TrackedChange, TrackedReplacement
    from ...oxml import TrackChange, TrackChangeAuthor

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
        """문단(또는 그 안의 *match*)을 삭제로 표시한다."""

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
        author_name: str = "AI Agent",
        date: str | None = None,
    ) -> "TrackedChange":
        """변경 항목만 등록한다(저수준 — 본문은 건드리지 않는다).

        본문을 건드리지 않으므로 결과의 ``paragraph`` 는 ``None`` 이다.
        """

        from .. import tracked as _tracked

        return _tracked.add_track_change(
            self._doc, change_type=change_type, author_name=author_name, date=date
        )

    # -- 조회 --------------------------------------------------------------

    @property
    def changes(self) -> dict[str, "TrackChange"]:
        """등록된 변경 항목 표(id → 항목)."""

        return self._doc.oxml.track_changes

    def change(self, change_id_ref: "int | str | None") -> "TrackChange | None":
        """id 로 변경 항목 하나를 찾는다."""

        return self._doc.oxml.track_change(change_id_ref)

    @property
    def authors(self) -> dict[str, "TrackChangeAuthor"]:
        """변경 작성자 표(id → 작성자)."""

        return self._doc.oxml.track_change_authors

    def author(self, author_id_ref: "int | str | None") -> "TrackChangeAuthor | None":
        """id 로 작성자 하나를 찾는다."""

        return self._doc.oxml.track_change_author(author_id_ref)
