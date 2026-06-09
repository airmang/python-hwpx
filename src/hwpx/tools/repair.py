# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree

from ..opc.relationships import is_header_part_name, is_section_part_name
from ..oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from .package_validator import MIMETYPE_PATH, validate_editor_open_safety, validate_package
from .recover import recover_entries

__all__ = [
    "RepairResult",
    "repair_from_recovered",
    "repair_repack",
    "main",
]


@dataclass(frozen=True)
class RepairResult:
    output_path: Path
    entries: tuple[str, ...]
    reordered: bool
    crc_ok: bool
    open_safety: dict[str, Any]
    recovered: bool = False


@dataclass(frozen=True)
class _BufferedEntry:
    info: ZipInfo
    payload: bytes


def _prepare_output_path(output_path: Path, *, overwrite: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"output file already exists: {output_path}")


def _clone_info(info: ZipInfo, *, compress_type: int) -> ZipInfo:
    cloned = ZipInfo(filename=info.filename, date_time=info.date_time)
    cloned.comment = info.comment
    cloned.extra = info.extra
    cloned.internal_attr = info.internal_attr
    cloned.external_attr = info.external_attr
    cloned.create_system = info.create_system
    cloned.compress_type = compress_type
    return cloned


def _read_entries(
    source_path: Path,
    *,
    max_entry_size: int,
    max_total_size: int,
) -> tuple[_BufferedEntry, ...]:
    entries: list[_BufferedEntry] = []
    total_size = 0
    with ZipFile(source_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > max_entry_size:
                raise ValueError(f"entry exceeds max_entry_size={max_entry_size}: {info.filename}")
            total_size += info.file_size
            if total_size > max_total_size:
                raise ValueError(f"archive exceeds max_total_size={max_total_size}")
            entries.append(_BufferedEntry(info=info, payload=archive.read(info)))
    return tuple(entries)


def _ordered_entries(entries: tuple[_BufferedEntry, ...]) -> tuple[_BufferedEntry, ...]:
    mimetype_entries = [entry for entry in entries if entry.info.filename == MIMETYPE_PATH]
    if not mimetype_entries:
        raise FileNotFoundError(f"missing required {MIMETYPE_PATH!r} entry")
    if len(mimetype_entries) > 1:
        raise ValueError(f"duplicate {MIMETYPE_PATH!r} entries are ambiguous")
    mimetype = mimetype_entries[0]
    return (mimetype,) + tuple(entry for entry in entries if entry.info.filename != MIMETYPE_PATH)


def _validation_error_summary(path: Path) -> str | None:
    report = validate_package(path)
    if report.ok:
        return None
    return "\n".join(f"- {issue}" for issue in report.errors[:10])


def _local_name(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _serialize_hwpml_compat_root(root: etree._Element) -> bytes:
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


def _normalize_hwpml_compat_root(part_name: str, payload: bytes) -> bytes:
    if not (is_section_part_name(part_name) or is_header_part_name(part_name)):
        return payload
    try:
        root = etree.fromstring(payload)
    except etree.XMLSyntaxError:
        return payload
    if _local_name(root) not in {"sec", "head"}:
        return payload
    return _serialize_hwpml_compat_root(root)


def _repair_section_layout_cache(part_name: str, payload: bytes) -> bytes:
    if not is_section_part_name(part_name):
        return _normalize_hwpml_compat_root(part_name, payload)
    try:
        root = etree.fromstring(payload)
    except etree.XMLSyntaxError:
        return payload

    changed = False
    for paragraph in root.iter():
        if _local_name(paragraph) != "p":
            continue
        for child in list(paragraph):
            if _local_name(child).lower() != "linesegarray":
                continue
            paragraph.remove(child)
            changed = True

    if changed or _local_name(root) in {"sec", "head"}:
        return _serialize_hwpml_compat_root(root)
    return payload


def _replace_with_validated_archive(
    tmp_path: Path,
    destination: Path,
) -> tuple[bool, dict[str, Any]]:
    try:
        with ZipFile(tmp_path, "r") as archive:
            crc_ok = archive.testzip() is None
        if not crc_ok:
            raise ValueError("repaired archive failed ZIP CRC/integrity self-check")

        validation_summary = _validation_error_summary(tmp_path)
        if validation_summary is not None:
            raise ValueError(f"repaired archive failed validation:\n{validation_summary}")

        open_safety = validate_editor_open_safety(tmp_path)
        if not open_safety.ok:
            raise ValueError(
                "repaired archive failed editor-open safety validation:\n"
                + open_safety.summary
            )
        open_safety_dict = open_safety.to_dict()

        os.replace(tmp_path, destination)
        return crc_ok, open_safety_dict
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def repair_repack(
    source: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    max_entry_size: int = 64 * 1024 * 1024,
    max_total_size: int = 512 * 1024 * 1024,
) -> RepairResult:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"input file not found: {source_path}")

    destination = Path(output_path)
    _prepare_output_path(destination, overwrite=overwrite)

    entries = _read_entries(
        source_path,
        max_entry_size=max_entry_size,
        max_total_size=max_total_size,
    )
    original_names = tuple(entry.info.filename for entry in entries)
    ordered = _ordered_entries(entries)
    reordered = original_names != tuple(entry.info.filename for entry in ordered)
    mimetype_entry = ordered[0]
    if mimetype_entry.info.compress_type != ZIP_STORED:
        reordered = True

    fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".hwpx.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED) as archive:
            for entry in ordered:
                compress_type = ZIP_STORED if entry.info.filename == MIMETYPE_PATH else entry.info.compress_type
                if compress_type != ZIP_STORED:
                    compress_type = ZIP_DEFLATED
                payload = _repair_section_layout_cache(
                    entry.info.filename,
                    entry.payload,
                )
                archive.writestr(
                    _clone_info(entry.info, compress_type=compress_type),
                    payload,
                )

        crc_ok, open_safety = _replace_with_validated_archive(tmp_path, destination)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return RepairResult(
        output_path=destination,
        entries=original_names,
        reordered=reordered,
        crc_ok=crc_ok,
        open_safety=open_safety,
    )


def repair_from_recovered(
    source: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    max_entry_size: int = 64 * 1024 * 1024,
    max_total_size: int = 512 * 1024 * 1024,
    max_source_size: int = 512 * 1024 * 1024,
) -> RepairResult:
    destination = Path(output_path)
    _prepare_output_path(destination, overwrite=overwrite)

    recovered = recover_entries(
        source,
        max_entry_size=max_entry_size,
        max_total_size=max_total_size,
        max_source_size=max_source_size,
    )
    if MIMETYPE_PATH not in recovered:
        raise FileNotFoundError(f"missing required {MIMETYPE_PATH!r} entry")

    original_names = tuple(recovered)
    ordered_names = (MIMETYPE_PATH,) + tuple(name for name in recovered if name != MIMETYPE_PATH)
    reordered = original_names != ordered_names

    fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".hwpx.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(MIMETYPE_PATH, recovered[MIMETYPE_PATH], compress_type=ZIP_STORED)
            for name in ordered_names:
                if name == MIMETYPE_PATH:
                    continue
                payload = _repair_section_layout_cache(name, recovered[name])
                archive.writestr(name, payload, compress_type=ZIP_DEFLATED)

        crc_ok, open_safety = _replace_with_validated_archive(tmp_path, destination)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return RepairResult(
        output_path=destination,
        entries=original_names,
        reordered=reordered,
        crc_ok=crc_ok,
        open_safety=open_safety,
        recovered=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair or recover an HWPX archive")
    parser.add_argument("input", help="Input .hwpx path")
    parser.add_argument("output", help="Output repaired .hwpx path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing output file",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Recover entries by scanning ZIP Local File Headers before repacking",
    )
    args = parser.parse_args(argv)

    try:
        if args.recover:
            result = repair_from_recovered(args.input, args.output, overwrite=args.force)
        else:
            result = repair_repack(args.input, args.output, overwrite=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Repaired {args.input} -> {result.output_path}")
    print(
        " ".join(
            [
                f"reordered={str(result.reordered).lower()}",
                f"crc_ok={str(result.crc_ok).lower()}",
                f"open_safety_ok={str(bool(result.open_safety.get('ok'))).lower()}",
                f"recovered={str(result.recovered).lower()}",
            ]
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
