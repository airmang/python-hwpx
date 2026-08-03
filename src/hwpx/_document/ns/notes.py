# SPDX-License-Identifier: Apache-2.0
"""`doc.notes` — 각주·미주·메모.

능력 레지스트리의 `footnote-endnote` 와 `memo` 두 영역이 여기로 온다. 셋 다
**본문 흐름 밖에 붙는 주석**이라는 한 가지 축이다 — 각주는 쪽 아래, 미주는
문서 끝, 메모는 여백에 놓이지만 저작 관점에서는 같은 일이다.

## `add_memo(anchor=...)` — 3-튜플의 소멸

5.x 는 메모를 두 갈래로 만들었다:

- `add_memo(text)` → `HwpxOxmlMemo` (본문에 앵커 없음)
- `add_memo_with_anchor(text, paragraph=...)` → `(Memo, Paragraph, str)` **3-튜플**

같은 동사의 두 형태이므로 `anchor=` 파라미터로 접었다. 3-튜플이 담던
문단과 필드 id 는 WP-C 가 `Memo.paragraph` / `Memo.field_id` 속성으로 옮긴다 —
그때까지는 5.x 와 같은 튜플을 돌려준다(아래 Note).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ...errors import HwpxValueError
from .._resolve import resolve_section
from ._base import _Namespace

if TYPE_CHECKING:
    from ...model import Memo, Note, Paragraph, Section

__all__ = ["NotesNamespace"]


class NotesNamespace(_Namespace):
    """각주·미주·메모 — 본문 흐름 밖 주석."""

    __slots__ = ()
    _path = "doc.notes"

    def _section(self, section, section_index, caller: str) -> "Section":
        return resolve_section(
            self._doc, section, section_index, caller=f"doc.notes.{caller}"
        )

    # -- 각주 / 미주 -------------------------------------------------------

    def add_footnote(
        self,
        text: str,
        paragraph: "Paragraph | None" = None,
        *,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "Note":
        """쪽 아래 각주를 단다."""

        from .. import shapes as _shapes

        return _shapes.add_footnote(
            self._doc,
            text=text,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_footnote"),
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_endnote(
        self,
        text: str,
        paragraph: "Paragraph | None" = None,
        *,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "Note":
        """문서 끝 미주를 단다."""

        from .. import shapes as _shapes

        return _shapes.add_endnote(
            self._doc,
            text=text,
            paragraph=paragraph,
            section=self._section(section, section_index, "add_endnote"),
            char_pr_id_ref=char_pr_id_ref,
        )

    # -- 메모 --------------------------------------------------------------

    @property
    def memos(self) -> list["Memo"]:
        """모든 섹션의 메모를 문서 순서로."""

        memos: list["Memo"] = []
        for section in self._doc.oxml.sections:
            memos.extend(section.memos)
        return memos

    def add_memo(
        self,
        text: str = "",
        *,
        anchor: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        section_index: int | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
        paragraph_text: str | None = None,
        field_id: str | None = None,
        author: str | None = None,
        created: "datetime | str | None" = None,
        number: int = 1,
        anchor_char_pr_id_ref: str | int | None = None,
    ) -> "Memo":
        """메모를 만든다. ``anchor`` 를 주면 그 문단에 앵커까지 건다.

        Args:
            anchor: 앵커를 걸 문단(객체 또는 인덱스). ``None`` 이면 앵커 없는
                메모만 만든다. 5.x 의 ``add_memo_with_anchor`` 가 이 인자다.

        5.x 의 앵커 변형은 ``(Memo, Paragraph, field_id)`` 3-튜플을 돌려줬다.
        이제 메모 하나이고, 문단과 필드 id 는 ``memo.paragraph`` /
        ``memo.field_id`` 로 읽는다.
        """

        from .. import memos as _memos

        target = self._section(section, section_index, "add_memo")
        if anchor is None:
            if paragraph_text is not None or field_id is not None or author is not None:
                raise HwpxValueError(
                    "앵커 없는 메모에는 앵커 인자를 줄 수 없습니다.",
                    code="note-argument-conflict",
                    context={"caller": "doc.notes.add_memo"},
                    suggestion="anchor= 로 앵커를 걸 문단을 지정하세요.",
                )
            return _memos.add_memo(
                self._doc,
                text=text,
                section=target,
                memo_shape_id_ref=memo_shape_id_ref,
                memo_id=memo_id,
                char_pr_id_ref=char_pr_id_ref,
                attributes=attributes,
            )

        from .._resolve import resolve_paragraph

        return _memos.add_memo_with_anchor(
            self._doc,
            text=text,
            paragraph=resolve_paragraph(
                self._doc, anchor, caller="doc.notes.add_memo"
            ),
            section=target,
            paragraph_text=paragraph_text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            anchor_char_pr_id_ref=anchor_char_pr_id_ref,
        )

    def attach(
        self,
        paragraph: "Paragraph | int",
        memo: "Memo",
        *,
        field_id: str | None = None,
        author: str | None = None,
        created: "datetime | str | None" = None,
        number: int = 1,
        char_pr_id_ref: str | int | None = None,
    ) -> "Memo":
        """이미 있는 메모를 문단에 앵커로 걸고 그 메모를 돌려준다.

        5.x 는 필드 id 문자열만 돌려줘서, 어느 메모가 걸렸는지 호출자가 따로
        들고 있어야 했다. 이제 메모 자신이 ``paragraph``·``field_id`` 를 안다.
        """

        from .. import memos as _memos
        from .._resolve import resolve_paragraph

        return _memos.attach_memo_field(
            self._doc,
            paragraph=resolve_paragraph(
                self._doc, paragraph, caller="doc.notes.attach"
            ),
            memo=memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_memo(self, memo: "Memo") -> None:
        """메모와 그 앵커를 제거한다."""

        from .. import memos as _memos

        _memos.remove_memo(self._doc, memo)
