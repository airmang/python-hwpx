from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as metadata_version

import pytest

import hwpx


def test_version_matches_distribution_metadata_when_installed() -> None:
    try:
        installed_version = metadata_version("python-hwpx")
    except PackageNotFoundError:
        pytest.skip("설치된 배포 메타데이터가 없어 비교를 건너뜁니다.")

    assert hwpx.__version__ == installed_version


def test_resolve_version_returns_fallback_when_metadata_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_not_found(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(hwpx, "_metadata_version", _raise_not_found)

    assert hwpx._resolve_version() == "0+unknown"
