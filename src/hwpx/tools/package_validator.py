# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Literal, Sequence
from zipfile import ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from lxml import etree as LET  # type: ignore[reportMissingImports]

from ..oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from ..opc.relationships import (
    MAIN_ROOTFILE_MEDIA_TYPE,
    ManifestRelationships,
    RootFileRef,
    is_header_part_name,
    is_section_part_name,
    parse_container_rootfiles,
    parse_manifest_relationships,
    select_main_rootfile,
)
from ..opc.security import (
    HwpxSecurityError,
    guard_xml_bytes,
    guard_xml_depth,
    guard_zip_file,
    parse_xml_stdlib,
)

EXPECTED_MIMETYPE = "application/hwp+zip"
MIMETYPE_PATH = "mimetype"
CONTAINER_PATH = "META-INF/container.xml"
HEADER_PATH = "Contents/header.xml"
VERSION_PATH = "version.xml"
PREVIEW_TEXT_PATH = "Preview/PrvText.txt"
RECOMMENDED_HANCOM_TARGET = "HWP201X"
# Both markers appear in real Hancom output across versions/filters: HWP2018 in
# some converted corpora, HWP201X in current Hancom-saved files and our captured
# Skeleton.hwpx (the from-scratch template every new document clones). Accept
# either so our own canonical output does not trip a false warning.
ACCEPTED_HANCOM_TARGETS = frozenset({"HWP2018", "HWP201X"})
# hh:head version: 1.4 was the original measured baseline; current Hancom emits
# 1.5 (our Skeleton.hwpx is 1.5). Accept both measured baselines.
ACCEPTED_HEAD_VERSIONS = frozenset({"1.4", "1.5"})

_XML_DECLARATION_RE = re.compile(rb"^<\?xml\s+([^?]*?)\?>", re.IGNORECASE)
_STANDALONE_YES_RE = re.compile(rb"\bstandalone\s*=\s*(['\"])yes\1", re.IGNORECASE)

IssueLevel = Literal["error", "warning"]

__all__ = [
    "EDITOR_OPEN_ADVISORY_ERROR_MARKERS",
    "PackageValidationIssue",
    "PackageValidationReport",
    "EditorOpenSafetyReport",
    "is_editor_open_blocking_issue",
    "validate_editor_open_safety",
    "validate_package",
    "main",
]

EDITOR_OPEN_ADVISORY_ERROR_MARKERS = (
    'missing XML declaration with standalone="yes"',
    "missing Hancom-compatible HWPML root namespace declarations",
    "manifest href missing from archive",
    "must be the first ZIP entry",
    "must use ZIP_STORED",
)


@dataclass(frozen=True)
class PackageValidationIssue:
    part_name: str
    message: str
    level: IssueLevel = "error"

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.part_name}: {self.message}"


def is_editor_open_blocking_issue(issue: PackageValidationIssue) -> bool:
    """Return whether a package issue should block editor-open-safe saves."""

    if not issue.is_error:
        return False
    return not any(
        marker in issue.message for marker in EDITOR_OPEN_ADVISORY_ERROR_MARKERS
    )


@dataclass(frozen=True)
class PackageValidationReport:
    checked_parts: tuple[str, ...]
    issues: tuple[PackageValidationIssue, ...]

    @property
    def errors(self) -> tuple[PackageValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.is_error)

    @property
    def warnings(self) -> tuple[PackageValidationIssue, ...]:
        return tuple(issue for issue in self.issues if not issue.is_error)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:  # pragma: no cover - convenience alias
        return self.ok


