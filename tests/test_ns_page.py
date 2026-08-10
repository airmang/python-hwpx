# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B2 게이트 — `doc.page`.

5.x 는 쪽 기하 하나로 루트를 12칸 먹었고, 그중 다섯이 머리말/꼬리말 동사였다
(`set_header_text`·`set_header_content`·`set_footer_text`·`set_footer_content`
+ 그 넷의 합집합인 `set_header_footer(kind=...)`).
"""

from __future__ import annotations

import io
import re
import warnings
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError, HwpxValueError

#: `section` 쌍을 받는 `doc.page` 멤버 전수.
PAGE_SECTION_MEMBERS = [
    "setup", "set_size", "set_margins", "set_columns", "set_header", "set_footer",
    "set_page_number", "remove_header", "remove_footer", "size", "margins",
    "grid", "set_grid", "visibility", "set_visibility", "line_numbers", "set_line_numbers",
    "text_direction", "set_text_direction",
]
_ARGS: dict[str, dict] = {
    "set_header": {"text": "머리말"},
    "set_footer": {"text": "꼬리말"},
}


def _part(document: HwpxDocument, name: str = "Contents/section0.xml") -> str:
    """저장된 패키지에서 한 파트를 꺼낸다.

    ``to_bytes()`` 는 ZIP 이라 바이트 비교·문자열 검색이 통하지 않는다(압축과
    아카이브 메타데이터가 섞인다). 계약은 XML 이므로 XML 로 비교한다.
    """

    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read(name).decode("utf-8")


_ID_ATTR = re.compile(r'\b(id|idRef)="(\d+)"')


def _canonical_ids(xml: str) -> str:
    """무작위로 생성되는 요소 id 를 **등장 순서 서수**로 바꾼다.

    두 저작 경로가 같은 XML 을 내는지 보려면 id 의 실제 값은 비교 대상이 아니다
    (호출마다 난수다). 다만 같은 값에는 같은 서수를 주므로 **연결 관계**
    (``hp:header id`` ↔ ``hp:headerApply idRef``)는 그대로 비교된다 —
    id 배선이 어긋나면 여기서 잡힌다.
    """

    seen: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        value = match.group(2)
        ordinal = seen.setdefault(value, str(len(seen)))
        return f'{match.group(1)}="#{ordinal}"'

    return _ID_ATTR.sub(_replace, xml)


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


# --------------------------------------------------------------------------
# 게이트 ① 위임 재현 — 옛 4메서드와 새 2메서드가 같은 결과를 낸다


def test_set_header_reproduces_the_old_text_verb(document: HwpxDocument) -> None:
    new = HwpxDocument.new()
    new.page.set_header(text="머리말", section=0)

    old = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old.set_header_text("머리말", section_index=0)

    assert _canonical_ids(_part(new)) == _canonical_ids(_part(old))


def test_set_footer_reproduces_the_old_content_verb(document: HwpxDocument) -> None:
    content = [{"text": "꼬리말", "align": "CENTER"}]

    new = HwpxDocument.new()
    new.page.set_footer(content=content, section=0)

    old = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old.set_footer_content(content, section_index=0)

    assert _canonical_ids(_part(new)) == _canonical_ids(_part(old))


def test_the_demoted_kind_dispatcher_still_answers_with_a_warning(
    document: HwpxDocument,
) -> None:
    with pytest.warns(DeprecationWarning) as record:
        document.set_header_footer(kind="header", text="머리말")
    assert "doc.page.set_header" in str(record[0].message)


def test_text_and_content_together_is_refused(document: HwpxDocument) -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        document.page.set_header(text="a", content=[{"text": "b"}], section=0)
    assert excinfo.value.code == "page-argument-conflict"


def test_neither_text_nor_content_is_refused(document: HwpxDocument) -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        document.page.set_footer(section=0)
    assert excinfo.value.code == "page-argument-missing"
    assert "remove_footer" in excinfo.value.suggestion


def test_remove_header_and_footer_clear_what_was_set(document: HwpxDocument) -> None:
    document.page.set_header(text="머리말", section=0)
    document.page.set_footer(text="꼬리말", section=0)
    document.page.remove_header(section=0)
    document.page.remove_footer(section=0)
    section = _part(document)
    assert "머리말" not in section and "꼬리말" not in section


# --------------------------------------------------------------------------
# 게이트 ② section=0 수용


def test_the_new_api_path_never_warns_about_the_old_one() -> None:
    """소유 모듈이 파사드 shim 을 되부르면 안 된다.

    5.x 의 ``layout.set_page_setup`` 은 ``doc.set_page_size(...)`` 를 불렀다.
    6.0 에서 그 이름은 shim 이므로, ``doc.page.setup()`` 만 부른 사용자가
    **자기가 부른 적 없는** 옛 이름의 경고를 받게 된다.
    """

    document = HwpxDocument.new()
    document.add_paragraph("본문")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        document.page.setup(paper_size="A4", columns=2, margins_mm={"left": 20}, section=0)
        document.page.set_header(text="h", section=0)
        document.page.set_footer(content=[{"text": "f"}], section=0)
        document.page.set_page_number(section=0)
    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


@pytest.mark.parametrize("name", PAGE_SECTION_MEMBERS)
def test_every_page_member_accepts_a_section_index(name: str) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    getattr(document.page, name)(**_ARGS.get(name, {}), section=0)


@pytest.mark.parametrize("name", PAGE_SECTION_MEMBERS)
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_page_members_report_bad_sections_as_typed_errors(name, kwargs, code) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    with pytest.raises(HwpxError) as excinfo:
        getattr(document.page, name)(**_ARGS.get(name, {}), **kwargs)
    assert excinfo.value.code == code


# --------------------------------------------------------------------------
# 단위가 다른 두 벌은 둘 다 산다


def test_mm_and_hwpunit_paths_both_work(document: HwpxDocument) -> None:
    document.page.setup(paper_size="A4", section=0)
    a4 = document.page.size(section=0)
    document.page.set_size(width=a4.width + 1000, section=0)
    assert document.page.size(section=0).width == a4.width + 1000

    document.page.set_margins(left=1234, section=0)
    assert document.page.margins(section=0).left == 1234


# --------------------------------------------------------------------------
# Q3b 가 연 3요소 — 읽고 쓸 수 있다


def test_grid_visibility_and_line_numbers_round_trip(document: HwpxDocument) -> None:
    """5.x 는 이 셋을 Skeleton 상수로 박제해 두고 바꾸지 못했다."""

    document.page.set_grid(line_grid=12, char_grid=8, wonggoji_format=True, section=0)
    grid = document.page.grid(section=0)
    assert (grid.line_grid, grid.char_grid, grid.wonggoji_format) == (12, 8, True)

    document.page.set_visibility(hide_first_header=True, show_line_number=True, section=0)
    visibility = document.page.visibility(section=0)
    assert visibility.hide_first_header is True
    assert visibility.show_line_number is True


# --------------------------------------------------------------------------
# 6.12 트레인㊸ 갭③ — text_direction(hp:secPr 세로쓰기)


def test_text_direction_defaults_to_horizontal(document: HwpxDocument) -> None:
    direction = document.page.text_direction(section=0)
    assert direction.direction == "HORIZONTAL"
    assert direction.vertical_header_footer is False


def test_set_text_direction_round_trips_through_save_and_reopen(document: HwpxDocument) -> None:
    document.page.set_text_direction(
        "VERTICAL", vertical_header_footer=True, section=0,
    )
    direction = document.page.text_direction(section=0)
    assert direction.direction == "VERTICAL"
    assert direction.vertical_header_footer is True

    reopened = HwpxDocument.open(document.to_bytes())
    reopened_direction = reopened.page.text_direction(section=0)
    assert reopened_direction.direction == "VERTICAL"
    assert reopened_direction.vertical_header_footer is True


def test_set_text_direction_accepts_verticalall(document: HwpxDocument) -> None:
    document.page.set_text_direction("VERTICALALL", section=0)
    assert document.page.text_direction(section=0).direction == "VERTICALALL"


def test_set_text_direction_rejects_unsupported_values(document: HwpxDocument) -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        document.page.set_text_direction("SIDEWAYS", section=0)
    assert excinfo.value.code == "page-text-direction-unsupported"
    assert excinfo.value.context["requested"] == "SIDEWAYS"


def test_set_text_direction_leaves_direction_untouched_when_only_header_footer_given(
    document: HwpxDocument,
) -> None:
    document.page.set_text_direction("VERTICAL", section=0)
    document.page.set_text_direction(vertical_header_footer=True, section=0)
    direction = document.page.text_direction(section=0)
    assert direction.direction == "VERTICAL"
    assert direction.vertical_header_footer is True

    document.page.set_line_numbers(count_by=5, start_number=3, section=0)
    shape = document.page.line_numbers(section=0)
    assert (shape.count_by, shape.start_number) == (5, 3)


def test_the_three_survive_a_save_round_trip(document: HwpxDocument, tmp_path) -> None:
    document.page.set_grid(line_grid=12, section=0)
    document.page.set_visibility(show_line_number=True, section=0)
    document.page.set_line_numbers(count_by=5, section=0)
    target = tmp_path / "geometry.hwpx"
    document.save_to_path(target)

    with HwpxDocument.open(target) as reopened:
        assert reopened.page.grid(section=0).line_grid == 12
        assert reopened.page.visibility(section=0).show_line_number is True
        assert reopened.page.line_numbers(section=0).count_by == 5


def test_page_number_lands_in_the_footer(document: HwpxDocument) -> None:
    document.page.set_page_number(target="footer", section=0)
    assert "PAGE" in _part(document).upper()


def test_set_columns_returns_the_inline_object(document: HwpxDocument) -> None:
    from hwpx import model

    assert isinstance(document.page.set_columns(2, section=0), model.InlineObject)
