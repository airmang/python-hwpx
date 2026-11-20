# SPDX-License-Identifier: Apache-2.0
"""6.x 공개 이름이 7.0에서 바뀌거나 없어졌을 때 새 자리를 알려 주는 안내 — 표 하나.

7.0은 공개 이름을 규칙대로 맞추고 얼린다. 6.x에 나간 이름을 바꾸거나 지우면 파이썬의
밋밋한 ``AttributeError``/``TypeError`` 대신 새 자리를 한 줄로 알려 주는 오류가 난다.
그 안내가 모두 이 모듈의 표 셋에서 나온다:

- :data:`NAMES` — 없어진 **이름**. ``{주인: {옛 이름: Removed}}``. 주인은 사용자가 쓰는 꼴이다:
  ``"doc"`` (루트 ``HwpxDocument``), ``"doc.styles"`` (묶음), ``"Paragraph"`` (``hwpx.model``),
  ``"CheckBox"`` (``hwpx.objects`` 값 형식), ``"hwpx.objects"`` (모듈). 부르면
  :class:`~hwpx.errors.HwpxAttributeError` (code ``document-name-removed``), 모듈의 이름이면
  :class:`RemovedNameImportError` (``from 모듈 import 이름`` 이 안내를 그대로 보이게 ImportError).
- :data:`ARGUMENTS` — 없어지거나 바뀐 **인자**. ``{"주인.메서드": Arguments}``. 옛 키워드를 주면
  :class:`~hwpx.errors.HwpxTypeError` (code ``hwpx-argument-removed``). 같은 줄에
  ``keyword_only=`` (위치 인자가 키워드 전용이 됨)와 ``xml_attributes=True`` (``**extra_attrs`` 가
  없어져 모르는 키워드가 옛 XML 속성 인자임)도 적는다.
- :mod:`hwpx.errors` 의 ``REMOVED_ARGUMENTS`` — 6.0이 예고하고 7.0이 지운 ``section_index=``·
  ``style_id_ref=`` (여러 메서드 공통). 이 모듈이 같은 장치로 함께 본다.

**행을 하나 더하면 안내가 난다.** 훅은 이미 걸려 있다:

- 루트: ``HwpxDocument.__getattr__`` (인스턴스)와 그 메타클래스(``HwpxDocument.from_package`` 같은
  클래스 접근), 인자는 ``@rejects_removed_arguments`` (루트 ``add_*``).
- 묶음: ``_Namespace.__getattr__`` 과 ``_Namespace.__init_subclass__`` (모든 공개 메서드).
- 모델·값 형식·모듈: :func:`install` 이 표가 가리키는 클래스·모듈에 훅을 단다(``hwpx.document``
  를 읽을 때 한 번). 클래스 파일은 고치지 않는다. ``hwpx.model``·``hwpx.objects`` 에 없는 클래스는
  :data:`_OWNER_PATHS` 에 한 줄 적는다.
- 모듈 함수의 인자는 정의에 ``@rejects_removed_arguments(caller="hwpx.equation.estimate_equation_size")``.

훅은 이름이 **실제로 없을 때만** 움직인다(``__getattr__`` 은 보통의 찾기가 실패할 때만 불리고,
인자 안내는 옛 이름이 서명에 없을 때만 붙는다). 그래서 이름을 바꾸기 전에 행을 먼저 적어 두어도
아무 일도 하지 않는다. 이 표에는 7.0 이름 정리(spec)의 안내 행이 모두 먼저 적혀 있고, 각 묶음이
이름을 바꾸는 순간 그 행의 안내가 살아난다.

7.0에서 처음 생긴 이름은 안내 없이 바꾼다(표에 적지 않는다). 반환 모양만 바뀐 것(list → tuple 등)과
같은 이름의 메서드 → 속성은 장치가 없다 — 이주 안내서(``docs/migration-7.0.md``)가 맡는다.
최상위 ``from hwpx import X`` 의 안내는 ``hwpx/__init__.py`` 의 표가 맡는다(경계 검사가 그 모양을 고정한다).
"""

from __future__ import annotations

import functools
import inspect
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Literal, TypeVar, cast

from .errors import (
    REMOVED_ARGUMENTS,
    HwpxAttributeError,
    HwpxError,
    HwpxTypeError,
    removed_argument_error,
)

__all__ = [
    "ARGUMENTS",
    "AUTOMATION_INSTALL",
    "Arguments",
    "MIGRATION_GUIDE_6_0_URL",
    "MIGRATION_GUIDE_7_0_URL",
    "Moved",
    "NAMES",
    "REMOVED_IN",
    "Removed",
    "RemovedNameImportError",
    "class_name_error",
    "guard_arguments",
    "install",
    "public_name",
    "removed_name_error",
]

#: 안내 표의 이름이 사라진 major.
REMOVED_IN = "7.0"

#: pip로 설치한 사용자에게는 저장소의 docs/ 폴더가 없으므로 URL을 준다.
MIGRATION_GUIDE_6_0_URL = "https://github.com/airmang/python-hwpx/blob/main/docs/migration-6.0.md"
MIGRATION_GUIDE_7_0_URL = "https://github.com/airmang/python-hwpx/blob/main/docs/migration-7.0.md"

#: 변환·짐작 기능이 옮겨 간 패키지와 그 설치 명령(7.0).
AUTOMATION_DISTRIBUTION = "python-hwpx-automation"
#: ``-U`` and the floor: a bare ``pip install`` beside an installed 7.x companion keeps it and pulls
#: python-hwpx back to 6.x.
AUTOMATION_INSTALL = f'pip install -U "{AUTOMATION_DISTRIBUTION}>=8"'


class RemovedNameImportError(HwpxError, ImportError):
    """A module-level name 7.0 removed (``from hwpx.objects import PictureRef``).

    An :class:`ImportError`, so ``from module import name`` shows the message as it is —
    Python replaces an ``AttributeError`` there with a bare "cannot import name". The
    ``code`` is ``document-name-removed``, as for the other removed names.
    """

    default_code = "document-name-removed"


# --------------------------------------------------------------------------
# 행의 꼴


@dataclass(frozen=True, slots=True)
class Moved:
    """python-hwpx-automation으로 옮긴 이름의 새 자리(문서를 첫 인자로 받는 함수)."""

    module: str
    function: str
    #: 한 줄 예(``to_markdown(doc)``).
    example: str

    @property
    def replacement(self) -> str:
        """그대로 붙여 쓸 수 있는 한 줄: ``from 모듈 import 함수; 예``."""

        return f"from {self.module} import {self.function}; {self.example}"


@dataclass(frozen=True, slots=True)
class Removed:
    """없어진 이름 하나: 어디로 갔고(replacement), 어떻게 쓰나(example)."""

    #: 새 자리(점 경로와 호출 모양, ``doc.page.set_header(text=...)``). 오류의 ``context["replacement"]``.
    replacement: str
    #: 한 문장 안내(7.0 행은 spec 의 hint 그대로). 비면 replacement·example 로 문장을 만든다.
    hint: str = ""
    #: 한 줄 예.
    example: str = ""
    kind: Literal["method", "property"] = "method"
    #: 반환 형식도 바뀌었으면 한 줄 설명(옮길 때 결과를 쓰는 곳을 본다).
    returns: str = ""
    #: 새 자리마저 python-hwpx-automation 으로 옮긴 이름(code ``document-name-moved``).
    moved: Moved | None = None
    #: 전체 대응표.
    guide: str = MIGRATION_GUIDE_7_0_URL

    @property
    def moving(self) -> bool:
        """새 자리가 python-hwpx-automation 에 있다."""

        return self.moved is not None


@dataclass(frozen=True, slots=True)
class Arguments:
    """한 메서드의 7.0 인자 안내."""

    #: 한 문장 안내(spec 의 hint 그대로).
    hint: str
    #: 옛 키워드 → 새 키워드(``None``: 대신할 키워드 없이 없어짐).
    renamed: Mapping[str, str | None] = field(default_factory=dict)
    #: 6.x 에 위치로 받던 인자가 7.0에서 키워드 전용이 된 것(위치 순서대로).
    keyword_only: tuple[str, ...] = ()
    #: ``**extra_attrs`` 가 없어져, 서명에 없는 키워드는 옛 XML 속성 인자다(D8).
    xml_attributes: bool = False


