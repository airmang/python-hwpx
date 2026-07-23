"""Executable core-only adoption contract.

These scenarios are intentionally boring: they are the common tasks that must
remain straightforward for a Python user who installs only ``python-hwpx``.
Application workflows, MCP tools, genre profiles and skill routing do not
belong in this suite.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from hwpx import HwpxDocument


CONTRACT_PATH = Path(__file__).parent / "data" / "golden_api_contract.json"
Scenario = Callable[[Path], None]


def _roundtrip(document: HwpxDocument) -> HwpxDocument:
    payload = document.to_bytes()
    assert payload.startswith(b"PK")
    return HwpxDocument.open(payload)


def _new_document(_: Path) -> None:
    with HwpxDocument.new() as document:
        assert len(document.sections) == 1
        assert document.to_bytes().startswith(b"PK")


def _open_from_bytes(_: Path) -> None:
    payload = HwpxDocument.new().to_bytes()
    with HwpxDocument.open(payload) as reopened:
        assert len(reopened.sections) == 1


def _context_manager(_: Path) -> None:
    document = HwpxDocument.new()
    with document as entered:
        assert entered is document
    assert "closed=True" in repr(document)


def _add_paragraph(_: Path) -> None:
    with HwpxDocument.new() as document:
        paragraph = document.add_paragraph("Hello HWPX")
        assert paragraph.text == "Hello HWPX"


def _iterate_runs(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("run text")
        assert any(run.text == "run text" for run in document.iter_runs())


def _replace_text(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("before value")
        assert document.replace_text_in_runs("before", "after") == 1
        assert any("after value" in paragraph.text for paragraph in document.paragraphs)


def _create_run_style(_: Path) -> None:
    with HwpxDocument.new() as document:
        style_id = document.ensure_run_style(bold=True, color="#336699", size=11)
        paragraph = document.add_paragraph("styled", char_pr_id_ref=style_id)
        assert paragraph.runs[0].char_pr_id_ref == style_id


def _format_paragraph(_: Path) -> None:
    with HwpxDocument.new() as document:
        index = len(document.paragraphs)
        document.add_paragraph("formatted")
        result = document.set_paragraph_format(
            paragraph_index=index,
            alignment="center",
            line_spacing_percent=160,
            spacing_after_pt=6,
        )
        assert result["formatted"] == 1


def _format_list(_: Path) -> None:
    with HwpxDocument.new() as document:
        index = len(document.paragraphs)
        document.add_paragraph("list item")
        result = document.set_list_format(
            paragraph_index=index,
            kind="bullet",
            bullet_char="•",
        )
        assert result["formatted"] == 1


def _add_table(_: Path) -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(2, 2)
        table.cell(0, 0).text = "A"
        table.cell(1, 1).text = "D"
        assert table.cell(0, 0).text == "A"
        assert table.cell(1, 1).text == "D"


def _merge_table_cells(_: Path) -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(2, 2)
        table.cell(0, 0).text = "merged"
        document.merge_table_cells(table, "A1:B1")
        assert table.cell(0, 0).text == "merged"


def _map_tables(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("Table heading")
        document.add_table(2, 3)
        table_map = document.get_table_map()
        assert table_map["tables"][0]["rows"] == 2
        assert table_map["tables"][0]["cols"] == 3


def _find_cell_by_label(_: Path) -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(1, 2)
        table.cell(0, 0).text = "Name:"
        found = document.find_cell_by_label("Name")
        assert found["count"] == 1
        assert found["matches"][0]["target_cell"]["col"] == 1


def _add_remove_section(_: Path) -> None:
    with HwpxDocument.new() as document:
        section = document.add_section()
        assert len(document.sections) == 2
        document.remove_section(section)
        assert len(document.sections) == 1


def _set_page_setup(_: Path) -> None:
    with HwpxDocument.new() as document:
        result = document.set_page_setup(
            paper_size="A4",
            orientation="landscape",
            margin_left_mm=20,
            margin_right_mm=20,
        )
        assert result["pageSize"]["width"] > result["pageSize"]["height"]
        assert result["margins"]["left"] == result["margins"]["right"]


def _set_header_footer(_: Path) -> None:
    with HwpxDocument.new() as document:
        header = document.set_header_text("Header")
        footer = document.set_footer_text("Footer")
        assert header.text == "Header"
        assert footer.text == "Footer"


def _set_page_number(_: Path) -> None:
    with HwpxDocument.new() as document:
        footer = document.set_page_number(prefix="Page ")
        assert "Page " in footer.text


def _add_bookmark(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_bookmark("golden-bookmark")
        assert "golden-bookmark" in document.paragraphs[-1].bookmarks


def _add_hyperlink(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_hyperlink("https://example.com", "Example")
        links = document.paragraphs[-1].hyperlinks
        assert links and links[0]["url"] == "https://example.com"


def _export_text(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("export me")
        assert "export me" in document.export_text()


def _export_markdown(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("markdown text")
        assert "markdown text" in document.export_markdown()


def _validate_document(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("valid")
        report = document.validate()
        assert hasattr(report, "ok")
        assert hasattr(report, "issues")


def _save_path_reopen(tmp_path: Path) -> None:
    target = tmp_path / "golden-path.hwpx"
    with HwpxDocument.new() as document:
        document.add_paragraph("saved path")
        assert document.save_to_path(target) == target
    with HwpxDocument.open(target) as reopened:
        assert any("saved path" in paragraph.text for paragraph in reopened.paragraphs)


def _save_stream_reopen(_: Path) -> None:
    stream = BytesIO()
    with HwpxDocument.new() as document:
        document.add_paragraph("saved stream")
        assert document.save_to_stream(stream) is stream
    with HwpxDocument.open(stream.getvalue()) as reopened:
        assert any("saved stream" in paragraph.text for paragraph in reopened.paragraphs)


def _preserve_unmodified_parts(_: Path) -> None:
    with HwpxDocument.new() as document:
        document.add_paragraph("preserve before")
        before = document.to_bytes()
    with HwpxDocument.open(before) as document:
        assert document.replace_text_in_runs("before", "after") == 1
        after = document.to_bytes()

    with ZipFile(BytesIO(before)) as before_zip, ZipFile(BytesIO(after)) as after_zip:
        before_parts = {name: before_zip.read(name) for name in before_zip.namelist()}
        after_parts = {name: after_zip.read(name) for name in after_zip.namelist()}
    assert before_parts.keys() == after_parts.keys()
    changed = {
        name
        for name in before_parts
        if before_parts[name] != after_parts[name]
    }
    assert changed == {"Contents/section0.xml"}


SCENARIOS: dict[str, Scenario] = {
    "new-document": _new_document,
    "open-from-bytes": _open_from_bytes,
    "context-manager": _context_manager,
    "add-paragraph": _add_paragraph,
    "iterate-runs": _iterate_runs,
    "replace-text": _replace_text,
    "create-run-style": _create_run_style,
    "format-paragraph": _format_paragraph,
    "format-list": _format_list,
    "add-table": _add_table,
    "merge-table-cells": _merge_table_cells,
    "map-tables": _map_tables,
    "find-cell-by-label": _find_cell_by_label,
    "add-remove-section": _add_remove_section,
    "set-page-setup": _set_page_setup,
    "set-header-footer": _set_header_footer,
    "set-page-number": _set_page_number,
    "add-bookmark": _add_bookmark,
    "add-hyperlink": _add_hyperlink,
    "export-text": _export_text,
    "export-markdown": _export_markdown,
    "validate-document": _validate_document,
    "save-path-reopen": _save_path_reopen,
    "save-stream-reopen": _save_stream_reopen,
    "preserve-unmodified-parts": _preserve_unmodified_parts,
}

CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_golden_api_contract_is_complete() -> None:
    assert len(CONTRACT["scenarios"]) >= 20
    assert CONTRACT["scenarios"] == list(SCENARIOS)


@pytest.mark.parametrize("scenario_id", CONTRACT["scenarios"])
def test_core_only_golden_scenario(scenario_id: str, tmp_path: Path) -> None:
    SCENARIOS[scenario_id](tmp_path)
    assert not any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in CONTRACT["forbiddenImportPrefixes"]
        for module_name in sys.modules
    )
