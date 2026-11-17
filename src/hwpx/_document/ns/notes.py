# SPDX-License-Identifier: Apache-2.0
"""`doc.notes` — 각주·미주·메모.

능력 레지스트리의 `footnote-endnote` 와 `memo` 두 영역이 여기로 온다. 셋 다
**본문 흐름 밖에 붙는 주석**이라는 한 가지 축이다 — 각주는 쪽 아래, 미주는
문서 끝, 메모는 여백에 놓이지만 저작 관점에서는 같은 일이다.

## `add_memo(paragraph=...)` — 3-튜플의 소멸

5.x 는 메모를 두 갈래로 만들었다:

- `add_memo(text)` → `HwpxOxmlMemo` (본문에 앵커 없음)
- `add_memo_with_anchor(text, paragraph=...)` → `(Memo, Paragraph, str)` **3-튜플**

같은 동사의 두 형태이므로 한 파라미터로 접었다(6.x 는 `anchor=`, 7.0 은 다른 묶음처럼
`paragraph=`). 3-튜플이 담던 문단과 필드 id 는 `Memo.paragraph` / `Memo.field_id` 속성이다.
"""

from __future__ import annotations

from datetime import datetime
from ...errors import HwpxValueError
from ...model import Memo, Note, Paragraph, Section
from .._resolve import optional_paragraph, resolve_section
from ._base import _Namespace

__all__ = ["NotesNamespace"]


