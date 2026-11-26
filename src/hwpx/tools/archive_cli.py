# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from ..errors import HwpxError, HwpxValueError
from ..opc.package import names_same_file, refuse_existing_hwp_target
from ..opc.relationships import is_header_part_name, is_section_part_name
from ..oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from .package_validator import validate_editor_open_safety, validate_package
from ..opc.security import HwpxSecurityError, guard_zip_file, read_member
from ..opc.xml_utils import parse_untrusted_xml

_XML_SUFFIXES = (".xml", ".hpf")
_PACK_METADATA_NAME = ".hwpx-pack-metadata.json"

__all__ = [
    "ArchiveEntryInfo",
    "UnpackResult",
    "PackResult",
    "pack_hwpx",
    "unpack_hwpx",
    "input_file_problem",
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
    open_safety: dict[str, Any]


def _guard_destructive_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"refusing to overwrite filesystem root: {resolved}")
    if resolved == Path.cwd().resolve():
        raise ValueError(f"refusing to overwrite current working directory: {resolved}")


def _same_or_inside(path: Path, folder: Path) -> bool:
    """Whether *path* is *folder* itself or lies anywhere under it, once both are resolved."""

    resolved = path.resolve()
    base = folder.resolve()
    lineage = (resolved, *resolved.parents)
    base_key = os.path.normcase(str(base))
    if any(os.path.normcase(str(candidate)) == base_key for candidate in lineage):
        return True
    if not base.exists():
        return False
    for candidate in lineage:
        try:
            if os.path.samefile(candidate, base):
                return True
        except OSError:  # a part of the path that does not exist yet
            continue
    return False


def _check_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    """Refuse an output folder unpacking may not replace. Nothing on disk changes here."""

    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(f"output exists and is not a directory: {output_dir}")
    if output_dir.is_dir() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"output directory is not empty: {output_dir}")
        _guard_destructive_target(output_dir)


def _make_missing_dirs(folder: Path) -> list[Path]:
    """Create *folder* and its missing parents; return the folders made, outermost first."""

    missing: list[Path] = []
    current = folder
    while not current.exists() and current != current.parent:
        missing.append(current)
        current = current.parent
    missing.reverse()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except BaseException:
        _remove_made_dirs(missing)
        raise
    return missing


def _remove_made_dirs(made: list[Path]) -> None:
    """Take back the folders a refused or failed call made, each only while it is empty."""

    for folder in reversed(made):
        try:
            folder.rmdir()
        except OSError:
            continue


def _move_into_place(staging: Path, target: Path) -> None:
    """Make the folder *staging* the folder at *target*.

    The folder already at *target* is set aside under another name first and removed only
    after the new one is in; when the new one cannot move in, it is put back.
    """

    set_aside: Path | None = None
    was_empty = False
    if target.is_dir():
        if any(target.iterdir()):
            set_aside = staging.with_suffix(".unpack-old")
            os.rename(target, set_aside)
        else:
            target.rmdir()
            was_empty = True
    try:
        os.rename(staging, target)
    except BaseException:
        if set_aside is not None:
            os.rename(set_aside, target)
        elif was_empty:
            target.mkdir()
        raise
    if set_aside is None:
        return
    try:
        if set_aside.is_symlink():
            set_aside.unlink()
        else:
            shutil.rmtree(set_aside)
    except OSError as exc:
        warnings.warn(
            f"unpacked into {target}, but what was there before could not be removed and stays in {set_aside}: {exc}",
            RuntimeWarning,
            stacklevel=3,
        )


_MAX_INDENT_GROWTH = 8
_MIN_INDENT_BUDGET = 64 * 1024


