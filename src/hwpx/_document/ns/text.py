# SPDX-License-Identifier: Apache-2.0
"""`doc.text` — 텍스트 순회·검색·치환·내보내기.

5.x는 이 축을 루트에 7칸으로 흩어 놓았다(`export_text`·`export_html`·
`export_markdown`·`export_rich_markdown`·`iter_runs`·`find_runs_by_style`·
`replace_text_in_runs`). 전부 "문서의 글자를 읽어 내거나 바꾼다"는 한 가지
일이라 한 네임스페이스로 모았다.

`export_rich_markdown` 은 동사가 아니라 `markdown` 의 변형이었으므로
`markdown(rich=True)` 파라미터로 접었다 — 6.0에서 강등된 3개 중 하나.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Iterator, cast

from ...errors import HwpxValueError, ReplaceScopeWarning
from ...oxml.namespaces import HP, tag_local_name
from ._base import _Namespace

if TYPE_CHECKING:
    from ...objects.highlight import Highlight
    from ...tools.markdown_import import MarkdownStyle
    from ...oxml import HwpxOxmlParagraph, HwpxOxmlRun
    from ..text_blocks import TextBlock, TextChangeReport, TextOutline

__all__ = ["TextNamespace"]

#: Subtrees a Hancom-style replace leaves alone: memo bodies (the memo list, and the text of a
#: memo field, the only field that carries its own paragraphs).
_NOT_REPLACED = frozenset({"memogroup", "memo", "fieldBegin"})
_STORIES = frozenset({"header", "footer"})


def _story_key(story: Any) -> tuple[str, str | None, str]:
    return (tag_local_name(story.tag), story.get("id"), story.get("applyPageType", "BOTH"))


def _paragraphs_everywhere(section_element: Any) -> Iterator[tuple[Any, str, tuple[str, str | None, str] | None]]:
    """Every paragraph of a section except memo bodies, in document order, with its role.

    A header or footer python-hwpx writes lives twice: under ``hp:secPr`` (``"story"``, the
    copy python-hwpx edits) and in a body ``hp:ctrl`` (``"mirror"``, the copy Hancom reads).
    Both carry the story's key so a caller can make the mirror follow the story.
    """

    counts: dict[tuple[str, str | None, str], int] = {}
    for sec_pr in section_element.iter(f"{HP}secPr"):
        for story in sec_pr:
            if tag_local_name(story.tag) in _STORIES:
                counts[_story_key(story)] = counts.get(_story_key(story), 0) + 1

    def walk(element: Any, parent: str, role: str, key: Any) -> Iterator[tuple[Any, str, Any]]:
        for child in element:
            name = tag_local_name(child.tag)
            if name in _NOT_REPLACED:
                continue
            child_role, child_key = role, key
            if name in _STORIES and counts.get(_story_key(child)) == 1:
                child_role = "story" if parent == "secPr" else "mirror" if parent == "ctrl" else role
                child_key = _story_key(child) if child_role != role else key
            if name == "p":
                yield child, child_role, child_key
            yield from walk(child, name, child_role, child_key)

    yield from walk(section_element, "", "plain", None)


def _run_matches(
    run: "HwpxOxmlRun",
    *,
    text_color: str | None,
    underline_type: str | None,
    underline_color: str | None,
    target_char: str | None,
) -> bool:
    if target_char is not None and (run.char_pr_id_ref or "").strip() != target_char:
        return False
    if text_color is None and underline_type is None and underline_color is None:
        return True
    style = run.style
    if style is None:
        return False
    return (
        (text_color is None or style.text_color() == text_color)
        and (underline_type is None or style.underline_type() == underline_type)
        and (underline_color is None or style.underline_color() == underline_color)
    )


class TextNamespace(_Namespace):
    """텍스트 순회·검색·치환·내보내기."""

    __slots__ = ()
    _path = "doc.text"

    # -- 내보내기 ----------------------------------------------------------

    def plain(self, **kwargs: object) -> str:
        """본문을 평문으로 내보낸다."""

        from .. import persistence as _persistence

        return _persistence.export_text(self._doc, **kwargs)

    def markdown(self, *, rich: bool = False, **kwargs: object) -> str:
        """본문을 Markdown 으로 내보낸다.

        Args:
            rich: 참이면 런 서식(굵게·기울임·밑줄 등)을 보존하는 확장 변환을
                쓴다. 5.x `export_rich_markdown` 이 이 파라미터로 접혔다.
        """

        from .. import persistence as _persistence

        if rich:
            return _persistence.export_rich_markdown(self._doc, **kwargs)
        return _persistence.export_markdown(self._doc, **kwargs)

    def html(self, **kwargs: object) -> str:
        """본문을 HTML 로 내보낸다."""

        from .. import persistence as _persistence

        return _persistence.export_html(self._doc, **kwargs)

    # -- 가져오기 ----------------------------------------------------------

    def append_markdown(self, markdown: str, *, style: "MarkdownStyle | None" = None) -> None:
        """*markdown* 을 마지막 구역 끝에 문단·목록·표로 덧붙인다.

        ``hwpx.tools.markdown_import.from_markdown`` 과 같은 부분 집합(제목 ``#``~``####``,
        문단, ``-``/``1.`` 목록, ``|`` 표, ``**굵게**``/``*기울임*``)을 쓴다.
        새 문단은 앞 문단의 서식을 물려받지 않는다. 모르는 Markdown 은 평문으로
        쓰고 오류를 내지 않는다. *style* 은
        :class:`hwpx.tools.markdown_import.MarkdownStyle`.
        """

        from ...tools.markdown_import import append_markdown

        append_markdown(self._doc, markdown, style=style)

    # -- 순회·검색 ---------------------------------------------------------

    def runs(self) -> Iterator["HwpxOxmlRun"]:
        """문서의 모든 런을 문서 순서로 내놓는다."""

        for paragraph in self._doc.paragraphs:
            for run in paragraph.runs:
                yield run

    def find_runs(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> list["HwpxOxmlRun"]:
        """주어진 서식 조건을 모두 만족하는 런을 돌려준다."""

        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None
        return [
            run
            for run in self.runs()
            if _run_matches(
                run,
                text_color=text_color,
                underline_type=underline_type,
                underline_color=underline_color,
                target_char=target_char,
            )
        ]

    # -- id 붙은 글 덩어리 ---------------------------------------------------

    def blocks(self) -> Iterator["TextBlock"]:
        """본문 문단과 표 칸 문단(칸 안 표 포함)을 문서 순서대로, 안정적인 id와 함께 내놓는다.

        id는 위치로 정해진다: ``s0p16`` (0번 구역의 16번 본문 문단, 번호는 0부터), ``s0p16t0r3c0q0`` (그 문단의 0번 표,
        3행 0열 칸의 0번 문단), 칸 안 표는 ``…q0t0r1c1q0`` 처럼 이어진다. 행·열은 칸의 주소라
        병합 칸은 대표 칸에서 한 번만 나온다. 저장·재열기 뒤에도 같고, 앞쪽에 문단·표·칸을
        넣거나 지울 때만 바뀐다. 머리말·꼬리말·각주·메모·글상자는 포함하지 않는다.
        """

        from ..text_blocks import iter_text_blocks

        return iter_text_blocks(self._doc)

    def outline(
        self,
        *,
        max_chars: int = 8000,
        max_items: int | None = None,
        max_block_chars: int = 200,
        after: str | None = None,
    ) -> "TextOutline":
        """글자가 있는 덩어리를 ``{"id", "where", "text"}`` 목록으로, 글자 예산 안에서 돌려준다.

        빈 문단은 빼고, 탭·줄 바꿈은 공백으로, 제어 문자는 지운다. *max_block_chars* 보다 긴
        덩어리는 앞부분만 남기고 ``…`` 로 끝낸다(``"truncated": True``). *max_chars* 는 각 항목의
        id·위치·글자를 센다. 예산이나 *max_items* 가 다하면 항목 단위로 멈추고 ``complete`` 가
        ``False``, ``next_after`` 가 마지막 id다 — 다음 쪽은 ``after=next_after`` 로 읽는다. 한 쪽에는 예산보다 큰 항목이라도 적어도 하나가 들어간다.
        ``to_text()`` 는 한 줄에 한 항목인 가장 짧은 프롬프트 형태다.
        """

        from ..text_blocks import outline

        return outline(
            self._doc,
            max_chars=max_chars,
            max_items=max_items,
            max_block_chars=max_block_chars,
            after=after,
        )

    def apply_changes(
        self,
        changes: "dict[str, str]",
        *,
        check_overflow: bool = True,
    ) -> "TextChangeReport":
        """``{id: 새 글}`` 을 한 번에 적용하고 id마다 결과를 보고한다.

        모든 id를 먼저 찾은 뒤 쓴다. 없는 id는 ``unknown_ids`` 로 보고하고 나머지는 적용한다.
        한 런 안에서 끝나는 바꿈은 런과 컨트롤을 모두 지키고, 서식이 다른 런에 걸치거나 탭·줄
        바꿈을 넣는 바꿈은 문단 첫 런의 서식으로 쓴다(``rewritten``). *check_overflow* 면 바뀐 칸을
        전후로 재어, 칸이 품는 줄보다 많이(그리고 전보다 많이) 필요할 것으로 추정되는 칸을
        ``overflow`` 에 넣는다 — 렌더가 아니라 form-fit 측정기의 추정이다.
        """

        from ..text_blocks import apply_text_changes

        return apply_text_changes(self._doc, changes, check_overflow=check_overflow)

    # -- 치환 --------------------------------------------------------------

    def replace(
        self,
        search: str,
        replacement: str,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
        limit: int | None = None,
        everywhere: bool = False,
    ) -> int:
        """서식 조건에 맞는 런 안에서 *search* 를 바꾸고 치환 횟수를 돌려준다.

        기본은 본문 문단만, 런 하나 안의 글만 본다. ``everywhere=True``면 한/글 "모두 바꾸기"처럼
        표 칸(칸 안 표 포함)·글상자·캡션·머리말·꼬리말·각주·미주·바탕쪽의 문단도 바꾸고, 서식이
        다른 런에 걸친 말도 바꾼다. 바꿀 글의 글자는 같은 자리의 찾은 글자가 있던 런의 서식을 따르고,
        남는 글자는 찾은 글의 마지막 글자 뒤에 붙는다. 탭·줄 바꿈이나 컨트롤·개체를 사이에 둔 글은 한 말로 보지 않는다. 메모 본문은
        바꾸지 않는다. 서식 조건을 주면 조건에 맞는 런만 보고, 맞지 않는 런은 말을 끊는다.
        어느 쪽이든 대소문자는 가린다(한/글 "모두 바꾸기"의 기본은 라틴 대소문자를 가리지 않는다).
        """

        if not search:
            raise HwpxValueError(
                "search 는 빈 문자열일 수 없습니다.",
                code="text-search-empty",
                context={"search": search},
                suggestion="바꿀 대상 문자열을 지정하세요.",
            )

        if everywhere:
            return self._replace_everywhere(
                search,
                replacement,
                limit=limit,
                text_color=text_color,
                underline_type=underline_type,
                underline_color=underline_color,
                target_char=str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None,
            )

        replacements = 0
        runs = self.find_runs(
            text_color=text_color,
            underline_type=underline_type,
            underline_color=underline_color,
            char_pr_id_ref=char_pr_id_ref,
        )

        for run in runs:
            remaining = None
            if limit is not None:
                remaining = limit - replacements
                if remaining <= 0:
                    break
            original_char_pr = run.char_pr_id_ref
            replaced_here = run.replace_text(search, replacement, count=remaining)
            if replaced_here and original_char_pr is not None:
                # 치환 중 XML 노드가 다시 쓰여도 원래 서식 참조를 잃지 않게 한다.
                run.char_pr_id_ref = original_char_pr
            replacements += replaced_here
            if limit is not None and replacements >= limit:
                break
        unfiltered = text_color is None and underline_type is None and underline_color is None and char_pr_id_ref is None
        if not replacements and unfiltered and (limit is None or limit > 0):
            self._warn_when_found_out_of_scope(search)
        return replacements

    def _warn_when_found_out_of_scope(self, search: str) -> None:
        """Say so when the default scope changed nothing but ``everywhere=True`` has text to look at."""

        from ...oxml import HwpxOxmlParagraph

        found = 0
        for section in self._doc.sections:
            for element, role, _key in _paragraphs_everywhere(section.element):
                if role != "mirror" and search in HwpxOxmlParagraph(element, section).text:
                    found += 1
        if found:
            warnings.warn(
                f"doc.text.replace가 바꾼 곳이 없습니다. 찾는 글은 문단 {found}곳에 있지만 기본 범위(본문 문단의 "
                "런 하나 안) 밖입니다: 표 칸·글상자·머리말 등이거나 서식이 다른 런에 걸쳐 있습니다. "
                "everywhere=True를 주면 그곳도 바꿉니다.",
                ReplaceScopeWarning,
                stacklevel=3,
            )

    def _replace_everywhere(
        self,
        search: str,
        replacement: str,
        *,
        limit: int | None,
        text_color: str | None,
        underline_type: str | None,
        underline_color: str | None,
        target_char: str | None,
    ) -> int:
        from ...oxml import HwpxOxmlParagraph
        from ...oxml.run import replace_across_runs

        def replace_in(paragraph: "HwpxOxmlParagraph", count: int | None) -> int:
            done = 0
            group: list[Any] = []
            for run in [*paragraph.runs, None]:
                if run is not None and _run_matches(
                    run,
                    text_color=text_color,
                    underline_type=underline_type,
                    underline_color=underline_color,
                    target_char=target_char,
                ):
                    group.append(run.element)
                    continue
                if group and (count is None or done < count):
                    done += replace_across_runs(
                        paragraph, group, search, replacement, count=None if count is None else count - done
                    )
                group = []
            return done

        total = 0
        # A mirror copy gets the same number of replacements as its story, so the two stay alike.
        story_counts: dict[Any, int] = {}
        mirrors: list[tuple["HwpxOxmlParagraph", Any]] = []
        for section in self._doc.sections:
            for element, role, key in _paragraphs_everywhere(section.element):
                paragraph = HwpxOxmlParagraph(element, section)
                if role == "mirror":
                    mirrors.append((paragraph, key))
                    continue
                if limit is not None and total >= limit:
                    continue
                done = replace_in(paragraph, None if limit is None else limit - total)
                total += done
                if role == "story":
                    story_counts[key] = story_counts.get(key, 0) + done
        for paragraph, key in mirrors:
            if story_counts.get(key):
                story_counts[key] -= replace_in(paragraph, story_counts[key])
        for master_page in self._doc.oxml.master_pages:
            # A master page part gives a paragraph what it needs from a section: mark_dirty() and document.
            part = cast(Any, master_page)
            for element, _role, _key in _paragraphs_everywhere(master_page.element):
                if limit is not None and total >= limit:
                    break
                total += replace_in(HwpxOxmlParagraph(element, part), None if limit is None else limit - total)
        return total

    # -- 형광펜 ------------------------------------------------------------

    def highlight(
        self,
        paragraph: "HwpxOxmlParagraph | int",
        match: str,
        *,
        color: str = "#FFFF00",
    ) -> "Highlight":
        """*match* 의 첫 등장을 형광펜(``markpenBegin``/``markpenEnd``)으로 감싼다."""

        from .. import highlight as _highlight
        from .._resolve import resolve_paragraph

        return _highlight.add_highlight(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.text.highlight"),
            match,
            color=color,
        )

    def highlights(self) -> tuple["Highlight", ...]:
        """문서의 모든 형광펜 구간을 문서 순서로 돌려준다."""

        from .. import highlight as _highlight

        return _highlight.list_highlights(self._doc)