@dataclass(frozen=True)
class EditorOpenSafetyReport:
    """Combined checks used before handing a saved HWPX to an editor."""

    validate_package: PackageValidationReport
    validate_document: Any | None
    blocking_package_errors: tuple[PackageValidationIssue, ...]
    reopen_ok: bool
    reopen_error: str | None = None
    document_validation_error: str | None = None

    @property
    def ok(self) -> bool:
        document_ok = (
            self.document_validation_error is None
            and self.validate_document is not None
            and bool(getattr(self.validate_document, "ok", False))
        )
        return not self.blocking_package_errors and self.reopen_ok and document_ok

    @property
    def summary(self) -> str:
        if self.ok:
            return "editor-open safety verification passed"
        failures: list[str] = []
        if self.blocking_package_errors:
            failures.extend(str(issue) for issue in self.blocking_package_errors[:10])
        if not self.reopen_ok and self.reopen_error:
            failures.append(f"reopen failed: {self.reopen_error}")
        if self.document_validation_error:
            failures.append(
                f"document validation could not run: {self.document_validation_error}"
            )
        document_report = self.validate_document
        if document_report is not None and not bool(
            getattr(document_report, "ok", False)
        ):
            errors = list(getattr(document_report, "errors", ()))
            if errors:
                failures.extend(
                    f"document validation failed: {error}" for error in errors[:10]
                )
            else:
                failures.append("document validation failed")
        return (
            "; ".join(failures)
            if failures
            else "editor-open safety verification failed"
        )

    def to_dict(self) -> dict[str, Any]:
        document_report = self.validate_document
        return {
            "ok": self.ok,
            "summary": self.summary,
            "validatePackage": {
                "ok": self.validate_package.ok,
                "errors": [str(issue) for issue in self.validate_package.errors],
                "warnings": [str(issue) for issue in self.validate_package.warnings],
                "blockingErrors": [
                    str(issue) for issue in self.blocking_package_errors
                ],
            },
            "validateDocument": (
                {
                    "ok": False,
                    "errors": [self.document_validation_error],
                    "warnings": [],
                }
                if document_report is None
                else {
                    "ok": bool(getattr(document_report, "ok", False)),
                    "errors": [
                        str(issue) for issue in getattr(document_report, "errors", ())
                    ],
                    "warnings": [
                        str(issue) for issue in getattr(document_report, "warnings", ())
                    ],
                }
            ),
            "reopen": {"ok": self.reopen_ok, "error": self.reopen_error},
        }


def validate_editor_open_safety(source: str | Path | bytes) -> EditorOpenSafetyReport:
    """Return package/document/reopen evidence for editor-open-safe handoff."""

    package_report = validate_package(source)
    blocking_errors = tuple(
        issue for issue in package_report.errors if is_editor_open_blocking_issue(issue)
    )

    document_report: Any | None = None
    document_error: str | None = None
    try:
        from .validator import validate_document

        document_report = validate_document(source)
    except Exception as exc:  # noqa: BLE001 - reported as evidence, not hidden
        document_error = f"{type(exc).__name__}: {exc}"

    reopen_ok = False
    reopen_error: str | None = None
    try:
        from ..document import HwpxDocument

        reopened = HwpxDocument.open(source)
        try:
            reopen_ok = True
        finally:
            reopened.close()
    except Exception as exc:  # noqa: BLE001 - reported as evidence, not hidden
        reopen_error = f"{type(exc).__name__}: {exc}"

    return EditorOpenSafetyReport(
        validate_package=package_report,
        validate_document=document_report,
        blocking_package_errors=blocking_errors,
        reopen_ok=reopen_ok,
        reopen_error=reopen_error,
        document_validation_error=document_error,
    )


def _open_zip(source: str | Path | bytes | BinaryIO) -> ZipFile:
    if isinstance(source, (str, Path)):
        return ZipFile(source, "r")
    if isinstance(source, bytes):
        return ZipFile(io.BytesIO(source), "r")
    return ZipFile(source, "r")


def _parse_xml(payload: bytes) -> ET.Element:
    return parse_xml_stdlib(payload)


def _root_declared_namespaces(payload: bytes) -> dict[str, str]:
    try:
        guard_xml_bytes(payload)
        parser = LET.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
        root = LET.fromstring(payload, parser=parser)
        guard_xml_depth(root)
    except (LET.XMLSyntaxError, ValueError):
        return {}
    return {
        "" if prefix is None else prefix: uri
        for prefix, uri in root.nsmap.items()
        if uri
    }


def _has_standalone_yes_declaration(payload: bytes) -> bool:
    stripped = payload.lstrip()
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:]
    match = _XML_DECLARATION_RE.match(stripped)
    return bool(match and _STANDALONE_YES_RE.search(match.group(1)))