def _m(replacement: str, example: str, returns: str = "") -> Removed:
    """6.0이 묶음으로 옮긴 루트 메서드(대응표 migration-6.0)."""

    return Removed(replacement, example=example, returns=returns, guide=MIGRATION_GUIDE_6_0_URL)


def _p(replacement: str, returns: str = "") -> Removed:
    """6.0이 묶음으로 옮긴 루트 속성(대응표 migration-6.0)."""

    return Removed(replacement, example=replacement, kind="property", returns=returns, guide=MIGRATION_GUIDE_6_0_URL)


def _moved(moved: Moved) -> Removed:
    """새 자리마저 7.0에서 python-hwpx-automation 으로 옮긴 루트 이름."""

    return Removed(moved.replacement, example=moved.example, moved=moved, guide=MIGRATION_GUIDE_7_0_URL)


def _gone(replacement: str, hint: str, *, example: str = "", kind: Literal["method", "property"] = "method") -> Removed:
    """7.0에서 바뀌거나 없어진 이름: 새 자리와 spec 의 hint 한 문장."""

    return Removed(replacement, hint=hint, example=example, kind=kind)


def _args(
    hint: str,
    *,
    keyword_only: tuple[str, ...] = (),
    xml_attributes: bool = False,
    **renamed: str | None,
) -> Arguments:
    """``_args(hint, 옛=새, 없어진=None)`` — 한 메서드의 인자 안내 한 줄."""

    return Arguments(hint, dict(renamed), keyword_only, xml_attributes)


_INSERT_BLANK_HINT = (
    "{call}() 는 7.0에서 한/글처럼 빈 칸을 넣는 것이 기본이다: blank=True 는 지우고, "
    "blank=False(기준 칸의 글·개체까지 복사)는 copy_content=True 로 쓴다"
)

_MARKDOWN = "hwpx_automation.markdown"
_FORMS = "hwpx_automation.forms"


# --------------------------------------------------------------------------
# 표 ① 없어진 이름 — {주인: {옛 이름: Removed}}
#
# 묶음마다 자기 주인의 칸에만 줄을 더한다(병합이 부딪히지 않게 주인을 묶음별로 모았다).
# 7.0 이름 정리의 안내 행은 spec(out/name7/spec.json)의 hint 로 미리 적혀 있다.

