# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence
from xml.etree import ElementTree as ET

from ..opc.package import HwpxPackage
from ..opc.relationships import parse_manifest_relationships
from .archive_cli import unpack_hwpx
from .page_guard import DocumentMetrics, collect_metrics

_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP_TAG = f"{{{_HP_NS}}}"
_NS = {"hh": _HH_NS, "hp": _HP_NS}
TEMPLATE_ANALYSIS_SCHEMA_VERSION = "hwpx.template-analysis.v2"
TEMPLATE_ANALYSIS_AGENT_SCHEMA_VERSION = "hwpx.template-analysis.agent-schema.v1"

__all__ = [
    "CellSummary",
    "CharPropertySummary",
    "ColumnWidthSummary",
    "FontFaceSummary",
    "HeaderSummary",
    "RunStyleReference",
    "SectionLayoutSummary",
    "TableSummary",
    "TemplateAnalysis",
    "analyze_template",
    "extract_template_parts",
    "main",
    "template_analysis_agent_schema",
]


@dataclass(frozen=True)
class HeaderSummary:
    font_count: int
    char_pr_count: int
    para_pr_count: int
    border_fill_count: int


@dataclass(frozen=True)
class FontFaceSummary:
    lang: str
    fonts: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class CharPropertySummary:
    id: str
    attributes: dict[str, str]
    flags: dict[str, bool]
    font_ref: dict[str, dict[str, str | None]]
    human_readable: str


@dataclass(frozen=True)
class RunStyleReference:
    section_path: str
    run_index: int
    char_pr_id_ref: str | None
    text: str
    style: dict[str, Any] | None


@dataclass(frozen=True)
class SectionLayoutSummary:
    section_path: str
    page_width: int | None
    page_height: int | None
    margins: dict[str, int]
    computed_body_width: int | None


@dataclass(frozen=True)
class ColumnWidthSummary:
    widths: tuple[int | None, ...]
    complete: bool
    source_cell_count: int
    skipped_colspan_cell_count: int


@dataclass(frozen=True)
class CellSummary:
    row: int
    col: int
    row_span: int
    col_span: int
    width: int | None
    height: int | None
    margin: dict[str, int]
    vert_align: str | None
    char_pr_id_refs: tuple[str, ...]
    runs: tuple[dict[str, Any], ...]
    text: str


@dataclass(frozen=True)
class TableSummary:
    section_path: str
    table_index: int
    row_count: int
    column_count: int
    column_widths: ColumnWidthSummary
    cells: tuple[CellSummary, ...]


@dataclass(frozen=True)
class TemplateAnalysis:
    schema_version: str
    source_name: str
    part_names: tuple[str, ...]
    rootfiles: tuple[str, ...]
    manifest_path: str
    manifest_item_paths: tuple[str, ...]
    header_paths: tuple[str, ...]
    section_paths: tuple[str, ...]
    master_page_paths: tuple[str, ...]
    history_paths: tuple[str, ...]
    bin_data_paths: tuple[str, ...]
    version_path: str | None
    header_summary: HeaderSummary
    font_faces: tuple[FontFaceSummary, ...]
    char_properties: tuple[CharPropertySummary, ...]
    section_layouts: tuple[SectionLayoutSummary, ...]
    table_summaries: tuple[TableSummary, ...]
    run_style_references: tuple[RunStyleReference, ...]
    proxy_metrics: DocumentMetrics


def _summarize_header(element: ET.Element | None) -> HeaderSummary:
    if element is None:
        return HeaderSummary(font_count=0, char_pr_count=0, para_pr_count=0, border_fill_count=0)

    font_count = len(element.findall(".//hh:fontface/hh:font", _NS))
    char_pr_count = len(element.findall(".//hh:charPr", _NS))
    para_pr_count = len(element.findall(".//hh:paraPr", _NS))
    border_fill_count = len(element.findall(".//hh:borderFill", _NS))
    return HeaderSummary(
        font_count=font_count,
        char_pr_count=char_pr_count,
        para_pr_count=para_pr_count,
        border_fill_count=border_fill_count,
    )


