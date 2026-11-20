# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, Union
from zipfile import BadZipFile, ZipFile

from .text_extractor import TextExtractor

__all__ = [
    "extract_plain",
    "main",
]

#: ``--format markdown`` moved with the Markdown export (python-hwpx-automation, 7.0).
_MARKDOWN_MOVED = (
    "--format markdown은 python-hwpx 7.0에서 python-hwpx-automation으로 옮겼습니다.\n"
    '    pip install -U "python-hwpx-automation>=8"\n'
    "    from hwpx_automation.markdown import to_markdown\n"
    "글만 뽑으려면 --format plain(기본값)을 쓰세요."
)


def __getattr__(name: str) -> object:
    if name == "extract_markdown":  # 6.x exported it from here; it went with the Markdown export (7.0)
        from .. import MovedToCompanion, _moved_modules

        raise MovedToCompanion(
            _moved_modules.moved_name_message(
                "hwpx.tools.text_extract_cli.extract_markdown", "from hwpx_automation.markdown import to_markdown"
            )
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def extract_plain(hwpx_path: Union[str, ZipFile], *, include_tables: bool = False) -> str:
    with TextExtractor(hwpx_path) as extractor:
        return extractor.extract_text(
            include_nested=include_tables,
            object_behavior="skip",
            skip_empty=True,
        )


def _hwpx_source(input_path: Path) -> "str | ZipFile":
    """The path itself for an HWPX file; for an HWP 5.0 file, the HWPX it converts to."""

    from ..opc.package import HwpxPackage

    with input_path.open("rb") as stream:
        is_hwp5 = stream.read(len(HwpxPackage.OLE2_MAGIC)) == HwpxPackage.OLE2_MAGIC
    if not is_hwp5:
        return str(input_path)
    import io
    import warnings

    from ..document import HwpxDocument
    from ..errors import Hwp5ConversionWarning

    with warnings.catch_warnings():
        # What the conversion left out is not the text; the text comes out either way.
        warnings.simplefilter("ignore", Hwp5ConversionWarning)
        document = HwpxDocument.open(input_path)
    try:
        data = document.to_bytes()
    finally:
        document.close()
    return ZipFile(io.BytesIO(data))


def _warn_duplicate_entries(input_path: Path) -> None:
    """Say on stderr when the archive holds a name twice: the text comes from the last entry of each."""

    from ..opc.security import _duplicate_entry_notice

    try:
        with ZipFile(input_path) as archive:
            notice = _duplicate_entry_notice(info.filename for info in archive.infolist())
    except (OSError, BadZipFile):
        return  # not a ZIP (an .hwp) or unreadable: the extraction says so itself
    if notice is not None:
        print(f"Warning: {notice}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract text from an HWPX (or HWP 5.0 .hwp) document")
    parser.add_argument("input", help="Path to the .hwpx or .hwp file")
    parser.add_argument("--format", "-f", choices=["plain", "markdown"], default="plain")
    parser.add_argument("--include-tables", action="store_true", help="Include nested table text")
    parser.add_argument("--output", "-o", help="Write output to a file instead of stdout")
    args = parser.parse_args(argv)
    if args.format == "markdown":
        print(f"Error: {_MARKDOWN_MOVED}", file=sys.stderr)
        return 2

    from .archive_cli import _input_file_problem

    input_path = Path(args.input)
    problem = _input_file_problem(input_path, tool="hwpx-text-extract", accepts_hwp=True)
    if problem is not None:
        print(f"Error: {problem}", file=sys.stderr)
        return 1

    _warn_duplicate_entries(input_path)
    try:
        source = _hwpx_source(input_path)
        result = extract_plain(source, include_tables=args.include_tables)
    except Exception as exc:  # noqa: BLE001 - one line for the person at the terminal
        print(f"Error: cannot read {args.input}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
    else:
        _print_text(result)
    return 0


def _print_text(text: str) -> None:
    """Print *text*; where standard output cannot hold it (a pipe in cp1252 on an English Windows cannot
    hold Korean), write it as UTF-8 -- the encoding ``--output`` writes -- instead of failing."""

    try:
        print(text)
    except UnicodeEncodeError:
        stream = sys.stdout
        stream.flush()
        stream.buffer.write((text + "\n").encode("utf-8"))
        stream.buffer.flush()


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
