"""Proxy checks for layout drift between a reference and an output HWPX.

This module does not calculate rendered page counts. It compares structural and
textual metrics that often correlate with page-layout drift.
"""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence
from zipfile import ZipFile

from lxml import etree

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "opf": "http://www.idpf.org/2007/opf/",
}

_SHAPE_TAGS = {
    "line",
    "rect",
    "ellipse",
    "arc",
    "polygon",
    "curve",
    "connectLine",
    "textart",
    "pic",
    "compose",
    "equation",
    "ole",
    "container",
}

__all__ = [
    "DocumentMetrics",
    "collect_metrics",
    "compare_metrics",
    "main",
]


@dataclass(frozen=True)
class DocumentMetrics:
    section_count: int
    paragraph_count: int
    page_break_count: int
    column_break_count: int
    table_count: int
    shape_count: int
    control_count: int
    table_shapes: list[tuple[str, str, str, str, str, str]]
    shape_types: list[tuple[str, int]]
    control_types: list[tuple[str, int]]
    text_char_total: int
    text_char_total_nospace: int
    paragraph_text_lengths: list[int]


def _section_files(zf: ZipFile) -> list[str]:
    try:
        root = etree.fromstring(zf.read("Contents/content.hpf"))
    except KeyError:
        return [
            name
            for name in zf.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        ]

    id_to_href: dict[str, str] = {}
    for item in root.findall(".//opf:item", namespaces=NS):
        item_id = item.get("id")
        href = item.get("href")
        if item_id and href:
            id_to_href[item_id] = href

    files: list[str] = []
    for itemref in root.findall(".//opf:itemref", namespaces=NS):
        idref = itemref.get("idref")
        if idref and idref in id_to_href:
            files.append(id_to_href[idref])
    return files


def _text_of_t_node(node: etree._Element) -> str:
    return "".join(node.itertext())


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_section_roots(source: str | Path | bytes | BinaryIO) -> Iterable[etree._Element]:
    if isinstance(source, bytes):
        archive = ZipFile(io.BytesIO(source), "r")
    else:
        archive = ZipFile(source, "r")

    try:
        for name in _section_files(archive):
            yield etree.fromstring(archive.read(name))
    finally:
        archive.close()


def collect_metrics(source: str | Path | bytes | BinaryIO) -> DocumentMetrics:
    section_roots = list(_iter_section_roots(source))

    paragraphs: list[etree._Element] = []
    tables: list[etree._Element] = []
    table_shapes: list[tuple[str, str, str, str, str, str]] = []
    shape_types: dict[str, int] = {}
    control_types: dict[str, int] = {}
    paragraph_text_lengths: list[int] = []
    text_char_total = 0
    text_char_total_nospace = 0
    page_break_count = 0
    column_break_count = 0

    for root in section_roots:
        section_paragraphs = root.xpath(".//hs:sec/hp:p", namespaces=NS)
        if not section_paragraphs:
            section_paragraphs = root.xpath(".//hp:p", namespaces=NS)
        paragraphs.extend(section_paragraphs)

        section_tables = root.xpath(".//hp:tbl", namespaces=NS)
        tables.extend(section_tables)

        for element in root.iter():
            name = _local_name(element.tag)
            if name in _SHAPE_TAGS:
                shape_types[name] = shape_types.get(name, 0) + 1
            if name == "ctrl":
                control_counted = False
                for child in element:
                    child_name = _local_name(child.tag)
                    control_types[child_name] = control_types.get(child_name, 0) + 1
                    control_counted = True
                if not control_counted:
                    control_types["ctrl"] = control_types.get("ctrl", 0) + 1

        for table in section_tables:
            size = table.find("hp:sz", namespaces=NS)
            table_shapes.append(
                (
                    table.get("rowCnt", ""),
                    table.get("colCnt", ""),
                    size.get("width", "") if size is not None else "",
                    size.get("height", "") if size is not None else "",
                    table.get("repeatHeader", ""),
                    table.get("pageBreak", ""),
                )
            )

        for paragraph in section_paragraphs:
            if paragraph.get("pageBreak") == "1":
                page_break_count += 1
            if paragraph.get("columnBreak") == "1":
                column_break_count += 1
            paragraph_length = 0
            for text_node in paragraph.xpath(".//hp:t", namespaces=NS):
                text = _text_of_t_node(text_node)
                paragraph_length += len(text)
                text_char_total += len(text)
                text_char_total_nospace += len("".join(text.split()))
            paragraph_text_lengths.append(paragraph_length)

    return DocumentMetrics(
        section_count=len(section_roots),
        paragraph_count=len(paragraphs),
        page_break_count=page_break_count,
        column_break_count=column_break_count,
        table_count=len(tables),
        shape_count=sum(shape_types.values()),
        control_count=sum(control_types.values()),
        table_shapes=table_shapes,
        shape_types=sorted(shape_types.items()),
        control_types=sorted(control_types.items()),
        text_char_total=text_char_total,
        text_char_total_nospace=text_char_total_nospace,
        paragraph_text_lengths=paragraph_text_lengths,
    )


