# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-C gates — the 6.0 return contract (design §2/§9 WP-C).

Every gate here is one of the seven WP-C completion gates. The namespace
modules (``doc.styles``/``doc.fields``/… in ``_document/ns/``) are WP-B's
exclusive file range and are still empty stubs at this point in the build
(design §9 — WP-B1/B2/B3 fill their bodies after WP-C lands), so the checks
below reach the return contract through the two paths that already exist:

- The ``_document/*.py`` implementation modules WP-C owns
  (``fields.py``/``media.py``/``memos.py``/``tracked.py``/``layout.py``),
  where the changed return statements actually live.
- The current ``HwpxDocument`` facade (``doc.add_check_box`` etc.), which
  still resolves — through the 6.0 migration shim — to those same functions.
  Calls through it are wrapped in a ``DeprecationWarning`` filter because the
  shim's job (warning on the moved name) is orthogonal to what is being
  verified here (the value it forwards).

Once WP-B wires ``doc.fields.add``/``doc.media.add_image``/etc. straight
through to these same functions, the namespace-level surface inherits the
same return types for free — there is nothing left for those methods to
convert.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import warnings
from pathlib import Path
from typing import Iterator

import pytest

from hwpx import HwpxDocument
from hwpx._document import media as _media
from hwpx._document import memos as _memos
from hwpx._document import tracked as _tracked
from hwpx.errors import HwpxValueError
from hwpx.form_fit import FitPolicy
from hwpx.objects import (
    BinaryItem,
    CheckBox,
    ColumnLayout,
    FieldFillResult,
    FieldLocation,
    FieldParameter,
    FormField,
    ListFormatResult,
    PageMargins,
    PageSetup,
    PageSize,
    ParagraphFormatResult,
    PictureRef,
    PictureReplacement,
    TrackedChange,
    TrackedReplacement,
    Units,
)

SRC = Path(__file__).resolve().parent.parent / "src" / "hwpx"
_DOCUMENT_FILES = ("fields.py", "media.py", "memos.py", "tracked.py", "layout.py")
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@contextlib.contextmanager
def _no_warnings() -> Iterator[None]:
    """Suppress the 6.0 migration shim's ``DeprecationWarning`` for one call.

    Calling the still-live 5.x facade names (``doc.add_check_box`` etc.) is
    the only way to reach these code paths before WP-B wires the namespace
    surface — the shim doing its job (warning on the moved name) is
    orthogonal to what these tests verify (the value it forwards).
    """

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


# --------------------------------------------------------------------------
# 게이트 ① `add_*` 반환 주석 — dict/tuple/str/int/Any 0건 (WP-C 소유 파일)


def _add_star_functions(path: Path) -> list[ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("add_")
    ]


_BANNED_RETURN_NAMES = {"dict", "tuple", "str", "int", "Any", "list"}


@pytest.mark.parametrize("filename", _DOCUMENT_FILES)
def test_add_star_return_annotations_avoid_banned_primitives(filename: str) -> None:
    """No ``add_*`` in a WP-C file names a raw dict/tuple/str/int/Any return.

    ``ast.unparse`` renders the *whole* annotation (e.g. ``BinaryItem``,
    ``HwpxOxmlInlineObject``, ``FieldFillResult``) — this only flags the
    banned primitive family names design §2.7 rules out, not every
    non-``hwpx.objects`` name (``add_picture``/``add_bookmark`` legitimately
    return ``hwpx.oxml`` types under §7's model-alias regime, which is a
    separate WP-A/WP-G concern).
    """

    offenders = []
    for func in _add_star_functions(SRC / "_document" / filename):
        if func.returns is None:
            offenders.append(f"{func.name} -> <no annotation>")
            continue
        names = {n.id for n in ast.walk(func.returns) if isinstance(n, ast.Name)}
        banned = names & _BANNED_RETURN_NAMES
        if banned:
            offenders.append(f"{func.name} -> {ast.unparse(func.returns)}")
    assert not offenders, f"{filename}: banned return annotations: {offenders}"


def test_every_wp_c_add_star_was_actually_found() -> None:
    """Sanity check on the AST walk above: it must see all 9 renamed functions.

    A parser regression that silently found 0 functions would make the gate
    above vacuously pass — this pins the expected names so that can't happen.
    """

    found = {
        func.name
        for filename in _DOCUMENT_FILES
        for func in _add_star_functions(SRC / "_document" / filename)
    }
    assert found == {
        "add_check_box",
        "add_form_field",
        "add_image",
        "add_picture",
        "add_memo",
        "add_memo_with_anchor",
        "add_track_change",
        "add_tracked_insert",
        "add_tracked_delete",
        "add_tracked_replace",
        "add_bookmark",
        "add_hyperlink",
    }


# --------------------------------------------------------------------------
# 게이트 ② `add_form_field` 20키 → `FormField` 속성 12개, id 별칭 3→1


def test_form_field_has_exactly_the_designed_twelve_attributes() -> None:
    members = {name for name in dir(FormField) if not name.startswith("_")}
    assert members == {
        "element",
        "field_id",
        "name",
        "prompt",
        "memo",
        "editable",
        "value",
        "field_type",
        "is_placeholder",
        "location",
        "parameters",
        "has_end",
    }, members


def test_form_field_collapses_the_5x_aliases() -> None:
    """id/fieldid/field_id → field_id; instruction → prompt; control_type → field_type."""

    members = {name for name in dir(FormField) if not name.startswith("_")}
    assert "id" not in members
    assert "fieldid" not in members
    assert "instruction" not in members
    assert "control_type" not in members
    assert "current_value" not in members  # -> value


def test_form_field_location_collapses_the_five_index_keys() -> None:
    # `dir(cls)` skips dataclass fields that have no default (they live only
    # in `__annotations__`, not as class attributes) — `dataclasses.fields`
    # is the correct introspection here, not `dir`.
    field_names = {f.name for f in dataclasses.fields(FieldLocation)}
    assert field_names == {
        "section_index",
        "paragraph_index",
        "paragraph_index_in_section",
        "run_index",
        "child_index",
    }


def test_add_form_field_returns_a_live_form_field() -> None:
    document = HwpxDocument.new()
    with _no_warnings():
        field = document.add_form_field("성명", prompt="이름 입력", memo="도움말")

    assert isinstance(field, FormField)
    assert field.field_id
    assert field.name == "성명"
    assert field.prompt == "이름 입력"
    assert field.memo == "도움말"
    assert field.is_placeholder is True
    assert field.has_end is True
    assert field.location.section_index == 0
    assert field.element.tag == f"{HP}fieldBegin"


def test_form_field_value_setter_fills_through_the_same_path_as_fill() -> None:
    """``field.value = x`` is not a raw overwrite — it goes through the
    style-preserving fill machinery, the same as ``doc.fields.fill``."""

    document = HwpxDocument.new()
    with _no_warnings():
        field = document.add_form_field("이름", prompt="입력하세요")
        field.value = "홍길동"

    assert field.value == "홍길동"
    assert field.is_placeholder is False
    with _no_warnings():
        (reread,) = document.list_form_fields()
    assert reread.value == "홍길동"


# --------------------------------------------------------------------------
# 게이트 ③ 결과 dataclass 전부 frozen=True + to_dict() — 리플렉션 검사

#: The pure-result payload family (design §2.4's dict-replacement table plus
#: the tuple/scalar replacements of §2.6 and their nested value types) —
#: distinct from the four *living* views (CheckBox/FormField/TrackedChange/
#: BinaryItem, design §2.3) that intentionally have neither trait.
_RESULT_DATACLASSES = (
    FieldFillResult,
    PictureReplacement,
    PictureRef,
    Units,
    ListFormatResult,
    ParagraphFormatResult,
    PageSize,
    PageMargins,
    ColumnLayout,
    PageSetup,
    FieldLocation,
    FieldParameter,
    TrackedChange,
    TrackedReplacement,
)


@pytest.mark.parametrize("cls", _RESULT_DATACLASSES, ids=lambda c: c.__name__)
def test_result_dataclasses_are_frozen_with_to_dict(cls: type) -> None:
    assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"
    assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} is not frozen"
    assert callable(getattr(cls, "to_dict", None)), f"{cls.__name__} has no to_dict()"


@pytest.mark.parametrize("cls", _RESULT_DATACLASSES, ids=lambda c: c.__name__)
def test_result_dataclasses_reject_mutation(cls: type) -> None:
    instance = object.__new__(cls)
    field_names = [f.name for f in dataclasses.fields(cls)]
    assert field_names, f"{cls.__name__} has no fields to probe"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field_names[0], None)


def test_checkbox_and_form_field_are_living_views_not_result_dataclasses() -> None:
    """The opposite half of the §2.3 split: settable, not frozen, no to_dict."""

    assert not dataclasses.is_dataclass(CheckBox)
    assert not dataclasses.is_dataclass(FormField)
    assert not hasattr(CheckBox, "to_dict")
    assert not hasattr(FormField, "to_dict")


def test_field_fill_result_to_dict_is_a_plain_camel_case_dict() -> None:
    document = HwpxDocument.new()
    with _no_warnings():
        document.add_form_field("주소", prompt="입력")
        result = document.fill_form_field("서울시", name="주소")
    payload = result.to_dict()
    assert payload["before"] == "입력"
    assert payload["after"] == "서울시"
    assert "ok" not in payload  # deleted, not merely False (design §2.4)
    assert payload["stylePreserved"] in (True, False)


# --------------------------------------------------------------------------
# 게이트 ④ 이주 완충 — `str(add_image(...)) == "BIN0001"`


def test_binary_item_stringifies_to_its_manifest_id() -> None:
    document = HwpxDocument.new()
    item = _media.add_image(document, _PNG, "png")
    assert isinstance(item, BinaryItem)
    assert str(item) == "BIN0001"
    # And through the still-live 5.x facade name (deprecated, not removed):
    with _no_warnings():
        legacy_item = document.add_image(_PNG, "png")
    assert str(legacy_item) == "BIN0002"


def test_picture_references_returns_picture_ref_tuples() -> None:
    document = HwpxDocument.new()
    with _no_warnings():
        document.add_picture(_PNG, "png", width=1000, height=2000)
    refs = _media.picture_references(document)
    assert isinstance(refs, tuple)
    (ref,) = refs
    assert isinstance(ref, PictureRef)
    assert ref.binary_item_id_ref == "BIN0001"
    assert ref.width == 1000
    assert ref.height == 2000


def test_add_picture_still_works_with_the_binary_item_migration_buffer() -> None:
    """``add_picture`` (kept, unmoved) consumes ``add_image``'s new return
    type without the caller doing anything — the ``__str__`` buffer working
    end to end, not just in isolation."""

    document = HwpxDocument.new()
    with _no_warnings():
        document.add_picture(_PNG, "png", width=1000, height=1000)
    (image,) = document.list_images()
    assert image.item_id == "BIN0001"


# --------------------------------------------------------------------------
# 게이트 ⑤ `TrackedChange`에 `__int__` 없음 — 암묵 변환 금지 단언


def test_tracked_change_has_no_implicit_int_conversion() -> None:
    assert "__int__" not in vars(TrackedChange)
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("some text")
    with _no_warnings():
        change = document.add_tracked_insert(paragraph, " more")
    assert isinstance(change, TrackedChange)
    with pytest.raises(TypeError):
        int(change)  # type: ignore[arg-type]


def test_add_tracked_replace_returns_named_fields_not_a_tuple() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("before old after", char_pr_id_ref="0")
    with _no_warnings():
        result = document.add_tracked_replace(paragraph, "old", "new")
    assert isinstance(result, TrackedReplacement)
    assert isinstance(result.insert, TrackedChange) and result.insert.kind == "INSERT"
    assert isinstance(result.delete, TrackedChange) and result.delete.kind == "DELETE"
    assert result.insert.change_id != result.delete.change_id


def test_add_track_change_low_level_primitive_has_no_paragraph() -> None:
    """Header-only metadata (design table row 39) isn't anchored to any text yet."""

    document = HwpxDocument.new()
    change = _tracked.add_track_change(document, "Insert")
    assert change.paragraph is None


# --------------------------------------------------------------------------
# `Memo.paragraph`/`.field_id` (oxml/memo.py) — replaces the 3-tuple/str


def test_memo_anchor_properties_are_none_until_attached() -> None:
    document = HwpxDocument.new()
    memo = _memos.add_memo(document, "just a memo, no anchor")
    assert memo.field_id is None
    assert memo.paragraph is None


def test_add_memo_with_anchor_returns_one_memo_not_a_3_tuple() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("anchor host")
    with _no_warnings():
        memo = document.add_memo_with_anchor(
            "anchored text", paragraph=paragraph, memo_shape_id_ref="0"
        )
    assert memo.text == "anchored text"
    assert memo.field_id
    assert memo.paragraph is not None
    assert memo.paragraph.element is paragraph.element


def test_attach_memo_field_returns_the_memo_with_field_id_resolvable() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("host")
    memo = _memos.add_memo(document, "comment text")
    with _no_warnings():
        returned = document.attach_memo_field(paragraph, memo, field_id="field-77")
    assert returned is memo
    assert returned.field_id == "field-77"


# --------------------------------------------------------------------------
# `fill_form_field` — `ok` 삭제, fail-closed raise (design §2.4)


def _click_here_field(document: HwpxDocument, *, name: str) -> None:
    paragraph = document.add_paragraph("", include_run=False)
    p = paragraph.element
    begin_run = p.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    p.append(begin_run)
    ctrl = begin_run.makeelement(f"{HP}ctrl", {"type": "FORM", "id": "ctrl-a"})
    begin_run.append(ctrl)
    field_begin = ctrl.makeelement(
        f"{HP}fieldBegin",
        {"id": "f-a", "fieldid": "f-a", "type": "ClickHere", "name": name, "prompt": name},
    )
    ctrl.append(field_begin)
    params = field_begin.makeelement(f"{HP}parameters", {"count": "1"})
    field_begin.append(params)
    string_param = params.makeelement(f"{HP}stringParam", {"name": "FieldName"})
    string_param.text = name
    params.append(string_param)
    text_run = p.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    p.append(text_run)
    t = text_run.makeelement(f"{HP}t", {})
    t.text = "입력"
    text_run.append(t)
    end_run = p.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    p.append(end_run)
    end_ctrl = end_run.makeelement(f"{HP}ctrl", {})
    end_run.append(end_ctrl)
    field_end = end_ctrl.makeelement(f"{HP}fieldEnd", {"beginIDRef": "f-a", "fieldid": "f-a"})
    end_ctrl.append(field_end)
    p.append(p.makeelement(f"{HP}lineSegArray", {}))
    paragraph.section.mark_dirty()


def test_fill_form_field_no_longer_has_an_ok_key() -> None:
    document = HwpxDocument.new()
    _click_here_field(document, name="주소")
    with _no_warnings():
        result = document.fill_form_field("서울시", name="주소")
    assert isinstance(result, FieldFillResult)
    assert not hasattr(result, "ok")
    assert "ok" not in result.to_dict()


def test_fill_form_field_fails_closed_on_hard_overflow_instead_of_ok_false() -> None:
    document = HwpxDocument.new()
    _click_here_field(document, name="주소")
    with _no_warnings():
        with pytest.raises(HwpxValueError) as excinfo:
            document.fill_form_field(
                "가" * 50,
                name="주소",
                fit_policy=FitPolicy(mode="fail_on_overflow", overflow="fail", max_lines=1),
                box_width=4000,
            )
    assert excinfo.value.code == "field-fit-failed"
    assert excinfo.value.suggestion
    assert excinfo.value.context["fit"]["overflowDetected"] is True

    # And the field itself was left untouched — fail-closed, not "wrote it
    # anyway and reported failure" (the 5.x `ok: bool` shape).
    with _no_warnings():
        (field,) = document.list_form_fields()
    assert field.value == "입력"


def test_fill_form_field_without_box_width_never_hard_fails() -> None:
    """Low-confidence, measure-free path (no box_width) still succeeds —
    only a *known* overflow raises."""

    document = HwpxDocument.new()
    _click_here_field(document, name="주소")
    with _no_warnings():
        result = document.fill_form_field(
            "가" * 50, name="주소", fit_policy=FitPolicy(overflow="fail")
        )
    assert isinstance(result, FieldFillResult)
    assert result.fit is not None
    assert result.fit.confidence == "low"


# --------------------------------------------------------------------------
# `set_page_setup` — mm 정직화 (design §2.4 PageSetup 코멘트)


def test_page_setup_reports_millimetres_not_relabelled_hwpunit() -> None:
    document = HwpxDocument.new()
    with _no_warnings():
        result = document.set_page_setup(
            paper_size="A4", orientation="landscape",
            margin_left_mm=20, margin_right_mm=20,
        )
    assert isinstance(result, PageSetup)
    # A4 landscape is 297x210mm -- not the ~84094 HWPUNIT 5.x mislabelled "mm".
    assert result.page_size.width_mm == 297.0
    assert result.page_size.height_mm == 210.0
    assert result.margins.left == 20
    assert result.margins.right == 20
    assert result.units.page == "mm"


# --------------------------------------------------------------------------
# 이주 맵 §8.3 대표 시나리오 (행 9~17) — dict/tuple 접근이 사라졌는지 직접 확인


def test_checkbox_setter_replaces_set_check_box_call_pattern() -> None:
    """§8.3 row 12: ``cb.checked = False`` replaces ``doc.set_check_box(...)``."""

    document = HwpxDocument.new()
    with _no_warnings():
        cb = document.add_check_box("동의")
    cb.checked = False
    assert cb.checked is False
    with _no_warnings():
        (reread,) = document.list_check_boxes()
    assert reread.checked is False