def template_analysis_agent_schema() -> dict[str, Any]:
    return {
        "schemaVersion": TEMPLATE_ANALYSIS_AGENT_SCHEMA_VERSION,
        "analysisSchemaVersion": TEMPLATE_ANALYSIS_SCHEMA_VERSION,
        "description": "Agent-oriented fields for template form-fit planning.",
        "fieldGuide": {
            "section_layouts[].computed_body_width": "Writable body width in HWP units after page margins and gutter.",
            "table_summaries[].column_widths.widths": "Per-column widths reconstructed only from non-colspan cells.",
            "table_summaries[].cells[].margin": "Cell margin attributes in HWP units.",
            "table_summaries[].cells[].vert_align": "Cell subList vertical alignment.",
            "table_summaries[].cells[].runs[].style": "Run charPrIDRef resolved to decoded style flags and font faces.",
            "char_properties[].flags": "Decoded bold, italic, underline, and strikeout booleans.",
        },
        "recommendedUse": [
            "Choose target cells by row/col and span before planning replacements.",
            "Use computed_body_width and column_widths to size generated tables.",
            "Preserve run charPrIDRef when replacing text in styled cells.",
        ],
    }


def _int_attr(element: ET.Element | None, name: str, default: int | None = None) -> int | None:
    if element is None:
        return default
    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _element_text(element: ET.Element) -> str:
    return "".join(text.text or "" for text in element.findall(f".//{_HP_TAG}t"))


