# SPDX-License-Identifier: Apache-2.0
"""Import-time guidance for what python-hwpx moved out of core (5.0 and 7.0).

``import hwpx.builder`` used to fail with a bare ``No module named
'hwpx.builder'``, which reads as "deleted" rather than "moved". A finder at the
end of :data:`sys.meta_path` answers only for the removed module names, after
every real finder has already missed, and raises ``ModuleNotFoundError`` with
the new location instead.

Two moves are described here. 5.0 moved the application workflows (document
plans, genre checks, agent runtime) to python-hwpx-automation. 7.0 moved what
converts or guesses rather than reads and writes what the file says — Markdown
and HTML, ingest, the framework loaders, label-guided form filling, mail merge,
previews, format rules and the report helpers — to the same package. Each entry
knows which release moved it and which migration guide explains it; the 5.0
wording is unchanged.

It is guidance, not a shim: nothing here imports the companion package, and no
removed path comes back as a file. Top-level names come from
``hwpx._MOVED_TO_COMPANION``; this module adds the nested modules, the
repository-only packages and the names 7.0 moved out of modules that stay
(:data:`MOVED_IN_7_0_NAMES`, raised by those modules' ``__getattr__``).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Protocol

COMPANION_DISTRIBUTION = "python-hwpx-automation"
#: The command an error tells the reader to run. ``-U`` and the floor matter: python-hwpx 7 works with
#: the companion from 8.0 on, and a bare ``pip install`` beside an installed 7.x companion keeps that
#: one and pulls python-hwpx back to 6.x to suit it.
COMPANION_INSTALL = f'pip install -U "{COMPANION_DISTRIBUTION}>=8"'
MIGRATION_GUIDE_URL = (
    "https://github.com/airmang/python-hwpx/blob/main/docs/migration-5.0.md"
)
MIGRATION_GUIDE_7_0_URL = (
    "https://github.com/airmang/python-hwpx/blob/main/docs/migration-7.0.md"
)
#: The release a move happened in → the guide that lists it.
MIGRATION_GUIDES: Mapping[str, str] = {
    "5.0": MIGRATION_GUIDE_URL,
    "7.0": MIGRATION_GUIDE_7_0_URL,
}

#: Removed modules below a package that still exists in core (5.0).
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

_MARKDOWN = "hwpx_automation.markdown"
_FORMS = "hwpx_automation.forms"
_MAIL_MERGE = "hwpx_automation.mail_merge"
_PREVIEW = "hwpx_automation.preview"
_COMPLIANCE = "hwpx_automation.office.compliance"
_UTILITIES = "hwpx_automation.office.utilities"

#: Modules 7.0 moved out from below a package that stays. ``hwpx.ingest`` and
#: ``hwpx.integrations`` are whole packages and come from ``hwpx._MOVED_TO_COMPANION``;
#: their submodules are guided through them.
MOVED_IN_7_0_MODULES: Mapping[str, str] = {
    "hwpx.equation.mathml": _PREVIEW,
    "hwpx.equation.render": _PREVIEW,
    "hwpx.tools.document_viewer": _PREVIEW,
    "hwpx.tools.form_choices": _FORMS,
    "hwpx.tools.format_rules": "hwpx_automation.format_rules",
    "hwpx.tools.layout_preview": _PREVIEW,
    "hwpx.tools.mail_merge": _MAIL_MERGE,
    "hwpx.tools.markdown_export": _MARKDOWN,
    "hwpx.tools.markdown_import": _MARKDOWN,
    "hwpx.tools.report_utils": _UTILITIES,
    "hwpx.tools.table_cleanup": _UTILITIES,
}

#: Removed packages that were repository QA, not product API. They have no
#: installable replacement; they live in a source checkout.
REPOSITORY_ONLY_MODULES: Mapping[str, str] = {
    "hwpx.benchmark": "python-hwpx 저장소 체크아웃에서 실행하세요.",
    "hwpx.conformance": "python-hwpx 저장소 체크아웃에서 실행하세요.",
    "hwpx.tools.fuzz": "python-hwpx 저장소 체크아웃의 scripts/fuzz/를 쓰세요.",
}


@dataclass(frozen=True, slots=True)
class MovedName:
    """A name 7.0 moved out of a module that stays: where it lives now."""

    target_module: str
    #: The name there, when it is not the old one (``export_markdown`` → ``to_markdown``).
    target_name: str | None = None

    def import_statement(self, legacy_name: str) -> str:
        return f"from {self.target_module} import {self.target_name or legacy_name}"


def _names(target_module: str, *names: str) -> dict[str, MovedName]:
    return {name: MovedName(target_module) for name in names}


_PREVIEW_NAMES = ("LayoutPreview", "PreviewPage", "render_layout_preview")
_VIEWER_NAMES = ("DocumentViewer", "FIDELITY_BADGE", "render_document_viewer")
_INGEST_NAMES = (
    "ConversionAttempt",
    "DocumentConverter",
    "DocumentIngestError",
    "DocumentIngestResult",
    "DocumentIngestor",
    "DocumentSourceInfo",
    "UnsupportedDocumentFormat",
)
_MAIL_MERGE_NAMES = (
    "MAIL_MERGE_REPORT_VERSION",
    "inspect_mail_merge_placeholders",
    "load_mail_merge_rows",
    "merge_template_rows",
)
_REFERENCE_NAMES = ("REFERENCE_CONSISTENCY_REPORT_VERSION", "inspect_reference_consistency")
_LABEL_NAMES = (
    "PathDirection",
    "SearchDirection",
    "TableCellReference",
    "TableFillApplied",
    "TableFillFailed",
    "TableFillResult",
    "TableFormSlot",
    "TableFormSlotsResult",
    "TableLabelCandidate",
    "TableLabelMatch",
    "TableLabelSearchResult",
    "fill_by_path",
    "find_cell_by_label",
    "form_slots",
)
_EXPORT_NAMES = {
    "export_html": MovedName(_MARKDOWN, "to_html"),
    "export_markdown": MovedName(_MARKDOWN, "to_markdown"),
}
_EQUATION_PREVIEW_NAMES = (
    "LABEL_LATEX_ERROR",
    "LABEL_LATEX_NO_LIB",
    "LABEL_MATHML",
    "LABEL_SCRIPT",
    "EquationRender",
    "MathMLUnavailableError",
    "latex2mathml_available",
    "latex_to_mathml",
    "render_equation",
)

#: The label-navigation names ``hwpx.tools`` re-exported (a subset of :data:`_LABEL_NAMES`).
_TOOLS_LABEL_NAMES = (
    "TableCellReference",
    "TableFillApplied",
    "TableFillFailed",
    "TableFillResult",
    "TableLabelMatch",
    "TableLabelSearchResult",
    "fill_by_path",
    "find_cell_by_label",
)

#: Names 7.0 moved out of a module that stays: ``{module: {name: MovedName}}``. Each of
#: these modules' ``__getattr__`` raises :func:`moved_name_error` for them.
MOVED_IN_7_0_NAMES: Mapping[str, Mapping[str, MovedName]] = {
    "hwpx.equation": _names(_PREVIEW, *_EQUATION_PREVIEW_NAMES),
    "hwpx.experimental": {
        **_names("hwpx_automation.ingest", *_INGEST_NAMES),
        **_names(_PREVIEW, *_PREVIEW_NAMES, "DocumentViewer", "render_document_viewer"),
    },
    "hwpx.tools": {
        **_EXPORT_NAMES,
        **_names(_PREVIEW, *_PREVIEW_NAMES, *_VIEWER_NAMES),
        **_names(_MAIL_MERGE, *_MAIL_MERGE_NAMES),
        **_names(_COMPLIANCE, *_REFERENCE_NAMES),
        **_names(_FORMS, *_TOOLS_LABEL_NAMES),
    },
    "hwpx.tools.doc_diff": _names(_COMPLIANCE, *_REFERENCE_NAMES),
    "hwpx.tools.exporter": dict(_EXPORT_NAMES),
    "hwpx.tools.table_navigation": _names(_FORMS, *_LABEL_NAMES),
}


class _Surface(Protocol):
    kind: str
    target_module: str | None
    target_name: str | None
    moved_in: str


def moved_modules(companion: Mapping[str, _Surface]) -> dict[str, str]:
    """Return ``{legacy module: new module}`` for every moved module name (5.0 and 7.0)."""

    return {legacy: target for legacy, (target, _moved_in) in _module_moves(companion).items()}


def module_moves_in(companion: Mapping[str, _Surface], release: str) -> dict[str, str]:
    """``{legacy module: new module}`` for the modules moved in *release* (``"5.0"``/``"7.0"``)."""

    return {
        legacy: target
        for legacy, (target, moved_in) in _module_moves(companion).items()
        if moved_in == release
    }


def _module_moves(companion: Mapping[str, _Surface]) -> dict[str, tuple[str, str]]:
    table = {
        f"hwpx.{name}": (surface.target_module, surface.moved_in)
        for name, surface in companion.items()
        if surface.kind in {"module", "renamed"}
        and surface.target_name is None
        and surface.target_module is not None
    }
    table.update({legacy: (target, "5.0") for legacy, target in NESTED_MOVED_MODULES.items()})
    table.update({legacy: (target, "7.0") for legacy, target in MOVED_IN_7_0_MODULES.items()})
    return dict(sorted(table.items()))


def moved_message(legacy: str, target: str, moved_in: str = "5.0") -> str:
    if moved_in == "5.0":
        return (
            f"{legacy}은(는) python-hwpx 5.0에서 {COMPANION_DISTRIBUTION} 패키지로 "
            f"이동했습니다. 새 경로: {target}\n"
            f"    {COMPANION_INSTALL}\n"
            f"    import {target}\n"
            f'4.x를 계속 쓰려면: pip install "python-hwpx<5"\n'
            f"전체 대체표: {MIGRATION_GUIDE_URL}"
        )
    return _moved_in_7_0_message(legacy, f"새 경로: {target}", f"import {target}")


def moved_name_message(legacy: str, statement: str) -> str:
    """The 7.0 message for a name (``hwpx.tools.export_markdown``) with its new import line."""

    return _moved_in_7_0_message(legacy, "", statement)


def _moved_in_7_0_message(legacy: str, where: str, statement: str) -> str:
    tail = f" {where}" if where else ""
    return (
        f"{legacy}은(는) python-hwpx 7.0에서 {COMPANION_DISTRIBUTION} 패키지로 "
        f"옮겼습니다.{tail}\n"
        f"    {COMPANION_INSTALL}\n"
        f"    {statement}\n"
        f'6.x를 계속 쓰려면: pip install "python-hwpx<7"\n'
        f"전체 대체표: {MIGRATION_GUIDE_7_0_URL}"
    )


def moved_name_error(module: str, name: str) -> ImportError | None:
    """The error for *name* that 7.0 moved out of *module*, or ``None`` if it did not.

    A moved function or class gives :class:`hwpx.MovedToCompanion`; a moved submodule
    name (``from hwpx.tools import mail_merge``) gives ``ModuleNotFoundError`` — both are
    ``ImportError``, so ``from module import name`` shows the message as it is.
    """

    from . import MovedToCompanion

    moved = MOVED_IN_7_0_NAMES.get(module, {}).get(name)
    if moved is not None:
        return MovedToCompanion(
            moved_name_message(f"{module}.{name}", moved.import_statement(name))
        )
    submodule = f"{module}.{name}"
    target = MOVED_IN_7_0_MODULES.get(submodule)
    if target is not None:
        return ModuleNotFoundError(moved_message(submodule, target, "7.0"), name=submodule)
    return None


def repository_only_message(legacy: str, replacement: str) -> str:
    return (
        f"{legacy}은(는) python-hwpx 5.0부터 배포본에 들어가지 않습니다. "
        f"{replacement}\n"
        f"전체 대체표: {MIGRATION_GUIDE_URL}"
    )


class _MovedModuleGuide:
    """Meta-path finder that explains removed module names instead of loading them."""

    def __init__(self, moved: Mapping[str, tuple[str, str]]) -> None:
        self._moved = dict(moved)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> None:
        moved = self._moved.get(fullname)
        if moved is not None:
            new_module, moved_in = moved
            raise ModuleNotFoundError(
                moved_message(fullname, new_module, moved_in), name=fullname
            )
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
    sys.meta_path.append(_MovedModuleGuide(_module_moves(companion)))
