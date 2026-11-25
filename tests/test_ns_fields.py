# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B2 게이트 — `doc.fields`.

능력 레지스트리의 `form-field-create` 와 `check-box` 두 영역.

**반환 타입은 WP-C 조인 대기.** 설계서 §2 가 정한 `FormField`·`CheckBox`·
`FieldFillResult` 는 WP-C 가 `hwpx.objects` 에 만든다. 여기서는 5.x 의
dict/list[dict] 를 그대로 통과시키되, **위임이 옳은지**를 못박는다 — 타입이
바뀌어도 이 테스트들은 그대로 살아야 한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError, HwpxTypeError


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


# --------------------------------------------------------------------------
# 누름틀


def test_add_registers_a_field_that_the_listing_finds(document: HwpxDocument) -> None:
    created = document.fields.add("이름", prompt="입력하세요", section=0)
    listed = document.fields.all
    assert len(listed) == 1
    assert listed[0].name == "이름"
    assert listed[0].prompt == "입력하세요"
    # 5.x 의 20키 dict 는 id 별칭을 셋(field_id/id/fieldid) 들고 있었다.
    assert created.field_id == listed[0].field_id


def test_fill_writes_the_value_into_the_named_field(document: HwpxDocument) -> None:
    document.fields.add("이름", section=0)
    result = document.fields.fill("홍길동", name="이름")
    # ``ok`` 키는 사라졌다 — 실패는 fail-closed 로 던진다(설계서 §2.4).
    assert not hasattr(result, "ok")
    assert result.after == "홍길동"
    assert result.field.name == "이름"
    assert document.fields.all[0].value == "홍길동"


def test_filling_an_unknown_field_fails_closed(document: HwpxDocument) -> None:
    with pytest.raises(Exception) as excinfo:
        document.fields.fill("값", name="없는이름")
    assert not isinstance(excinfo.value, AttributeError), "내부가 새면 안 된다"


@pytest.mark.parametrize("value", [["a", "b"], {"k": "v"}, ("a",), True, b"bytes", object()])
def test_a_value_that_is_not_text_or_a_number_is_refused_and_leaves_the_field(
    document: HwpxDocument, value: object
) -> None:
    # #811: str() of a list or a dict wrote Python's spelling of it ("['a', 'b']") into the form.
    document.fields.add("field", prompt="type here", section=0)
    before = document.to_bytes()
    with pytest.raises(HwpxTypeError) as excinfo:
        document.fields.fill(value, name="field")  # type: ignore[arg-type]
    assert excinfo.value.code == "hwpx-type-error" and excinfo.value.suggestion
    assert document.to_bytes() == before


@pytest.mark.parametrize("value,shown", [(120, "120"), (2.5, "2.5"), (Decimal("1.50"), "1.50")])
def test_a_number_is_written_as_its_digits(document: HwpxDocument, value: object, shown: str) -> None:
    document.fields.add("field", section=0)
    assert document.fields.fill(value, name="field").after == shown  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# 체크박스


def test_add_check_box_and_toggle_it(document: HwpxDocument) -> None:
    created = document.fields.add_check_box("동의", checked=True, name="agree", section=0)
    assert created.checked is True
    assert created.caption == "동의"
    assert len(document.fields.check_boxes) == 1

    toggled = document.fields.set_check_box(False, name="agree")
    assert toggled.checked is False
    assert document.fields.check_boxes[0].checked is False


# --------------------------------------------------------------------------
# section 규약


@pytest.mark.parametrize("name,args", [("add", ("이름",)), ("add_check_box", ("동의",))])
def test_creating_members_accept_a_section_index(name, args) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    getattr(document.fields, name)(*args, section=0)


@pytest.mark.parametrize("name,args", [("add", ("이름",)), ("add_check_box", ("동의",))])
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section_index": 0}, "hwpx-argument-removed"),
    ],
    ids=["out-of-range", "wrong-type", "removed-section-index"],
)
def test_bad_sections_are_typed_errors(name, args, kwargs, code) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    with pytest.raises(HwpxError) as excinfo:
        getattr(document.fields, name)(*args, **kwargs)
    assert excinfo.value.code == code


# --------------------------------------------------------------------------
# 옛 루트 이름은 경고와 함께 같은 결과를 낸다


def test_every_removed_root_name_points_at_doc_fields(document: HwpxDocument) -> None:
    """7.0: 6.x 가 경고와 함께 남겨 둔 루트 이름은 없어졌고, 부르면 새 자리를 말한다."""

    from hwpx.errors import HwpxAttributeError

    for name, target in [
        ("add_form_field", "doc.fields.add"),
        ("list_form_fields", "doc.fields.all"),
        ("add_check_box", "doc.fields.add_check_box"),
        ("list_check_boxes", "doc.fields.check_boxes"),
        ("set_check_box", "doc.fields.set_check_box"),
        ("fill_form_field", "doc.fields.fill"),
    ]:
        with pytest.raises(HwpxAttributeError) as excinfo:
            getattr(document, name)
        assert target in str(excinfo.value)


# --------------------------------------------------------------------------
# WP-C 조인 지점 — 지금 무엇을 돌려주는지 명시적으로 고정해 둔다


def test_the_return_contract_is_domain_objects(document: HwpxDocument) -> None:
    """WP-C 조인 완료 — 5.x 의 dict/list[dict] 가 도메인 객체가 됐다."""

    from hwpx.objects import CheckBox, FieldFillResult, FormField

    created = document.fields.add("이름", section=0)
    assert isinstance(created, FormField)
    assert isinstance(document.fields.all, tuple)
    assert all(isinstance(entry, FormField) for entry in document.fields.all)
    assert isinstance(document.fields.fill("홍길동", name="이름"), FieldFillResult)
    assert isinstance(document.fields.add_check_box("동의", section=0), CheckBox)
    assert isinstance(document.fields.check_boxes, tuple)


def test_the_form_field_id_aliases_collapsed_to_one(document: HwpxDocument) -> None:
    """5.x dict 는 같은 값을 ``field_id``/``id``/``fieldid`` 셋으로 들고 있었다."""

    field = document.fields.add("이름", section=0)
    assert field.field_id
    assert not hasattr(field, "id")
    assert not hasattr(field, "fieldid")
    # 인덱스 5키도 하나의 위치 객체로 접혔다.
    assert field.location.section_index == 0
    assert field.location.paragraph_index >= 0


def test_a_check_box_is_a_living_view(document: HwpxDocument) -> None:
    """``checked`` 가 속성이므로 5.x ``set_check_box`` 가 필요 없어진다."""

    box = document.fields.add_check_box("동의", checked=False, name="agree", section=0)
    box.checked = True
    assert document.fields.check_boxes[0].checked is True
