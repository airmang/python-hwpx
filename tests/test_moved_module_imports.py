# SPDX-License-Identifier: Apache-2.0
"""``import`` of a module moved out in 5.0 names where it went."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import hwpx
from hwpx import _moved_modules

ROOT = Path(__file__).resolve().parents[1]
REMOVED = ROOT / "docs" / "architecture" / "module-ownership-removed-5.0.json"
MIGRATION_GUIDE = ROOT / "docs" / "migration-5.0.md"

MOVED = _moved_modules.moved_modules(hwpx._MOVED_TO_COMPANION)
GUIDED = {**MOVED, **_moved_modules.REPOSITORY_ONLY_MODULES}


def _removed_module_names() -> set[str]:
    paths = json.loads(REMOVED.read_text(encoding="utf-8"))["paths"]
    names = set()
    for path in paths:
        dotted = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        names.add(dotted.removesuffix(".__init__"))
    return names


def test_every_removed_module_is_guided_by_itself_or_a_removed_parent() -> None:
    unguided = []
    for name in sorted(_removed_module_names()):
        parts = name.split(".")
        ancestors = {".".join(parts[:end]) for end in range(2, len(parts) + 1)}
        if not ancestors & set(GUIDED):
            unguided.append(name)
    assert not unguided


@pytest.mark.parametrize(("legacy", "target"), sorted(MOVED.items()))
def test_importing_a_moved_module_names_its_new_location(legacy: str, target: str) -> None:
    with pytest.raises(ModuleNotFoundError) as raised:
        importlib.import_module(legacy)

    message = str(raised.value)
    assert raised.value.name == legacy
    assert f"새 경로: {target}" in message
    assert "pip install python-hwpx-automation" in message
    assert _moved_modules.MIGRATION_GUIDE_URL in message
    assert target.startswith("hwpx_automation.")


@pytest.mark.parametrize("legacy", sorted(_moved_modules.REPOSITORY_ONLY_MODULES))
def test_importing_a_repository_only_package_says_it_is_not_shipped(legacy: str) -> None:
    with pytest.raises(ModuleNotFoundError, match="배포본에 들어가지 않습니다") as raised:
        importlib.import_module(legacy)
    assert raised.value.name == legacy


def test_the_issue_import_forms_reach_the_guidance() -> None:
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.office.authoring.builder"):
        from hwpx.builder import Paragraph  # noqa: F401
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.office.exam"):
        import hwpx.exam.parser  # noqa: F401
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.office.compliance.pii"):
        from hwpx.tools.pii import scan_personal_info  # noqa: F401


def test_guidance_does_not_load_the_companion_or_touch_unrelated_names() -> None:
    with pytest.raises(ModuleNotFoundError) as raised:
        importlib.import_module("hwpx.no_such_module")
    assert str(raised.value) == "No module named 'hwpx.no_such_module'"
    assert importlib.util.find_spec("hwpx.house_style") is None
    assert importlib.util.find_spec("hwpx.tools.mail_merge") is not None
    assert not any(name.startswith("hwpx_automation") for name in sys.modules)


def test_the_guide_is_installed_once_behind_the_real_finders() -> None:
    _moved_modules.install(hwpx._MOVED_TO_COMPANION)

    guides = [
        index
        for index, finder in enumerate(sys.meta_path)
        if isinstance(finder, _moved_modules._MovedModuleGuide)
    ]
    assert len(guides) == 1
    path_finder = sys.meta_path.index(importlib.machinery.PathFinder)
    assert guides[0] > path_finder


def test_the_migration_guide_module_table_matches_the_guidance() -> None:
    guide = MIGRATION_GUIDE.read_text(encoding="utf-8")
    section = guide.split("### Module paths", 1)[1].split("\n---", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0].startswith("`hwpx."):
            rows[cells[0].strip("`")] = cells[1]

    assert set(rows) == set(GUIDED)
    assert {legacy: rows[legacy].strip("`") for legacy in MOVED} == MOVED
