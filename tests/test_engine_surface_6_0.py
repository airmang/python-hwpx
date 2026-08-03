# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-A 게이트 — 6.0 루트 표면의 계약을 기계로 강제한다.

여기 있는 것은 전부 설계서 §9 WP-A의 완료 게이트다. 하나라도 붉어지면 6.0의
표면 약속이 깨진 것이다.
"""

from __future__ import annotations

import ast
import inspect
import json
import warnings
from pathlib import Path

import pytest

from hwpx._document import _resolve
from hwpx._document._legacy import LEGACY_REMOVED_IN, _LegacyFacade
from hwpx._document.ns import NAMESPACES
from hwpx.document import HwpxDocument
from hwpx.errors import (
    HwpxError,
    HwpxLookupError,
    HwpxTypeError,
    HwpxValueError,
)

DATA = Path(__file__).parent / "data"
SRC = Path(__file__).resolve().parent.parent / "src" / "hwpx"

#: 설계서 §1.4 — 6.0 루트 예산. 게이트는 ≤35, 실제는 34이며 여유 1칸은
#: 1-in-1-out 규칙으로 관리한다.
ROOT_SURFACE_BUDGET = 35
_PUBLIC_DUNDERS = {"__init__", "__repr__", "__enter__", "__exit__"}


def _root_members() -> dict[str, object]:
    return {
        name: member
        for name, member in vars(HwpxDocument).items()
        if not name.startswith("_") or name in _PUBLIC_DUNDERS
    }


def _pair_members() -> list[str]:
    """`section` / `section_index` 쌍을 받는 공개 멤버."""

    found = []
    for name in dir(HwpxDocument):
        if name.startswith("_"):
            continue
        static = inspect.getattr_static(HwpxDocument, name)
        func = static.fget if isinstance(static, property) else static
        if not callable(func):
            continue
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            continue
        if "section" in params and "section_index" in params:
            found.append(name)
    return sorted(found)


# --------------------------------------------------------------------------
# 게이트 ① 루트 공개 멤버 ≤ 35


def test_root_surface_is_within_budget() -> None:
    members = _root_members()
    assert len(members) <= ROOT_SURFACE_BUDGET, (
        f"루트 표면이 예산을 넘었습니다: {len(members)} > {ROOT_SURFACE_BUDGET}. "
        "새 루트 멤버는 1-in-1-out — 하나 넣으려면 하나 빼세요. "
        f"현재: {sorted(members)}"
    )


def test_root_lock_matches_the_live_class() -> None:
    """락은 코드에서 유도된다 — 문서 둘이 서로 맞는 것으로는 부족하다."""

    locked = json.loads((DATA / "document_facade_surface.json").read_text(encoding="utf-8"))
    assert set(locked) == set(_root_members())


def test_every_namespace_is_exposed_on_the_root() -> None:
    for attr, cls in NAMESPACES.items():
        assert attr in _root_members(), f"네임스페이스 {attr} 가 루트에 없습니다"
        document = HwpxDocument.new()
        assert isinstance(getattr(document, attr), cls)


# --------------------------------------------------------------------------
# 게이트 ② shim 락 — 각 항목이 행선지와 제거 버전을 갖는다


def test_legacy_shim_lock_is_complete_and_actionable() -> None:
    locked = json.loads((DATA / "document_legacy_shims.json").read_text(encoding="utf-8"))
    live = {n for n in vars(_LegacyFacade) if not n.startswith("__")}
    assert set(locked) == live, "shim 락이 _LegacyFacade 와 어긋났습니다"
    for name, entry in locked.items():
        assert entry["replacement"], f"{name} 에 행선지가 없습니다"
        assert entry["removedIn"] == LEGACY_REMOVED_IN, name


def test_legacy_shims_are_a_shrinking_ratchet() -> None:
    """shim 수는 늘 수 없다. 7.0에서 0이 된다.

    이 숫자를 올리려면 6.0 루트에서 무언가를 새로 강등했다는 뜻이므로,
    설계서 §1의 결정표와 함께 검토돼야 한다.
    """

    locked = json.loads((DATA / "document_legacy_shims.json").read_text(encoding="utf-8"))
    assert len(locked) <= 79


def test_every_5_x_public_name_still_resolves() -> None:
    """5.8.0의 102개 이름 중 6.0에서 사라진 것은 없다 — 이동은 제거가 아니다."""

    root = set(json.loads((DATA / "document_facade_surface.json").read_text(encoding="utf-8")))
    shims = set(json.loads((DATA / "document_legacy_shims.json").read_text(encoding="utf-8")))
    document = HwpxDocument.new()
    for name in root | shims:
        assert hasattr(document, name), name


@pytest.mark.parametrize("name", sorted(vars(_LegacyFacade)))
def test_moved_surface_warns_with_its_destination(name: str) -> None:
    if name.startswith("__"):
        pytest.skip("dunder")
    static = inspect.getattr_static(_LegacyFacade, name)
    func = static.fget if isinstance(static, property) else static
    assert func.__hwpx_moved_to__, name
    assert func.__hwpx_removed_in__ == LEGACY_REMOVED_IN


def test_a_moved_call_warns_and_still_works() -> None:
    document = HwpxDocument.new()
    with pytest.warns(DeprecationWarning) as record:
        document.set_header_text("머리말", section=0)
    message = str(record[0].message)
    assert "doc.page.set_header" in message
    assert "7.0" in message


def test_repr_does_not_warn_about_its_own_summary() -> None:
    document = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        repr(document)


# --------------------------------------------------------------------------
# 게이트 ④ `section=0` 수용 — 실물 결함의 회귀 테스트


def test_the_reported_third_party_failure_is_fixed() -> None:
    """jkf87/hwpx-skill 이 우회 코드를 심게 만든 바로 그 호출.

    5.x: AttributeError: 'int' object has no attribute 'properties'
    """

    document = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        document.set_header_text("머리말", section=0)


@pytest.mark.parametrize("name", _pair_members())
def test_section_index_is_accepted_everywhere(name: str) -> None:
    document, call = _prepared(name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        call(document, section=0)


@pytest.mark.parametrize("name", _pair_members())
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_bad_section_arguments_raise_typed_errors(name, kwargs, code) -> None:
    """`AttributeError` 가 공개 경로로 새지 않는다 — 전부 typed 다."""

    document, call = _prepared(name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(HwpxError) as excinfo:
            call(document, **kwargs)
    assert excinfo.value.code == code
    assert excinfo.value.suggestion


_CHART = b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
_ARGS: dict[str, tuple] = {
    "add_paragraph": ("t",),
    "add_heading": ("t",),
    "add_table": (1, 1),
    "add_picture": (_PNG, "png"),
    "add_bookmark": ("bm",),
    "add_hyperlink": ("https://example.invalid", "link"),
    "add_footnote": ("fn",),
    "add_endnote": ("en",),
    "add_memo": ("m",),
    "add_memo_with_anchor": ("m",),
    "add_form_field": ("f",),
    "add_check_box": ("cb",),
    "add_chart": (_CHART,),
    "add_equation": ("x=1",),
    "add_shape": ("rect",),
    "set_header_text": ("h",),
    "set_footer_text": ("f",),
    "set_header_content": ([{"text": "h"}],),
    "set_footer_content": ([{"text": "f"}],),
    "remove_paragraph": (0,),
}
_KWARGS: dict[str, dict] = {"set_header_footer": {"kind": "header", "text": "h"}}


def _prepared(name: str):
    document = HwpxDocument.new()
    document.add_paragraph("seed")

    def call(doc, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return getattr(doc, name)(*_ARGS.get(name, ()), **_KWARGS.get(name, {}), **kwargs)

    return document, call


def test_resolver_rejects_bool_as_an_index() -> None:
    """`section=True` 를 인덱스 1 로 읽으면 조용히 엉뚱한 섹션에 쓴다."""

    document = HwpxDocument.new()
    with pytest.raises(HwpxTypeError) as excinfo:
        _resolve.resolve_section(document, True)
    assert excinfo.value.code == "section-invalid-type"


def test_resolver_accepts_objects_negative_indexes_and_none() -> None:
    document = HwpxDocument.new()
    last = document.sections[-1]
    assert _resolve.resolve_section(document, None) is last
    assert _resolve.resolve_section(document, 0) is document.sections[0]
    assert _resolve.resolve_section(document, -1) is last
    assert _resolve.resolve_section(document, last) is last
    assert _resolve.resolve_section(document, None, 0) is document.sections[0]


def test_paragraph_resolution_follows_the_same_rule() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    # 문단 래퍼는 접근할 때마다 새로 만들어지므로 동일성이 아니라 같은
    # XML 요소를 가리키는지로 확인한다.
    assert _resolve.resolve_paragraph(document, 0).element is document.paragraphs[0].element
    with pytest.raises(HwpxLookupError) as excinfo:
        _resolve.resolve_paragraph(document, 999)
    assert excinfo.value.code == "paragraph-not-found"


# --------------------------------------------------------------------------
# 게이트 ⑤ 리졸버 우회 0건 (AST)


def _class_functions(path: Path, class_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for member in node.body:
                if isinstance(member, ast.FunctionDef):
                    yield member


def test_no_public_section_path_bypasses_the_resolver() -> None:
    """`section` 쌍을 받는 함수는 전부 한 리졸버를 거친다.

    5.x는 31개 중 6개만 거쳤고, 나머지가 int를 그대로 흘려 `AttributeError`를
    냈다. 이 검사가 그 상태로 되돌아가는 것을 막는다.
    """

    offenders = []
    for path, cls, decorated_ok in (
        (SRC / "document.py", "HwpxDocument", False),
        (SRC / "_document" / "_legacy.py", "_LegacyFacade", True),
    ):
        for func in _class_functions(path, cls):
            args = func.args
            names = {a.arg for a in (*args.args, *args.kwonlyargs)}
            if not {"section", "section_index"} <= names:
                continue
            calls_resolver = any(
                isinstance(node, ast.Attribute) and node.attr in {"resolve_section"}
                for node in ast.walk(func)
            )
            wrapped = decorated_ok and any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Name)
                and d.func.id == "_moved"
                for d in func.decorator_list
            )
            if not (calls_resolver or wrapped):
                offenders.append(f"{path.name}::{func.name}")
    assert not offenders, f"리졸버를 우회하는 section 경로: {offenders}"


def test_the_moved_decorator_really_normalizes_the_pair() -> None:
    """위 검사가 인정하는 `@_moved` 경로가 실제로 정규화하는지 확인한다.

    데코레이터가 통과 사유인 이상, 그것이 일을 한다는 증거가 같이 있어야 한다.
    """

    static = inspect.getattr_static(_LegacyFacade, "set_header_text")
    assert static.__hwpx_resolves_section__ is True
    static = inspect.getattr_static(_LegacyFacade, "export_text")
    assert static.__hwpx_resolves_section__ is False


# --------------------------------------------------------------------------
# 게이트 ⑥ 공개 시그니처에 `HwpxOxml*` 리터럴 0건


def test_new_public_signatures_name_model_types_not_oxml_ones() -> None:
    """6.0에 새로 생긴 루트 표면은 `hwpx.model` 어휘로 말한다.

    5.x부터 있던 79개 shim의 시그니처는 **동결**이다 — 그것을 고치면 이주
    창의 의미가 없어진다(호출자가 보던 계약이 그대로여야 한다). 그래서 이
    검사는 6.0이 새로 만든 표면에만 적용된다.
    """

    locked_5x = set(json.loads((DATA / "document_legacy_shims.json").read_text(encoding="utf-8")))
    offenders = []
    for func in _class_functions(SRC / "document.py", "HwpxDocument"):
        if func.name in locked_5x or func.name.startswith("_"):
            continue
        rendered = ast.unparse(func.returns) if func.returns else ""
        if "HwpxOxml" in rendered and func.name not in _FROZEN_5X_RETURNS:
            offenders.append(f"{func.name} -> {rendered}")
    assert not offenders, (
        "새 공개 시그니처가 hwpx.model 대신 oxml 구현 이름을 노출합니다: " f"{offenders}"
    )


#: 5.x부터 있던 유지 멤버 — 시그니처가 동결이라 oxml 이름을 그대로 쓴다.
#: 이 이름들을 `hwpx.model` 어휘로 바꾸는 것은 표면 변경이므로 별도 결정이다.
_FROZEN_5X_RETURNS = {
    "add_paragraph",
    "add_picture",
    "add_section",
    "add_table",
    "oxml",
    "paragraphs",
    "remove_section",
    "sections",
}


def test_model_aliases_are_the_same_objects_as_oxml() -> None:
    """래퍼가 아니라 별칭이다 — 두 벌의 객체 모델을 만들지 않는다."""

    import hwpx.model as model
    from hwpx import oxml

    assert model.Paragraph is oxml.HwpxOxmlParagraph
    assert model.Table is oxml.HwpxOxmlTable
    assert model.Section is oxml.HwpxOxmlSection


def test_model_surface_lock_matches_the_live_classes() -> None:
    import hwpx.model as model

    locked = json.loads((DATA / "model_surface.json").read_text(encoding="utf-8"))
    assert set(locked["classes"]) == set(model.__all__)
    for name, entry in locked["classes"].items():
        cls = getattr(model, name)
        live = {member for member in dir(cls) if not member.startswith("_")}
        missing = sorted(set(entry["stable"]) - live)
        assert not missing, f"{name} 의 stable 멤버가 사라졌습니다: {missing}"


# --------------------------------------------------------------------------
# add_heading — 개요 스타일과 개요 수준이 함께 붙는다


@pytest.mark.parametrize("level", range(1, 11))
def test_add_heading_binds_style_and_outline_level_together(level: int) -> None:
    """5.x의 결함: 개요 번호는 붙는데 스타일은 바탕글(0)."""

    document = HwpxDocument.new()
    paragraph = document.add_heading(f"제목 {level}", level=level)
    style = document.styles[str(paragraph.style_id_ref)]
    assert style.name == f"개요 {level}"

    para_pr = document.oxml.paragraph_property(paragraph.para_pr_id_ref)
    assert para_pr is not None and para_pr.heading is not None
    assert para_pr.heading.type == "OUTLINE"
    assert str(para_pr.heading.level) == str(level - 1)


@pytest.mark.parametrize("level", [0, 11, -1])
def test_add_heading_rejects_levels_outside_the_hwpx_outline(level: int) -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_heading("t", level=level)
    assert excinfo.value.code == "heading-level-out-of-range"
    assert excinfo.value.suggestion


def test_add_heading_accepts_an_explicit_style_name() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_heading("t", level=1, style="개요 3")
    assert document.styles[str(paragraph.style_id_ref)].name == "개요 3"


def test_add_heading_reports_a_missing_outline_style_with_the_available_list() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_heading("t", level=1, style="개요1")  # 공백 누락 오타
    assert excinfo.value.code == "style-not-found"
    assert "개요 1" in excinfo.value.context["available"]


# --------------------------------------------------------------------------
# doc.styles 는 이름이 옮겨간 게 아니라 의미가 넓어졌다


def test_styles_namespace_keeps_the_5_x_mapping_contract() -> None:
    document = HwpxDocument.new()
    styles = document.styles
    assert styles["0"].name == "바탕글"
    assert len(styles) == len(document.oxml.styles)
    assert bool(styles) is True
    assert "0" in styles
    assert [entry.name for entry in styles.values()][:2] == ["바탕글", "본문"]
    assert dict(styles.items())["0"] == styles["0"]


def test_namespaces_are_stateless_views_of_the_same_document() -> None:
    document = HwpxDocument.new()
    assert document.styles is not document.styles
    assert document.styles.document is document
