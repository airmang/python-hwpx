# SPDX-License-Identifier: Apache-2.0
"""`doc.text` — 텍스트 순회·검색·치환·평문 내보내기.

5.x는 이 축을 루트에 7칸으로 흩어 놓았다(`export_text`·`export_html`·
`export_markdown`·`export_rich_markdown`·`iter_runs`·`find_runs_by_style`·
`replace_text_in_runs`). 전부 "문서의 글자를 읽어 내거나 바꾼다"는 한 가지
일이라 한 네임스페이스로 모았다.

다른 형식으로 바꾸는 `markdown`·`html`·`append_markdown` 은 7.0에서
python-hwpx-automation(`hwpx_automation.markdown`)으로 옮겼다. 부르면 새 자리를
알려 주는 오류가 난다(``_base._Namespace.__getattr__``). 평문(`plain`)은 파일에
적힌 글을 그대로 내놓으므로 엔진에 남는다.
"""

from __future__ import annotations

import re
import warnings
from types import ModuleType
from typing import TYPE_CHECKING, Any, Iterable, Iterator, cast

from ...errors import HwpxValueError, ReplaceScopeWarning, argument_type_error
from ...objects.highlight import Highlight
from ...objects.results import ObjectPlace, ParagraphPlace, TextMatch
from ...oxml import HwpxOxmlParagraph, HwpxOxmlRun
from ...oxml.namespaces import HP, tag_local_name
from ._base import _LazyModule, _Namespace


# Named in annotations only; loaded when a hint is resolved (``import hwpx`` stays light).
def _load_text_blocks() -> ModuleType:
    from .. import text_blocks

    return text_blocks


if TYPE_CHECKING:
    from .. import text_blocks as _text_blocks
else:
    _text_blocks = _LazyModule(_load_text_blocks)

__all__ = ["TextNamespace"]

#: Subtrees a Hancom-style replace leaves alone: memo bodies (the memo list, and the text of a
#: memo field, the only field that carries its own paragraphs).
_NOT_REPLACED = frozenset({"memogroup", "memo", "fieldBegin"})
_STORIES = frozenset({"header", "footer"})


def _story_key(story: Any) -> tuple[str, str | None, str]:
    return (tag_local_name(story.tag), story.get("id"), story.get("applyPageType", "BOTH"))


