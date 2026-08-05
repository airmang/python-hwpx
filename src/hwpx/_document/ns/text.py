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

from typing import TYPE_CHECKING, Iterator

from ...errors import HwpxValueError
from ._base import _Namespace

if TYPE_CHECKING:
    from ...objects.highlight import Highlight
    from ...oxml import HwpxOxmlParagraph, HwpxOxmlRun

__all__ = ["TextNamespace"]


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

        matches: list["HwpxOxmlRun"] = []
        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None

        for run in self.runs():
            if target_char is not None:
                if (run.char_pr_id_ref or "").strip() != target_char:
                    continue
            style = run.style
            if text_color is not None:
                if style is None or style.text_color() != text_color:
                    continue
            if underline_type is not None:
                if style is None or style.underline_type() != underline_type:
                    continue
            if underline_color is not None:
                if style is None or style.underline_color() != underline_color:
                    continue
            matches.append(run)
        return matches

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
    ) -> int:
        """서식 조건에 맞는 런 안에서 *search* 를 바꾸고 치환 횟수를 돌려준다."""

        if not search:
            raise HwpxValueError(
                "search 는 빈 문자열일 수 없습니다.",
                code="text-search-empty",
                context={"search": search},
                suggestion="바꿀 대상 문자열을 지정하세요.",
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
        return replacements

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
