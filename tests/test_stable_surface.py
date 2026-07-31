# SPDX-License-Identifier: Apache-2.0
"""최상위 ``hwpx`` 공개 표면의 3계층 경계 계약.

- stable: ``__all__`` 고정 집합. 접근 시 경고 없음.
- experimental: ``hwpx.experimental``로 재내보내짐. 최상위 접근 시 ``DeprecationWarning``.
- deprecated: 대체 경로 안내 경고. 최상위 접근 시 ``DeprecationWarning``.

4.0.0에서 제거되는 이름은 0개 — 기존 82개 이름 전부 최상위로 계속 import 가능해야
한다. 4.0.0에서 stable에 ``HwpxError`` 1개가 추가되어 stable 67·전체 83이 된다.
"""

from __future__ import annotations

import importlib
import re
import warnings
from pathlib import Path

import pytest

import hwpx
from hwpx import _DEPRECATED_EXPORTS, _EXPERIMENTAL_EXPORTS


# The 5.0 top-level surface. A name leaving this set is a removal and a contract
# break, which is the whole point of pinning the counts below: the surface should
# only change when someone means it to.
STABLE_NAMES = frozenset(hwpx.__all__)

EXPERIMENTAL_NAMES = frozenset(_EXPERIMENTAL_EXPORTS)

DEPRECATED_NAMES = frozenset(_DEPRECATED_EXPORTS)

ALL_LEGACY_NAMES = STABLE_NAMES | EXPERIMENTAL_NAMES | DEPRECATED_NAMES
RETIRED_NAMES = frozenset(
    {
        "analyze_template_formfit",
        "apply_template_formfit",
        "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION",
        "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION",
    }
)

REMOVED_MODULES = (
    "agent",
    "authoring",
    "builder",
    "design",
    "presets",
    "exam",
    "evalplan_fill",
    "form_fill",
    "formfill_quality",
    "guidance_scan",
    "template_formfit",
    "fill_residue",
    "visual",
)
REMOVED_TOOL_MODULES = (
    "pii",
    "official_lint",
    "table_compute",
    "style_profile",
    "advanced_generators",
    "report_parser",
)
REMOVED_FORM_FIT_SUBMODULES = ("seal", "wordbox")
MOVED_NAMES = tuple(sorted(getattr(hwpx, "_MOVED_TO_COMPANION", {})))


def _joined_pattern(names: tuple[str, ...]) -> str:
    return "|".join(re.escape(name) for name in names)


REMOVED_REFERENCE_PATTERN = re.compile(
    r"\bhwpx\.(?:"
    + _joined_pattern(REMOVED_MODULES)
    + r")(?=\.|\b)(?!-)"
    + r"|\bhwpx\.tools\.(?:"
    + _joined_pattern(REMOVED_TOOL_MODULES)
    + r")(?=\.|\b)(?!-)"
    + r"|\bhwpx\.form_fit\.(?:"
    + _joined_pattern(REMOVED_FORM_FIT_SUBMODULES)
    + r")(?=\.|\b)(?!-)"
    + r"|\b(?:src/)?hwpx/(?:"
    + _joined_pattern(REMOVED_MODULES)
    + r")(?=/|\b)(?!-)"
    + r"|\b(?:src/)?hwpx/tools/(?:"
    + _joined_pattern(REMOVED_TOOL_MODULES)
    + r")(?=/|\b)(?!-)"
    + r"|\b(?:src/)?hwpx/form_fit/(?:"
    + _joined_pattern(REMOVED_FORM_FIT_SUBMODULES)
    + r")(?=/|\b)(?!-)"
    + (
        r"|from\s+hwpx\s+import\s+[^\n]*\b(?:"
        + _joined_pattern(MOVED_NAMES)
        + r")\b"
        if MOVED_NAMES
        else ""
    )
)


def test_all_is_exactly_the_stable_set() -> None:
    """``__all__`` is exactly the 34 stable names — no experimental, no deprecated."""

    assert len(hwpx.__all__) == 34
    assert STABLE_NAMES.isdisjoint(EXPERIMENTAL_NAMES)
    assert STABLE_NAMES.isdisjoint(DEPRECATED_NAMES)
    # __all__에 중복 없음.
    assert len(hwpx.__all__) == len(STABLE_NAMES)