def _format_xml_bytes(payload: bytes) -> bytes:
    """Re-indent an XML part, falling back to the original bytes.

    Indentation is an amplifier: at the depth libxml2 accepts, every leaf gains
    two spaces per level, so a 4-byte element can grow past 500 bytes. The
    payload is guarded first, and a result that grew beyond the per-member
    allowance is discarded in favour of the input.
    """

    try:
        element = parse_untrusted_xml(payload, part_name="XML part")
    except (etree.XMLSyntaxError, HwpxSecurityError):
        return payload
    etree.indent(element, space="  ")
    formatted = etree.tostring(
        element,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    # Real parts grow at most ~1.7x when indented (measured across the repo's
    # packages); anything past this is the indentation acting as an amplifier.
    if len(formatted) > max(_MAX_INDENT_GROWTH * len(payload), _MIN_INDENT_BUDGET):
        return payload
    return formatted


def _normalize_hwpml_compat_root(rel_path: str, payload: bytes) -> bytes:
    if not (is_section_part_name(rel_path) or is_header_part_name(rel_path)):
        return payload
    try:
        root = parse_untrusted_xml(payload, part_name=rel_path)
    except (etree.XMLSyntaxError, HwpxSecurityError):
        return payload
    if not (root.tag.endswith("}sec") or root.tag.endswith("}head")):
        return payload

    wrapped = etree.Element(root.tag, nsmap=HWPML_COMPAT_ROOT_NAMESPACES)
    wrapped.attrib.update(root.attrib)
    wrapped.text = root.text
    wrapped.tail = root.tail
    for child in root:
        wrapped.append(child)
    return etree.tostring(
        wrapped,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
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


def _summarize_pack_validation(output_path: Path) -> dict[str, Any]:
    report = validate_package(output_path)
    if report.ok:
        safety_report = validate_editor_open_safety(output_path)
        if safety_report.ok:
            return safety_report.to_dict()
        raise ValueError(
            "packed archive failed editor-open safety validation:\n"
            + safety_report.summary
        )
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
    if _same_or_inside(source_path, destination):
        raise HwpxValueError(
            f"input file {source_path} is at or inside the output folder {destination}, and unpacking "
            "replaces that folder; give an output folder that does not hold the input",
            code="package-unpack-input-inside-output",
            context={"input": str(source_path), "output": str(destination)},
            suggestion="Unpack into a new folder outside the one that holds the input file.",
        )
    _check_output_dir(destination, overwrite=overwrite)

    # The whole input is unpacked into a new folder beside the output folder first. The
    # output folder changes only after every member was read and written, so an input
    # that does not open, or that fails partway, costs none of the folder's old contents.
    final_dir = Path(os.path.abspath(destination))
    with ZipFile(source_path, "r") as archive:
        guard_zip_file(archive)
        entries = _iter_file_entries(archive)
        made = _make_missing_dirs(final_dir.parent)
        staging = final_dir.parent / f".{final_dir.name}.{os.urandom(4).hex()}.unpack-tmp"
        try:
            staging.mkdir()
            for entry in entries:
                data = read_member(archive, entry.path)
                if pretty_xml and entry.path.endswith(_XML_SUFFIXES):
                    data = _format_xml_bytes(data)
                target = staging / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            _write_pack_metadata(staging, entries)
            _move_into_place(staging, final_dir)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            _remove_made_dirs(made)
            raise

    return UnpackResult(output_dir=destination, metadata_path=_metadata_path(destination), entries=entries)


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
    if _same_or_inside(destination, root):
        raise HwpxValueError(
            f"output {destination} is at or inside the input folder {root}, where the next pack would "
            "take it in as a part; give an output path outside that folder",
            code="package-pack-output-inside-input",
            context={"input": str(root), "output": str(destination)},
            suggestion="Write the packed file outside the folder being packed.",
        )
    refuse_existing_hwp_target(destination)  # overwrite=True (--force) does not lift this
    if destination.exists() and not overwrite:
        raise FileExistsError(f"output file already exists: {destination}")

    files = _discover_files(root)
    if "mimetype" not in files:
        raise FileNotFoundError(f"missing required 'mimetype' file in {root}")

    metadata = _read_pack_metadata(root)
    compress_types = {entry.path: entry.compress_type for entry in metadata}
    ordered_paths = _resolve_write_order(files, metadata)

    # The output's folder is made only now, after every refusal above, and taken back
    # when the pack fails: a call that writes no file leaves no folder either.
    made = _make_missing_dirs(Path(os.path.abspath(destination)).parent)
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".hwpx.tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as archive:
            archive.write(root / "mimetype", "mimetype", compress_type=ZIP_STORED)
            for rel_path in ordered_paths:
                if rel_path == "mimetype":
                    continue
                compress_type = compress_types.get(rel_path, ZIP_DEFLATED)
                if compress_type != ZIP_STORED:
                    compress_type = ZIP_DEFLATED
                payload = _normalize_hwpml_compat_root(
                    rel_path,
                    (root / rel_path).read_bytes(),
                )
                archive.writestr(rel_path, payload, compress_type=compress_type)

        open_safety = _summarize_pack_validation(tmp_path)
        os.replace(tmp_path, destination)
    except BaseException:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        _remove_made_dirs(made)
        raise

    return PackResult(
        output_path=destination,
        entries=ordered_paths,
        open_safety=open_safety,
    )


def input_file_problem(path: str | os.PathLike[str], *, tool: str, accepts_hwp: bool = False) -> str | None:
    """One line saying why a command-line tool cannot read *path*, or ``None`` when it can try.

    Shared by the ``hwpx-*`` commands (and any command built on python-hwpx): a missing
    path, a folder, an HWP 3.x file, and an HWP 5.0 ``.hwp`` file given to a tool that
    reads only HWPX (*accepts_hwp* false) get the same short words everywhere. *tool* is
    the command's name as the message gives it. Only the first bytes are read; ``None``
    does not promise the file opens.
    """

    from ..opc.package import HwpxPackage

    target = Path(path)
    if not target.exists():
        return f"file not found: {target}"
    if target.is_dir():
        return f"{target} is a folder; give the path of an .hwpx file"
    try:
        with target.open("rb") as stream:
            head = stream.read(len(HwpxPackage.HWP3_MAGIC))
    except OSError as exc:
        return f"cannot read {target}: {exc.strerror or exc}"
    if head.startswith(HwpxPackage.HWP3_MAGIC):
        return f"{target.name} is an HWP 3.x file, which python-hwpx cannot read; open it in Hancom Office and save it as .hwpx"
    if head.startswith(HwpxPackage.OLE2_MAGIC) and not accepts_hwp:
        converted = target.with_suffix(".hwpx").name
        return (
            f"{target.name} is an HWP 5.0 (.hwp) file and {tool} reads .hwpx files only; convert it first: "
            f"python -c \"from hwpx import HwpxDocument; HwpxDocument.open(r'{target}').save('{converted}')\""
        )
    return None


_input_file_problem = input_file_problem

#: The codes of an output path refused before anything was written (see ``_refuse_output_over_document``).
_OUTPUT_REFUSAL_CODES = frozenset({"package-output-is-input", "hwp5-overwrite-existing"})


def _refuse_output_over_document(
    output: str | os.PathLike[str], *inputs: str | os.PathLike[str]
) -> None:
    """Refuse a path a command is about to write text, JSON or XML to when a document is there.

    Asked for every such output argument before the command writes anything: an output that names
    one of the files the command reads (*inputs*), under any spelling the file system resolves to
    it, would replace that document with what was read from it (``package-output-is-input``); and
    an ``.hwp`` file that is already there is written over by nothing
    (:func:`hwpx.opc.package.refuse_existing_hwp_target`, ``hwp5-overwrite-existing``; a file with
    no bytes passes). Any other path passes, a file that is already there included.
    """

    for source in inputs:
        if names_same_file(output, source):
            raise HwpxValueError(
                f"output {os.fspath(output)} is the input file {os.fspath(source)}; writing there would "
                "replace the document, so nothing was written.",
                code="package-output-is-input",
                context={"input": str(source), "output": str(output)},
                suggestion="Give another output path; the input file was not changed.",
            )
    refuse_existing_hwp_target(output)


def _error_line(exc: BaseException) -> str:
    """What a command prints after ``ERROR:`` for *exc*: for a refused output path the message, how
    to go on and the error's code on one line; for anything else the message as it always was."""

    if isinstance(exc, HwpxError) and exc.code in _OUTPUT_REFUSAL_CODES:
        return " ".join(part for part in (str(exc), exc.suggestion, f"[{exc.code}]") if part)
    return str(exc)


def _printable_stdout() -> None:
    """Let standard output print any character: one it cannot encode (a Korean file name into a cp1252 pipe
    on an English Windows) comes out as an escape instead of failing the command with UnicodeEncodeError.
    Output that fits the stream's encoding is unchanged."""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="backslashreplace")
    except (ValueError, OSError):  # a closed or detached stream: nothing to set
        return


def unpack_main(argv: Sequence[str] | None = None) -> int:
    _printable_stdout()
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

    problem = _input_file_problem(args.input, tool="hwpx-unpack")
    if problem is not None:
        print(f"ERROR: {problem}")
        return 1
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
    _warn_duplicate_entries(args.input, "only the last of each was unpacked")
    return 0


def _warn_duplicate_entries(path: str | Path, consequence: str) -> None:
    from zipfile import BadZipFile, ZipFile

    from ..opc.security import _duplicate_entry_notice

    try:
        with ZipFile(path) as archive:
            notice = _duplicate_entry_notice(info.filename for info in archive.infolist())
    except (OSError, BadZipFile):
        return
    if notice is not None:
        print(f"WARN: {notice}; {consequence}")


def pack_main(argv: Sequence[str] | None = None) -> int:
    _printable_stdout()
    parser = argparse.ArgumentParser(description="Pack a directory into an HWPX archive")
    parser.add_argument("input", help="Input directory")
    parser.add_argument("output", help="Output .hwpx path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing output file",
    )
    args = parser.parse_args(argv)

    if Path(args.input).is_file():
        print(f"ERROR: {args.input} is a file; hwpx-pack takes the folder hwpx-unpack made")
        return 1
    try:
        result = pack_hwpx(args.input, args.output, overwrite=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Packed {args.input} -> {result.output_path}")
    print(f"open_safety_ok={str(bool(result.open_safety.get('ok'))).lower()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    _printable_stdout()
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
