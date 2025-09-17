from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence

from lxml import etree

from ..document import HwpxDocument
from ..oxml import load_schema, parse_header_xml, parse_section_xml

_DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parent / "_schemas"

__all__ = [
    "DocumentSchemas",
    "ValidationIssue",
    "ValidationReport",
    "load_default_schemas",
    "validate_document",
    "main",
]


@dataclass(frozen=True)
class DocumentSchemas:
    """Container for XML schema objects used to validate HWPX documents."""

    header: etree.XMLSchema
    section: etree.XMLSchema


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a schema validation failure for a specific package part."""

    part_name: str
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        location = ""
        if self.line is not None:
            location = f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        return f"{self.part_name}{location}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated result of validating an HWPX document against schemas."""

    validated_parts: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        """Whether every validated part satisfied the schema constraints."""

        return not self.issues

    def __bool__(self) -> bool:  # pragma: no cover - convenience alias
        return self.ok


def load_default_schemas(schema_dir: Path | None = None) -> DocumentSchemas:
    """Load the reference header and body schemas bundled with the project."""

    directory = Path(schema_dir) if schema_dir is not None else _DEFAULT_SCHEMA_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Schema directory does not exist: {directory}")

    header_schema = load_schema(directory / "header.xsd")
    section_schema = load_schema(directory / "section.xsd")
    return DocumentSchemas(header=header_schema, section=section_schema)


def _iter_parts(document: HwpxDocument) -> Iterable[tuple[str, bytes, bool]]:
    """Yield ``(part_name, xml_bytes, is_header)`` tuples for schema checks."""

    for header in document.oxml.headers:
        yield (
            header.part_name,
            ET.tostring(header.element, encoding="utf-8"),
            True,
        )
    for section in document.oxml.sections:
        yield (
            section.part_name,
            ET.tostring(section.element, encoding="utf-8"),
            False,
        )


def _issues_from_error(part_name: str, exc: etree.DocumentInvalid) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    error_log = getattr(exc, "error_log", None)
    if error_log is not None:
        recorded = False
        for entry in error_log:
            recorded = True
            issues.append(
                ValidationIssue(
                    part_name=part_name,
                    message=entry.message,
                    line=getattr(entry, "line", None),
                    column=getattr(entry, "column", None),
                )
            )
        if recorded:
            return issues
    issues.append(ValidationIssue(part_name=part_name, message=str(exc)))
    return issues


def validate_document(
    source: str | Path | bytes | BinaryIO,
    *,
    schema_dir: Path | None = None,
    header_schema: etree.XMLSchema | None = None,
    section_schema: etree.XMLSchema | None = None,
) -> ValidationReport:
    """Validate the header and section XML parts of an HWPX archive."""

    document = HwpxDocument.open(source)
    if header_schema is None or section_schema is None:
        schemas = load_default_schemas(schema_dir)
        if header_schema is None:
            header_schema = schemas.header
        if section_schema is None:
            section_schema = schemas.section

    if header_schema is None or section_schema is None:  # pragma: no cover - defensive
        raise ValueError("Header and section schemas must be provided for validation")

    validated_parts: list[str] = []
    issues: list[ValidationIssue] = []

    for part_name, payload, is_header in _iter_parts(document):
        validated_parts.append(part_name)
        schema = header_schema if is_header else section_schema
        validator = parse_header_xml if is_header else parse_section_xml
        try:
            validator(payload, schema=schema)
        except etree.DocumentInvalid as exc:
            issues.extend(_issues_from_error(part_name, exc))
        except Exception as exc:  # pragma: no cover - defensive branch
            issues.append(ValidationIssue(part_name=part_name, message=str(exc)))

    return ValidationReport(validated_parts=tuple(validated_parts), issues=tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hwpx.tools.validator``."""

    parser = argparse.ArgumentParser(description="Validate HWPX documents against the official schemas")
    parser.add_argument("source", help="Path to the HWPX file to validate")
    parser.add_argument(
        "--schema-root",
        type=Path,
        default=None,
        help="Directory containing the OWPML schema XML files. Defaults to the bundled DevDoc copy.",
    )
    args = parser.parse_args(argv)

    report = validate_document(args.source, schema_dir=args.schema_root)

    for part_name in report.validated_parts:
        print(f"validated {part_name}")

    if report.issues:
        for issue in report.issues:
            print(f"ERROR: {issue}")
        return 1

    print("All schema validations passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