def test_layer_counts() -> None:
    assert len(STABLE_NAMES) == 34
    assert len(EXPERIMENTAL_NAMES) == 15
    # Emptied in 5.0: the 4.x notice promised these names would go in the next major.
    assert len(DEPRECATED_NAMES) == 0
    assert len(ALL_LEGACY_NAMES) == 49


def test_hwpx_error_is_stable_and_importable() -> None:
    """4.0.0 신규 stable: 구조화 예외 베이스는 경고 없이 최상위 import 가능하다."""

    assert "HwpxError" in STABLE_NAMES
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert hwpx.HwpxError is importlib.import_module("hwpx.errors").HwpxError


@pytest.mark.parametrize("name", sorted(ALL_LEGACY_NAMES))
def test_every_name_still_importable(name: str) -> None:
    """제거 0건: 82개 이름 전부 최상위 접근으로 여전히 해석된다."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        value = getattr(hwpx, name)
    assert value is not None


@pytest.mark.parametrize("name", sorted(STABLE_NAMES - {"__version__"}))
def test_stable_access_does_not_warn(name: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        getattr(hwpx, name)  # 경고가 나면 DeprecationWarning이 예외로 승격되어 실패.


def test_version_access_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert isinstance(hwpx.__version__, str)


@pytest.mark.parametrize("name", sorted(EXPERIMENTAL_NAMES))
def test_experimental_top_level_access_warns(name: str) -> None:
    with pytest.warns(DeprecationWarning) as record:
        getattr(hwpx, name)
    message = str(record[0].message)
    assert name in message
    assert "hwpx.experimental" in message


# The deprecated-access test is gone rather than left parametrized over an empty
# set. pytest reports that as a skip, which reads as "environment-gated" when it
# actually means "this asserts nothing" — the same silent-pass shape this work has
# been removing. 5.0 ships no deprecated top-level names, and their absence is
# asserted directly below.


def test_removed_formfit_names_are_gone_not_merely_warned() -> None:
    """The 4.x notice said these go in the next major, so they must be absent.

    A name that still resolves with a warning has not been removed; it has been
    postponed. Asserting absence is what makes the earlier promise checkable, and
    the replacement path now lives in the migration guide rather than in a warning
    nobody sees until they hit it.
    """

    assert frozenset(hwpx._RETIRED_SURFACES) == RETIRED_NAMES
    for name in RETIRED_NAMES:
        assert name not in hwpx.__all__
        assert name not in DEPRECATED_NAMES
        with pytest.raises(hwpx.RetiredSurface):
            getattr(hwpx, name)


def test_experimental_module_reexports_all_experimental_names() -> None:
    experimental = importlib.import_module("hwpx.experimental")
    assert frozenset(experimental.__all__) == EXPERIMENTAL_NAMES
    for name in EXPERIMENTAL_NAMES:
        assert hasattr(experimental, name)


def test_experimental_module_import_does_not_warn() -> None:
    """권장 경로(hwpx.experimental)는 경고를 내지 않는다."""

    import hwpx.experimental as experimental  # noqa: F401  (재import는 캐시됨)

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for name in EXPERIMENTAL_NAMES:
            getattr(experimental, name)


def test_experimental_top_level_resolves_same_object_as_experimental_module() -> None:
    experimental = importlib.import_module("hwpx.experimental")
    for name in EXPERIMENTAL_NAMES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            top_level = getattr(hwpx, name)
        assert top_level is getattr(experimental, name)


def test_dir_includes_all_three_layers() -> None:
    listing = set(dir(hwpx))
    assert ALL_LEGACY_NAMES <= listing


def test_unknown_attribute_still_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        hwpx.this_name_does_not_exist  # noqa: B018


def test_documentation_does_not_teach_a_module_this_package_no_longer_has() -> None:
    """A library whose API reference documents absent modules is not documented.

    5.0 removed the workflow families, and the docs tree kept describing some of
    them: ``api_reference.md`` had a "Proposal presets" section with a working
    ``from hwpx.presets import ...`` example, and ``usage.md`` had the same in
    prose. Both survived every gate — the suites import the package, not the
    manual.

    The migration guide is exempt: naming a removed module is exactly its job.
    Historical design notes and the 4.x compatibility record are exempt for the
    same reason — they describe what was true when written.
    """

    docs = Path(__file__).resolve().parents[1] / "docs"
    exempt = {
        "migration-5.0.md",
        "migration-4.0.md",
        "compatibility-observation-4.x.md",
        "changelog.md",
        "2026-06-02-hwpx-builder-design.md",
    }
    # A trailing hyphen means a schema identifier (`hwpx.agent-batch/v1`), not
    # an import path. Those are contract names; where they moved is a different
    # question, answered in the schema-freeze note itself.
    # 모듈 경로만 보면 절반만 잡는다. 공개 코드에서 더 흔한 형태는
    # ``from hwpx import create_document_from_plan`` 처럼 **이름**을 가져오는
    # 쪽이고(66·56개 파일), 그건 hwpx.<module> 패턴에 걸리지 않는다.
    # 이동한 이름 표는 패키지가 이미 갖고 있으므로 그것을 쓴다.
    offences: list[str] = []
    for document in sorted(docs.rglob("*.md")):
        if document.name in exempt:
            continue
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            # 대체 경로를 함께 적은 줄은 이주 안내지 import 지침이 아니다.
            # 다만 "같은 줄에 대체 이름이 있으면 면제"는 너무 헐겁다 — 주석
            # 한 줄로 실제 import 문이 면제된다. 실행되는 코드는 면제하지
            # 않고 산문에서만 면제한다.
            stripped = line.lstrip()
            if not stripped.startswith(("from ", "import ")) and (
                "hwpx_automation" in line or "hwpx_mcp_server" in line
            ):
                continue
            for match in REMOVED_REFERENCE_PATTERN.finditer(line):
                offences.append(f"{document.relative_to(docs)}:{number}: {match.group(0)}")

    assert not offences, "documentation references removed modules:\n" + "\n".join(offences)


@pytest.mark.parametrize(
    "reference",
    (
        "hwpx.visual.oracle",
        "src/hwpx/visual/oracle.py",
        "hwpx/visual/oracle.py",
        "hwpx.form_fit.seal",
        "src/hwpx/form_fit/wordbox.py",
        "hwpx.tools.style_profile",
        "src/hwpx/tools/official_lint.py",
    ),
)
def test_removed_reference_gate_catches_dotted_and_slash_forms(
    reference: str,
) -> None:
    assert REMOVED_REFERENCE_PATTERN.search(reference)


@pytest.mark.parametrize(
    "schema",
    (
        "hwpx.visual-review.v1",
        "hwpx.visual-qa-metrics/v2",
        "hwpx.agent-batch/v1",
    ),
)
def test_removed_reference_gate_preserves_schema_identifiers(schema: str) -> None:
    assert REMOVED_REFERENCE_PATTERN.search(schema) is None


def test_current_scripts_do_not_reference_removed_core_paths() -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    offences: list[str] = []
    for script in sorted(scripts.rglob("*")):
        if not script.is_file() or script.suffix.casefold() not in {
            ".applescript",
            ".md",
            ".ps1",
            ".py",
        }:
            continue
        for number, line in enumerate(
            script.read_text(encoding="utf-8").splitlines(),
            1,
        ):
            for match in REMOVED_REFERENCE_PATTERN.finditer(line):
                offences.append(
                    f"{script.relative_to(scripts)}:{number}: {match.group(0)}"
                )
    assert not offences, "current scripts reference removed core paths:\n" + "\n".join(
        offences
    )


def test_every_python_fence_in_the_docs_parses() -> None:
    """```python 이라고 적은 블록은 파이썬이어야 한다.

    ``safe-write-contract.md``는 시그니처를 보여주려고 함수 **선언** 표기의
    ``*``를 호출문에 섞어 적었다. 붙여넣으면 SyntaxError다. 파이썬이라고
    표시한 것을 파싱조차 못 하면, 그 아래 설명이 아무리 정확해도 독자는
    첫 줄에서 막힌다.

    본문 조각(``self`` 나 앞 문맥 변수가 필요한 발췌)은 파싱은 되므로 이
    검사와 충돌하지 않는다 — 실행이 아니라 문법만 본다.
    """

    import ast
    import re
    from pathlib import Path

    docs = Path(__file__).resolve().parents[1] / "docs"
    broken: list[str] = []
    for document in sorted(docs.rglob("*.md")):
        text = document.read_text(encoding="utf-8")
        for match in re.finditer(r"```python\n(.*?)\n```", text, re.DOTALL):
            line = text[: match.start()].count("\n") + 1
            try:
                ast.parse(match.group(1))
            except SyntaxError as exc:
                broken.append(f"{document.relative_to(docs)}:{line}: {exc.msg}")

    assert not broken, "python 블록이 파싱되지 않는다:\n  " + "\n  ".join(broken)