NAMES: dict[str, dict[str, Removed]] = {
    # == 루트 HwpxDocument (WP1) ==========================================
    #
    # 6.0이 묶음으로 옮기고 7.0이 지운 79개(#723). 새 자리는 7.0 이름이다.
    "doc": {
        # -- doc.styles -------------------------------------------------
        "border_fill": _m("doc.styles.border_fill(...)", 'doc.styles.border_fill("1")', "GenericElement → BorderFillInfo"),
        "border_fills": _p("doc.styles.border_fills", "값 GenericElement → BorderFillInfo"),
        "bullet": _m("doc.styles.bullet(...)", 'doc.styles.bullet("1")'),
        "bullets": _p("doc.styles.bullets"),
        "char_properties": _p("doc.styles.char_properties"),
        "char_property": _m("doc.styles.char_property(...)", 'doc.styles.char_property("0")'),
        "ensure_border_fill": _m(
            "doc.styles.ensure_border_fill(...)", 'doc.styles.ensure_border_fill(fill_color="#FFFF00", border_width_mm=0.12)'
        ),
        "ensure_numbering": _m("doc.styles.ensure_numbering(...)", 'doc.styles.ensure_numbering(kind="bullet")', "list → tuple"),
        "ensure_run_style": _m("doc.styles.ensure_run(...)", 'doc.styles.ensure_run(bold=True, base_char_pr_id_ref="0")'),
        "memo_shape": _m("doc.styles.memo_shape(...)", 'doc.styles.memo_shape("0")'),
        "memo_shapes": _p("doc.styles.memo_shapes"),
        "paragraph_properties": _p("doc.styles.paragraph_properties"),
        "paragraph_property": _m("doc.styles.paragraph_property(...)", 'doc.styles.paragraph_property("0")'),
        "set_list_format": _m(
            "doc.styles.apply_list_format(...)", 'doc.styles.apply_list_format(paragraph=0, kind="number")',
            "dict → ListFormatResult",
        ),
        "set_paragraph_format": _m(
            "doc.styles.apply_paragraph_format(...)", 'doc.styles.apply_paragraph_format(paragraph=0, alignment="CENTER")',
            "dict → ParagraphFormatResult",
        ),
        "style": _m("doc.styles.get(...)", 'doc.styles.get("바탕글")'),
        # -- doc.page ---------------------------------------------------
        "remove_footer": _m("doc.page.remove_footer(...)", "doc.page.remove_footer(section=0)"),
        "remove_header": _m("doc.page.remove_header(...)", "doc.page.remove_header(section=0)"),
        "set_columns": _m("doc.page.set_columns(...)", 'doc.page.set_columns(2, separator_type="SOLID", separator_width_mm=0.12)'),
        "set_footer_content": _m("doc.page.set_footer(content=...)", 'doc.page.set_footer(content=[{"text": "꼬리말"}])'),
        "set_footer_text": _m("doc.page.set_footer(text=...)", 'doc.page.set_footer(text="꼬리말")'),
        "set_header_content": _m("doc.page.set_header(content=...)", 'doc.page.set_header(content=[{"text": "머리말"}])'),
        "set_header_footer": _m(
            "doc.page.set_header(...) / doc.page.set_footer(...)", 'doc.page.set_header(text="머리말")'
        ),
        "set_header_text": _m("doc.page.set_header(text=...)", 'doc.page.set_header(text="머리말")'),
        "set_page_margins": _m("doc.page.set_margins(...)", "doc.page.set_margins(left=5669, right=5669)"),
        "set_page_number": _m(
            "doc.page.set_page_number(...)", 'doc.page.set_page_number(position="BOTTOM_CENTER", alignment="CENTER")'
        ),
        "set_page_setup": _m("doc.page.setup(...)", 'doc.page.setup(paper_size="A4")', "dict → PageSetup"),
        "set_page_size": _m("doc.page.set_size(...)", 'doc.page.set_size(orientation="LANDSCAPE")'),
        # -- doc.text (Markdown·HTML 은 7.0에서 python-hwpx-automation 으로) -----
        "export_html": _moved(Moved(_MARKDOWN, "to_html", "to_html(doc)")),
        "export_markdown": _moved(Moved(_MARKDOWN, "to_markdown", "to_markdown(doc)")),
        "export_rich_markdown": _moved(Moved(_MARKDOWN, "to_markdown", "to_markdown(doc, rich=True)")),
        "export_text": _m("doc.text.plain(...)", "doc.text.plain()"),
        "find_runs_by_style": _m("doc.text.find_runs(...)", 'doc.text.find_runs(text_color="#FF0000")', "list → tuple"),
        "iter_runs": _m("doc.text.iter_runs()", "for run in doc.text.iter_runs(): ..."),
        "replace_text_in_runs": _m("doc.text.replace(...)", 'doc.text.replace("옛 글", "새 글")'),
        # -- doc.parts --------------------------------------------------
        "headers": _p("doc.parts.headers", "list → tuple"),
        "histories": _p("doc.parts.histories", "list → tuple"),
        "master_pages": _p("doc.parts.master_pages", "list → tuple"),
        "version": _p("doc.parts.version"),
        # -- doc.tables (이름표 찾기는 7.0에서 python-hwpx-automation 으로, 표 지도는 남는다) --
        "fill_by_path": _moved(Moved(_FORMS, "fill_by_path", 'fill_by_path(doc, {"성명 > right": "홍길동"})')),
        "find_cell_by_label": _moved(Moved(_FORMS, "find_cell_by_label", 'find_cell_by_label(doc, "성명")')),
        "get_table_map": _m("doc.tables.map()", "doc.tables.map()"),
        "merge_table_cells": _m("doc.tables.merge_cells(...)", 'doc.tables.merge_cells(table, "A1:B1")'),
        # -- doc.fields -------------------------------------------------
        "add_check_box": _m("doc.fields.add_check_box(...)", 'doc.fields.add_check_box("동의")', "dict → CheckBox"),
        "add_form_field": _m("doc.fields.add(...)", 'doc.fields.add("성명")', "dict → FormField"),
        "fill_form_field": _m("doc.fields.fill(...)", 'doc.fields.fill("홍길동", index=0)', "dict → FieldFillResult"),
        "list_check_boxes": _m("doc.fields.check_boxes", "doc.fields.check_boxes", "list[dict] → tuple[CheckBox, ...] (속성)"),
        "list_form_fields": _m("doc.fields.all", "doc.fields.all", "list[dict] → tuple[FormField, ...] (속성)"),
        "set_check_box": _m("doc.fields.set_check_box(...)", 'doc.fields.set_check_box(True, name="동의")', "dict → CheckBox"),
        # -- doc.shapes -------------------------------------------------
        "add_chart": _m("doc.shapes.add_chart(...)", "doc.shapes.add_chart(chart_xml, width=14400, height=7200)"),
        "add_control": _m("doc.shapes.add_control(...)", "doc.shapes.add_control()"),
        "add_ellipse": _m("doc.shapes.add_ellipse(...)", "doc.shapes.add_ellipse(14400, 7200, line_width_mm=0.12)"),
        "add_equation": _m("doc.shapes.add_equation(...)", 'doc.shapes.add_equation("{a} over {b}", font_size=11.0)'),
        "add_line": _m("doc.shapes.add_line(...)", "doc.shapes.add_line(0, 0, 14400, 0, line_width_mm=0.12)"),
        "add_rectangle": _m("doc.shapes.add_rectangle(...)", "doc.shapes.add_rectangle(14400, 7200, line_width_mm=0.12)"),
        "add_shape": _m("doc.shapes.add_raw(...)", 'doc.shapes.add_raw("rect")'),
        # -- doc.media --------------------------------------------------
        "add_image": _m("doc.media.add_image(...)", 'doc.media.add_image(data, "png")', "str → BinaryItem"),
        "list_images": _m("doc.media.images", "doc.media.images", "list[dict] → tuple[BinaryItem, ...] (속성)"),
        "picture_references": _m("doc.media.pictures", "doc.media.pictures", "list[dict] → tuple[Picture, ...] (속성)"),
        "remove_image": _m("doc.media.remove_image(...)", 'doc.media.remove_image("BIN0001")'),
        "replace_picture": _m(
            "doc.media.replace_picture(...)", 'doc.media.replace_picture(data, "png", index=0)', "dict → PictureReplacement"
        ),
        # -- doc.notes --------------------------------------------------
        "add_endnote": _m("doc.notes.add_endnote(...)", 'doc.notes.add_endnote("미주", paragraph=paragraph)'),
        "add_footnote": _m("doc.notes.add_footnote(...)", 'doc.notes.add_footnote("각주", paragraph=paragraph)'),
        "add_memo": _m("doc.notes.add_memo(...)", 'doc.notes.add_memo("메모")'),
        "add_memo_with_anchor": _m(
            "doc.notes.add_memo(paragraph=...)", 'doc.notes.add_memo("메모", paragraph=paragraph)', "3-튜플 → Memo"
        ),
        "attach_memo_field": _m("doc.notes.attach(...)", "doc.notes.attach(paragraph, memo)", "str → Memo"),
        "memos": _p("doc.notes.memos", "list → tuple"),
        "remove_memo": _m("doc.notes.remove_memo(...)", "doc.notes.remove_memo(memo)"),
        # -- doc.refs ---------------------------------------------------
        "add_bookmark": _m("doc.refs.add_bookmark(...)", 'doc.refs.add_bookmark("책갈피", paragraph=paragraph)', "→ Bookmark"),
        "add_hyperlink": _m("doc.refs.add_hyperlink(...)", 'doc.refs.add_hyperlink("https://example.com", "누리집")', "→ Hyperlink"),
        # -- doc.tracking -----------------------------------------------
        "add_track_change": _m(
            "doc.tracking.add_change(...)", 'doc.tracking.add_change("Insert", author="홍길동")', "int → TrackedChange"
        ),
        "add_tracked_delete": _m("doc.tracking.delete(...)", 'doc.tracking.delete(paragraph, match="옛 글")', "int → TrackedChange"),
        "add_tracked_insert": _m("doc.tracking.insert(...)", 'doc.tracking.insert(paragraph, "새 글")', "int → TrackedChange"),
        "add_tracked_replace": _m(
            "doc.tracking.replace(...)", 'doc.tracking.replace(paragraph, "옛 글", "새 글")', "tuple[int, int] → TrackedReplacement"
        ),
        "track_change": _m("doc.tracking.change(...)", 'doc.tracking.change("1")', "TrackChange → TrackedChange"),
        "track_change_author": _m("doc.tracking.author(...)", 'doc.tracking.author("1")'),
        "track_change_authors": _p("doc.tracking.authors"),
        "track_changes": _p("doc.tracking.changes", "dict → tuple[TrackedChange, ...]"),
        # -- 강등 --------------------------------------------------------
        "remove_paragraph": _m("paragraph.remove()", "doc.paragraphs[3].remove()"),
        # -- 7.0: 저장 동사 넷을 doc.save 하나로(N1, D4) ----------------------
        "save_to_path": _gone(
            "doc.save(path)",
            "doc.save_to_path(path)는 7.0에서 doc.save(path)로 합쳤다. 늘 MutationReport를 돌려준다(저장한 경로는 report.path).",
            example='doc.save("out.hwpx")',
        ),
        "save_to_stream": _gone(
            "doc.save(stream)",
            "doc.save_to_stream(stream)는 7.0에서 doc.save(stream)로 합쳤다. 넘긴 스트림을 그대로 쓰면 된다(반환은 MutationReport).",
            example="doc.save(buffer)",
        ),
        "save_report": _gone(
            "doc.save(target, quality=...)",
            "doc.save_report(target, quality=...)는 7.0에서 doc.save(target, quality=...)로 합쳤다. 품질 보고는 "
            "report.quality, 게이트 실패는 SaveError(quality-gate-failed)의 .report. before/edit_mask/ledger는 "
            "SavePipeline().run(...)으로.",
            example='doc.save("out.hwpx", quality=QualityPolicy.strict()).quality',
        ),
        "from_package": _gone(
            "HwpxDocument.open(package)",
            "HwpxDocument.from_package(package)는 7.0에서 없어졌다: HwpxDocument.open(package)",
            example="HwpxDocument.open(package)",
        ),
    },
    # == 묶음 (WP2) ========================================================
    "doc.styles": {
        "border_fill_info": _gone(
            "doc.styles.border_fill(id)",
            "doc.styles.border_fill_info(id)는 7.0에서 doc.styles.border_fill(id)로 합쳤다(같은 BorderFillInfo)",
        ),
    },
    "doc.page": {
        "hide_page_elements": _gone(
            "doc.page.add_page_hiding(...)",
            "doc.page.hide_page_elements(p, ...)는 7.0에서 doc.page.add_page_hiding(p, ...)이고 PageHiding을 돌려준다",
        ),
        "restart_page_number": _gone(
            "doc.page.add_number_restart(...)",
            "doc.page.restart_page_number(p, ...)는 7.0에서 doc.page.add_number_restart(p, ...)이고 NumberRestart를 돌려준다",
        ),
    },
    "doc.text": {
        "blocks": _gone(
            "doc.text.iter_blocks()",
            "doc.text.blocks()는 7.0에서 doc.text.iter_blocks()이다(문서 전체를 늦게 훑는 것은 iter_)",
        ),
        "runs": _gone(
            "doc.text.iter_runs()",
            "doc.text.runs()는 7.0에서 doc.text.iter_runs()이다(paragraph.runs tuple과 겹치지 않게)",
        ),
        # 7.0에서 python-hwpx-automation 으로 옮긴 메서드(#726).
        "markdown": _moved(Moved(_MARKDOWN, "to_markdown", "to_markdown(doc)")),
        "html": _moved(Moved(_MARKDOWN, "to_html", "to_html(doc)")),
        "append_markdown": _moved(Moved(_MARKDOWN, "append_markdown", 'append_markdown(doc, "# 제목")')),
    },
    "doc.tables": {
        "find_cell_by_label": _moved(Moved(_FORMS, "find_cell_by_label", 'find_cell_by_label(doc, "성명")')),
        "form_slots": _moved(Moved(_FORMS, "form_slots", "form_slots(doc)")),
        "fill_by_path": _moved(Moved(_FORMS, "fill_by_path", 'fill_by_path(doc, {"성명 > right": "홍길동"})')),
    },
    "doc.fields": {
        "choices": _moved(Moved(_FORMS, "form_choices", "form_choices(doc)")),
        "choose": _moved(Moved(_FORMS, "choose", 'choose(doc, {"참석 여부": "예"})')),
    },
    # spec 밖(WP2): 7.0의 읽기(doc.shapes.rubies → Ruby)와 같은 이름·같은 값으로(N8, N3).
    "doc.shapes": {
        "add_dutmal": _gone(
            "doc.shapes.add_ruby(...)",
            "doc.shapes.add_dutmal(main_text, sub_text, pos_type=, align=, sz_ratio=)는 7.0에서 "
            "doc.shapes.add_ruby(text, ruby_text, position=, alignment=, size_ratio=)이고 Ruby를 돌려준다",
            example='doc.shapes.add_ruby("본말", "덧말", position="TOP")',
        ),
    },
    "doc.media": {
        "picture_references": _gone(
            "doc.media.pictures",
            "doc.media.picture_references()는 7.0에서 없어졌다: doc.media.pictures (Picture: item_id·width·height, "
            "몇 번째는 tuple 순서)",
            kind="property",
        ),
    },
    "doc.parts": {
        "set_compatible_document_target_program": _gone(
            "doc.parts.set_document_options(target_program=...)",
            "doc.parts.set_compatible_document_target_program(...)는 7.0에서 doc.parts.set_document_options("
            "target_program=)로 합쳤다(읽기는 doc.parts.document_options)",
        ),
        "set_doc_option_link_info": _gone(
            "doc.parts.set_document_options(link_path=...)",
            "doc.parts.set_doc_option_link_info(...)는 7.0에서 doc.parts.set_document_options(link_path=, page_inherit=, "
            "footnote_inherit=)로 합쳤다(읽기는 doc.parts.document_options)",
        ),
        "set_layout_compatibility_flags": _gone(
            "doc.parts.set_document_options(layout_compatibility=...)",
            "doc.parts.set_layout_compatibility_flags(...)는 7.0에서 doc.parts.set_document_options("
            "layout_compatibility=)로 합쳤다(읽기는 doc.parts.document_options)",
        ),
        "set_license_mark": _gone(
            "doc.parts.set_document_options(license_type=...)",
            "doc.parts.set_license_mark(...)는 7.0에서 doc.parts.set_document_options(license_type=, license_flag=, "
            "license_lang=)로 합쳤다(읽기는 doc.parts.document_options)",
        ),
    },
    # == 모델: 문단·런·서식·개체 (WP3) =======================================
    "Paragraph": {
        "add_new_num": _gone(
            "Paragraph.add_number_restart(...)",
            "paragraph.add_new_num(...)은 7.0에서 add_number_restart(...)이고 NumberRestart를 돌려준다",
        ),
        # spec 은 지움(N10, 안내 문구 없음): 변경 추적은 doc.tracking 한 곳에서.
        "add_tracked_insert": _gone(
            "doc.tracking.insert(paragraph, text)",
            "paragraph.add_tracked_insert(...)는 7.0에서 없어졌다: doc.tracking.insert(paragraph, text)"
            "(변경 기록을 만들고 TrackedChange를 돌려준다)",
        ),
        "add_tracked_delete": _gone(
            "doc.tracking.delete(paragraph, match=...)",
            "paragraph.add_tracked_delete(...)는 7.0에서 없어졌다: doc.tracking.delete(paragraph, match=...)"
            "(변경 기록을 만들고 TrackedChange를 돌려준다)",
        ),
    },
    "InlineObject": {
        "get_attribute": _gone(
            "InlineObject.attributes.get(name)",
            "get_attribute(name)는 7.0에서 없어졌다: obj.attributes.get(name)",
        ),
    },
    "Shape": {
        "get_attribute": _gone(
            "Shape.attributes.get(name)",
            "get_attribute(name)는 7.0에서 없어졌다: obj.attributes.get(name)",
        ),
    },
    # D15: hwpx.objects 로 다시 내보내는 형식(구현 파일은 WP3).
    "RunStyle": {
        "is_emboss": _gone("RunStyle.emboss", "RunStyle.is_emboss()는 7.0에서 속성 emboss이다", kind="property"),
        "is_engrave": _gone("RunStyle.engrave", "RunStyle.is_engrave()는 7.0에서 속성 engrave이다", kind="property"),
        "is_subscript": _gone(
            "RunStyle.subscript", "RunStyle.is_subscript()는 7.0에서 속성 subscript이다(run.subscript와 같은 이름)",
            kind="property",
        ),
        "is_superscript": _gone(
            "RunStyle.superscript", "RunStyle.is_superscript()는 7.0에서 속성 superscript이다", kind="property"
        ),
        "text_color": _gone("RunStyle.color", "RunStyle.text_color()는 7.0에서 없어졌다: .color", kind="property"),
    },
    "Font": {
        "binary_item_id_ref": _gone("Font.item_id", "Font.binary_item_id_ref는 7.0에서 item_id이다", kind="property"),
    },
    # spec 밖(WP3): Font.substitution 의 형식도 같은 이름으로(N7).
    "FontSubstitution": {
        "binary_item_id_ref": _gone(
            "FontSubstitution.item_id", "FontSubstitution.binary_item_id_ref는 7.0에서 item_id이다(Font.item_id와 같게)",
            kind="property",
        ),
    },
    "ParagraphProperty": {
        "align": _gone("ParagraphProperty.alignment", "ParagraphProperty.align은 7.0에서 alignment이다", kind="property"),
    },
    "Caption": {
        "full_sz": _gone("Caption.full_size", "Caption.full_sz는 7.0에서 Caption.full_size이다", kind="property"),
    },
    # == 모델: 표·구역·메모·부품 (WP4) =======================================
    "HeaderFooter": {
        "apply_page_type": _gone(
            "HeaderFooter.page_type",
            "HeaderFooter.apply_page_type은 7.0에서 page_type(읽고 쓰기)이다",
        ),
    },
    "SectionProperties": {
        "get_footer": _gone("SectionProperties.footer(...)", "SectionProperties.get_footer(...)는 7.0에서 footer(...)이다"),
        "get_header": _gone("SectionProperties.header(...)", "SectionProperties.get_header(...)는 7.0에서 header(...)이다"),
        "set_start_numbering": _gone(
            "SectionProperties.set_start_numbers(...)",
            "SectionProperties.set_start_numbering(...)은 7.0에서 set_start_numbers(...)이다",
        ),
        "start_numbering": _gone(
            "SectionProperties.start_numbers",
            "SectionProperties.start_numbering은 7.0에서 start_numbers(StartNumbers, doc.page.start_numbers()와 같은 값)이다",
            kind="property",
        ),
    },
    "Table": {
        "get_cell_map": _gone("Table.cell_map", "table.get_cell_map()은 7.0에서 속성 table.cell_map(tuple의 tuple)이다"),
    },
    # 메모 모양은 구역 단위다: 한/글은 구역의 memoShapeIDRef 에 두고 MEMO 누름틀에는 늘 65535를 쓴다.
    "Memo": {
        "memo_shape_id_ref": _gone(
            "doc.sections[i].properties.memo_shape_id_ref",
            "memo.memo_shape_id_ref는 7.0에서 없어졌다: 메모 모양은 메모마다가 아니라 구역마다다(한/글은 구역의 "
            "memoShapeIDRef에 두고 누름틀에는 늘 65535를 쓴다). 읽기는 doc.sections[i].properties.memo_shape_id_ref, "
            "쓰기는 doc.notes.set_memo_shape(shape_id, section=i). 6.x 문서에 적힌 값은 그대로 읽힌다: "
            "누름틀 메모는 memo.attributes['MemoShapeIDRef'], hp:memogroup 메모는 memo.attributes['memoShapeIDRef']",
            kind="property",
        ),
    },
    # == 값 형식 (WP5b) ====================================================
    "CheckBox": {
        "section_index": _gone(
            "CheckBox.section",
            "CheckBox.section_index(번호)는 7.0에서 section(Section 객체)이다. 번호가 필요하면 doc.sections.index(cb.section)",
            kind="property",
        ),
    },
    # spec 밖(WP5b): 글머리표 머리(Bullet.para_head)의 정렬도 alignment(Alignment)로(N9, D11).
    "BulletParaHead": {
        "align": _gone(
            "BulletParaHead.alignment",
            "BulletParaHead.align(문자열)은 7.0에서 alignment(Alignment)이다(ParagraphProperty.alignment와 같은 이름)",
            kind="property",
        ),
    },
    "hwpx.objects": {
        "PictureRef": _gone(
            "doc.media.pictures",
            "PictureRef는 7.0에서 없어졌다: doc.media.pictures 의 Picture(item_id·width·height)",
            kind="property",
        ),
    },
}


