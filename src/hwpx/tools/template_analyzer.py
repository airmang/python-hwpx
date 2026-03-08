from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

from ..opc.package import HwpxPackage
from .page_guard import DocumentMetrics, collect_metrics

_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HH = {"hh": _HH_NS}

__all__ = [
    "HeaderSummary",
    "TemplateAnalysis",
    "analyze_template",
    "extract_template_parts",
    "main",
]


@dataclass(frozen=True)
class HeaderSummary:
    font_count: int
    char_pr_count: int
    para_pr_count: int
    border_fill_count: int


@dataclass(frozen=True)
class TemplateAnalysis:
    source_name: str
    part_names: tuple[str, ...]
    rootfiles: tuple[str, ...]
    manifest_path: str
    header_paths: tuple[str, ...]
    section_paths: tuple[str, ...]
    version_path: str | None
    header_summary: HeaderSummary
    proxy_metrics: DocumentMetrics


def _summarize_header(element: ET.Element | None) -> HeaderSummary:
    if element is None:
        return HeaderSummary(font_count=0, char_pr_count=0, para_pr_count=0, border_fill_count=0)

    font_count = len(element.findall(".//hh:fontface/hh:font", _HH))
    char_pr_count = len(element.findall(".//hh:charPr", _HH))
    para_pr_count = len(element.findall(".//hh:paraPr", _HH))
    border_fill_count = len(element.findall(".//hh:borderFill", _HH))
    return HeaderSummary(
        font_count=font_count,
        char_pr_count=char_pr_count,
        para_pr_count=para_pr_count,
        border_fill_count=border_fill_count,
    )


def analyze_template(source: str | Path) -> TemplateAnalysis:
    source_path = Path(source)
    package = HwpxPackage.open(source_path)

    header_paths = tuple(package.header_paths())
    header_xml = package.get_xml(header_paths[0]) if header_paths else None
    manifest_path = package.main_content.full_path
    version_path = package.version_path()

    return TemplateAnalysis(
        source_name=source_path.name,
        part_names=tuple(package.part_names()),
        rootfiles=tuple(rootfile.full_path for rootfile in package.iter_rootfiles()),
        manifest_path=manifest_path,
        header_paths=header_paths,
        section_paths=tuple(package.section_paths()),
        version_path=version_path,
        header_summary=_summarize_header(header_xml),
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
        root = Path(extract_dir)
        root.mkdir(parents=True, exist_ok=True)
        written.append(_write_part(package, package.main_content.full_path, root / package.main_content.full_path))
        for part_name in package.header_paths():
            written.append(_write_part(package, part_name, root / part_name))
        for part_name in package.section_paths():
            written.append(_write_part(package, part_name, root / part_name))
        version_path = package.version_path()
        if version_path and package.has_part(version_path):
            written.append(_write_part(package, version_path, root / version_path))
        if package.has_part(package.CONTAINER_PATH):
            written.append(_write_part(package, package.CONTAINER_PATH, root / package.CONTAINER_PATH))

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
    print(f"manifest: {analysis.manifest_path}")
    print(f"rootfiles: {', '.join(analysis.rootfiles) or '(none)'}")
    print(f"headers: {', '.join(analysis.header_paths) or '(none)'}")
    print(f"sections: {', '.join(analysis.section_paths) or '(none)'}")
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
        description="Analyze a reference HWPX template for template-preserving workflows"
    )
    parser.add_argument("input", help="Input HWPX path")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    parser.add_argument("--output-json", help="Write the JSON summary to a file")
    parser.add_argument(
        "--extract-dir",
        help="Copy manifest, header, sections, version, and container.xml into a directory",
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

    for path in written:
        print(f"extracted: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