def _truncated_text(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _extract_font_faces(header_xml: ET.Element | None) -> tuple[FontFaceSummary, ...]:
    if header_xml is None:
        return ()
    summaries: list[FontFaceSummary] = []
    for fontface in header_xml.findall(".//hh:fontface", _NS):
        lang = (fontface.get("lang") or "").lower()
        fonts: list[dict[str, str]] = []
        for font in fontface.findall("hh:font", _NS):
            fonts.append({key: value for key, value in font.attrib.items()})
        summaries.append(FontFaceSummary(lang=lang, fonts=tuple(fonts)))
    return tuple(summaries)


def _font_lookup(font_faces: Sequence[FontFaceSummary]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for face in font_faces:
        lang_fonts = lookup.setdefault(face.lang, {})
        for font in face.fonts:
            font_id = font.get("id")
            face_name = font.get("face") or font.get("name")
            if font_id is not None and face_name is not None:
                lang_fonts[font_id] = face_name
    return lookup


def _active_style_flags(char_pr: ET.Element) -> dict[str, bool]:
    underline = char_pr.find("hh:underline", _NS)
    strikeout = char_pr.find("hh:strikeout", _NS)
    return {
        "bold": char_pr.find("hh:bold", _NS) is not None,
        "italic": char_pr.find("hh:italic", _NS) is not None,
        "underline": underline is not None and (underline.get("type") or "SOLID").upper() != "NONE",
        "strikeout": strikeout is not None and (strikeout.get("shape") or "SOLID").upper() != "NONE",
    }


def _font_ref_summary(
    char_pr: ET.Element,
    font_faces: dict[str, dict[str, str]],
) -> dict[str, dict[str, str | None]]:
    font_ref = char_pr.find("hh:fontRef", _NS)
    if font_ref is None:
        return {}
    summary: dict[str, dict[str, str | None]] = {}
    for lang, font_id in sorted(font_ref.attrib.items()):
        summary[lang] = {
            "id": font_id,
            "face": font_faces.get(lang.lower(), {}).get(font_id),
        }
    return summary


def _human_style(flags: dict[str, bool], font_ref: dict[str, dict[str, str | None]]) -> str:
    parts = [name for name in ("bold", "italic", "underline", "strikeout") if flags.get(name)]
    faces = sorted({str(item["face"]) for item in font_ref.values() if item.get("face")})
    if faces:
        parts.append("font=" + ",".join(faces))
    return ", ".join(parts) if parts else "regular"


def _extract_char_properties(
    header_xml: ET.Element | None,
    font_faces: Sequence[FontFaceSummary],
) -> tuple[CharPropertySummary, ...]:
    if header_xml is None:
        return ()
    fonts = _font_lookup(font_faces)
    summaries: list[CharPropertySummary] = []
    for char_pr in header_xml.findall(".//hh:charPr", _NS):
        char_id = char_pr.get("id")
        if char_id is None:
            continue
        flags = _active_style_flags(char_pr)
        font_ref = _font_ref_summary(char_pr, fonts)
        summaries.append(
            CharPropertySummary(
                id=char_id,
                attributes={key: value for key, value in char_pr.attrib.items()},
                flags=flags,
                font_ref=font_ref,
                human_readable=_human_style(flags, font_ref),
            )
        )
    return tuple(summaries)


def _style_lookup(char_properties: Sequence[CharPropertySummary]) -> dict[str, dict[str, Any]]:
    return {
        item.id: {
            "id": item.id,
            "flags": item.flags,
            "fontRef": item.font_ref,
            "humanReadable": item.human_readable,
        }
        for item in char_properties
    }


def _run_summary(run: ET.Element, style_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    char_ref = run.get("charPrIDRef")
    return {
        "charPrIDRef": char_ref,
        "text": _truncated_text(_element_text(run)),
        "style": style_by_id.get(char_ref or ""),
    }


def _extract_run_style_references(
    section_path: str,
    section_xml: ET.Element,
    style_by_id: dict[str, dict[str, Any]],
) -> tuple[RunStyleReference, ...]:
    refs: list[RunStyleReference] = []
    for index, run in enumerate(section_xml.findall(f".//{_HP_TAG}run")):
        char_ref = run.get("charPrIDRef")
        refs.append(
            RunStyleReference(
                section_path=section_path,
                run_index=index,
                char_pr_id_ref=char_ref,
                text=_truncated_text(_element_text(run)),
                style=style_by_id.get(char_ref or ""),
            )
        )
    return tuple(refs)


def _margin_summary(element: ET.Element | None) -> dict[str, int]:
    return {
        name: _int_attr(element, name, 0) or 0
        for name in ("left", "right", "top", "bottom", "header", "footer", "gutter")
    }


def _extract_section_layout(section_path: str, section_xml: ET.Element) -> SectionLayoutSummary:
    page_pr = section_xml.find(f".//{_HP_TAG}pagePr")
    margin = page_pr.find(f"{_HP_TAG}margin") if page_pr is not None else None
    margins = _margin_summary(margin)
    page_width = _int_attr(page_pr, "width")
    body_width = None
    if page_width is not None:
        body_width = max(
            page_width
            - margins.get("left", 0)
            - margins.get("right", 0)
            - margins.get("gutter", 0),
            0,
        )
    return SectionLayoutSummary(
        section_path=section_path,
        page_width=page_width,
        page_height=_int_attr(page_pr, "height"),
        margins=margins,
        computed_body_width=body_width,
    )


def _cell_int(cell: ET.Element, child_name: str, attr: str, default: int | None = None) -> int | None:
    return _int_attr(cell.find(f"{_HP_TAG}{child_name}"), attr, default)


def _cell_summary(
    row_index: int,
    cell_index: int,
    cell: ET.Element,
    style_by_id: dict[str, dict[str, Any]],
) -> CellSummary:
    addr = cell.find(f"{_HP_TAG}cellAddr")
    span = cell.find(f"{_HP_TAG}cellSpan")
    margin = cell.find(f"{_HP_TAG}cellMargin")
    sublist = cell.find(f"{_HP_TAG}subList")
    runs = tuple(_run_summary(run, style_by_id) for run in cell.findall(f".//{_HP_TAG}run"))
    char_refs = tuple(
        sorted({str(run["charPrIDRef"]) for run in runs if run.get("charPrIDRef") is not None})
    )
    return CellSummary(
        row=_int_attr(addr, "rowAddr", row_index) or row_index,
        col=_int_attr(addr, "colAddr", cell_index) or cell_index,
        row_span=_int_attr(span, "rowSpan", 1) or 1,
        col_span=_int_attr(span, "colSpan", 1) or 1,
        width=_cell_int(cell, "cellSz", "width"),
        height=_cell_int(cell, "cellSz", "height"),
        margin={
            name: _int_attr(margin, name, 0) or 0
            for name in ("left", "right", "top", "bottom")
        },
        vert_align=sublist.get("vertAlign") if sublist is not None else None,
        char_pr_id_refs=char_refs,
        runs=runs,
        text=_truncated_text(_element_text(cell)),
    )


def _column_width_summary(cells: Sequence[CellSummary], column_count: int) -> ColumnWidthSummary:
    widths: list[int | None] = [None] * max(column_count, 0)
    source_cell_count = 0
    skipped_colspan_cell_count = 0
    for cell in cells:
        if cell.col_span != 1:
            skipped_colspan_cell_count += 1
            continue
        if cell.width is None or cell.width <= 0:
            continue
        if 0 <= cell.col < len(widths) and widths[cell.col] is None:
            widths[cell.col] = cell.width
            source_cell_count += 1
    return ColumnWidthSummary(
        widths=tuple(widths),
        complete=all(width is not None for width in widths),
        source_cell_count=source_cell_count,
        skipped_colspan_cell_count=skipped_colspan_cell_count,
    )


def _extract_tables(
    section_path: str,
    section_xml: ET.Element,
    style_by_id: dict[str, dict[str, Any]],
) -> tuple[TableSummary, ...]:
    tables: list[TableSummary] = []
    for table_index, table in enumerate(section_xml.findall(f".//{_HP_TAG}tbl")):
        cells: list[CellSummary] = []
        for row_index, row in enumerate(table.findall(f"{_HP_TAG}tr")):
            for cell_index, cell in enumerate(row.findall(f"{_HP_TAG}tc")):
                cells.append(_cell_summary(row_index, cell_index, cell, style_by_id))
        column_count = _int_attr(table, "colCnt", 0) or 0
        if column_count <= 0 and cells:
            column_count = max(cell.col + max(cell.col_span, 1) for cell in cells)
        row_count = _int_attr(table, "rowCnt", 0) or 0
        if row_count <= 0 and cells:
            row_count = max(cell.row + max(cell.row_span, 1) for cell in cells)
        tables.append(
            TableSummary(
                section_path=section_path,
                table_index=table_index,
                row_count=row_count,
                column_count=column_count,
                column_widths=_column_width_summary(cells, column_count),
                cells=tuple(cells),
            )
        )
    return tuple(tables)


def _is_bindata_path(path: str) -> bool:
    return any(part.lower() == "bindata" for part in PurePosixPath(path).parts)


def analyze_template(source: str | Path) -> TemplateAnalysis:
    source_path = Path(source)
    package = HwpxPackage.open(source_path)
    relationships = parse_manifest_relationships(
        package.manifest_tree(),
        package.main_content.full_path,
        known_parts=package.part_names(),
    )

    header_paths = tuple(package.header_paths())
    header_xml = package.get_xml(header_paths[0]) if header_paths else None
    font_faces = _extract_font_faces(header_xml)
    char_properties = _extract_char_properties(header_xml, font_faces)
    style_by_id = _style_lookup(char_properties)

    section_layouts: list[SectionLayoutSummary] = []
    table_summaries: list[TableSummary] = []
    run_style_references: list[RunStyleReference] = []
    section_paths = tuple(package.section_paths())
    for section_path in section_paths:
        section_xml = package.get_xml(section_path)
        section_layouts.append(_extract_section_layout(section_path, section_xml))
        table_summaries.extend(_extract_tables(section_path, section_xml, style_by_id))
        run_style_references.extend(_extract_run_style_references(section_path, section_xml, style_by_id))

    return TemplateAnalysis(
        schema_version=TEMPLATE_ANALYSIS_SCHEMA_VERSION,
        source_name=source_path.name,
        part_names=tuple(package.part_names()),
        rootfiles=tuple(rootfile.full_path for rootfile in package.iter_rootfiles()),
        manifest_path=package.main_content.full_path,
        manifest_item_paths=tuple(item.resolved_path for item in relationships.items),
        header_paths=header_paths,
        section_paths=section_paths,
        master_page_paths=tuple(package.master_page_paths()),
        history_paths=tuple(package.history_paths()),
        bin_data_paths=tuple(
            item.resolved_path for item in relationships.items if _is_bindata_path(item.resolved_path)
        ),
        version_path=package.version_path(),
        header_summary=_summarize_header(header_xml),
        font_faces=font_faces,
        char_properties=char_properties,
        section_layouts=tuple(section_layouts),
        table_summaries=tuple(table_summaries),
        run_style_references=tuple(run_style_references),
        proxy_metrics=collect_metrics(source_path),
    )


def _write_part(package: HwpxPackage, part_name: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(package.get_part(part_name))
    return destination


def extract_template_parts(
    source: str | Path,
    *,
    extract_dir: str | Path | None = None,
    extract_header: str | Path | None = None,
    extract_section: str | Path | None = None,
    extract_section_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    source_path = Path(source)
    package = HwpxPackage.open(source_path)
    written: list[Path] = []

    if extract_dir is not None:
        result = unpack_hwpx(source_path, extract_dir, pretty_xml=False)
        written.extend(result.output_dir / entry.path for entry in result.entries)
        written.append(result.metadata_path)

    if extract_header is not None:
        header_paths = package.header_paths()
        if not header_paths:
            raise FileNotFoundError("package does not contain a header part")
        written.append(_write_part(package, header_paths[0], Path(extract_header)))

    if extract_section is not None:
        section_paths = package.section_paths()
        if not section_paths:
            raise FileNotFoundError("package does not contain a section part")
        written.append(_write_part(package, section_paths[0], Path(extract_section)))

    if extract_section_dir is not None:
        section_root = Path(extract_section_dir)
        section_root.mkdir(parents=True, exist_ok=True)
        for part_name in package.section_paths():
            written.append(_write_part(package, part_name, section_root / Path(part_name).name))

    return tuple(written)


def _print_summary(analysis: TemplateAnalysis) -> None:
    metrics = analysis.proxy_metrics
    print(f"source: {analysis.source_name}")
    print(f"schema: {analysis.schema_version}")
    print(f"manifest: {analysis.manifest_path}")
    print(f"rootfiles: {', '.join(analysis.rootfiles) or '(none)'}")
    print(f"headers: {', '.join(analysis.header_paths) or '(none)'}")
    print(f"sections: {', '.join(analysis.section_paths) or '(none)'}")
    print(f"masterPages: {', '.join(analysis.master_page_paths) or '(none)'}")
    print(f"histories: {', '.join(analysis.history_paths) or '(none)'}")
    print(f"BinData: {', '.join(analysis.bin_data_paths) or '(none)'}")
    if analysis.version_path:
        print(f"version part: {analysis.version_path}")
    print(
        "header styles: "
        f"fonts={analysis.header_summary.font_count}, "
        f"charPr={analysis.header_summary.char_pr_count}, "
        f"paraPr={analysis.header_summary.para_pr_count}, "
        f"borderFill={analysis.header_summary.border_fill_count}"
    )
    print(
        "template enrichment: "
        f"fontFaces={len(analysis.font_faces)}, "
        f"charProperties={len(analysis.char_properties)}, "
        f"tables={len(analysis.table_summaries)}, "
        f"runStyleRefs={len(analysis.run_style_references)}"
    )
    print(
        "layout-drift proxy: "
        f"paragraphs={metrics.paragraph_count}, "
        f"tables={metrics.table_count}, "
        f"shapes={metrics.shape_count}, "
        f"controls={metrics.control_count}, "
        f"pageBreaks={metrics.page_break_count}, "
        f"columnBreaks={metrics.column_break_count}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a reference HWPX template for pack-ready, template-preserving workflows"
    )
    parser.add_argument("input", help="Input HWPX path")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    parser.add_argument("--output-json", help="Write the JSON summary to a file")
    parser.add_argument("--schema-json", action="store_true", help="Print the agent-friendly JSON schema")
    parser.add_argument("--output-schema-json", help="Write the agent-friendly JSON schema to a file")
    parser.add_argument(
        "--extract-dir",
        help=(
            "Create a pack-ready extracted workspace that preserves archive-relative paths "
            "and hwpx-pack metadata"
        ),
    )
    parser.add_argument("--extract-header", help="Copy the first header.xml part to a path")
    parser.add_argument("--extract-section", help="Copy the first section XML part to a path")
    parser.add_argument(
        "--extract-section-dir",
        help="Backward-compatible alias that copies section*.xml files into a directory",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: file not found: {input_path}")
        return 1

    try:
        analysis = analyze_template(input_path)
        schema_only = (
            args.schema_json
            and not args.json
            and not args.output_json
            and not args.extract_dir
            and not args.extract_header
            and not args.extract_section
            and not args.extract_section_dir
        )
        if schema_only:
            print(json.dumps(template_analysis_agent_schema(), ensure_ascii=False, indent=2))
            return 0
        written = extract_template_parts(
            input_path,
            extract_dir=args.extract_dir,
            extract_header=args.extract_header,
            extract_section=args.extract_section,
            extract_section_dir=args.extract_section_dir,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.json or args.output_json:
        payload = json.dumps(asdict(analysis), ensure_ascii=False, indent=2)
        if args.json:
            print(payload)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload, encoding="utf-8")
    else:
        _print_summary(analysis)

    if args.schema_json or args.output_schema_json:
        schema_payload = json.dumps(template_analysis_agent_schema(), ensure_ascii=False, indent=2)
        if args.schema_json:
            print(schema_payload)
        if args.output_schema_json:
            schema_path = Path(args.output_schema_json)
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(schema_payload, encoding="utf-8")

    for path in written:
        print(f"extracted: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
