from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.template_analyzer import (
    TEMPLATE_ANALYSIS_SCHEMA_VERSION,
    analyze_template,
    template_analysis_agent_schema,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _build_enriched_template(path: Path) -> str:
    document = HwpxDocument.new()
    document.set_page_size(width=72000, height=36000, orientation="LANDSCAPE")
    document.set_page_margins(left=7000, right=5000, top=3000, bottom=3000, gutter=1000)
    rich_style = document.ensure_run_style(
        bold=True,
        italic=True,
        underline=True,
        strike=True,
        font="함초롬바탕",
        size=12,
    )
    document.add_paragraph("Styled body", char_pr_id_ref=rich_style)

    table = document.add_table(2, 3, width=30000, height=6000)
    table.set_cell_text(0, 0, "Merged Header")
    table.merge_cells("A1:B1")
    table.set_cell_text(1, 0, "Styled Cell")

    styled_cell = table.cell(1, 0)
    run = styled_cell.element.find(f".//{HP}run")
    assert run is not None
    run.set("charPrIDRef", rich_style)
    margin = styled_cell.element.find(f"{HP}cellMargin")
    assert margin is not None
    margin.set("left", "11")
    margin.set("right", "12")
    margin.set("top", "13")
    margin.set("bottom", "14")
    sublist = styled_cell.element.find(f"{HP}subList")
    assert sublist is not None
    sublist.set("vertAlign", "BOTTOM")
    table.mark_dirty()

    document.save_to_path(path)
    return rich_style


def test_template_analyzer_reports_rich_styles_table_geometry_and_body_width(tmp_path: Path) -> None:
    source = tmp_path / "enriched-template.hwpx"
    rich_style = _build_enriched_template(source)

    analysis = analyze_template(source)

    assert analysis.schema_version == TEMPLATE_ANALYSIS_SCHEMA_VERSION
    assert analysis.section_layouts[0].computed_body_width == 59000
    assert any(
        any(font.get("face") == "함초롬바탕" for font in face.fonts)
        for face in analysis.font_faces
    )

    rich = next(item for item in analysis.char_properties if item.id == rich_style)
    assert rich.flags == {
        "bold": True,
        "italic": True,
        "underline": True,
        "strikeout": True,
    }
    assert "font=함초롬바탕" in rich.human_readable

    table = analysis.table_summaries[0]
    assert table.column_count == 3
    assert table.column_widths.widths == (10000, 10000, 10000)
    assert table.column_widths.skipped_colspan_cell_count >= 1

    styled_cell = next(cell for cell in table.cells if cell.row == 1 and cell.col == 0)
    assert styled_cell.margin == {"left": 11, "right": 12, "top": 13, "bottom": 14}
    assert styled_cell.vert_align == "BOTTOM"
    assert styled_cell.char_pr_id_refs == (rich_style,)
    assert styled_cell.runs[0]["style"]["flags"]["bold"] is True
    assert styled_cell.runs[0]["style"]["fontRef"]["hangul"]["face"] == "함초롬바탕"

    assert any(
        ref.char_pr_id_ref == rich_style and ref.style and ref.style["flags"]["strikeout"]
        for ref in analysis.run_style_references
    )


def test_template_analyzer_schema_json_option_is_agent_friendly(tmp_path: Path) -> None:
    source = tmp_path / "schema-template.hwpx"
    _build_enriched_template(source)

    result = subprocess.run(
        [sys.executable, "-m", "hwpx.tools.template_analyzer", str(source), "--schema-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload == template_analysis_agent_schema()
    assert payload["schemaVersion"] == "hwpx.template-analysis.agent-schema.v1"
    assert "table_summaries[].column_widths.widths" in payload["fieldGuide"]
