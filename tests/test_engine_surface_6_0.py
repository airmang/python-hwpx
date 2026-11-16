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
from hwpx._document._legacy import LEGACY_REMOVED_IN, REMOVED_NAMES
from hwpx._document.ns import NAMESPACES
from hwpx.document import HwpxDocument
from hwpx.errors import (
    HwpxAttributeError,
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


def _section_members() -> list[str]:
    """`section` 을 받는 루트 공개 멤버(6.x 는 `section_index` 와 쌍이었다)."""

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
        # `remove_section(section)` 은 지울 구역을 위치로 받는 다른 계약이다.
        if "section" in params and params["section"].kind is inspect.Parameter.KEYWORD_ONLY:
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


# 루트 멤버의 이름·서명은 공개 표면 잠금(tests/data/public_surface.json 의 root 층,
# tests/test_public_surface.py)이 잠근다. 여기서는 예산만 본다.


def test_every_namespace_is_exposed_on_the_root() -> None:
    for attr, cls in NAMESPACES.items():
        assert attr in _root_members(), f"네임스페이스 {attr} 가 루트에 없습니다"
        document = HwpxDocument.new(empty_first_line=True)
        assert isinstance(getattr(document, attr), cls)


# --------------------------------------------------------------------------
# 게이트 ② 지운 이름 표 — 각 항목이 새 자리와 한 줄 예를 갖고, 부르면 그것을 말한다


def test_removed_name_lock_is_the_guide_table() -> None:
    """락(6.x 의 shim 락)은 7.0에서 안내 표가 됐다 — 코드의 표와 같아야 한다."""

    locked = json.loads((DATA / "document_legacy_shims.json").read_text(encoding="utf-8"))
    assert set(locked) == set(REMOVED_NAMES)
    assert len(locked) == 79
    for name, entry in locked.items():
        assert entry["replacement"], f"{name} 에 행선지가 없습니다"
        assert entry["example"], f"{name} 에 예가 없습니다"
        assert entry["removedIn"] == LEGACY_REMOVED_IN == "7.0", name


def test_the_root_answers_no_removed_name() -> None:
    """7.0: 79개 가운데 루트에 남은 것은 없다(`hasattr` 는 False)."""

    document = HwpxDocument.new(empty_first_line=True)
    for name in REMOVED_NAMES:
        assert inspect.getattr_static(HwpxDocument, name, None) is None, name
        assert not hasattr(document, name), name
        assert getattr(document, name, None) is None, name


@pytest.mark.parametrize("name", sorted(REMOVED_NAMES))
def test_a_removed_name_says_where_it_went(name: str) -> None:
    document = HwpxDocument.new(empty_first_line=True)
    with pytest.raises(HwpxAttributeError) as excinfo:
        getattr(document, name)
    error = excinfo.value
    assert isinstance(error, AttributeError)
    assert error.context["replacement"] == REMOVED_NAMES[name].replacement
    assert REMOVED_NAMES[name].replacement in str(error)
    assert REMOVED_NAMES[name].example in str(error)
    assert "7.0" in str(error)
    if REMOVED_NAMES[name].moving:
        # 6.0의 새 자리(doc.text.markdown 등)마저 7.0에서 python-hwpx-automation으로 옮겼다.
        assert error.code == "document-name-moved"
        assert "pip install python-hwpx-automation" in str(error)
        assert "https://github.com/airmang/python-hwpx/blob/main/docs/migration-7.0.md" in str(error.suggestion)
        return
    assert error.code == "document-name-removed"
    # pip 사용자에게 없는 저장소 경로(docs/...) 대신 저장소 문서의 URL을 준다.
    assert "https://github.com/airmang/python-hwpx/blob/main/docs/migration-6.0.md" in str(error.suggestion)


def test_an_unknown_name_is_a_plain_attribute_error() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    with pytest.raises(AttributeError) as excinfo:
        getattr(document, "no_such_name")
    assert not isinstance(excinfo.value, HwpxError)


def _moved_targets(replacement: str) -> list[str]:
    """안내 문구의 새 자리에서 점 경로만 뽑는다.

    ``doc.page.set_header(text=...)`` 는 ``doc.page.set_header``,
    ``a / b`` 는 둘 다, ``paragraph.remove()`` 는 문단 메서드다.
    """

    return [part.strip().split("(")[0] for part in replacement.split(" / ")]


@pytest.mark.parametrize("name", sorted(name for name, entry in REMOVED_NAMES.items() if not entry.moving))
def test_moved_destination_exists(name: str) -> None:
    """새 자리 문자열이 실제 속성으로 풀려야 한다(ARC-08).

    없는 이름을 가리키는 안내를 따라 고친 코드는 또 ``AttributeError`` 가 난다.
    7.0에서 python-hwpx-automation으로 옮긴 자리(``moving``)는 ``test_moved_in_7_0.py`` 가 본다.
    """

    with HwpxDocument.new(empty_first_line=True) as document:
        roots = {"doc": document, "paragraph": document.add_paragraph("x")}
        for target in _moved_targets(REMOVED_NAMES[name].replacement):
            head, *rest = target.split(".")
            assert head in roots, f"{name}: 모르는 뿌리 {target!r}"
            assert rest, f"{name}: 속성 없는 대상 {target!r}"
            owner = roots[head]
            for attribute in rest[:-1]:
                owner = getattr(owner, attribute)
            # 값을 읽지 않고 이름만 본다: 일부 속성은 읽을 때 문서를 훑는다.
            assert hasattr(type(owner), rest[-1]) or hasattr(owner, rest[-1]), (
                f"{name}: {target} 가 없습니다"
            )


def test_repr_does_not_warn_about_its_own_summary() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        repr(document)


# --------------------------------------------------------------------------
# 게이트 ④ `section=0` 수용 — 실물 결함의 회귀 테스트


def test_the_reported_third_party_failure_is_fixed() -> None:
    """jkf87/hwpx-skill 이 우회 코드를 심게 만든 바로 그 호출(지금은 새 자리에서).

    5.x: AttributeError: 'int' object has no attribute 'properties'
    """

    document = HwpxDocument.new(empty_first_line=True)
    document.page.set_header(text="머리말", section=0)


@pytest.mark.parametrize("name", _section_members())
def test_a_section_index_is_accepted_everywhere(name: str) -> None:
    document, call = _prepared(name)
    call(document, section=0)


@pytest.mark.parametrize("name", _section_members())
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section_index": 0}, "hwpx-argument-removed"),
        ({"style_id_ref": 0}, "hwpx-argument-removed"),
    ],
    ids=["out-of-range", "wrong-type", "removed-section-index", "removed-style-id-ref"],
)
def test_bad_section_arguments_raise_typed_errors(name, kwargs, code) -> None:
    """`AttributeError` 가 공개 경로로 새지 않는다 — 전부 typed 다."""

    document, call = _prepared(name)
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
}


