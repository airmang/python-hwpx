# SPDX-License-Identifier: Apache-2.0
"""Import-time guidance for the modules python-hwpx 5.0 moved out of core.

``import hwpx.builder`` used to fail with a bare ``No module named
'hwpx.builder'``, which reads as "deleted" rather than "moved". A finder at the
end of :data:`sys.meta_path` answers only for the removed module names, after
every real finder has already missed, and raises ``ModuleNotFoundError`` with
the new location instead.

It is guidance, not a shim: nothing here imports the companion package, and no
removed path comes back as a file. Top-level names come from
``hwpx._MOVED_TO_COMPANION``; this module adds only the nested modules and the
repository-only packages that table does not describe.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from types import ModuleType
from typing import Protocol

COMPANION_DISTRIBUTION = "python-hwpx-automation"
MIGRATION_GUIDE_URL = (
    "https://github.com/airmang/python-hwpx/blob/main/docs/migration-5.0.md"
)

#: Removed modules below a package that still exists in core.
NESTED_MOVED_MODULES: Mapping[str, str] = {
    "hwpx.form_fit.seal": "hwpx_automation.office.form_fill.fit.seal",
    "hwpx.form_fit.wordbox": "hwpx_automation.office.form_fill.fit.wordbox",
    "hwpx.tools.advanced_generators": (
        "hwpx_automation.office.authoring.advanced_generators"
    ),
    "hwpx.tools.official_lint": "hwpx_automation.office.compliance.official_lint",
    "hwpx.tools.pii": "hwpx_automation.office.compliance.pii",
    "hwpx.tools.report_parser": "hwpx_automation.office.authoring.report_parser",
    "hwpx.tools.style_profile": "hwpx_automation.office.authoring.style_profile",
    "hwpx.tools.table_compute": "hwpx_automation.office.utilities.table_compute",
}

#: Removed packages that were repository QA, not product API. They have no
#: installable replacement; they live in a source checkout.
REPOSITORY_ONLY_MODULES: Mapping[str, str] = {
    "hwpx.benchmark": "python-hwpx 저장소 체크아웃에서 실행하세요.",
    "hwpx.conformance": "python-hwpx 저장소 체크아웃에서 실행하세요.",
    "hwpx.tools.fuzz": "python-hwpx 저장소 체크아웃의 scripts/fuzz/를 쓰세요.",
}


class _Surface(Protocol):
    kind: str
    target_module: str | None
    target_name: str | None


def moved_modules(companion: Mapping[str, _Surface]) -> dict[str, str]:
    """Return ``{legacy module: new module}`` for every moved module name."""

    table = {
        f"hwpx.{name}": surface.target_module
        for name, surface in companion.items()
        if surface.kind in {"module", "renamed"}
        and surface.target_name is None
        and surface.target_module is not None
    }
    table.update(NESTED_MOVED_MODULES)
    return dict(sorted(table.items()))


def moved_message(legacy: str, target: str) -> str:
    return (
        f"{legacy}은(는) python-hwpx 5.0에서 {COMPANION_DISTRIBUTION} 패키지로 "
        f"이동했습니다. 새 경로: {target}\n"
        f"    pip install {COMPANION_DISTRIBUTION}\n"
        f"    import {target}\n"
        f'4.x를 계속 쓰려면: pip install "python-hwpx<5"\n'
        f"전체 대체표: {MIGRATION_GUIDE_URL}"
    )


def repository_only_message(legacy: str, replacement: str) -> str:
    return (
        f"{legacy}은(는) python-hwpx 5.0부터 배포본에 들어가지 않습니다. "
        f"{replacement}\n"
        f"전체 대체표: {MIGRATION_GUIDE_URL}"
    )


class _MovedModuleGuide:
    """Meta-path finder that explains removed module names instead of loading them."""

    def __init__(self, moved: Mapping[str, str]) -> None:
        self._moved = dict(moved)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> None:
        moved = self._moved.get(fullname)
        if moved is not None:
            raise ModuleNotFoundError(moved_message(fullname, moved), name=fullname)
        repository_only = REPOSITORY_ONLY_MODULES.get(fullname)
        if repository_only is not None:
            raise ModuleNotFoundError(
                repository_only_message(fullname, repository_only), name=fullname
            )
        return None


def install(companion: Mapping[str, _Surface]) -> None:
    """Append the guide to ``sys.meta_path`` once, behind every real finder."""

    if any(isinstance(finder, _MovedModuleGuide) for finder in sys.meta_path):
        return
    sys.meta_path.append(_MovedModuleGuide(moved_modules(companion)))