def _check_hwpml_compat_root(
    issues: list[PackageValidationIssue],
    part_name: str,
    payload: bytes,
    root: ET.Element,
) -> None:
    if not (
        is_section_part_name(part_name)
        or is_header_part_name(part_name)
        or part_name == HEADER_PATH
    ):
        return
    if not (root.tag.endswith("}sec") or root.tag.endswith("}head")):
        return
    if not _has_standalone_yes_declaration(payload):
        _error(
            issues,
            part_name,
            'missing XML declaration with standalone="yes"',
        )
    declared = _root_declared_namespaces(payload)
    missing = [
        prefix
        for prefix, uri in HWPML_COMPAT_ROOT_NAMESPACES.items()
        if declared.get(prefix) != uri
    ]
    if missing:
        _error(
            issues,
            part_name,
            "missing Hancom-compatible HWPML root namespace declarations: "
            + ", ".join(missing),
        )


def _local_name(element: ET.Element) -> str:
    tag = element.tag
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _children_by_local(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child) == name]


def _first_child_by_local(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child) == name:
            return child
    return None


def _simple_paragraph_text_length(paragraph: ET.Element) -> int | None:
    """Return visible text length for plain text-only paragraphs.

    Paragraphs containing fields, shapes, tables, or other embedded controls are
    skipped to avoid guessing how a specific editor counts their layout units.
    """

    total = 0
    for child in paragraph:
        child_name = _local_name(child).lower()
        if child_name == "linesegarray":
            continue
        if child_name != "run":
            return None
        for run_child in child:
            run_child_name = _local_name(run_child).lower()
            if run_child_name == "t":
                total += len("".join(run_child.itertext()))
            elif run_child_name in {"tab", "linebreak", "hyphen", "nbspace"}:
                total += 1
            else:
                return None
    return total


def _check_line_seg_text_positions(
    issues: list[PackageValidationIssue],
    part_name: str,
    root: ET.Element,
) -> None:
    if not is_section_part_name(part_name):
        return

    for paragraph_index, paragraph in enumerate(
        element for element in root.iter() if _local_name(element) == "p"
    ):
        text_length = _simple_paragraph_text_length(paragraph)
        if text_length is None:
            continue
        for child in paragraph:
            if _local_name(child).lower() != "linesegarray":
                continue
            for line_seg in child:
                if _local_name(line_seg).lower() != "lineseg":
                    continue
                textpos_raw = line_seg.get("textpos")
                if textpos_raw is None:
                    continue
                try:
                    textpos = int(textpos_raw)
                except ValueError:
                    _error(
                        issues,
                        part_name,
                        f"paragraph {paragraph_index} has non-integer lineseg textpos={textpos_raw!r}",
                    )
                    continue
                if textpos > text_length:
                    _error(
                        issues,
                        part_name,
                        "paragraph "
                        f"{paragraph_index} has stale lineseg textpos={textpos} "
                        f"beyond text length {text_length}",
                    )


def _check_table_editor_acceptance(
    issues: list[PackageValidationIssue],
    part_name: str,
    root: ET.Element,
) -> None:
    if not is_section_part_name(part_name):
        return

    required_table_children = ("sz", "pos", "outMargin", "inMargin")
    required_cell_children = ("subList", "cellAddr", "cellSpan", "cellSz", "cellMargin")
    for table_index, table in enumerate(
        element for element in root.iter() if _local_name(element) == "tbl"
    ):
        for child_name in required_table_children:
            if _first_child_by_local(table, child_name) is None:
                _error(
                    issues,
                    part_name,
                    f"table {table_index} missing Hancom-required hp:{child_name}",
                )
        for cell_index, cell in enumerate(
            element for element in table.iter() if _local_name(element) == "tc"
        ):
            for child_name in required_cell_children:
                if _first_child_by_local(cell, child_name) is None:
                    _error(
                        issues,
                        part_name,
                        "table "
                        f"{table_index} cell {cell_index} missing Hancom-required hp:{child_name}",
                    )