def _ratio_delta(reference_value: int, output_value: int) -> float:
    base = max(reference_value, 1)
    return abs(output_value - reference_value) / base


def compare_metrics(
    reference: DocumentMetrics,
    output: DocumentMetrics,
    *,
    max_text_delta_ratio: float = 0.15,
    max_paragraph_delta_ratio: float = 0.25,
) -> list[str]:
    errors: list[str] = []

    if reference.section_count != output.section_count:
        errors.append(
            f"section count mismatch: ref={reference.section_count}, out={output.section_count}"
        )
    if reference.paragraph_count != output.paragraph_count:
        errors.append(
            f"paragraph count mismatch: ref={reference.paragraph_count}, out={output.paragraph_count}"
        )
    if reference.page_break_count != output.page_break_count:
        errors.append(
            "pageBreak count mismatch: "
            f"ref={reference.page_break_count}, out={output.page_break_count}"
        )
    if reference.column_break_count != output.column_break_count:
        errors.append(
            "columnBreak count mismatch: "
            f"ref={reference.column_break_count}, out={output.column_break_count}"
        )
    if reference.table_count != output.table_count:
        errors.append(f"table count mismatch: ref={reference.table_count}, out={output.table_count}")
    if reference.shape_count != output.shape_count:
        errors.append(f"shape count mismatch: ref={reference.shape_count}, out={output.shape_count}")
    if reference.control_count != output.control_count:
        errors.append(
            f"control count mismatch: ref={reference.control_count}, out={output.control_count}"
        )
    if reference.table_shapes != output.table_shapes:
        errors.append("table shape mismatch (rowCnt/colCnt/width/height/repeatHeader/pageBreak)")
    if reference.shape_types != output.shape_types:
        errors.append("shape type histogram mismatch")
    if reference.control_types != output.control_types:
        errors.append("control type histogram mismatch")

    text_delta = _ratio_delta(reference.text_char_total_nospace, output.text_char_total_nospace)
    if text_delta > max_text_delta_ratio:
        errors.append(
            "total text length drift exceeded: "
            f"ref={reference.text_char_total_nospace}, out={output.text_char_total_nospace}, "
            f"delta={text_delta:.2%}, limit={max_text_delta_ratio:.2%}"
        )

    if len(reference.paragraph_text_lengths) == len(output.paragraph_text_lengths):
        for index, (ref_len, out_len) in enumerate(
            zip(reference.paragraph_text_lengths, output.paragraph_text_lengths),
            start=1,
        ):
            if ref_len == 0 and out_len == 0:
                continue
            delta = _ratio_delta(ref_len, out_len)
            if delta > max_paragraph_delta_ratio:
                errors.append(
                    f"paragraph {index} text drift exceeded: "
                    f"ref={ref_len}, out={out_len}, delta={delta:.2%}, "
                    f"limit={max_paragraph_delta_ratio:.2%}"
                )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reference-vs-output HWPX layout-drift proxy checker"
    )
    parser.add_argument("--reference", "-r", required=True, help="Reference HWPX path")
    parser.add_argument("--output", "-o", required=True, help="Output HWPX path")
    parser.add_argument("--max-text-delta-ratio", type=float, default=0.15)
    parser.add_argument("--max-paragraph-delta-ratio", type=float, default=0.25)
    parser.add_argument("--json", action="store_true", help="Print collected metrics as JSON")
    args = parser.parse_args(argv)

    reference = collect_metrics(args.reference)
    output = collect_metrics(args.output)

    if args.json:
        print(
            json.dumps(
                {"reference": asdict(reference), "output": asdict(output)},
                ensure_ascii=False,
                indent=2,
            )
        )

    errors = compare_metrics(
        reference,
        output,
        max_text_delta_ratio=args.max_text_delta_ratio,
        max_paragraph_delta_ratio=args.max_paragraph_delta_ratio,
    )
    if errors:
        print("FAIL: page guard")
        for error in errors:
            print(f" - {error}")
        return 1

    print("PASS: page guard")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
