# SPDX-License-Identifier: Apache-2.0
"""``dev`` extra, CONTRIBUTING, CI가 같은 개발 의존성을 말하는지 본다(ARC-12 (6)).

CONTRIBUTING은 ``.[dev]`` 뒤에 ruff와 pytest를 돌리라고 하는데, 전에는 ``dev``에
ruff·pillow·openpyxl·pyyaml이 없어 그대로 따라 하면 실패했다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def _extras() -> dict[str, list[str]]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return project["project"]["optional-dependencies"]


def test_dev_extra_contains_everything_ci_installs() -> None:
    extras = _extras()
    ci = set(extras["test"]) | set(extras["typecheck"])
    assert ci <= set(extras["dev"]), sorted(ci - set(extras["dev"]))


def test_ci_installs_the_extras_dev_is_built_from() -> None:
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert re.search(r"pip install -e \.\[test,typecheck\]", workflow)


def test_contributing_names_the_dev_extra_and_the_ci_extras() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert 'pip install -e ".[dev]"' in text
    assert 'pip install -e ".[test,typecheck]"' in text