def _check_section_properties_location(
    issues: list[PackageValidationIssue],
    part_name: str,
    root: ET.Element,
) -> None:
    if not is_section_part_name(part_name):
        return

    section_properties = next(
        (element for element in root.iter() if _local_name(element) == "secPr"),
        None,
    )
    if section_properties is None:
        _warning(issues, part_name, "missing hp:secPr section properties")
        return

    first_paragraph = _first_child_by_local(root, "p")
    first_run = (
        _first_child_by_local(first_paragraph, "run")
        if first_paragraph is not None
        else None
    )
    if (
        first_run is None
        or _first_child_by_local(first_run, "secPr") is not section_properties
    ):
        _warning(
            issues,
            part_name,
            "hp:secPr must be carried by the first paragraph's first hp:run",
        )


def _check_header_editor_acceptance(
    issues: list[PackageValidationIssue],
    part_name: str,
    root: ET.Element,
) -> None:
    if part_name != HEADER_PATH or _local_name(root) != "head":
        return

    compatible = _first_child_by_local(root, "compatibleDocument")
    if compatible is None:
        _warning(issues, part_name, "missing hh:compatibleDocument declaration")
    else:
        target_program = compatible.get("targetProgram")
        if not target_program:
            _warning(issues, part_name, "hh:compatibleDocument missing targetProgram")
        elif target_program not in ACCEPTED_HANCOM_TARGETS:
            _warning(
                issues,
                part_name,
                "hh:compatibleDocument targetProgram is "
                f"{target_program!r}; expected one of "
                f"{sorted(ACCEPTED_HANCOM_TARGETS)} "
                f"({RECOMMENDED_HANCOM_TARGET!r} recommended) for Hancom compatibility",
            )

    version = root.get("version")
    if version not in ACCEPTED_HEAD_VERSIONS:
        _warning(
            issues,
            part_name,
            f"hh:head version is {version!r}; expected one of "
            f"{sorted(ACCEPTED_HEAD_VERSIONS)} (measured compatibility baselines)",
        )


def _char_properties(root: ET.Element) -> dict[str, ET.Element]:
    return {
        element.get("id", ""): element
        for element in root.iter()
        if _local_name(element) == "charPr" and element.get("id")
    }


def _check_bold_fontref_axis(
    issues: list[PackageValidationIssue],
    part_name: str,
    root: ET.Element,
) -> None:
    if part_name != HEADER_PATH or _local_name(root) != "head":
        return

    for char_pr_id, char_pr in _char_properties(root).items():
        if _first_child_by_local(char_pr, "bold") is None:
            continue
        font_ref = _first_child_by_local(char_pr, "fontRef")
        if font_ref is None:
            _warning(
                issues,
                part_name,
                f"bold charPr id={char_pr_id!r} has no hh:fontRef; "
                "macOS Hancom may not synthesize bold weight",
            )
            continue
        if not any(font_ref.get(attr) for attr in ("hangul", "latin", "hanja")):
            _warning(
                issues,
                part_name,
                f"bold charPr id={char_pr_id!r} has an empty hh:fontRef",
            )


def _error(issues: list[PackageValidationIssue], part_name: str, message: str) -> None:
    issues.append(PackageValidationIssue(part_name, message, "error"))


def _warning(
    issues: list[PackageValidationIssue], part_name: str, message: str
) -> None:
    issues.append(PackageValidationIssue(part_name, message, "warning"))


def _safe_read(zf: ZipFile, part_name: str) -> bytes | None:
    try:
        return zf.read(part_name)
    except (BadZipFile, KeyError, OSError):
        return None


def _fallback_named_parts(
    names: set[str], *, token: str, extra_token: str | None = None
) -> list[str]:
    matches: list[str] = []
    for name in sorted(names):
        part_name = PurePosixPath(name).name.lower()
        if token not in part_name:
            continue
        if extra_token is not None and extra_token not in part_name:
            continue
        matches.append(name)
    return matches


