from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from .package_validator import validate_package

_XML_SUFFIXES = (".xml", ".hpf")
_PACK_METADATA_NAME = ".hwpx-pack-metadata.json"

__all__ = [
    "ArchiveEntryInfo",
    "UnpackResult",
    "PackResult",
    "pack_hwpx",
    "unpack_hwpx",
    "pack_main",
    "unpack_main",
    "main",
]


@dataclass(frozen=True)
class ArchiveEntryInfo:
    path: str
    compress_type: int


@dataclass(frozen=True)
class UnpackResult:
    output_dir: Path
    metadata_path: Path
    entries: tuple[ArchiveEntryInfo, ...]


@dataclass(frozen=True)
class PackResult:
    output_path: Path
    entries: tuple[str, ...]


def _guard_destructive_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"refusing to overwrite filesystem root: {resolved}")
    if resolved == Path.cwd().resolve():
        raise ValueError(f"refusing to overwrite current working directory: {resolved}")


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(f"output exists and is not a directory: {output_dir}")
    if output_dir.exists():
        if any(output_dir.iterdir()):
            if not overwrite:
                raise FileExistsError(f"output directory is not empty: {output_dir}")
            _guard_destructive_target(output_dir)
            shutil.rmtree(output_dir)
        else:
            output_dir.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)


def _prepare_output_path(output_path: Path, *, overwrite: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"output file already exists: {output_path}")


def _format_xml_bytes(payload: bytes) -> bytes:
    try:
        element = etree.fromstring(payload)
    except etree.XMLSyntaxError:
        return payload
    etree.indent(element, space="  ")
    return etree.tostring(
        element,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )


def _iter_file_entries(archive: ZipFile) -> tuple[ArchiveEntryInfo, ...]:
    entries: list[ArchiveEntryInfo] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        entries.append(ArchiveEntryInfo(path=info.filename, compress_type=info.compress_type))
    return tuple(entries)


def _metadata_path(root: Path) -> Path:
    return root / _PACK_METADATA_NAME


def _write_pack_metadata(root: Path, entries: tuple[ArchiveEntryInfo, ...]) -> Path:
    destination = _metadata_path(root)
    payload = {
        "format_version": 1,
        "entries": [asdict(entry) for entry in entries],
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def _read_pack_metadata(root: Path) -> tuple[ArchiveEntryInfo, ...]:
    metadata_file = _metadata_path(root)
    if not metadata_file.is_file():
        return ()

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    entries: list[ArchiveEntryInfo] = []
    for entry in data.get("entries", []):
        path = str(entry.get("path", "")).strip()
        if not path:
            continue
        entries.append(
            ArchiveEntryInfo(
                path=path.replace("\\", "/"),
                compress_type=int(entry.get("compress_type", ZIP_DEFLATED)),
            )
        )
    return tuple(entries)


def _discover_files(root: Path) -> set[str]:
    paths: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root).as_posix()
        if rel_path == _PACK_METADATA_NAME:
            continue
        paths.add(rel_path)
    return paths


def _resolve_write_order(paths: set[str], metadata: tuple[ArchiveEntryInfo, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()

    if "mimetype" in paths:
        ordered.append("mimetype")
        seen.add("mimetype")

    for entry in metadata:
        if entry.path in paths and entry.path not in seen:
            ordered.append(entry.path)
            seen.add(entry.path)

    for path in sorted(paths):
        if path in seen:
            continue
        ordered.append(path)
        seen.add(path)

    return tuple(ordered)


def _summarize_pack_validation(output_path: Path) -> None:
    report = validate_package(output_path)
    if report.ok:
        return
    summary = "\n".join(f"- {issue}" for issue in report.errors[:10])
    raise ValueError(f"packed archive failed validation:\n{summary}")


def unpack_hwpx(
    source: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    pretty_xml: bool = False,
) -> UnpackResult:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"input file not found: {source_path}")

    destination = Path(output_dir)
    _prepare_output_dir(destination, overwrite=overwrite)

    with ZipFile(source_path, "r") as archive:
        entries = _iter_file_entries(archive)
        for entry in entries:
            data = archive.read(entry.path)
            if pretty_xml and entry.path.endswith(_XML_SUFFIXES):
                data = _format_xml_bytes(data)
            target = destination / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    metadata_path = _write_pack_metadata(destination, entries)
    return UnpackResult(output_dir=destination, metadata_path=metadata_path, entries=entries)


def _add_unpack_xml_format_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pretty-xml",
        action="store_true",
        help="Reformat XML/HWPF payloads for easier manual inspection",
    )
    group.add_argument(
        "--no-pretty-xml",
        action="store_true",
        help="Deprecated alias for the default raw-byte preserving behavior",
    )


