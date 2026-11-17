# SPDX-License-Identifier: Apache-2.0
"""sdist가 돌릴 수 없는 테스트 파일을 싣지 않는지 본다.

6.12.0 sdist는 setuptools 기본 규칙대로 ``tests/test*.py`` 310개를 실었지만 그
테스트가 기대는 fixtures·conftest는 빠져 있어 sdist만으로는 하나도 돌릴 수 없었다.
``MANIFEST.in``의 ``prune tests``가 그 파일들을 뺀다.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from tests.distribution_build import build

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_prunes_tests() -> None:
    lines = [
        line.strip()
        for line in (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "prune tests" in lines


@pytest.fixture(scope="module")
def sdist_members(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    output = tmp_path_factory.mktemp("sdist-contents")
    build(output, "--sdist", capture_output=True, text=True)
    sdist = next(output.glob("*.tar.gz"))
    with tarfile.open(sdist, "r:gz") as archive:
        return [member.name for member in archive.getmembers() if member.isfile()]


def test_sdist_carries_no_test_files(sdist_members: list[str]) -> None:
    shipped_tests = [name for name in sdist_members if "/tests/" in name]
    assert shipped_tests == []


def test_sdist_still_carries_every_source_package(sdist_members: list[str]) -> None:
    assert any(name.endswith("/src/hwpx/__init__.py") for name in sdist_members)
    assert any(name.endswith("/src/hwpx/hwp5/reader.py") for name in sdist_members)
    assert any(name.endswith("/src/hwpx/_document/ns/text.py") for name in sdist_members)
    assert any(name.endswith("/pyproject.toml") for name in sdist_members)
    assert any(name.endswith("/README.md") for name in sdist_members)