def _check_mimetype(
    zf: ZipFile,
    infos: list[ZipInfo],
    name_set: set[str],
    issues: list[PackageValidationIssue],
) -> None:
    if MIMETYPE_PATH not in name_set:
        _error(issues, MIMETYPE_PATH, "missing required file")
        return
    mimetype_bytes = _safe_read(zf, MIMETYPE_PATH)
    if mimetype_bytes is None:
        _error(
            issues,
            MIMETYPE_PATH,
            "unable to read entry for integrity validation",
        )
        return
    try:
        mimetype = mimetype_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        mimetype = "<binary>"
    if mimetype != EXPECTED_MIMETYPE:
        _error(
            issues,
            MIMETYPE_PATH,
            f"expected {EXPECTED_MIMETYPE!r}, got {mimetype!r}",
        )
    if infos[0].filename != MIMETYPE_PATH:
        _error(issues, MIMETYPE_PATH, "must be the first ZIP entry")
    if zf.getinfo(MIMETYPE_PATH).compress_type != ZIP_STORED:
        _error(issues, MIMETYPE_PATH, "must use ZIP_STORED")


def _check_required_presence(
    name_set: set[str], issues: list[PackageValidationIssue]
) -> None:
    if CONTAINER_PATH not in name_set:
        _error(issues, CONTAINER_PATH, "missing required file")
    if VERSION_PATH not in name_set:
        _warning(
            issues,
            VERSION_PATH,
            "missing optional version.xml; minimum editor-open package set allows omission",
        )


def _check_preview_text(
    zf: ZipFile, name_set: set[str], issues: list[PackageValidationIssue]
) -> None:
    if PREVIEW_TEXT_PATH not in name_set:
        _warning(
            issues,
            PREVIEW_TEXT_PATH,
            "missing Preview/PrvText.txt; macOS Hancom compatibility may require it",
        )
        return
    preview_bytes = _safe_read(zf, PREVIEW_TEXT_PATH)
    if preview_bytes is None:
        _error(issues, PREVIEW_TEXT_PATH, "unable to read preview text entry")
    elif len(preview_bytes) > 1024 * 1024:
        _warning(
            issues,
            PREVIEW_TEXT_PATH,
            "Preview/PrvText.txt is unusually large; expected a compact text snapshot",
        )


def _parse_all_xml(
    zf: ZipFile, names: list[str], issues: list[PackageValidationIssue]
) -> dict[str, ET.Element]:
    xml_roots: dict[str, ET.Element] = {}
    for name in names:
        if not (name.endswith(".xml") or name.endswith(".hpf")):
            continue
        payload = _safe_read(zf, name)
        if payload is None:
            _error(issues, name, "unable to read entry for XML parsing")
            continue
        try:
            root = _parse_xml(payload)
            xml_roots[name] = root
            _check_hwpml_compat_root(issues, name, payload, root)
            _check_line_seg_text_positions(issues, name, root)
            _check_table_editor_acceptance(issues, name, root)
            _check_section_properties_location(issues, name, root)
            _check_header_editor_acceptance(issues, name, root)
            _check_bold_fontref_axis(issues, name, root)
        except ValueError as exc:
            _error(issues, name, str(exc))
    return xml_roots


def _check_rootfile_parts(
    rootfiles: tuple[RootFileRef, ...],
    name_set: set[str],
    issues: list[PackageValidationIssue],
) -> None:
    for rootfile in rootfiles:
        if rootfile.full_path not in name_set:
            _error(
                issues,
                CONTAINER_PATH,
                f"rootfile points to missing part {rootfile.full_path!r}",
            )


def _check_manifest_hrefs(
    relationships: ManifestRelationships,
    selected_rootfile: RootFileRef,
    name_set: set[str],
    issues: list[PackageValidationIssue],
) -> None:
    for item in relationships.items:
        if item.resolved_path not in name_set:
            _error(
                issues,
                selected_rootfile.full_path,
                f"manifest href missing from archive: {item.href!r} -> {item.resolved_path!r}",
            )

    for idref in relationships.dangling_idrefs:
        _warning(
            issues,
            selected_rootfile.full_path,
            f"spine itemref references missing manifest id {idref!r}",
        )