class NotesNamespace(_Namespace):
    """각주·미주·메모 — 본문 흐름 밖 주석."""

    __slots__ = ()
    _path = "doc.notes"

    def _section(self, section, caller: str) -> "Section":
        return resolve_section(
            self._doc, section, caller=f"doc.notes.{caller}"
        )

    # -- 각주 / 미주 -------------------------------------------------------

    def add_footnote(
        self,
        text: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
        offset: int | None = None,
    ) -> "Note":
        """쪽 아래 각주를 *paragraph* (문단 객체나 번호) 끝에 단다. 주지 않으면 *section* 끝에 새 문단을 만든다.

        *offset* 를 주면 그 문단의 그 글자 자리(``paragraph.text`` 의 자리)에 단다: 그 자리 컨트롤 뒤, 그 자리 글자 앞.
        글 가운데면 한/글처럼 그 런의 ``hp:t`` 를 둘로 나누고 사이에 둔다. 뒤 번호는 다시 매긴다."""

        from .. import shapes as _shapes

        return _shapes.add_footnote(
            self._doc,
            text=text,
            paragraph=optional_paragraph(
                self._doc, paragraph, section=section,
                caller="doc.notes.add_footnote",
            ),
            section=self._section(section, "add_footnote"),
            char_pr_id_ref=char_pr_id_ref,
            offset=offset,
        )

    def add_endnote(
        self,
        text: str,
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        char_pr_id_ref: str | int | None = None,
        offset: int | None = None,
    ) -> "Note":
        """문서 끝 미주를 *paragraph* (문단 객체나 번호) 끝에 단다. 주지 않으면 *section* 끝에 새 문단을 만든다.

        *offset* 를 주면 그 문단의 그 글자 자리(``paragraph.text`` 의 자리)에 단다: 그 자리 컨트롤 뒤, 그 자리 글자 앞.
        글 가운데면 한/글처럼 그 런의 ``hp:t`` 를 둘로 나누고 사이에 둔다. 뒤 번호는 다시 매긴다."""

        from .. import shapes as _shapes

        return _shapes.add_endnote(
            self._doc,
            text=text,
            paragraph=optional_paragraph(
                self._doc, paragraph, section=section,
                caller="doc.notes.add_endnote",
            ),
            section=self._section(section, "add_endnote"),
            char_pr_id_ref=char_pr_id_ref,
            offset=offset,
        )

    @property
    def footnotes(self) -> "tuple[Note, ...]":
        """문서의 모든 각주를 문서 순서로. 표 칸·글상자 안의 것도 본다.

        번호는 ``note.number`` 로 읽는다(한/글이 매기는 방식: 종류마다 1부터,
        구역·새 번호 지정이 다시 시작시킨다). ``note.paragraph`` 는 각주 표시가
        놓인 문단이다.
        """

        return self._notes("footNote")

    @property
    def endnotes(self) -> "tuple[Note, ...]":
        """문서의 모든 미주를 문서 순서로. 표 칸·글상자 안의 것도 본다."""

        return self._notes("endNote")

    def _notes(self, tag: str) -> "tuple[Note, ...]":
        from ...oxml.note_authoring import iter_document_notes

        sections = self._doc.oxml.sections
        if not sections:
            return ()
        return tuple(iter_document_notes(sections[0], tag))

    # -- 메모 --------------------------------------------------------------

    @property
    def memos(self) -> tuple["Memo", ...]:
        """모든 섹션의 메모를 문서 순서로."""

        return tuple(memo for section in self._doc.oxml.sections for memo in section.memos)

    def add_memo(
        self,
        text: str = "",
        *,
        paragraph: "Paragraph | int | None" = None,
        section: "int | Section | None" = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
        paragraph_text: str | None = None,
        field_id: str | None = None,
        author: str | None = None,
        created: "datetime | str | None" = None,
        number: int | None = None,
        paragraph_char_pr_id_ref: str | int | None = None,
        match: str | None = None,
        index: int = 0,
    ) -> "Memo":
        """메모를 만든다. ``paragraph`` 를 주면 그 문단에 메모를 건다(앵커).

        Args:
            paragraph: 메모를 걸 문단(객체 또는 번호). ``None`` 이면 문단에 걸지 않은
                메모만 만든다. 5.x 의 ``add_memo_with_anchor`` 가 이 인자다.
            paragraph_text: *paragraph* 의 글을 이것으로 바꾼 뒤 건다.
            paragraph_char_pr_id_ref: 문단에 메모를 거는 필드(``fieldBegin type="MEMO"``)의 글자 모양.
            match: 문단 전체가 아니라 그 글자들에만 메모를 건다(한 런 안에 있어야
                한다). 한/글에서 글을 골라 메모를 넣은 것과 같다.
            index: *match* 가 문단에 여러 번 나오면 몇 번째(0부터, 기본 0 = 처음) 것에
                걸지 고른다. 한 런 안에 온전히 든 곳만 앞에서부터 겹치지 않게 센다. 그만큼
                나오지 않으면 ``note-match-not-found``, *match* 없이 주면 ``note-argument-conflict``.

        메모 본문을 문단 여러 개로 쓰려면 첫 문단 뒤에 문단을 잇는다(한/글의 메모 안 Enter와 같다).
        *text* 의 ``"\\n"`` 은 문단이 아니라 줄 바꿈(``hp:lineBreak``)이 된다::

            memo = doc.notes.add_memo("첫 줄", paragraph=p, match="정답")
            last = memo.paragraphs[0]
            for line in ("둘째 줄", "셋째 줄"):
                last = last.insert_after(line)

        5.x 의 앵커 변형은 ``(Memo, Paragraph, field_id)`` 3-튜플을 돌려줬다.
        이제 메모 하나이고, 문단과 필드 id 는 ``memo.paragraph`` /
        ``memo.field_id`` 로 읽는다.

        메모 모양은 메모마다가 아니라 구역마다다(한/글 2024 저장본): :meth:`set_memo_shape`.
        """

        from .. import memos as _memos

        target = self._section(section, "add_memo")
        if paragraph is None:
            if (paragraph_text is not None or field_id is not None or author is not None or match is not None
                    or index != 0):
                raise HwpxValueError(
                    "문단에 걸지 않는 메모에는 문단 인자를 줄 수 없습니다.",
                    code="note-argument-conflict",
                    context={"caller": "doc.notes.add_memo"},
                    suggestion="paragraph= 로 메모를 걸 문단을 지정하세요.",
                )
            return _memos.add_memo(
                self._doc,
                text=text,
                section=target,
                memo_id=memo_id,
                char_pr_id_ref=char_pr_id_ref,
                attributes=attributes,
            )

        from .._resolve import resolve_paragraph

        return _memos.add_memo_with_anchor(
            self._doc,
            text=text,
            paragraph=resolve_paragraph(
                self._doc, paragraph, caller="doc.notes.add_memo"
            ),
            section=target,
            paragraph_text=paragraph_text,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            paragraph_char_pr_id_ref=paragraph_char_pr_id_ref,
            match=match,
            index=index,
        )

    def attach(
        self,
        paragraph: "Paragraph | int",
        memo: "Memo",
        *,
        field_id: str | None = None,
        author: str | None = None,
        created: "datetime | str | None" = None,
        number: int | None = None,
        char_pr_id_ref: str | int | None = None,
        match: str | None = None,
        index: int = 0,
    ) -> "Memo":
        """이미 있는 메모를 문단에 앵커로 걸고 그 메모를 돌려준다.

        ``match`` 를 주면 문단 전체가 아니라 그 글자들에만 건다(``add_memo`` 와 같다).
        ``index`` 는 *match* 가 몇 번째(0부터) 나오는 곳인지 고른다(``add_memo`` 와 같다).

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
            match=match,
            index=index,
        )

    def remove_memo(self, memo: "Memo") -> None:
        """메모와 그 앵커를 제거한다."""

        from .. import memos as _memos

        _memos.remove_memo(self._doc, memo)

    def set_memo_shape(
        self,
        memo_shape_id_ref: "str | int | None",
        *,
        section: "int | Section | str | None" = None,
    ) -> None:
        """구역의 메모가 그려질 메모 모양(``hh:memoPr``)을 정한다.

        한/글은 메모 모양을 구역(``hp:secPr`` 의 ``memoShapeIDRef``)에 두고, MEMO 누름틀에는 늘
        ``MemoShapeIDRef=65535`` 를 쓴다(한/글 2024 저장본). 그래서 메모 하나가 아니라 그 구역의 모든
        메모가 이 모양이다. ``None``(또는 ``"0"``)은 한/글 기본 모양. ``section`` 은 구역 번호·객체,
        ``"all"`` 은 모든 구역, 주지 않으면 마지막 구역. 머리에 없는 id 는 거부한다
        (``note-memo-shape-not-found``). 모양은 ``doc.styles.ensure_memo_shape(...)`` 로 만들고, 구역의
        것은 ``doc.sections[i].properties.memo_shape_id_ref`` 로 읽는다.
        """

        if section == "all":
            targets = list(self._doc.sections)
        else:
            targets = [self._section(section, "set_memo_shape")]
        for target in targets:  # an unknown id fails on the first, before any section changes
            target.properties.memo_shape_id_ref = memo_shape_id_ref