def _resolve_pretty_xml_flag(args: argparse.Namespace) -> bool:
    if getattr(args, "no_pretty_xml", False):
        print(
            "WARN: --no-pretty-xml is deprecated because raw XML preservation is now the default.",
            file=sys.stderr,
        )
    return bool(getattr(args, "pretty_xml", False))


def pack_hwpx(
    input_dir: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> PackResult:
    root = Path(input_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"input directory not found: {root}")

    destination = Path(output_path)
    _prepare_output_path(destination, overwrite=overwrite)

    files = _discover_files(root)
    if "mimetype" not in files:
        raise FileNotFoundError(f"missing required 'mimetype' file in {root}")

    metadata = _read_pack_metadata(root)
    compress_types = {entry.path: entry.compress_type for entry in metadata}
    ordered_paths = _resolve_write_order(files, metadata)

    fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".hwpx.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as archive:
            archive.write(root / "mimetype", "mimetype", compress_type=ZIP_STORED)
            for rel_path in ordered_paths:
                if rel_path == "mimetype":
                    continue
                compress_type = compress_types.get(rel_path, ZIP_DEFLATED)
                if compress_type != ZIP_STORED:
                    compress_type = ZIP_DEFLATED
                archive.write(root / rel_path, rel_path, compress_type=compress_type)

        _summarize_pack_validation(tmp_path)
        os.replace(tmp_path, destination)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return PackResult(output_path=destination, entries=ordered_paths)


def unpack_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unpack an HWPX file into a directory (raw XML bytes are preserved by default)"
    )
    parser.add_argument("input", help="Input .hwpx path")
    parser.add_argument("output", help="Output directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow deleting an existing non-empty output directory",
    )
    _add_unpack_xml_format_args(parser)
    args = parser.parse_args(argv)

    try:
        result = unpack_hwpx(
            args.input,
            args.output,
            overwrite=args.force,
            pretty_xml=_resolve_pretty_xml_flag(args),
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Unpacked {args.input} -> {result.output_dir}")
    print(f"Recorded archive metadata at {result.metadata_path}")
    return 0


def pack_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pack a directory into an HWPX archive")
    parser.add_argument("input", help="Input directory")
    parser.add_argument("output", help="Output .hwpx path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing output file",
    )
    args = parser.parse_args(argv)

    try:
        result = pack_hwpx(args.input, args.output, overwrite=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Packed {args.input} -> {result.output_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HWPX archive utility helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    unpack_parser = subparsers.add_parser("unpack", help="Unpack an HWPX file")
    unpack_parser.add_argument("input")
    unpack_parser.add_argument("output")
    unpack_parser.add_argument("--force", action="store_true")
    _add_unpack_xml_format_args(unpack_parser)

    pack_parser = subparsers.add_parser("pack", help="Pack a directory into HWPX")
    pack_parser.add_argument("input")
    pack_parser.add_argument("output")
    pack_parser.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "unpack":
        forward = [args.input, args.output]
        if args.force:
            forward.append("--force")
        if args.pretty_xml:
            forward.append("--pretty-xml")
        if args.no_pretty_xml:
            forward.append("--no-pretty-xml")
        return unpack_main(forward)

    forward = [args.input, args.output]
    if args.force:
        forward.append("--force")
    return pack_main(forward)


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