def _resolve_section_paths(
    relationships: ManifestRelationships,
    selected_rootfile: RootFileRef,
    name_set: set[str],
    issues: list[PackageValidationIssue],
) -> list[str]:
    section_paths = [
        path for path in relationships.spine_paths if is_section_part_name(path)
    ]
    resolved_section_paths: list[str]
    if section_paths:
        resolved_section_paths = list(dict.fromkeys(section_paths))
        for path in section_paths:
            if path not in name_set:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    f"spine section part missing from archive: {path!r}",
                )
    else:
        fallback_sections = [
            name for name in sorted(name_set) if is_section_part_name(name)
        ]
        if fallback_sections:
            resolved_section_paths = fallback_sections
            _warning(
                issues,
                selected_rootfile.full_path,
                "manifest spine does not resolve any section parts; engine will fall back "
                "to filename-based section discovery",
            )
        else:
            resolved_section_paths = []
            _error(
                issues,
                selected_rootfile.full_path,
                "no section parts found in manifest spine or archive fallback",
            )
    return resolved_section_paths


def _check_header_section_counts(
    relationships: ManifestRelationships,
    xml_roots: dict[str, ET.Element],
    resolved_section_paths: list[str],
    name_set: set[str],
    issues: list[PackageValidationIssue],
) -> None:
    resolved_header_paths = list(dict.fromkeys(relationships.header_paths))
    if not resolved_header_paths and HEADER_PATH in name_set:
        resolved_header_paths = [HEADER_PATH]
    for header_path in resolved_header_paths:
        header_root = xml_roots.get(header_path)
        if header_root is None or _local_name(header_root) != "head":
            continue
        declared_section_count = header_root.get("secCnt")
        if declared_section_count is None:
            _warning(
                issues,
                header_path,
                "hh:head secCnt is missing; resolved section count cannot be cross-checked",
            )
            continue
        try:
            parsed_section_count = int(declared_section_count)
        except ValueError:
            _error(
                issues,
                header_path,
                f"hh:head secCnt must be an integer, got {declared_section_count!r}",
            )
            continue
        if parsed_section_count != len(resolved_section_paths):
            _error(
                issues,
                header_path,
                "hh:head secCnt does not match resolved section count: "
                f"declared={parsed_section_count}, resolved={len(resolved_section_paths)}",
            )


def _check_header_fallback(
    relationships: ManifestRelationships,
    name_set: set[str],
    selected_rootfile: RootFileRef,
    issues: list[PackageValidationIssue],
) -> None:
    if not relationships.header_paths and HEADER_PATH in name_set:
        _warning(
            issues,
            selected_rootfile.full_path,
            "manifest spine does not resolve a header part; engine will fall back to "
            f"{HEADER_PATH!r}",
        )

    for path in relationships.header_paths:
        if path not in name_set:
            _error(
                issues,
                selected_rootfile.full_path,
                f"header part missing from archive: {path!r}",
            )


def _check_master_page_parts(
    relationships: ManifestRelationships,
    name_set: set[str],
    selected_rootfile: RootFileRef,
    issues: list[PackageValidationIssue],
) -> None:
    if not relationships.master_page_paths:
        fallback_master_pages = _fallback_named_parts(
            name_set, token="master", extra_token="page"
        )
        if fallback_master_pages:
            _warning(
                issues,
                selected_rootfile.full_path,
                "manifest does not reference masterPage parts; engine will fall back to "
                "filename-based discovery",
            )
    for path in relationships.master_page_paths:
        if path not in name_set:
            _error(
                issues,
                selected_rootfile.full_path,
                f"masterPage part missing from archive: {path!r}",
            )


def _check_history_parts(
    relationships: ManifestRelationships,
    name_set: set[str],
    selected_rootfile: RootFileRef,
    issues: list[PackageValidationIssue],
) -> None:
    if not relationships.history_paths:
        fallback_histories = _fallback_named_parts(name_set, token="history")
        if fallback_histories:
            _warning(
                issues,
                selected_rootfile.full_path,
                "manifest does not reference history parts; engine will fall back to "
                "filename-based discovery",
            )
    for path in relationships.history_paths:
        if path not in name_set:
            _error(
                issues,
                selected_rootfile.full_path,
                f"history part missing from archive: {path!r}",
            )


