# SPDX-License-Identifier: Apache-2.0
"""7.0 moved conversion and guessing to python-hwpx-automation: every old name says where.

python-hwpx 7.0 keeps the engine that reads and writes what the file says. Markdown and
HTML, ingest and the framework loaders, label-guided form filling and check-mark
choices, mail merge, previews, format rules, the table/report helpers and the reference
consistency lint moved to python-hwpx-automation 8.0. Core does not import that
package; each old name raises an error that names the new place and the install
command:

- ``from hwpx import X`` (``_MOVED_TO_COMPANION``, 7.0 rows) → ``MovedToCompanion``
- ``from hwpx.tools / hwpx.experimental / hwpx.equation / exporter / table_navigation /
  doc_diff import X`` (``_moved_modules.MOVED_IN_7_0_NAMES``) → ``MovedToCompanion``
- ``import hwpx.tools.markdown_import`` etc. (``MOVED_IN_7_0_MODULES`` and the ``ingest``/
  ``integrations`` rows) → ``ModuleNotFoundError``
- ``doc.text.markdown`` and the other moved methods, and the 6.x root names whose new
  place moved too → ``HwpxAttributeError`` (``code="document-name-moved"``), ``hasattr``
  is ``False``.

The new places are the receiving package's names (``hwpx_automation.markdown.to_markdown``
…); the receiving side keeps them stable because these messages print them.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

import hwpx
from hwpx import HwpxDocument, _moved_modules
from hwpx._document import _legacy
from hwpx.errors import ERROR_CODES, HwpxAttributeError

INSTALL = 'pip install -U "python-hwpx-automation>=8"'
GUIDE = _moved_modules.MIGRATION_GUIDE_7_0_URL
ROOT = Path(__file__).resolve().parents[1]

#: The receiving package's modules (MOVE8 "받는 자리"). A hint that names anything else is a typo.
RECEIVERS = {
    "hwpx_automation.markdown",
    "hwpx_automation.ingest",
    "hwpx_automation.integrations",
    "hwpx_automation.forms",
    "hwpx_automation.mail_merge",
    "hwpx_automation.preview",
    "hwpx_automation.format_rules",
    "hwpx_automation.office.utilities",
    "hwpx_automation.office.compliance",
}

ROOT_7_0 = sorted(name for name, surface in hwpx._MOVED_TO_COMPANION.items() if surface.moved_in == "7.0")
MODULE_NAMES = sorted(
    (module, name) for module, names in _moved_modules.MOVED_IN_7_0_NAMES.items() for name in names
)
MODULES_7_0 = sorted(_moved_modules.module_moves_in(hwpx._MOVED_TO_COMPANION, "7.0").items())


def _receiver(target: str) -> str:
    for receiver in sorted(RECEIVERS, key=len, reverse=True):
        if target == receiver or target.startswith(f"{receiver}."):
            return receiver
    raise AssertionError(f"{target} is not a receiving module")


def _assert_guides(message: str, statement: str) -> None:
    assert "python-hwpx 7.0에서" in message
    assert INSTALL in message
    assert statement in message
    assert GUIDE in message
    ast.parse(statement)


# --------------------------------------------------------------------------
# from hwpx import X


@pytest.mark.parametrize("name", ROOT_7_0)
def test_a_root_name_moved_in_7_0_names_its_new_import(name: str) -> None:
    surface = hwpx._MOVED_TO_COMPANION[name]
    statement = surface.import_statement(name)
    assert statement is not None
    _receiver(surface.target_module or "")
    with pytest.raises(hwpx.MovedToCompanion) as raised:
        getattr(hwpx, name)
    _assert_guides(str(raised.value), statement)
    assert name not in hwpx.__all__


def test_the_root_7_0_rows_are_exactly_the_moved_stable_and_experimental_names() -> None:
    stable = {
        "HwpxMarkdownConverter",
        "MAIL_MERGE_REPORT_VERSION",
        "inspect_mail_merge_placeholders",
        "load_mail_merge_rows",
        "merge_template_rows",
        "REFERENCE_CONSISTENCY_REPORT_VERSION",
        "inspect_reference_consistency",
    }
    experimental = {
        "ConversionAttempt",
        "DocumentConverter",
        "DocumentIngestError",
        "DocumentIngestResult",
        "DocumentIngestor",
        "DocumentSourceInfo",
        "UnsupportedDocumentFormat",
        "LayoutPreview",
        "PreviewPage",
        "render_layout_preview",
        "DocumentViewer",
        "render_document_viewer",
    }
    assert set(ROOT_7_0) == stable | experimental | {"ingest", "integrations"}
    # An experimental name that moved no longer points at hwpx.experimental.
    assert not (experimental & set(hwpx._EXPERIMENTAL_EXPORTS))


def test_the_issue_import_forms_reach_the_guidance() -> None:
    with pytest.raises(ImportError, match="hwpx_automation.ingest import HwpxMarkdownConverter"):
        from hwpx import HwpxMarkdownConverter  # noqa: F401
    with pytest.raises(ImportError, match="hwpx_automation.mail_merge import merge_template_rows"):
        from hwpx import merge_template_rows  # noqa: F401
    with pytest.raises(ImportError, match="import hwpx_automation.ingest as ingest"):
        from hwpx import ingest  # noqa: F401


# --------------------------------------------------------------------------
# from hwpx.<module> import X


@pytest.mark.parametrize(("module", "name"), MODULE_NAMES)
def test_a_name_moved_out_of_a_staying_module_names_its_new_import(module: str, name: str) -> None:
    moved = _moved_modules.MOVED_IN_7_0_NAMES[module][name]
    _receiver(moved.target_module)
    owner = importlib.import_module(module)
    with pytest.raises(hwpx.MovedToCompanion) as raised:
        getattr(owner, name)
    _assert_guides(str(raised.value), moved.import_statement(name))
    assert name not in getattr(owner, "__all__", ())


def test_from_import_shows_the_message_as_it_is() -> None:
    with pytest.raises(ImportError, match="from hwpx_automation.markdown import to_markdown"):
        from hwpx.tools import export_markdown  # noqa: F401
    with pytest.raises(ImportError, match="from hwpx_automation.forms import fill_by_path"):
        from hwpx.tools.table_navigation import fill_by_path  # noqa: F401
    with pytest.raises(ImportError, match="from hwpx_automation.preview import render_equation"):
        from hwpx.equation import render_equation  # noqa: F401
    with pytest.raises(ImportError, match="from hwpx_automation.preview import render_layout_preview"):
        from hwpx.experimental import render_layout_preview  # noqa: F401
    with pytest.raises(ImportError, match="from hwpx_automation.office.compliance import inspect_reference_consistency"):
        from hwpx.tools.doc_diff import inspect_reference_consistency  # noqa: F401


def test_what_stays_still_imports() -> None:
    from hwpx.equation import EQEDIT_MATHML_OPERATOR_COMMANDS, eqedit_to_latex, estimate_equation_size, latex_to_eqedit
    from hwpx.experimental import estimate_pages
    from hwpx.tools import doc_diff, export_text, get_table_map
    from hwpx.tools.exporter import ListLabels, NoteLabels, table_grid_text

    assert "\\triangle" in EQEDIT_MATHML_OPERATOR_COMMANDS
    assert all(callable(item) for item in (eqedit_to_latex, latex_to_eqedit, estimate_equation_size, estimate_pages))
    assert all(callable(item) for item in (doc_diff, export_text, get_table_map, ListLabels, NoteLabels, table_grid_text))
    document = HwpxDocument.new()
    document.add_table(1, 2).cell(0, 0).text = "성명"
    assert document.tables.map()["tables"][0]["cells"][0]["text"] == "성명"
    assert hasattr(document.fields, "add") and hasattr(document.text, "plain")


def test_an_unrelated_missing_name_is_a_plain_attribute_error() -> None:
    import hwpx.tools

    for owner in (hwpx.tools, importlib.import_module("hwpx.equation"), importlib.import_module("hwpx.experimental")):
        with pytest.raises(AttributeError) as raised:
            getattr(owner, "no_such_name")
        assert not isinstance(raised.value, ImportError)


# --------------------------------------------------------------------------
# import hwpx.<moved module>


@pytest.mark.parametrize(("legacy", "target"), MODULES_7_0)
def test_importing_a_module_moved_in_7_0_names_its_new_place(legacy: str, target: str) -> None:
    _receiver(target)
    with pytest.raises(ModuleNotFoundError) as raised:
        importlib.import_module(legacy)
    assert raised.value.name == legacy
    _assert_guides(str(raised.value), f"import {target}")
    assert f"새 경로: {target}" in str(raised.value)


def test_submodules_of_a_moved_package_are_guided_through_it() -> None:
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.integrations"):
        import hwpx.integrations.langchain  # noqa: F401
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.ingest"):
        from hwpx.ingest.base import DocumentIngestor  # noqa: F401


def test_a_moved_submodule_name_is_guided_in_the_from_form_too() -> None:
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.mail_merge"):
        from hwpx.tools import mail_merge  # noqa: F401
    with pytest.raises(ModuleNotFoundError, match="hwpx_automation.preview"):
        from hwpx.equation import mathml  # noqa: F401


def test_no_moved_file_is_left_in_the_source_tree() -> None:
    src = ROOT / "src"
    for legacy, _target in MODULES_7_0:
        path = src.joinpath(*legacy.split("."))
        assert not path.with_suffix(".py").exists(), legacy
        assert not path.is_dir(), legacy


def test_the_guidance_does_not_import_the_automation_package() -> None:
    # What these calls import, not what the process holds: another test may have imported automation.
    before = set(sys.modules)
    for name in ROOT_7_0:
        with pytest.raises(ImportError):
            getattr(hwpx, name)
    for module, name in MODULE_NAMES:
        with pytest.raises(ImportError):
            getattr(importlib.import_module(module), name)
    assert not any(module.startswith("hwpx_automation") for module in set(sys.modules) - before)


# --------------------------------------------------------------------------
# doc.<namespace>.<moved method> and the 6.x root names


@pytest.mark.parametrize("path", sorted(_legacy.MOVED_METHODS))
def test_a_moved_method_names_its_function_and_the_install_command(path: str) -> None:
    moved = _legacy.MOVED_METHODS[path]
    _receiver(moved.module)
    document = HwpxDocument.new()
    namespace_name, name = path.split(".")[1:]
    namespace = getattr(document, namespace_name)
    assert not hasattr(namespace, name)
    with pytest.raises(HwpxAttributeError) as raised:
        getattr(namespace, name)
    error = raised.value
    assert isinstance(error, AttributeError)
    assert error.code == "document-name-moved"
    assert error.context["replacement"] == moved.replacement
    assert error.context["install"] == INSTALL
    assert error.context["movedIn"] == "7.0"
    assert f"`{moved.replacement}`" in str(error) and INSTALL in str(error)
    assert GUIDE in (error.suggestion or "")
    ast.parse(moved.replacement)


def test_the_moved_methods_are_the_eight_the_move_named() -> None:
    assert set(_legacy.MOVED_METHODS) == {
        "doc.text.markdown",
        "doc.text.html",
        "doc.text.append_markdown",
        "doc.tables.find_cell_by_label",
        "doc.tables.form_slots",
        "doc.tables.fill_by_path",
        "doc.fields.choices",
        "doc.fields.choose",
    }


@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("export_markdown", "from hwpx_automation.markdown import to_markdown; to_markdown(doc)"),
        ("export_rich_markdown", "from hwpx_automation.markdown import to_markdown; to_markdown(doc, rich=True)"),
        ("export_html", "from hwpx_automation.markdown import to_html; to_html(doc)"),
        ("fill_by_path", 'from hwpx_automation.forms import fill_by_path; fill_by_path(doc, {"성명 > right": "홍길동"})'),
        ("find_cell_by_label", 'from hwpx_automation.forms import find_cell_by_label; find_cell_by_label(doc, "성명")'),
    ],
)
def test_a_6x_root_name_whose_new_place_moved_names_the_automation_function(name: str, replacement: str) -> None:
    document = HwpxDocument.new()
    assert not hasattr(document, name)
    with pytest.raises(HwpxAttributeError) as raised:
        getattr(document, name)
    assert raised.value.code == "document-name-moved"
    assert raised.value.context["replacement"] == replacement
    assert raised.value.context["movingToAutomation"] is True
    assert INSTALL in str(raised.value)


def test_get_table_map_points_at_the_map_that_stays() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxAttributeError) as raised:
        document.get_table_map()
    assert raised.value.code == "document-name-removed"
    assert raised.value.context["replacement"] == "doc.tables.map()"
    assert raised.value.context["movingToAutomation"] is False
    assert _legacy.REMOVED_NAMES["get_table_map"].moving is False


def test_the_moved_code_is_registered() -> None:
    assert "document-name-moved" in ERROR_CODES
    for gone in (
        "ingest-failed",
        "ingest-format-unsupported",
        "equation-mathml-unavailable",
        "text-markdown-style-invalid",
        "table-path-invalid-type",
    ):
        assert gone not in ERROR_CODES


def test_a_namespace_keeps_its_other_names_and_plain_errors() -> None:
    document = HwpxDocument.new()
    with pytest.raises(AttributeError) as raised:
        document.text.no_such_method  # noqa: B018
    assert not isinstance(raised.value, HwpxAttributeError)
    assert document.text.plain() == document.text.plain()


# --------------------------------------------------------------------------
# packaging: no console script or extra pulls a moved feature back in


def test_the_moved_extras_stay_as_empty_names() -> None:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - Python 3.10
        import tomli as tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]
    for name in ("visual", "xlsx", "preview", "langchain", "llamaindex"):
        assert extras[name] == [], name
    assert "hwpx-check-format" not in project["scripts"]