def _paragraphs_everywhere(section_element: Any) -> Iterator[tuple[Any, str, tuple[str, str | None, str] | None]]:
    """Every paragraph of a section except memo bodies, in document order, with its role.

    A header or footer python-hwpx up to 6.x wrote lives twice: under ``hp:secPr`` (``"story"``,
    the copy python-hwpx edited) and in a body ``hp:ctrl`` (``"mirror"``, the copy Hancom reads).
    Both carry the story's key so a caller can make the mirror follow the story. One written
    once, as Hancom and python-hwpx 7.0 write it, is ``"plain"``.
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


def _search_pattern(search: "str | re.Pattern[str]", regex: bool, *, argument: str) -> "str | re.Pattern[str]":
    """*search* checked: a non-empty string, or a compiled regular expression when *regex* (or given one)."""

    if isinstance(search, re.Pattern):
        if not search.pattern:
            raise HwpxValueError(
                "the regular expression is empty",
                code="text-search-empty",
                suggestion="Pass the text or the regular expression to look for.",
            )
        return search
    if not isinstance(search, str):
        raise argument_type_error(
            argument, search, "str or re.Pattern", suggestion='Pass "글", or re.compile(r"\\d+") for a regular expression.'
        )
    if not search:
        raise HwpxValueError(
            "search 는 빈 문자열일 수 없습니다.",
            code="text-search-empty",
            context={"search": search},
            suggestion="바꿀 대상 문자열을 지정하세요.",
        )
    if not regex:
        return search
    try:
        return re.compile(search)
    except re.error as error:
        raise HwpxValueError(
            f"the regular expression {search!r} does not compile: {error}",
            code="text-pattern-invalid",
            context={"pattern": search, "error": str(error)},
            suggestion="Write it as Python's re module reads it, or pass regex=False to look for the text as it is.",
        ) from error


def _check_template(pattern: "re.Pattern[str]", replacement: str) -> None:
    """Refuse a *replacement* whose group references *pattern* cannot fill, before anything changes."""

    groups = [""] * pattern.groups
    for name, index in pattern.groupindex.items():
        groups[index - 1] = name
    # a pattern of the same groups, all matching nothing, gives a match to expand the template on
    shape = "".join(f"(?P<{name}>)" if name else "()" for name in groups)
    probe = cast("re.Match[str]", re.compile(shape).match(""))  # an empty shape matches ""
    try:
        probe.expand(replacement)
    except (re.error, IndexError) as error:
        raise HwpxValueError(
            f"the replacement {replacement!r} refers to a group the pattern does not have: {error}",
            code="text-replacement-invalid",
            context={"replacement": replacement, "groups": pattern.groups, "names": sorted(pattern.groupindex)},
            suggestion="Refer to groups as \\1 or \\g<name>; write a backslash itself as \\\\.",
        ) from error


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
        (text_color is None or style.color == text_color)
        and (underline_type is None or style.underline_type == underline_type)
        and (underline_color is None or style.underline_color == underline_color)
    )


class TextNamespace(_Namespace):
    """텍스트 순회·검색·치환·평문 내보내기."""

    __slots__ = ()
    _path = "doc.text"

    # -- 내보내기 ----------------------------------------------------------

    def plain(self, **kwargs: object) -> str:
        """본문을 평문으로 내보낸다."""

        from .. import persistence as _persistence

        return _persistence.export_text(self._doc, **kwargs)

    # -- 순회·검색 ---------------------------------------------------------

    def iter_runs(self) -> Iterator["HwpxOxmlRun"]:
        """본문 문단(``doc.paragraphs``)의 런을 문서 순서로 하나씩 내놓는다(문단 하나의 런은 ``paragraph.runs``)."""

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
    ) -> tuple["HwpxOxmlRun", ...]:
        """본문 런 가운데 주어진 서식 조건을 모두 만족하는 런을 문서 순서로 돌려준다."""

        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None
        return tuple(
            run
            for run in self.iter_runs()
            if _run_matches(
                run,
                text_color=text_color,
                underline_type=underline_type,
                underline_color=underline_color,
                target_char=target_char,
            )
        )

    # -- 문서 전체 훑기 ----------------------------------------------------

    def iter_paragraphs(self, *, where: "Iterable[str] | str | None" = None) -> Iterator["ParagraphPlace"]:
        """문서의 **모든** 문단을 문서 순서로, 어디에 있는지와 함께 내놓는다.

        ``doc.paragraphs`` 는 본문 문단만 보지만, 이것은 표 칸(칸 안 표 포함)·글상자·묶음 개체 안
        글상자·캡션·머리말·꼬리말·각주·미주·메모·바탕쪽의 문단까지 한 번씩 내놓는다. 각 값의
        ``where`` 가 가장 안쪽 자리(``"body"``·``"cell"``·``"text_box"``·``"caption"``·``"header"``·
        ``"footer"``·``"footnote"``·``"endnote"``·``"memo"``·``"master_page"``·``"hidden_comment"``)이고,
        표 칸이면 ``table``·``row``·``col`` 이 그 칸이다. *where* 로 자리를 고른다
        (``where={"cell", "text_box"}``). python-hwpx 6.x 가 머리말·꼬리말을 두 벌 쓴 문서에서도 한 번만 나온다.
        ``"hidden_comment"`` 는 숨은 설명(``hp:hiddenComment``): 한/글이 문단에 두지만 보이거나 인쇄하지 않는 글이다.
        """

        from ..text_blocks import iter_paragraph_places

        return iter_paragraph_places(self._doc, where)

    def iter_objects(
        self,
        *,
        kinds: "Iterable[str] | str | None" = None,
        where: "Iterable[str] | str | None" = None,
    ) -> Iterator["ObjectPlace"]:
        """문서의 **모든** 개체(표·그림·수식·도형·OLE·차트·동영상·글맵시)를 문서 순서로, 자리와 함께.

        본문뿐 아니라 표 칸·글상자·머리말·꼬리말·각주·바탕쪽 안의 개체, 묶음 개체의 구성원도
        나온다. ``kind`` 는 ``"table"``·``"picture"``·``"equation"``·``"shape"``·``"ole"``·
        ``"chart"``·``"video"``·``"textart"``, 자리 값은 :meth:`iter_paragraphs` 와 같다(그 개체를 품은
        문단의 자리). *kinds*·*where* 로 고른다. 글맵시의 글은 한/글이 적은 그대로
        ``place.object.attributes["text"]`` 로 읽는다(``hp:textart/@text``).
        """

        from ..text_blocks import iter_object_places

        return iter_object_places(self._doc, kinds, where)

    def find(
        self,
        pattern: "str | re.Pattern[str]",
        *,
        regex: bool = False,
        where: "Iterable[str] | str | None" = None,
    ) -> tuple["TextMatch", ...]:
        """*pattern* 이 나오는 곳을 문서 순서로 모두 돌려준다(``TextMatch`` 의 tuple).

        :meth:`iter_paragraphs` 가 훑는 모든 문단(표 칸·칸 안 표·글상자·캡션·머리말·꼬리말·각주·미주·
        메모·바탕쪽)에서 찾고, *where* 로 자리를 고른다(``where="body"``, ``where={"cell",
        "header"}``). 각 값의 ``paragraph``·``start``·``end`` 는 ``paragraph.text`` 의 자리라서
        ``m.paragraph.format_range(m.start, m.end, bold=True)`` 에 그대로 넘길 수 있고, ``text`` 는
        찾은 글, ``groups`` 는 정규식의 묶음이다.

        ``regex=True`` 면 *pattern* 을 파이썬 ``re`` 정규식으로 읽는다(컴파일한 ``re.Pattern`` 을
        주면 늘 정규식). 빈 일치(``^``·``\\b`` 만)는 세지 않는다. 서식이 다른 런에 걸친 말도
        찾지만, :meth:`replace` 의 ``everywhere=True`` 처럼 탭·줄 바꿈·특수 공백이나 컨트롤·개체를
        사이에 둔 글은 한 말로 보지 않는다(정규식의 ``^``·``$`` 도 그 토막의 처음과 끝이다).
        대소문자는 가린다(정규식이면 ``(?i)`` 로 끈다). 문서를 바꾸지 않는다.
        """

        from ...oxml.run import regex_matches, text_stretch_spans
        from ..text_blocks import iter_paragraph_places

        search = _search_pattern(pattern, regex, argument="pattern")
        found: list[TextMatch] = []
        for place in iter_paragraph_places(self._doc, where):
            runs = [run.element for run in place.paragraph.runs]
            for offset, segments in text_stretch_spans(runs):
                combined = "".join(segment.text for segment in segments)
                if isinstance(search, re.Pattern):
                    spans = [(m.start(), m.end(), m.groups()) for m in regex_matches(search, combined)]
                else:
                    spans = []
                    position = combined.find(search)
                    while position != -1:
                        spans.append((position, position + len(search), ()))
                        position = combined.find(search, position + len(search))
                for start, end, groups in spans:
                    found.append(
                        TextMatch(
                            paragraph=place.paragraph,
                            start=offset + start,
                            end=offset + end,
                            text=combined[start:end],
                            groups=groups,
                            where=place.where,
                            section=place.section,
                            page_type=place.page_type,
                            table=place.table,
                            row=place.row,
                            col=place.col,
                            owner=place.owner,
                            depth=place.depth,
                        )
                    )
        return tuple(found)

    # -- id 붙은 글 덩어리 ---------------------------------------------------

    def iter_blocks(self) -> Iterator["_text_blocks.TextBlock"]:
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
    ) -> "_text_blocks.TextOutline":
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
    ) -> "_text_blocks.TextChangeReport":
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
        search: "str | re.Pattern[str]",
        replacement: str,
        *,
        regex: bool = False,
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

        ``regex=True`` 면 *search* 를 파이썬 ``re`` 정규식으로 읽고(컴파일한 ``re.Pattern`` 을 주면 늘
        정규식), *replacement* 의 ``\\1``·``\\g<이름>`` 을 찾은 묶음으로 채운다(``re.sub`` 의 바꿀 글과
        같다. 백슬래시 자체는 ``\\\\``). 빈 일치는 바꾸지 않고, ``^``·``$`` 는 위의 한 말로 보는
        토막의 처음과 끝이다. 잘못된 정규식(``text-pattern-invalid``)과 없는 묶음을 부르는 바꿀 글
        (``text-replacement-invalid``)은 아무것도 바꾸기 전에 거부한다. 바뀐 문단(과 그 문단을 품은
        표의 문단)의 줄 배치 캐시는 지운다.
        """

        if isinstance(search, (str, re.Pattern)) and not isinstance(replacement, str):
            raise argument_type_error(
                "replacement", replacement, "str", suggestion=f"str({replacement!r}) 처럼 글로 바꿔 넘기세요."
            )
        pattern = _search_pattern(search, regex, argument="search")
        if isinstance(pattern, re.Pattern):
            _check_template(pattern, replacement)

        if everywhere:
            return self._replace_everywhere(
                pattern,
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
            if isinstance(pattern, re.Pattern):
                from ...oxml.run import replace_across_runs

                replaced_here = replace_across_runs(run.paragraph, [run.element], pattern, replacement, count=remaining)
            else:
                replaced_here = run.replace_text(pattern, replacement, count=remaining)
            if replaced_here and original_char_pr is not None:
                # 치환 중 XML 노드가 다시 쓰여도 원래 서식 참조를 잃지 않게 한다.
                run.char_pr_id_ref = original_char_pr
            replacements += replaced_here
            if limit is not None and replacements >= limit:
                break
        unfiltered = text_color is None and underline_type is None and underline_color is None and char_pr_id_ref is None
        if not replacements and unfiltered and (limit is None or limit > 0):
            self._warn_when_found_out_of_scope(pattern)
        return replacements

    def _warn_when_found_out_of_scope(self, search: "str | re.Pattern[str]") -> None:
        """Say so when the default scope changed nothing but ``everywhere=True`` has text to look at."""

        from ...oxml import HwpxOxmlParagraph
        from ...oxml.run import regex_matches

        def holds(text: str) -> bool:
            return bool(regex_matches(search, text)) if isinstance(search, re.Pattern) else search in text

        found = 0
        for section in self._doc.sections:
            for element, role, _key in _paragraphs_everywhere(section.element):
                if role != "mirror" and holds(HwpxOxmlParagraph(element, section).text):
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
        search: "str | re.Pattern[str]",
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
        match: str | None = None,
        *,
        color: str = "#FFFF00",
        start: int | None = None,
        end: int | None = None,
    ) -> "Highlight":
        """*match* 의 첫 등장을 형광펜(``markpenBegin``/``markpenEnd``)으로 감싼다.

        한/글이 저장하는 모양 그대로, 그 글을 담은 ``hp:t`` 안에 쓴다:
        ``<hp:t>앞 <hp:markpenBegin color="#FFFF00"/>글<hp:markpenEnd/> 뒤</hp:t>``. 글자 수와
        ``paragraph.text`` 는 그대로이다. *paragraph* 는 번호나 문단 객체(표 칸·글상자·머리말의
        문단도)이다. 서식이 다른 런에 걸친 *match* 는 거절한다(``text-highlight-match-crosses-markup``).
        ``format_range(highlight=)``·``ensure_run(highlight=)`` 는 이것이 아니라 글자 모양의 음영 색
        (``hh:charPr/@shadeColor``)이다.

        *match* 대신 *start*·*end* 를 주면 그 문단의 글자 ``[start, end)``(``paragraph.text`` 의 자리)를 칠한다. 런을
        넘어도 된다: 한/글처럼 시작은 첫 글자의 ``hp:t``, 끝은 마지막 글자의 ``hp:t`` 에 한 번씩 둔다
        (``highlight_across_runs``). 이미 있는 형광펜과 겹치면 ``paragraph-range-splits-mark`` 로 거절한다.
        """

        from .. import highlight as _highlight
        from .._resolve import resolve_paragraph

        return _highlight.add_highlight(
            self._doc,
            resolve_paragraph(self._doc, paragraph, caller="doc.text.highlight"),
            match,
            color=color,
            start=start,
            end=end,
        )

    def highlight_span(
        self,
        start_paragraph: "HwpxOxmlParagraph | int",
        start: int,
        end_paragraph: "HwpxOxmlParagraph | int",
        end: int,
        *,
        color: str = "#FFFF00",
    ) -> tuple["Highlight", ...]:
        """*start_paragraph* 의 글자 *start* 부터 *end_paragraph* 의 글자 *end* 앞까지 칠하고, 문단마다 하나씩 돌려준다.

        한/글은 문단을 넘는 형광펜을 문단마다 시작·끝 한 쌍으로 쓴다(``highlight_two_paragraphs``). 두 문단은 같은 목록
        (본문, 같은 표 칸 …)에 이 차례로 있어야 한다(``paragraph-range-invalid``). 글자가 없는 문단은 건너뛴다.
        """

        from .. import highlight as _highlight
        from .._resolve import resolve_paragraph
        from ...errors import HwpxValueError

        first = resolve_paragraph(self._doc, start_paragraph, caller="doc.text.highlight_span")
        last = resolve_paragraph(self._doc, end_paragraph, caller="doc.text.highlight_span")
        first_element: Any = first.element
        last_element: Any = last.element
        parent = first_element.getparent()
        siblings = [node for node in parent if node.tag == first_element.tag] if parent is not None else []
        if (parent is None or last_element.getparent() is not parent
                or siblings.index(first_element) > siblings.index(last_element)):
            raise HwpxValueError(
                "the two paragraphs are not in one paragraph list in this order",
                code="paragraph-range-invalid",
                suggestion="Pass two paragraphs of the body (or of one cell), the first one first.",
            )
        chosen = siblings[siblings.index(first.element):siblings.index(last.element) + 1]
        paragraphs = [first if node is first.element else last if node is last.element
                      else type(first)(node, first.section) for node in chosen]
        from ...oxml.text_ranges import _check_offset, check_highlight_range

        _check_offset("start", start, 0, len(first.text))
        _check_offset("end", end, start + 1 if len(paragraphs) == 1 else 0, len(last.text))
        spans = []
        for index, paragraph in enumerate(paragraphs):
            low = start if index == 0 else 0
            high = end if index == len(paragraphs) - 1 else len(paragraph.text)
            if high > low:
                check_highlight_range(paragraph, low, high)  # every part checked before any is written
                spans.append((paragraph, low, high))
        return tuple(_highlight.add_highlight(self._doc, paragraph, color=color, start=low, end=high)
                     for paragraph, low, high in spans)

    @property
    def highlights(self) -> tuple["Highlight", ...]:
        """문서의 모든 형광펜 구간을 문서 순서로 돌려준다(:meth:`highlight` 가 넣는 것). 본문만이 아니라
        표 칸·글상자·캡션·머리말·꼬리말·각주·메모·바탕쪽의 문단도 본다(:meth:`iter_paragraphs` 의 문단)."""

        from .. import highlight as _highlight

        return _highlight.list_highlights(self._doc)