def _check_version_part(
    relationships: ManifestRelationships,
    name_set: set[str],
    selected_rootfile: RootFileRef,
    issues: list[PackageValidationIssue],
) -> None:
    if relationships.version_path is None and VERSION_PATH in name_set:
        _warning(
            issues,
            selected_rootfile.full_path,
            "manifest does not reference a version part; engine will fall back to "
            f"{VERSION_PATH!r}",
        )
    elif (
        relationships.version_path is not None
        and relationships.version_path not in name_set
    ):
        _error(
            issues,
            selected_rootfile.full_path,
            f"manifest version part missing from archive: {relationships.version_path!r}",
        )


def validate_package(source: str | Path | bytes | BinaryIO) -> PackageValidationReport:
    checked_parts: list[str] = []
    issues: list[PackageValidationIssue] = []

    try:
        archive = _open_zip(source)
    except BadZipFile:
        return PackageValidationReport(
            checked_parts=(),
            issues=(PackageValidationIssue("archive", "not a valid ZIP archive"),),
        )

    with archive as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]
        name_set = set(names)
        checked_parts.extend(names)
        try:
            guard_zip_file(zf)
        except HwpxSecurityError as exc:
            _error(issues, "archive", str(exc))
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        if not infos:
            _error(issues, "archive", "empty archive")
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        bad_entry = zf.testzip()
        if bad_entry is not None:
            _error(issues, bad_entry, "ZIP CRC/integrity check failed")

        _check_mimetype(zf, infos, name_set, issues)
        _check_required_presence(name_set, issues)
        _check_preview_text(zf, name_set, issues)

        xml_roots = _parse_all_xml(zf, names, issues)

        container_root = xml_roots.get(CONTAINER_PATH)
        if container_root is None:
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        rootfiles = parse_container_rootfiles(container_root)
        if not rootfiles:
            _error(issues, CONTAINER_PATH, "declares no rootfile entries")
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        _check_rootfile_parts(rootfiles, name_set, issues)

        selected_rootfile, used_rootfile_fallback = select_main_rootfile(rootfiles)
        if selected_rootfile is None:
            return PackageValidationReport(tuple(checked_parts), tuple(issues))
        if used_rootfile_fallback:
            _warning(
                issues,
                CONTAINER_PATH,
                "no rootfile is marked as "
                f"{MAIN_ROOTFILE_MEDIA_TYPE!r}; engine will use the first declaration "
                f"{selected_rootfile.full_path!r}",
            )

        manifest_root = xml_roots.get(selected_rootfile.full_path)
        if manifest_root is None:
            _error(
                issues,
                selected_rootfile.full_path,
                "selected main rootfile is missing or not well-formed XML",
            )
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        relationships = parse_manifest_relationships(
            manifest_root,
            selected_rootfile.full_path,
            known_parts=name_set,
        )

        _check_manifest_hrefs(relationships, selected_rootfile, name_set, issues)
        resolved_section_paths = _resolve_section_paths(
            relationships, selected_rootfile, name_set, issues
        )
        _check_header_section_counts(
            relationships, xml_roots, resolved_section_paths, name_set, issues
        )
        _check_header_fallback(relationships, name_set, selected_rootfile, issues)
        _check_master_page_parts(relationships, name_set, selected_rootfile, issues)
        _check_history_parts(relationships, name_set, selected_rootfile, issues)
        _check_version_part(relationships, name_set, selected_rootfile, issues)

    return PackageValidationReport(tuple(checked_parts), tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate HWPX package structure using engine-aligned ZIP/container/manifest checks"
    )
    parser.add_argument("source", help="Path to the HWPX file")
    args = parser.parse_args(argv)

    report = validate_package(args.source)
    for issue in report.issues:
        prefix = "ERROR" if issue.is_error else "WARN"
        print(f"{prefix}: {issue}")

    if report.errors:
        return 1

    if report.warnings:
        print("Package validation passed with warnings.")
    else:
        print("All package validations passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
