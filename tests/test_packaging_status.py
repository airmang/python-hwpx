# SPDX-License-Identifier: Apache-2.0
"""패키지 분류와 README가 같은 개발 단계를 말하는지 본다(7.0: 안정)."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_classifier_says_production_stable() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    statuses = [c for c in project["classifiers"] if c.startswith("Development Status ::")]
    assert statuses == ["Development Status :: 5 - Production/Stable"]


def test_readmes_do_not_call_the_package_beta() -> None:
    for name in ("README.md", "README_EN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "Production/Stable" in text, name
        assert "Beta" not in text, name
