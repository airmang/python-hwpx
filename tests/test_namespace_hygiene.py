# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B2/B3 게이트 — 네임스페이스 위생.

두 가지를 기계로 지킨다.

**① 내부가 자기 shim 을 되부르지 않는다.** 소유 모듈이 `doc.set_page_size(...)`
같은 **옛 이름**을 부르면, `doc.page.setup()` 만 부른 사용자가 자기가 부른 적
없는 이름의 `DeprecationWarning` 을 받는다. 6.0 에서 이건 새 API 가 깨끗하지
않다는 뜻이다.

**② 능력 레지스트리가 새 경로로 해석된다.** `_CAPABILITY_AREAS` 의
`authoring_methods` 는 여전히 5.x 루트 이름을 가리킨다(그 이름들은 shim 으로
살아 있으므로 유효하다). 6.0 의 네임스페이스 경로도 실재하는지 함께 확인한다 —
레지스트리가 표면 분할의 근거였으므로, 근거와 결과가 어긋나면 안 된다.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

from hwpx.capabilities import _CAPABILITY_AREAS
from hwpx.document import HwpxDocument

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "hwpx"
SHIM_LOCK = pathlib.Path(__file__).parent / "data" / "document_legacy_shims.json"

#: 소유 모듈이 파사드 shim 을 되부르는 지점의 현재 수. **감소만 허용한다.**
#:
#: 6.0 착수 시점 37 → `_document/layout.py` 9건 정리(WP-B2) → 28.
#: 나머지는 각 파일 소유 패키지가 정리한다. 이 숫자가 늘면 새 코드가 옛
#: 표면으로 다시 배선됐다는 뜻이므로 CI 가 막는다.
MAX_INTERNAL_SHIM_CALLBACKS = 28

_DOCLIKE = re.compile(r"^(doc|document)$")


def _internal_shim_callbacks() -> list[str]:
    shims = set(json.loads(SHIM_LOCK.read_text(encoding="utf-8")))
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "_legacy.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        documents = {
            node.arg
            for node in ast.walk(tree)
            if isinstance(node, ast.arg)
            and node.annotation is not None
            and "HwpxDocument" in ast.unparse(node.annotation)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in shims:
                continue
            value = node.value
            if isinstance(value, ast.Name) and (
                value.id in documents or _DOCLIKE.match(value.id)
            ):
                found.append(
                    f"{path.relative_to(SRC.parent.parent)}:{node.lineno} "
                    f"{value.id}.{node.attr}"
                )
    return sorted(found)


def test_internal_shim_callbacks_only_shrink() -> None:
    found = _internal_shim_callbacks()
    assert len(found) <= MAX_INTERNAL_SHIM_CALLBACKS, (
        "내부에서 파사드 shim 을 되부르는 지점이 늘었습니다. 새 코드는 소유 "
        "모듈의 함수를 직접 불러야 합니다:\n" + "\n".join(found)
    )


def test_the_page_namespace_is_free_of_internal_callbacks() -> None:
    """WP-B2 가 정리한 `layout.py` 는 0 이어야 한다."""

    offenders = [entry for entry in _internal_shim_callbacks() if "layout.py" in entry]
    assert offenders == [], offenders


@pytest.mark.parametrize(
    "namespace,verbs",
    [
        ("page", ["setup", "set_header", "set_footer", "set_page_number"]),
        ("tables", ["map", "fill_by_path", "find_cell_by_label", "merge_cells"]),
        ("fields", ["add", "fill", "add_check_box", "set_check_box"]),
        ("shapes", ["add_line", "add_rectangle", "add_ellipse", "add_chart", "add_equation"]),
        ("media", ["add_image", "remove_image", "replace_picture", "picture_references"]),
        ("notes", ["add_footnote", "add_endnote", "add_memo", "attach", "remove_memo"]),
        ("refs", ["add_bookmark", "add_hyperlink"]),
        ("tracking", ["insert", "delete", "replace", "add_change", "change", "author"]),
        ("styles", ["resolve", "ensure_run", "apply_paragraph_format"]),
        ("text", ["plain", "markdown", "html", "runs", "find_runs", "replace"]),
    ],
)
def test_every_namespace_exposes_its_verbs(namespace: str, verbs: list[str]) -> None:
    surface = getattr(HwpxDocument.new(), namespace)
    missing = [verb for verb in verbs if not hasattr(surface, verb)]
    assert missing == [], f"doc.{namespace} 에 없는 멤버: {missing}"


def test_every_capability_authoring_method_resolves_on_the_document() -> None:
    """레지스트리가 표면 분할의 근거였으므로 근거와 결과가 어긋나면 안 된다."""

    document = HwpxDocument.new()
    for row in _CAPABILITY_AREAS:
        for method in row["authoring_methods"]:
            assert hasattr(document, method), f"{row['area']}: {method}"


#: 능력 영역 → 6.0 네임스페이스. 설계서 §1.2 의 도출표를 코드로 고정한다.
AREA_NAMESPACES = {
    "paragraph-table-authoring": None,  # 루트
    "table-create": None,               # 루트
    "picture": None,                    # 루트(add_picture) + doc.media
    "shape-authoring": "shapes",
    "shape-escape-hatch": "shapes",
    "curve-objects": "shapes",
    "chart": "shapes",
    "equation": "shapes",
    "redline": "tracking",
    "memo": "notes",
    "footnote-endnote": "notes",
    "toc-crossref": "refs",
    "form-field-create": "fields",
    "check-box": "fields",
    "table-structure": "tables",
    "form-fill": "tables",
    "edit-plan": None,
    "encrypted-hwpx": None,
    "hwp5-binary": None,
}


def test_the_namespace_map_covers_every_capability_area() -> None:
    assert {row["area"] for row in _CAPABILITY_AREAS} == set(AREA_NAMESPACES)


def test_areas_with_a_namespace_actually_have_one() -> None:
    document = HwpxDocument.new()
    for area, namespace in AREA_NAMESPACES.items():
        if namespace is None:
            continue
        assert hasattr(document, namespace), f"{area} → doc.{namespace}"
