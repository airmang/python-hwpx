# SPDX-License-Identifier: Apache-2.0
"""pyproject의 정확한 패키지 목록이 소스 트리와 어긋나지 않는지 본다.

`[tool.setuptools] packages`는 일부러 손으로 적는 목록이다. 그래서 새 하위
패키지를 만들고 목록에 넣는 것을 잊으면 그 패키지는 휠에 실리지 않는다.
편집 설치(`pip install -e`)로 도는 테스트는 소스 트리를 그대로 보므로 이 누락을
못 잡는다. 6.12까지 `hwpx.integrations`(LangChain 로더·LlamaIndex 리더)가 이렇게
빠진 채 배포됐다. 이 테스트는 휠을 빌드하지 않고 소스 트리와 목록만 견준다.
"""
from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI lane
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _declared_packages() -> set[str]:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = metadata["tool"]["setuptools"]["packages"]
    assert isinstance(packages, list)
    return set(packages)


def _source_packages() -> set[str]:
    """`src/hwpx` 아래에서 파이썬 모듈을 담은 모든 폴더(패키지 이름으로)."""
    found: set[str] = set()
    for module in (SRC / "hwpx").rglob("*.py"):
        if "__pycache__" in module.parts:
            continue
        found.add(".".join(module.parent.relative_to(SRC).parts))
    return found


def _packages_with_init() -> set[str]:
    return {
        ".".join(init.parent.relative_to(SRC).parts)
        for init in (SRC / "hwpx").rglob("__init__.py")
        if "__pycache__" not in init.parts
    }


def test_every_regular_package_is_in_the_wheel_package_list() -> None:
    missing = sorted(_packages_with_init() - _declared_packages())
    assert not missing, (
        "src/hwpx 아래 __init__.py가 있는 폴더가 pyproject.toml "
        f"[tool.setuptools] packages에 없어 휠에 실리지 않는다: {missing}"
    )


def test_every_folder_with_python_modules_is_in_the_wheel_package_list() -> None:
    # `hwpx.opc`처럼 __init__.py 없는 이름공간 패키지도 모듈을 담고 있으면 목록에 있어야 한다.
    missing = sorted(_source_packages() - _declared_packages())
    assert not missing, (
        "파이썬 모듈이 든 폴더가 pyproject.toml packages에 없어 휠에 실리지 않는다: "
        f"{missing}"
    )


def test_every_declared_package_exists_in_the_source_tree() -> None:
    stale = sorted(
        name for name in _declared_packages() if not (SRC / Path(*name.split("."))).is_dir()
    )
    assert not stale, f"pyproject.toml packages에 소스 트리에 없는 패키지가 있다: {stale}"


def test_ci_imports_every_package_from_the_built_wheel() -> None:
    # 편집 설치로 도는 pytest 대신, 빌드한 휠을 빈 venv에 깔아 모든 패키지를 가져온다.
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "python scripts/check_wheel_imports.py" in workflow
    assert "python -m build --wheel" in workflow

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_wheel_imports", ROOT / "scripts" / "check_wheel_imports.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.declared_packages()) == _declared_packages()


def test_moved_packages_are_not_declared() -> None:
    # 6.12.0 휠에 빠졌던 hwpx.integrations는 7.0에서 hwpx.ingest와 함께
    # python-hwpx-automation으로 옮겼다. 목록에 남으면 없는 패키지를 싣게 된다.
    declared = _declared_packages()
    assert "hwpx.integrations" not in declared
    assert "hwpx.ingest" not in declared
    assert "hwpx._document.ns" in declared