# --------------------------------------------------------------------------
# 표 ② 없어지거나 바뀐 인자 — {"주인.메서드": Arguments}

ARGUMENTS: dict[str, Arguments] = {
    # == 루트 (WP1) ========================================================
    "doc.add_paragraph": _args(
        "doc.add_paragraph(..., pageBreak='1') 같은 XML 속성 인자와 run_attributes=는 7.0에서 없어졌다: "
        "p = doc.add_paragraph(...); p.page_break = True",
        run_attributes=None,
        xml_attributes=True,
    ),
    "doc.add_heading": _args(
        "doc.add_heading(..., <XML 속성>=)은 7.0에서 없어졌다: 돌려받은 문단의 속성으로",
        xml_attributes=True,
    ),
    "doc.add_table": _args(
        "doc.add_table(..., run_attributes=, <XML 속성>=)은 7.0에서 없어졌다: 돌려받은 표·문단의 속성으로",
        run_attributes=None,
        xml_attributes=True,
    ),
    "doc.add_picture": _args(
        "doc.add_picture(line_width=33, align=...)는 7.0에서 line_width_mm=0.12, alignment=... 로 바뀌었다"
        "(run_attributes=·XML 속성 인자는 없어짐)",
        line_width="line_width_mm",
        align="alignment",
        run_attributes=None,
        xml_attributes=True,
    ),
    # == 묶음 (WP2) ========================================================
    "doc.styles.apply_list_format": _args(
        "doc.styles.apply_list_format(paragraph_index=, paragraph_indexes=)는 7.0에서 paragraph=, paragraphs=(번호·문단 객체)로 바뀌었다",
        paragraph_index="paragraph",
        paragraph_indexes="paragraphs",
    ),
    "doc.styles.apply_paragraph_format": _args(
        "doc.styles.apply_paragraph_format: paragraph_index= → paragraph=, paragraph_indexes= → paragraphs=(번호·문단), "
        "border_width='0.12 mm' → border_width_mm=0.12, line_spacing_percent= → line_spacing=",
        paragraph_index="paragraph",
        paragraph_indexes="paragraphs",
        border_width="border_width_mm",
        line_spacing_percent="line_spacing",
    ),
    "doc.styles.ensure_border_fill": _args(
        "doc.styles.ensure_border_fill(border_width='0.7 mm')는 7.0에서 border_width_mm=0.7 이다(한/글 굵기 목록의 값만)",
        border_width="border_width_mm",
    ),
    "doc.styles.ensure_font": _args(
        "doc.styles.ensure_font(binary_item_id_ref=)는 7.0에서 item_id= (대체 글꼴은 subst_item_id=)",
        binary_item_id_ref="item_id",
        subst_binary_item_id_ref="subst_item_id",
    ),
    # 메모 선 굵기: 한/글 2024 로 lineWidth 가 굵기 목록의 순번임을 확인한 뒤(후속 memow) mm 하나로.
    "doc.styles.ensure_memo_shape": _args(
        "doc.styles.ensure_memo_shape(line_width=1)은 7.0에서 line_width_mm=0.12 (mm, 한/글 굵기 목록의 값)이다",
        line_width="line_width_mm",
    ),
    "doc.styles.ensure_paragraph_format": _args(
        "doc.styles.ensure_paragraph_format(base_para_pr_id=, line_spacing_percent=)는 7.0에서 base_para_pr_id_ref=, line_spacing= 이다",
        base_para_pr_id="base_para_pr_id_ref",
        line_spacing_percent="line_spacing",
    ),
    "doc.styles.ensure_run": _args(
        "doc.styles.ensure_run(base_char_pr_id=)는 7.0에서 base_char_pr_id_ref= 이다",
        base_char_pr_id="base_char_pr_id_ref",
    ),
    "doc.fields.fill": _args(
        "doc.fields.fill(field_index=, fit_policy=)는 7.0에서 index=, fit= 이다",
        field_index="index",
        fit_policy="fit",
    ),
    "doc.shapes.add_arc": _args(
        "doc.shapes.add_arc(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_chart": _args("doc.shapes.add_chart(size=(w, h))는 7.0에서 width=w, height=h 이다", size=None),
    "doc.shapes.add_connector": _args(
        "doc.shapes.add_connector(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_curve": _args(
        "doc.shapes.add_curve(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_drop_cap": _args(
        "doc.shapes.add_drop_cap(style='TripleLine')는 7.0에서 kind='TripleLine' 이다(style=은 어디서나 문단 스타일)",
        style="kind",
    ),
    # spec 밖(WP2): 읽기 ComposedCharacter 의 이름(text·frame·inner_size·arrangement)으로(N9, N3).
    "doc.shapes.add_composed_character": _args(
        "doc.shapes.add_composed_character(compose_text, circle_type=, char_sz=, compose_type=)는 7.0에서 "
        "add_composed_character(text, frame=, inner_size=, arrangement=)이고 ComposedCharacter를 돌려준다",
        compose_text="text",
        circle_type="frame",
        char_sz="inner_size",
        compose_type="arrangement",
    ),
    "doc.shapes.add_ellipse": _args(
        "doc.shapes.add_ellipse(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_equation": _args(
        "doc.shapes.add_equation(base_unit=1100, size=(w, h))는 7.0에서 font_size=11.0(pt), width=w, height=h 이다",
        base_unit="font_size",
        size=None,
    ),
    "doc.shapes.add_line": _args(
        "doc.shapes.add_line(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_polygon": _args(
        "doc.shapes.add_polygon(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.shapes.add_rectangle": _args(
        "doc.shapes.add_rectangle(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "doc.media.replace_picture": _args(
        "doc.media.replace_picture(picture_index=, binary_item_id_ref=)는 7.0에서 index=, old_item_id= 이다",
        picture_index="index",
        binary_item_id_ref="old_item_id",
    ),
    "doc.notes.add_endnote": _args(
        "doc.notes.add_endnote(text, p)는 7.0에서 doc.notes.add_endnote(text, paragraph=p) — paragraph는 키워드로",
        keyword_only=("paragraph",),
    ),
    "doc.notes.add_footnote": _args(
        "doc.notes.add_footnote(text, p)는 7.0에서 doc.notes.add_footnote(text, paragraph=p) — paragraph는 키워드로",
        keyword_only=("paragraph",),
    ),
    "doc.notes.add_memo": _args(
        "doc.notes.add_memo(anchor=p)는 7.0에서 paragraph=p 이다(anchor_char_pr_id_ref= → paragraph_char_pr_id_ref=). "
        "memo_shape_id_ref=는 없어졌다: 메모 모양은 구역마다다 — doc.notes.set_memo_shape(shape_id, section=i)",
        anchor="paragraph",
        anchor_char_pr_id_ref="paragraph_char_pr_id_ref",
        memo_shape_id_ref=None,
    ),
    "doc.tracking.add_change": _args(
        "doc.tracking.add_change(author_name=)는 7.0에서 author= 이다", author_name="author"
    ),
    "doc.page.set_columns": _args(
        "doc.page.set_columns(separator_width='0.12 mm')는 7.0에서 separator_width_mm=0.12 이다",
        separator_width="separator_width_mm",
    ),
    "doc.page.set_page_number": _args("doc.page.set_page_number(align=)는 7.0에서 alignment= 이다", align="alignment"),
    "doc.parts.add_master_page": _args(
        "doc.parts.add_master_page(...)는 7.0에서 MasterPage를 돌려준다(id는 .id). paragraphs=[...]는 없어졌다: "
        "mp.add_paragraph('...')",
        paragraphs=None,
    ),
    "doc.parts.set_paragraph_auto_spacing": _args(
        "doc.parts.set_paragraph_auto_spacing(para_pr_id)는 7.0에서 para_pr_id_ref 이다(위치 인자로 부르면 그대로)",
        para_pr_id="para_pr_id_ref",
    ),
    # == 모델: 문단·런·서식·개체 (WP3) =======================================
    "Paragraph.add_chart": _args("paragraph.add_chart(size=(w, h))는 7.0에서 width=, height= 이다", size=None),
    "Paragraph.add_ellipse": _args(
        "paragraph.add_ellipse(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    "Paragraph.add_equation": _args(
        "paragraph.add_equation(base_unit=1100, size=(w, h))는 7.0에서 font_size=11.0(pt), width=, height= 이다",
        base_unit="font_size",
        size=None,
    ),
    "Paragraph.add_line": _args(
        "paragraph.add_line(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    "Paragraph.add_picture": _args(
        "paragraph.add_picture(binary_item_id_ref=, line_width=33, align=)는 7.0에서 item_id=, line_width_mm=0.12, alignment= 이다",
        binary_item_id_ref="item_id",
        line_width="line_width_mm",
        align="alignment",
    ),
    "Paragraph.add_rectangle": _args(
        "paragraph.add_rectangle(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    # spec 밖(WP3): 같은 선 굵기를 받는 나머지 문단 메서드(D2 — 한 이름·한 단위).
    "Paragraph.add_arc": _args(
        "paragraph.add_arc(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    "Paragraph.add_polygon": _args(
        "paragraph.add_polygon(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    "Paragraph.add_curve": _args(
        "paragraph.add_curve(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    "Paragraph.add_connector": _args(
        "paragraph.add_connector(line_width='33')는 7.0에서 line_width_mm=0.12 이다", line_width="line_width_mm"
    ),
    # spec 밖(WP3): Caption.full_size 와 같은 이름(N3).
    "InlineObject.set_caption": _args(
        "obj.set_caption(full_sz=)는 7.0에서 full_size= 이다(caption.full_size와 같은 이름)", full_sz="full_size"
    ),
    "Shape.set_caption": _args(
        "shape.set_caption(full_sz=)는 7.0에서 full_size= 이다(caption.full_size와 같은 이름)", full_sz="full_size"
    ),
    "Table.set_caption": _args(
        "table.set_caption(full_sz=)는 7.0에서 full_size= 이다(caption.full_size와 같은 이름)", full_sz="full_size"
    ),
    "Shape.set_draw_text": _args(
        "Shape.set_draw_text(vert_align=)는 7.0에서 vertical_alignment= 이다(표 칸과 같은 이름)",
        vert_align="vertical_alignment",
    ),
    "Shape.set_position": _args(
        "Shape.set_position(horz_rel_to=, vert_rel_to=, horz_align=, vert_align=)는 7.0에서 horizontal_relative_to=, "
        "vertical_relative_to=, horizontal_alignment=, vertical_alignment= 이다",
        horz_rel_to="horizontal_relative_to",
        vert_rel_to="vertical_relative_to",
        horz_align="horizontal_alignment",
        vert_align="vertical_alignment",
    ),
    "hwpx.equation.estimate_equation_size": _args(
        "estimate_equation_size(script, base_unit=1100)는 7.0에서 font_size=11.0(pt) 이다", base_unit="font_size"
    ),
    # == 모델: 표·구역·메모·부품 (WP4) =======================================
    "Document.add_paragraph": _args(
        "Document.add_paragraph(run_attributes=, inherit_outline=, <XML 속성>=)는 7.0에서 없어졌다",
        run_attributes=None,
        inherit_outline=None,
        xml_attributes=True,
    ),
    "Section.add_paragraph": _args(
        "Section.add_paragraph(run_attributes=, inherit_outline=, <XML 속성>=)는 7.0에서 없어졌다",
        run_attributes=None,
        inherit_outline=None,
        xml_attributes=True,
    ),
    "Section.add_memo": _args(
        "Section.add_memo(memo_shape_id_ref=)는 7.0에서 없어졌다: 메모 모양은 구역마다다 — "
        "section.properties.memo_shape_id_ref = shape_id (doc.notes.set_memo_shape)",
        memo_shape_id_ref=None,
    ),
    "MemoGroup.add_memo": _args(
        "MemoGroup.add_memo(memo_shape_id_ref=)는 7.0에서 없어졌다: 메모 모양은 구역마다다 — "
        "section.properties.memo_shape_id_ref = shape_id (doc.notes.set_memo_shape)",
        memo_shape_id_ref=None,
    ),
    "SectionProperties.add_master_page_reference": _args(
        "SectionProperties.add_master_page_reference(id_ref=)는 7.0에서 master_page_id= 이다(MasterPage 도 받는다)",
        id_ref="master_page_id",
    ),
    "HeaderFooter.add_paragraph": _args(
        "HeaderFooter.add_paragraph(align=)는 7.0에서 없어졌다: p = hf.add_paragraph('글'); p.alignment = 'CENTER'",
        align=None,
    ),
    "Document.ensure_memo_shape": _args(
        "Document.ensure_memo_shape(line_width=1)은 7.0에서 line_width_mm=0.12 (mm, 한/글 굵기 목록의 값)이다",
        line_width="line_width_mm",
    ),
    "HeaderPart.ensure_memo_shape": _args(
        "HeaderPart.ensure_memo_shape(line_width=1)은 7.0에서 line_width_mm=0.12 (mm, 한/글 굵기 목록의 값)이다",
        line_width="line_width_mm",
    ),
    "Table.cell": _args(
        "table.cell(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_border_fill": _args(
        "table.set_cell_border_fill(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_borders": _args(
        "table.set_cell_borders(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_fill_gradient": _args(
        "table.set_cell_fill_gradient(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_fill_image": _args(
        "table.set_cell_fill_image(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_shading": _args(
        "table.set_cell_shading(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.set_cell_text": _args(
        "table.set_cell_text(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    "Table.split_merged_cell": _args(
        "table.split_merged_cell(row_index=, col_index=)는 7.0에서 row=, col= 이다(위치 인자로 부르면 그대로)",
        row_index="row",
        col_index="col",
    ),
    # rows(소유자 결정 2026-11-16): 행·열 넣기의 기본이 한/글처럼 빈 칸이 되면서 뜻이 뒤집힌 blank= 를 긍정형으로.
    "Table.insert_rows": _args(_INSERT_BLANK_HINT.format(call="table.insert_rows"), blank="copy_content"),
    "Table.insert_columns": _args(_INSERT_BLANK_HINT.format(call="table.insert_columns"), blank="copy_content"),
    "doc.tables.insert_rows": _args(_INSERT_BLANK_HINT.format(call="doc.tables.insert_rows"), blank="copy_content"),
    "doc.tables.insert_columns": _args(
        _INSERT_BLANK_HINT.format(call="doc.tables.insert_columns"), blank="copy_content"
    ),
    # == 값 형식 (WP5b) ====================================================
    # spec 은 keep 이었지만 묶음 개체의 구성원도 도형과 같은 선 굵기 이름·단위(D2, N4)와 풀어 쓴 이름(N3)으로.
    "ContainerMember.rect": _args(
        "ContainerMember.rect(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "ContainerMember.ellipse": _args(
        "ContainerMember.ellipse(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "ContainerMember.polygon": _args(
        "ContainerMember.polygon(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "ContainerMember.line": _args(
        "ContainerMember.line(line_width='33')는 7.0에서 line_width_mm=0.12 (mm, float)이다", line_width="line_width_mm"
    ),
    "ContainerMember.text_box": _args(
        "ContainerMember.text_box(line_width='33', vert_align=)는 7.0에서 line_width_mm=0.12, vertical_alignment= 이다"
        "(shape.set_draw_text와 같은 이름)",
        line_width="line_width_mm",
        vert_align="vertical_alignment",
    ),
}


# --------------------------------------------------------------------------
# 주인 이름


#: 구현 클래스 이름 → ``hwpx.model`` 의 공개 이름(오류 문장과 표의 주인이 쓰는 이름).
_PUBLIC_NAMES: dict[str, str] = {
    "HwpxOxmlDocument": "Document",
    "HwpxOxmlSection": "Section",
    "HwpxOxmlParagraph": "Paragraph",
    "HwpxOxmlRun": "Run",
    "HwpxOxmlTable": "Table",
    "HwpxOxmlTableRow": "TableRow",
    "HwpxOxmlTableColumn": "TableColumn",
    "HwpxOxmlTableCell": "TableCell",
    "HwpxOxmlInlineObject": "InlineObject",
    "HwpxOxmlShape": "Shape",
    "HwpxOxmlEquation": "Equation",
    "HwpxOxmlPicture": "Picture",
    "HwpxOxmlMemo": "Memo",
    "HwpxOxmlMemoGroup": "MemoGroup",
    "HwpxOxmlNote": "Note",
    "HwpxOxmlSectionHeaderFooter": "HeaderFooter",
    "HwpxOxmlSectionProperties": "SectionProperties",
    "HwpxOxmlHeader": "HeaderPart",
    "HwpxOxmlHistory": "History",
    "HwpxOxmlMasterPage": "MasterPage",
    "HwpxOxmlVersion": "Version",
    "HwpxTableGridPosition": "GridPosition",
}

#: ``hwpx.model``·``hwpx.objects`` 에 없는 주인 클래스의 자리(``모듈:이름``).
_OWNER_PATHS: dict[str, str] = {
    "RunStyle": "hwpx.oxml.run:RunStyle",
    "Font": "hwpx.oxml.header:Font",
    "FontSubstitution": "hwpx.oxml.header:FontSubstitution",
    "ParagraphProperty": "hwpx.oxml.header:ParagraphProperty",
    "Caption": "hwpx.oxml.objects:Caption",
    "BulletParaHead": "hwpx.oxml.header:BulletParaHead",
}

#: 표의 주인 가운데 훅이 클래스 정의에 직접 있는 것(:func:`install` 이 건너뛴다).
_HOOKED_IN_PLACE = ("doc",)


def public_name(cls: type) -> str:
    """*cls* 를 사용자가 부르는 이름(``HwpxOxmlParagraph`` → ``Paragraph``)."""

    return _PUBLIC_NAMES.get(cls.__name__, cls.__name__)


def _hooked_in_place(owner: str) -> bool:
    return owner in _HOOKED_IN_PLACE or owner.startswith("doc.")


# --------------------------------------------------------------------------
# 이름 안내


def _moved_error(what: str, name: str, moved: Moved, **context: object) -> HwpxAttributeError:
    return HwpxAttributeError(
        f"{what} 는 python-hwpx {REMOVED_IN}에서 {AUTOMATION_DISTRIBUTION}으로 옮겼습니다: "
        f"`{moved.replacement}` — `{AUTOMATION_INSTALL}`",
        code="document-name-moved",
        context={
            "name": name,
            "replacement": moved.replacement,
            "movedIn": REMOVED_IN,
            "movedTo": moved.module,
            "install": AUTOMATION_INSTALL,
            **context,
        },
        suggestion=f"{AUTOMATION_INSTALL} 후 {moved.replacement} — 전체 대응표: {MIGRATION_GUIDE_7_0_URL}",
    )


def removed_name_error(owner: str, name: str) -> HwpxError | None:
    """*owner* 의 *name* 이 7.0에서 없어진 이름이면 새 자리를 알려 주는 오류를, 아니면 ``None``.

    *owner* 는 표의 주인(``"doc"``, ``"doc.styles"``, ``"Paragraph"``, ``"hwpx.objects"``)이다.
    모듈의 이름이면 :class:`RemovedNameImportError`, 그 밖은 :class:`~hwpx.errors.HwpxAttributeError`.
    """

    entry = NAMES.get(owner, {}).get(name)
    if entry is None:
        return None
    root = owner == "doc"
    if root:
        what = f"doc.{name}" + ("(...)" if entry.kind == "method" else "")
    else:
        what = f"{owner}.{name}" + ("(...)" if entry.kind == "method" and owner.startswith("doc.") else "")
    if entry.moved is not None:
        if root:
            return _moved_error(what, name, entry.moved, removedIn=REMOVED_IN, movingToAutomation=True)
        return _moved_error(what, name, entry.moved, namespace=owner)
    if entry.hint:
        message = entry.hint
        if entry.example and entry.example not in message:
            message += f" 예: {entry.example}"
    else:
        message = (
            f"{what} 는 python-hwpx {REMOVED_IN}에서 없어졌습니다. "
            f"{entry.replacement} 를 쓰세요. 예: {entry.example}"
        )
        if entry.returns:
            message += f" (돌려주는 값도 바뀌었습니다: {entry.returns})"
    error_type: type[HwpxError] = RemovedNameImportError if owner.startswith("hwpx.") else HwpxAttributeError
    return error_type(
        message,
        code="document-name-removed",
        context={
            "name": name,
            "owner": owner,
            "replacement": entry.replacement,
            "removedIn": REMOVED_IN,
            "movingToAutomation": False,
        },
        suggestion=f"{entry.example or entry.replacement} — 전체 대응표: {entry.guide}",
    )


def class_name_error(cls: type, name: str) -> AttributeError | None:
    """*cls* 나 그 조상(``Picture`` → ``InlineObject``)의 표에 *name* 이 있으면 그 안내 오류를, 아니면 ``None``."""

    for klass in cls.__mro__:
        owner = public_name(klass)
        if name in NAMES.get(owner, ()):
            return cast(AttributeError, removed_name_error(owner, name))
    return None


def _declared(cls: type, name: str) -> bool:
    return any(name in vars(klass) for klass in cls.__mro__)


def _hint_getattr(self: Any, name: str) -> Any:
    """설치된 ``__getattr__``: 표에 있는 없어진 이름이면 새 자리를, 아니면 보통의 ``AttributeError``."""

    cls = type(self)
    if _declared(cls, name):
        # The name exists and its descriptor (a property, an unset slot) raised AttributeError:
        # let that error show instead of a hint about a name that is still here.
        return object.__getattribute__(self, name)
    error = class_name_error(cls, name)
    if error is None:
        error = AttributeError(f"{cls.__name__!r} object has no attribute {name!r}")
    error.name = name
    error.obj = self
    raise error


def _chained_getattr(previous: Callable[[Any, str], Any]) -> Callable[[Any, str], Any]:
    def __getattr__(self: Any, name: str) -> Any:
        error = None if _declared(type(self), name) else class_name_error(type(self), name)
        if error is not None:
            error.name = name
            error.obj = self
            raise error
        return previous(self, name)

    return __getattr__


# --------------------------------------------------------------------------
# 인자 안내


_Func = TypeVar("_Func", bound=Callable[..., Any])

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


def _renamed_argument_error(caller: str, name: str, new: str | None, rule: Arguments) -> HwpxTypeError:
    if new:
        head = f"{caller}() 의 {name}= 인자는 python-hwpx {REMOVED_IN}에서 {new}= 로 바뀌었습니다."
    else:
        head = f"{caller}() 의 {name}= 인자는 python-hwpx {REMOVED_IN}에서 없어졌습니다."
    return HwpxTypeError(
        f"{head} {rule.hint}",
        code="hwpx-argument-removed",
        context={"caller": caller, "argument": name, "replacement": new, "removedIn": REMOVED_IN},
        suggestion=rule.hint,
    )


def _xml_attribute_error(caller: str, name: str, rule: Arguments) -> HwpxTypeError:
    return HwpxTypeError(
        f"{caller}() 는 {name}= 를 받지 않습니다 — python-hwpx {REMOVED_IN}에서 XML 속성을 키워드로 받던 "
        f"길(**extra_attrs)이 없어졌습니다. {rule.hint}",
        code="hwpx-argument-removed",
        context={"caller": caller, "argument": name, "replacement": None, "removedIn": REMOVED_IN, "xmlAttribute": True},
        suggestion=rule.hint,
    )


def _positional_error(caller: str, names: tuple[str, ...], extra: int, rule: Arguments) -> HwpxTypeError:
    moved = names[:extra] if extra <= len(names) else names
    listed = ", ".join(f"{name}=" for name in moved)
    return HwpxTypeError(
        f"{caller}() 에 위치 인자를 {extra}개 더 주었습니다 — python-hwpx {REMOVED_IN}에서 {listed} 는 "
        f"키워드로만 받습니다. {rule.hint}",
        code="hwpx-argument-removed",
        context={"caller": caller, "argument": moved[0], "replacement": f"{moved[0]}=", "removedIn": REMOVED_IN},
        suggestion=rule.hint,
    )


def guard_arguments(func: _Func, caller: str, *, removed_everywhere: bool = False) -> _Func:
    """*func* 가 7.0에서 없어진 인자를 받으면 새 자리를 알려 주게 감싼다.

    :data:`ARGUMENTS` 의 ``caller`` 줄(옛→새 키워드, 키워드 전용이 된 위치 인자, XML 속성 키워드)과,
    *removed_everywhere* 이면 :data:`hwpx.errors.REMOVED_ARGUMENTS` (``section_index=``·
    ``style_id_ref=``)를 본다. 옛 이름이 아직 서명에 있으면 그 이름은 건드리지 않는다 — 그래서 이름을
    바꾸기 전의 줄은 아무 일도 하지 않고, 감쌀 것이 없으면 *func* 를 그대로 돌려준다.
    ``inspect.signature`` 는 *func* 의 서명을 그대로 읽는다.
    """

    if getattr(func, "__hwpx_guard__", None) == caller:
        return func
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return func
    rule = ARGUMENTS.get(caller)
    kinds = {parameter.kind for parameter in parameters.values()}
    renamed = {old: new for old, new in (rule.renamed.items() if rule else ()) if old not in parameters}
    everywhere = (
        tuple(name for name in REMOVED_ARGUMENTS if name not in parameters) if removed_everywhere else ()
    )
    xml_attributes = bool(rule and rule.xml_attributes and inspect.Parameter.VAR_KEYWORD not in kinds)
    keyword_only: tuple[str, ...] = ()
    if rule and rule.keyword_only and inspect.Parameter.VAR_POSITIONAL not in kinds:
        if all(
            name in parameters and parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
            for name in rule.keyword_only
        ):
            keyword_only = rule.keyword_only
    if not (renamed or everywhere or xml_attributes or keyword_only):
        return func
    assert rule is not None or everywhere
    known = frozenset(parameters)
    capacity = sum(1 for parameter in parameters.values() if parameter.kind in _POSITIONAL)

    @functools.wraps(func)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if kwargs:
            for name in kwargs:
                if name in known:
                    continue
                if name in renamed:
                    raise _renamed_argument_error(caller, name, renamed[name], cast(Arguments, rule))
                if name in everywhere:
                    raise removed_argument_error(name, caller)
                if xml_attributes:
                    raise _xml_attribute_error(caller, name, cast(Arguments, rule))
        if keyword_only and len(args) > capacity:
            raise _positional_error(caller, keyword_only, len(args) - capacity, cast(Arguments, rule))
        return func(*args, **kwargs)

    guarded.__hwpx_guard__ = caller  # type: ignore[attr-defined]
    return cast(_Func, guarded)


def caller_name(func: Callable[..., Any]) -> str:
    """오류 문장에 쓸 *func* 의 이름: ``doc.add_paragraph``, ``Document.add_paragraph``."""

    qualname = func.__qualname__
    owner, _, method = qualname.rpartition(".")
    if not owner:
        return f"{func.__module__}.{qualname}"
    if owner == "HwpxDocument":
        return f"doc.{method}"
    return f"{_PUBLIC_NAMES.get(owner, owner)}.{method}"


# --------------------------------------------------------------------------
# 모델·값 형식·모듈에 훅 달기


def _loaded(module: str) -> ModuleType:
    # install() runs once hwpx.document has loaded the model and value-type modules; it reads
    # them from sys.modules rather than importing anything itself.
    found = sys.modules.get(module)
    if found is None:
        raise AssertionError(f"안내 표의 주인이 사는 모듈 {module!r} 가 아직 읽히지 않았습니다")
    return found


def _resolve_owner(owner: str) -> type | ModuleType:
    if owner.startswith("hwpx."):
        return _loaded(owner)
    path = _OWNER_PATHS.get(owner)
    if path is not None:
        module, _, name = path.partition(":")
        return cast(type, getattr(_loaded(module), name))
    for module in ("hwpx.model", "hwpx.objects"):
        found = getattr(_loaded(module), owner, None)
        if isinstance(found, type):
            return found
    raise AssertionError(f"안내 표의 주인 {owner!r} 를 hwpx.model·hwpx.objects·_OWNER_PATHS 에서 찾지 못했습니다")


def _install_class_hook(cls: type) -> None:
    current = vars(cls).get("__getattr__")
    if getattr(current, "__hwpx_hint__", False):
        return
    previous = inspect.getattr_static(cls, "__getattr__", None)
    if getattr(previous, "__hwpx_hint__", False):
        return  # an ancestor's hook already walks this class's table too
    hook = _hint_getattr if previous is None else _chained_getattr(previous)
    hook.__hwpx_hint__ = True  # type: ignore[attr-defined]
    cls.__getattr__ = hook  # type: ignore[attr-defined]


def _install_module_hook(module: ModuleType) -> None:
    previous = module.__dict__.get("__getattr__")
    if getattr(previous, "__hwpx_hint__", False):
        return
    owner = module.__name__

    def __getattr__(name: str) -> Any:
        error = removed_name_error(owner, name)
        if error is not None:
            raise error
        if previous is not None:
            return previous(name)
        raise AttributeError(f"module {owner!r} has no attribute {name!r}")

    __getattr__.__hwpx_hint__ = True  # type: ignore[attr-defined]
    module.__getattr__ = __getattr__  # type: ignore[method-assign]


_installed = False


def install() -> None:
    """표가 가리키는 모델·값 형식 클래스와 모듈에 안내 훅을 단다(한 번).

    이름 줄이 있는 주인에는 ``__getattr__`` 을(이미 있으면 그 앞에서 표를 먼저 보게), 인자 줄이 있는
    메서드에는 :func:`guard_arguments` 를 단다. 루트(``doc``)와 묶음(``doc.*``)의 훅은 그 클래스에 직접
    있고, 모듈 함수의 인자는 정의의 ``@rejects_removed_arguments`` 가 맡는다. ``hwpx.document`` 를
    읽을 때 불린다 — 그때는 모델 클래스가 모두 만들어져 있다.
    """

    global _installed
    if _installed:
        return
    _installed = True
    for owner, rows in NAMES.items():
        if not rows or _hooked_in_place(owner):
            continue
        target = _resolve_owner(owner)
        if isinstance(target, ModuleType):
            _install_module_hook(target)
        else:
            _install_class_hook(target)
    for caller in ARGUMENTS:
        owner, _, method = caller.rpartition(".")
        if _hooked_in_place(owner) or owner.startswith("hwpx."):
            continue
        cls = _resolve_owner(owner)
        assert isinstance(cls, type)
        function = inspect.getattr_static(cls, method, None)
        # A classmethod (ContainerMember.rect) is guarded inside and wrapped again.
        wrap = type(function) if isinstance(function, (classmethod, staticmethod)) else None
        if wrap is not None:
            function = function.__func__  # type: ignore[union-attr]
        if not inspect.isfunction(function):
            raise AssertionError(f"인자 안내 {caller!r}: {owner} 에 메서드 {method!r} 가 없습니다")
        guarded = guard_arguments(function, caller)
        if guarded is not function:
            setattr(cls, method, wrap(guarded) if wrap is not None else guarded)
