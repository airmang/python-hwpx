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
import warnings

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


def test_all_is_exactly_the_stable_set() -> None:
    """``__all__`` is exactly the 34 stable names — no experimental, no deprecated."""

    assert len(hwpx.__all__) == 34
    assert STABLE_NAMES.isdisjoint(EXPERIMENTAL_NAMES)
    assert STABLE_NAMES.isdisjoint(DEPRECATED_NAMES)
    # __all__에 중복 없음.
    assert len(hwpx.__all__) == len(STABLE_NAMES)


def test_layer_counts() -> None:
    assert len(STABLE_NAMES) == 34
    assert len(EXPERIMENTAL_NAMES) == 12
    # Emptied in 5.0: the 4.x notice promised these names would go in the next major.
    assert len(DEPRECATED_NAMES) == 0
    assert len(ALL_LEGACY_NAMES) == 46


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

    for name in ("analyze_template_formfit", "apply_template_formfit",
                 "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION",
                 "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION"):
        assert name not in hwpx.__all__
        assert name not in DEPRECATED_NAMES
        with pytest.raises(AttributeError):
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

    import re
    from pathlib import Path

    docs = Path(__file__).resolve().parents[1] / "docs"
    exempt = {
        "migration-5.0.md",
        "migration-4.0.md",
        "compatibility-observation-4.x.md",
        "changelog.md",
        "2026-06-02-hwpx-builder-design.md",
    }
    removed = (
        "agent", "authoring", "builder", "design", "presets", "exam",
        "evalplan_fill", "form_fill", "formfill_quality", "guidance_scan",
        "template_formfit", "fill_residue",
    )
    removed_tools = (
        "pii", "official_lint", "table_compute", "style_profile",
        "advanced_generators", "report_parser",
    )
    # A trailing hyphen means a schema identifier (`hwpx.agent-batch/v1`), not
    # an import path. Those are contract names; where they moved is a different
    # question, answered in the schema-freeze note itself.
    pattern = re.compile(
        r"\bhwpx\.(?:" + "|".join(removed) + r")\b(?!-)"
        r"|\bhwpx\.tools\.(?:" + "|".join(removed_tools) + r")\b(?!-)"
    )

    offences: list[str] = []
    for document in sorted(docs.rglob("*.md")):
        if document.name in exempt:
            continue
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            # A line naming the replacement alongside the removed module is a
            # migration pointer, which is the opposite of teaching someone to
            # import it.
            if "hwpx_mcp_server" in line:
                continue
            for match in pattern.finditer(line):
                offences.append(f"{document.relative_to(docs)}:{number}: {match.group(0)}")

    assert not offences, "documentation references removed modules:\n" + "\n".join(offences)