def _prepared(name: str):
    document = HwpxDocument.new(empty_first_line=True)
    document.add_paragraph("seed")

    def call(doc, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return getattr(doc, name)(*_ARGS.get(name, ()), **kwargs)

    return document, call


def test_resolver_rejects_bool_as_an_index() -> None:
    """`section=True` 를 인덱스 1 로 읽으면 조용히 엉뚱한 섹션에 쓴다."""

    document = HwpxDocument.new(empty_first_line=True)
    with pytest.raises(HwpxTypeError) as excinfo:
        _resolve.resolve_section(document, True)
    assert excinfo.value.code == "section-invalid-type"


def test_resolver_accepts_objects_negative_indexes_and_none() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    last = document.sections[-1]
    assert _resolve.resolve_section(document, None) is last
    assert _resolve.resolve_section(document, 0) is document.sections[0]
    assert _resolve.resolve_section(document, -1) is last
    assert _resolve.resolve_section(document, last) is last


def test_paragraph_resolution_follows_the_same_rule() -> None:
    document = HwpxDocument.new(empty_first_line=True)
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
    """`section` 을 받는 루트 함수는 전부 한 리졸버를 거친다.

    5.x는 31개 중 6개만 거쳤고, 나머지가 int를 그대로 흘려 `AttributeError`를
    냈다. 이 검사가 그 상태로 되돌아가는 것을 막는다.
    """

    offenders = []
    for func in _class_functions(SRC / "document.py", "HwpxDocument"):
        args = func.args
        names = {a.arg for a in args.kwonlyargs}
        if "section" not in names:
            continue
        calls_resolver = any(
            isinstance(node, ast.Attribute) and node.attr in {"resolve_section"}
            for node in ast.walk(func)
        )
        if not calls_resolver:
            offenders.append(f"document.py::{func.name}")
    assert not offenders, f"리졸버를 우회하는 section 경로: {offenders}"


# --------------------------------------------------------------------------
# 게이트 ⑥ 공개 시그니처에 `HwpxOxml*` 리터럴 0건


def test_new_public_signatures_name_model_types_not_oxml_ones() -> None:
    """6.0에 새로 생긴 루트 표면은 `hwpx.model` 어휘로 말한다.

    5.x부터 있던 유지 멤버(아래 `_FROZEN_5X_RETURNS`)는 빼고 6.0이 새로 만든
    표면에만 적용된다. 7.0에서 지운 79개 이름은 루트에 없다.
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


# hwpx.model 의 계약 멤버 목록과 docs/stable-api.md 의 수는 공개 표면 잠금
# (tests/data/public_surface.json 의 model 층, tests/test_public_surface.py)이 잠근다.


# --------------------------------------------------------------------------
# add_heading — 개요 스타일과 개요 수준이 함께 붙는다


@pytest.mark.parametrize("level", range(1, 11))
def test_add_heading_binds_style_and_outline_level_together(level: int) -> None:
    """5.x의 결함: 개요 번호는 붙는데 스타일은 바탕글(0)."""

    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_heading(f"제목 {level}", level=level)
    style = document.styles[str(paragraph.style_id_ref)]
    assert style.name == f"개요 {level}"

    para_pr = document.oxml.paragraph_property(paragraph.para_pr_id_ref)
    assert para_pr is not None and para_pr.heading is not None
    assert para_pr.heading.type == "OUTLINE"
    assert str(para_pr.heading.level) == str(level - 1)


@pytest.mark.parametrize("level", [0, 11, -1])
def test_add_heading_rejects_levels_outside_the_hwpx_outline(level: int) -> None:
    document = HwpxDocument.new(empty_first_line=True)
    with pytest.raises(HwpxValueError) as excinfo:
        document.add_heading("t", level=level)
    assert excinfo.value.code == "heading-level-out-of-range"
    assert excinfo.value.suggestion


def test_add_heading_accepts_an_explicit_style_name() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_heading("t", level=1, style="개요 3")
    assert document.styles[str(paragraph.style_id_ref)].name == "개요 3"


def test_add_heading_reports_a_missing_outline_style_with_the_available_list() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    with pytest.raises(HwpxLookupError) as excinfo:
        document.add_heading("t", level=1, style="개요1")  # 공백 누락 오타
    assert excinfo.value.code == "style-not-found"
    assert "개요 1" in excinfo.value.context["available"]


# --------------------------------------------------------------------------
# doc.styles 는 이름이 옮겨간 게 아니라 의미가 넓어졌다


def test_styles_namespace_keeps_the_5_x_mapping_contract() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    styles = document.styles
    assert styles["0"].name == "바탕글"
    assert len(styles) == len(document.oxml.styles)
    assert bool(styles) is True
    assert "0" in styles
    assert [entry.name for entry in styles.values()][:2] == ["바탕글", "본문"]
    assert dict(styles.items())["0"] == styles["0"]


def test_namespaces_are_stateless_views_of_the_same_document() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    assert document.styles is not document.styles
    assert document.styles.document is document
