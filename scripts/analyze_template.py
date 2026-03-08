#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
}


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//hp:t", NS))


def summarize_header(root: etree._Element) -> list[str]:
    lines = ["== header summary =="]

    font_lines: list[str] = []
    for fontface in root.findall(".//hh:fontface", NS):
        language = fontface.get("lang", "?")
        for font in fontface.findall("hh:font", NS):
            if language == "HANGUL":
                font_lines.append(f"font[{font.get('id', '?')}]={font.get('face', '?')}")
    if font_lines:
        lines.append("fonts: " + ", ".join(font_lines[:12]))

    char_ids = [char_pr.get("id", "?") for char_pr in root.findall(".//hh:charPr", NS)]
    para_ids = [para_pr.get("id", "?") for para_pr in root.findall(".//hh:paraPr", NS)]
    border_ids = [border.get("id", "?") for border in root.findall(".//hh:borderFill", NS)]
    lines.append(f"charPr count: {len(char_ids)}")
    lines.append(f"paraPr count: {len(para_ids)}")
    lines.append(f"borderFill count: {len(border_ids)}")
    return lines


def summarize_table(table: etree._Element, indent: str = "") -> list[str]:
    rows = table.get("rowCnt", "?")
    cols = table.get("colCnt", "?")
    table_id = table.get("id", "?")
    size = table.find("hp:sz", NS)
    width = size.get("width", "?") if size is not None else "?"
    height = size.get("height", "?") if size is not None else "?"

    lines = [f"{indent}table id={table_id} rows={rows} cols={cols} width={width} height={height}"]
    for row in table.findall("hp:tr", NS):
        for cell in row.findall("hp:tc", NS):
            address = cell.find("hp:cellAddr", NS)
            span = cell.find("hp:cellSpan", NS)
            cell_size = cell.find("hp:cellSz", NS)
            sub_list = cell.find("hp:subList", NS)
            col = address.get("colAddr", "?") if address is not None else "?"
            row_index = address.get("rowAddr", "?") if address is not None else "?"
            col_span = span.get("colSpan", "1") if span is not None else "1"
            row_span = span.get("rowSpan", "1") if span is not None else "1"
            cell_width = cell_size.get("width", "?") if cell_size is not None else "?"
            cell_height = cell_size.get("height", "?") if cell_size is not None else "?"
            preview = ""
            if sub_list is not None:
                preview = _text(sub_list).strip().replace("\n", " ")[:40]
            lines.append(
                f"{indent}  cell({col},{row_index}) size={cell_width}x{cell_height} "
                f"span={col_span}x{row_span} text={preview!r}"
            )
    return lines


def summarize_section(root: etree._Element) -> list[str]:
    lines = ["== section summary =="]
    section = root.find(".//hs:sec", NS)
    if section is None:
        section = root

    paragraphs = section.findall("hp:p", NS)
    lines.append(f"paragraph count: {len(paragraphs)}")

    for index, paragraph in enumerate(paragraphs, start=1):
        text = _text(paragraph).strip().replace("\n", " ")
        table = paragraph.find(".//hp:tbl", NS)
        if table is not None:
            lines.append(f"P{index}: [table paragraph]")
            lines.extend(summarize_table(table, indent="  "))
            continue
        preview = text[:80]
        lines.append(f"P{index}: paraPr={paragraph.get('paraPrIDRef', '0')} text={preview!r}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a reference HWPX template")
    parser.add_argument("input", help="Input HWPX path")
    parser.add_argument("--extract-header", metavar="PATH", help="Copy Contents/header.xml to PATH")
    parser.add_argument(
        "--extract-section-dir",
        metavar="DIR",
        help="Copy every Contents/section*.xml into DIR",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        raise SystemExit(f"File not found: {input_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        with zipfile.ZipFile(input_path, "r") as archive:
            archive.extractall(work)

        header_path = work / "Contents" / "header.xml"
        section_paths = sorted((work / "Contents").glob("section*.xml"))
        if not header_path.is_file() or not section_paths:
            raise SystemExit("Contents/header.xml or section*.xml not found")

        if args.extract_header:
            shutil.copy2(header_path, args.extract_header)
            print(f"header.xml -> {args.extract_header}")

        if args.extract_section_dir:
            output_dir = Path(args.extract_section_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            for src in section_paths:
                destination = output_dir / src.name
                shutil.copy2(src, destination)
                print(f"{src.name} -> {destination}")

        header_root = etree.parse(str(header_path)).getroot()
        print("\n".join(summarize_header(header_root)))
        print()

        for section_path in section_paths:
            print(f"## {section_path.name}")
            section_root = etree.parse(str(section_path)).getroot()
            print("\n".join(summarize_section(section_root)))
            print()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
