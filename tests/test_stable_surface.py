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


# 3.8.0 시점 최상위 표면 전수(82). 이 목록에서 이름이 사라지면 = 제거 = 계약 위반.
STABLE_NAMES = frozenset(hwpx.__all__)

EXPERIMENTAL_NAMES = frozenset(_EXPERIMENTAL_EXPORTS)

DEPRECATED_NAMES = frozenset(_DEPRECATED_EXPORTS)

ALL_LEGACY_NAMES = STABLE_NAMES | EXPERIMENTAL_NAMES | DEPRECATED_NAMES


def test_all_is_exactly_the_stable_set() -> None:
    """``__all__``은 stable 67개로 고정된다(experimental/deprecated 미포함)."""

    assert len(hwpx.__all__) == 67
    assert STABLE_NAMES.isdisjoint(EXPERIMENTAL_NAMES)
    assert STABLE_NAMES.isdisjoint(DEPRECATED_NAMES)
    # __all__에 중복 없음.
    assert len(hwpx.__all__) == len(STABLE_NAMES)


def test_layer_counts() -> None:
    assert len(STABLE_NAMES) == 67
    assert len(EXPERIMENTAL_NAMES) == 12
    assert len(DEPRECATED_NAMES) == 4
    assert len(ALL_LEGACY_NAMES) == 83


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


@pytest.mark.parametrize("name", sorted(DEPRECATED_NAMES))
def test_deprecated_top_level_access_warns(name: str) -> None:
    with pytest.warns(DeprecationWarning) as record:
        getattr(hwpx, name)
    message = str(record[0].message)
    assert name in message
    assert "deprecated" in message


@pytest.mark.parametrize("name", ["analyze_template_formfit", "apply_template_formfit"])
def test_formfit_warning_names_replacement_path(name: str) -> None:
    """formfit 쌍 경고는 대체(구조적 form-fill) 경로를 안내해야 한다."""

    with pytest.warns(DeprecationWarning) as record:
        getattr(hwpx, name)
    message = str(record[0].message)
    assert "hwpx.table_patch" in message
    assert "form_fill" in message  # analyze_form_fill/apply_form_fill/verify_form_fill


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
