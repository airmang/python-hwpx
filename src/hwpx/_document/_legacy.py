# SPDX-License-Identifier: Apache-2.0
"""7.0에서 없어진 ``HwpxDocument`` 루트 이름 79개의 안내 표.

6.0은 루트 표면을 102개에서 34개로 줄이고, 옮겨 간 79개 이름을 경고와 함께
남겨 두었다(``DeprecationWarning``, "7.0에서 제거"). 7.0은 그 예고를 실행한다.
이 모듈에는 더 이상 위임 코드가 없다 — **표만 남는다.**

표가 하는 일은 오류 메시지 하나다. 지운 이름을 부르면 파이썬의 밋밋한
``AttributeError: 'HwpxDocument' object has no attribute 'set_header_text'``
대신, 그 이름이 어디로 갔는지 한 줄 예와 함께 알려 준다::

    >>> doc.set_header_text("머리말")
    HwpxAttributeError: doc.set_header_text 는 python-hwpx 7.0에서 없어졌습니다.
    doc.page.set_header(text=...) 를 쓰세요. 예: doc.page.set_header(text="머리말")

오류는 :class:`~hwpx.errors.HwpxAttributeError` (``AttributeError`` 이기도 하다)라서
``hasattr(doc, "set_header_text")`` 는 ``False`` 이고 ``getattr(doc, name, None)`` 도
``None`` 이다. 표의 근거는 6.0의 위임 shim이 기록하던 행선지
(``tests/data/document_legacy_shims.json``, 7.0부터는 이 표에서 다시 만든다)다.

``moving`` 이 참인 6개(``export_html`` …)는 새 자리(``doc.text.markdown`` 등)마저
자동화 패키지(python-hwpx-automation)로 이사할 예정이다. 이사 단계가 그 행의
``replacement``·``example`` 을 고친다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..errors import HwpxAttributeError

__all__ = ["LEGACY_REMOVED_IN", "MIGRATION_GUIDE_URL", "REMOVED_NAMES", "RemovedName", "removed_name_error"]

#: 옛 이름이 사라진 major. ``describe_capabilities()`` 가 이 값을 보고한다.
LEGACY_REMOVED_IN = "7.0"

#: 전수 대응표. pip로 설치한 사용자에게는 저장소의 docs/ 폴더가 없으므로 URL을 준다.
MIGRATION_GUIDE_URL = (
    "https://github.com/airmang/python-hwpx/blob/main/docs/migration-6.0.md"
)


@dataclass(frozen=True, slots=True)
class RemovedName:
    """지운 이름 하나: 무엇이었고(kind), 어디로 갔고(replacement), 어떻게 쓰나(example)."""

    kind: Literal["method", "property"]
    replacement: str
    example: str
    #: 6.0에서 반환 형식도 바뀌었으면 한 줄 설명(옮길 때 결과를 쓰는 곳을 본다).
    returns: str = ""
    #: 새 자리마저 자동화 패키지로 이사할 예정인 이름.
    moving: bool = False


def _m(replacement: str, example: str, returns: str = "", *, moving: bool = False) -> RemovedName:
    return RemovedName("method", replacement, example, returns, moving)


def _p(replacement: str) -> RemovedName:
    return RemovedName("property", replacement, replacement)


REMOVED_NAMES: dict[str, RemovedName] = {
    # -- doc.styles ---------------------------------------------------------
    "border_fill": _m("doc.styles.border_fill(...)", 'doc.styles.border_fill("1")'),
    "border_fills": _p("doc.styles.border_fills"),
    "bullet": _m("doc.styles.bullet(...)", 'doc.styles.bullet("1")'),
    "bullets": _p("doc.styles.bullets"),
    "char_properties": _p("doc.styles.char_properties"),
    "char_property": _m("doc.styles.char_property(...)", 'doc.styles.char_property("0")'),
    "ensure_border_fill": _m("doc.styles.ensure_border_fill(...)", 'doc.styles.ensure_border_fill(fill_color="#FFFF00")'),
    "ensure_numbering": _m("doc.styles.ensure_numbering(...)", 'doc.styles.ensure_numbering(kind="bullet")'),
    "ensure_run_style": _m("doc.styles.ensure_run(...)", "doc.styles.ensure_run(bold=True)"),
    "memo_shape": _m("doc.styles.memo_shape(...)", 'doc.styles.memo_shape("0")'),
    "memo_shapes": _p("doc.styles.memo_shapes"),
    "paragraph_properties": _p("doc.styles.paragraph_properties"),
    "paragraph_property": _m("doc.styles.paragraph_property(...)", 'doc.styles.paragraph_property("0")'),
    "set_list_format": _m(
        "doc.styles.apply_list_format(...)", 'doc.styles.apply_list_format(paragraph_index=0, kind="number")',
        "dict → ListFormatResult",
    ),
    "set_paragraph_format": _m(
        "doc.styles.apply_paragraph_format(...)", 'doc.styles.apply_paragraph_format(paragraph_index=0, alignment="CENTER")',
        "dict → ParagraphFormatResult",
    ),
    "style": _m("doc.styles.get(...)", 'doc.styles.get("바탕글")'),
    # -- doc.page -----------------------------------------------------------
    "remove_footer": _m("doc.page.remove_footer(...)", "doc.page.remove_footer(section=0)"),
    "remove_header": _m("doc.page.remove_header(...)", "doc.page.remove_header(section=0)"),
    "set_columns": _m("doc.page.set_columns(...)", "doc.page.set_columns(2)"),
    "set_footer_content": _m("doc.page.set_footer(content=...)", 'doc.page.set_footer(content=[{"text": "꼬리말"}])'),
    "set_footer_text": _m("doc.page.set_footer(text=...)", 'doc.page.set_footer(text="꼬리말")'),
    "set_header_content": _m("doc.page.set_header(content=...)", 'doc.page.set_header(content=[{"text": "머리말"}])'),
    "set_header_footer": _m(
        "doc.page.set_header(...) / doc.page.set_footer(...)", 'doc.page.set_header(text="머리말")'
    ),
    "set_header_text": _m("doc.page.set_header(text=...)", 'doc.page.set_header(text="머리말")'),
    "set_page_margins": _m("doc.page.set_margins(...)", "doc.page.set_margins(left=5669, right=5669)"),
    "set_page_number": _m("doc.page.set_page_number(...)", 'doc.page.set_page_number(position="BOTTOM_CENTER")'),
    "set_page_setup": _m("doc.page.setup(...)", 'doc.page.setup(paper_size="A4")', "dict → PageSetup"),
    "set_page_size": _m("doc.page.set_size(...)", 'doc.page.set_size(orientation="LANDSCAPE")'),
    # -- doc.text -----------------------------------------------------------
    "export_html": _m("doc.text.html(...)", "doc.text.html()", moving=True),
    "export_markdown": _m("doc.text.markdown(...)", "doc.text.markdown()", moving=True),
    "export_rich_markdown": _m("doc.text.markdown(rich=True)", "doc.text.markdown(rich=True)", moving=True),
    "export_text": _m("doc.text.plain(...)", "doc.text.plain()"),
    "find_runs_by_style": _m("doc.text.find_runs(...)", 'doc.text.find_runs(text_color="#FF0000")'),
    "iter_runs": _m("doc.text.runs()", "for run in doc.text.runs(): ..."),
    "replace_text_in_runs": _m("doc.text.replace(...)", 'doc.text.replace("옛 글", "새 글")'),
    # -- doc.parts ----------------------------------------------------------
    "headers": _p("doc.parts.headers"),
    "histories": _p("doc.parts.histories"),
    "master_pages": _p("doc.parts.master_pages"),
    "version": _p("doc.parts.version"),
    # -- doc.tables ---------------------------------------------------------
    "fill_by_path": _m("doc.tables.fill_by_path(...)", 'doc.tables.fill_by_path({"성명 > right": "홍길동"})', moving=True),
    "find_cell_by_label": _m("doc.tables.find_cell_by_label(...)", 'doc.tables.find_cell_by_label("성명")', moving=True),
    "get_table_map": _m("doc.tables.map()", "doc.tables.map()", moving=True),
    "merge_table_cells": _m("doc.tables.merge_cells(...)", 'doc.tables.merge_cells(table, "A1:B1")'),
    # -- doc.fields ---------------------------------------------------------
    "add_check_box": _m("doc.fields.add_check_box(...)", 'doc.fields.add_check_box("동의")', "dict → CheckBox"),
    "add_form_field": _m("doc.fields.add(...)", 'doc.fields.add("성명")', "dict → FormField"),
    "fill_form_field": _m("doc.fields.fill(...)", 'doc.fields.fill("홍길동", name="성명")', "dict → FieldFillResult"),
    "list_check_boxes": _m("doc.fields.check_boxes", "doc.fields.check_boxes", "list[dict] → tuple[CheckBox, ...] (속성)"),
    "list_form_fields": _m("doc.fields.all", "doc.fields.all", "list[dict] → tuple[FormField, ...] (속성)"),
    "set_check_box": _m("doc.fields.set_check_box(...)", 'doc.fields.set_check_box(True, name="동의")', "dict → CheckBox"),
    # -- doc.shapes ---------------------------------------------------------
    "add_chart": _m("doc.shapes.add_chart(...)", "doc.shapes.add_chart(chart_xml)"),
    "add_control": _m("doc.shapes.add_control(...)", "doc.shapes.add_control()"),
    "add_ellipse": _m("doc.shapes.add_ellipse(...)", "doc.shapes.add_ellipse(14400, 7200)"),
    "add_equation": _m("doc.shapes.add_equation(...)", 'doc.shapes.add_equation("{a} over {b}")'),
    "add_line": _m("doc.shapes.add_line(...)", "doc.shapes.add_line(0, 0, 14400, 0)"),
    "add_rectangle": _m("doc.shapes.add_rectangle(...)", "doc.shapes.add_rectangle(14400, 7200)"),
    "add_shape": _m("doc.shapes.add_raw(...)", 'doc.shapes.add_raw("rect")'),
    # -- doc.media ----------------------------------------------------------
    "add_image": _m("doc.media.add_image(...)", 'doc.media.add_image(data, "png")', "str → BinaryItem"),
    "list_images": _m("doc.media.images", "doc.media.images", "list[dict] → tuple[BinaryItem, ...] (속성)"),
    "picture_references": _m("doc.media.picture_references()", "doc.media.picture_references()", "list[dict] → tuple[PictureRef, ...]"),
    "remove_image": _m("doc.media.remove_image(...)", 'doc.media.remove_image("BIN0001")'),
    "replace_picture": _m("doc.media.replace_picture(...)", 'doc.media.replace_picture(data, "png")', "dict → PictureReplacement"),
    # -- doc.notes ----------------------------------------------------------
    "add_endnote": _m("doc.notes.add_endnote(...)", 'doc.notes.add_endnote("미주", paragraph)'),
    "add_footnote": _m("doc.notes.add_footnote(...)", 'doc.notes.add_footnote("각주", paragraph)'),
    "add_memo": _m("doc.notes.add_memo(...)", 'doc.notes.add_memo("메모")'),
    "add_memo_with_anchor": _m(
        "doc.notes.add_memo(anchor=...)", 'doc.notes.add_memo("메모", anchor=paragraph)', "3-튜플 → Memo"
    ),
    "attach_memo_field": _m("doc.notes.attach(...)", "doc.notes.attach(paragraph, memo)", "str → Memo"),
    "memos": _p("doc.notes.memos"),
    "remove_memo": _m("doc.notes.remove_memo(...)", "doc.notes.remove_memo(memo)"),
    # -- doc.refs -----------------------------------------------------------
    "add_bookmark": _m("doc.refs.add_bookmark(...)", 'doc.refs.add_bookmark("책갈피", paragraph=paragraph)'),
    "add_hyperlink": _m("doc.refs.add_hyperlink(...)", 'doc.refs.add_hyperlink("https://example.com", "누리집")'),
    # -- doc.tracking -------------------------------------------------------
    "add_track_change": _m("doc.tracking.add_change(...)", 'doc.tracking.add_change("Insert")', "int → TrackedChange"),
    "add_tracked_delete": _m("doc.tracking.delete(...)", 'doc.tracking.delete(paragraph, match="옛 글")', "int → TrackedChange"),
    "add_tracked_insert": _m("doc.tracking.insert(...)", 'doc.tracking.insert(paragraph, "새 글")', "int → TrackedChange"),
    "add_tracked_replace": _m(
        "doc.tracking.replace(...)", 'doc.tracking.replace(paragraph, "옛 글", "새 글")', "tuple[int, int] → TrackedReplacement"
    ),
    "track_change": _m("doc.tracking.change(...)", 'doc.tracking.change("1")'),
    "track_change_author": _m("doc.tracking.author(...)", 'doc.tracking.author("1")'),
    "track_change_authors": _p("doc.tracking.authors"),
    "track_changes": _p("doc.tracking.changes"),
    # -- 강등 ----------------------------------------------------------------
    "remove_paragraph": _m("paragraph.remove()", "doc.paragraphs[3].remove()"),
}


def removed_name_error(name: str) -> HwpxAttributeError | None:
    """*name* 이 7.0에서 지운 루트 이름이면 그 자리를 알려 주는 오류를, 아니면 ``None``."""

    entry = REMOVED_NAMES.get(name)
    if entry is None:
        return None
    what = f"doc.{name}" + ("(...)" if entry.kind == "method" else "")
    message = (
        f"{what} 는 python-hwpx {LEGACY_REMOVED_IN}에서 없어졌습니다. "
        f"{entry.replacement} 를 쓰세요. 예: {entry.example}"
    )
    if entry.returns:
        message += f" (돌려주는 값도 바뀌었습니다: {entry.returns})"
    return HwpxAttributeError(
        message,
        code="document-name-removed",
        context={
            "name": name,
            "replacement": entry.replacement,
            "removedIn": LEGACY_REMOVED_IN,
            "movingToAutomation": entry.moving,
        },
        suggestion=f"{entry.example} — 전체 대응표: {MIGRATION_GUIDE_URL}",
    )


class _LegacyFacade:
    """지운 이름의 목록을 클래스 꼴로 한 번 더 보인다(``HwpxDocument`` 는 상속하지 않는다).

    ``tests/test_documentation_code_fences.py`` 가 ``vars(_LegacyFacade)`` 로 "문서가 옛
    이름을 가르치지 않는가"를 검사한다. 그 파일은 7.0 이름 정리 단계 밖이라 이름을
    남겨 둔다. 값은 :data:`REMOVED_NAMES` 의 항목이다 — 부를 수 있는 것은 없다.
    """


for _name, _entry in REMOVED_NAMES.items():
    setattr(_LegacyFacade, _name, _entry)
del _name, _entry
