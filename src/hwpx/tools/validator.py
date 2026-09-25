# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence

from lxml import etree

from ..document import HwpxDocument
from ..oxml import load_schema, parse_header_xml, parse_section_xml

_DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parent / "_schemas"

#: The full OWPML schema (KS X 6101, ``DevDoc/OWPML SCHEMA``) bundled as ``owpml-*.xsd``.
_OWPML_SCHEMAS = {"header": "owpml-header.xsd", "section": "owpml-body.xsd"}
#: Hancom writes the 2011 namespaces; the schema declares the 2024 ones.
_OWPML_NAMESPACES = tuple(
    (f"http://www.hancom.co.kr/hwpml/2011/{name}".encode(), f"http://www.owpml.org/owpml/2024/{name}".encode())
    for name in ("paragraph", "section", "core", "head", "master-page", "history")
)
#: ``hp:secPr``'s children in the schema's order. Hancom writes ``grid`` before ``startNum``; a
#: validator stops checking a parent at its first misplaced child, so the copy that is checked
#: is put in this order first and the page, note and border settings after it get checked too.
_SEC_PR_ORDER = {
    name: index
    for index, name in enumerate(
        ("startNum", "grid", "visibility", "lineNumberShape", "pagePr", "footNotePr", "endNotePr",
         "pageBorderFill", "masterPage", "presentation")
    )
}
_OWPML_PARAGRAPH = "{http://www.owpml.org/owpml/2024/paragraph}"
_QUOTED = re.compile(r"'[^']*'")
_SCHEMA_ERROR = re.compile(r"Element '([^']+)'(?:, attribute '([^']+)')?: (.*)")

#: Schema violations that documents Hancom opens carry -- its own and python-hwpx output it
#: accepts: Hancom's practice departing from the 2024 schema, not faults, so not reported.
#: Each is "<part> | <prefix>:<element>[@attribute]: <kind>", values left out.
_KNOWN_OWPML_DEVIATIONS = frozenset(
    {
        "header | core:fillBrush: element not expected",
        "header | core:img: element not expected",
        "header | head:autoSpacing: element not expected",
        "header | head:binDataList: element not expected",
        "header | head:bold: element not expected",
        "header | head:bottomBorder@color: value not allowed",
        "header | head:bottomBorder@type: value not allowed",
        "header | head:charPr@shadeColor: value not allowed",
        "header | head:diagonal@color: value not allowed",
        "header | head:docOption: element not expected",
        "header | head:italic: element not expected",
        "header | head:leftBorder@color: value not allowed",
        "header | head:leftBorder@type: value not allowed",
        "header | head:paraHead@level: value not allowed",
        "header | head:paraHead@numFormat: value not allowed",
        "header | head:paraPr@textDir: attribute not allowed",
        "header | head:rightBorder@color: value not allowed",
        "header | head:rightBorder@type: value not allowed",
        "header | head:shadow@color: value not allowed",
        "header | head:strikeout: required attribute missing: 'shape'",
        "header | head:strikeout@color: value not allowed",
        "header | head:strikeout@shape: value not allowed",
        "header | head:tabItem: element not expected",
        "header | head:topBorder@color: value not allowed",
        "header | head:topBorder@type: value not allowed",
        "header | head:trackChange@date: value not allowed",
        "header | head:typeInfo: required attribute missing: 'familyType'",
        "header | head:typeInfo@armStyle: value not allowed",
        "header | head:typeInfo@letterform: value not allowed",
        "header | head:typeInfo@midline: value not allowed",
        "header | head:underline: element not expected",
        "header | head:underline@color: value not allowed",
        "header | head:underline@shape: value not allowed",
        "header | paragraph:switch: element not expected",
        "section | core:center: element not expected",
        "section | core:extent: element not expected",
        "section | core:fillBrush: element not expected",
        "section | core:img: element not expected",
        "section | core:pt0: element not expected",
        "section | core:pt: element not expected",
        "section | core:startPt: element not expected",
        "section | core:transMatrix: element not expected",
        "section | paragraph:autoNum: missing child",
        "section | paragraph:btn@command: attribute not allowed",
        "section | paragraph:chart: attribute not allowed",
        "section | paragraph:chart@chartIDRef: attribute not allowed",
        "section | paragraph:chart@dropcapstyle: attribute not allowed",
        "section | paragraph:chart@id: attribute not allowed",
        "section | paragraph:chart@lock: attribute not allowed",
        "section | paragraph:chart@numberingType: attribute not allowed",
        "section | paragraph:chart@textFlow: attribute not allowed",
        "section | paragraph:chart@textWrap: attribute not allowed",
        "section | paragraph:chart@zOrder: attribute not allowed",
        "section | paragraph:checkBtn@command: attribute not allowed",
        "section | paragraph:comboBox@command: attribute not allowed",
        "section | paragraph:ctrl@charStyleIDRef: attribute not allowed",
        "section | paragraph:drawText: element not expected",
        "section | paragraph:dutmal@option: The value '…' does not match the fixed value constraint '…'.",
        "section | paragraph:dutmal@szRatio: value not allowed",
        "section | paragraph:edit@command: attribute not allowed",
        "section | paragraph:endNote@instid: attribute not allowed",
        "section | paragraph:endNote@number: attribute not allowed",
        "section | paragraph:endNote@suffixChar: attribute not allowed",
        "section | paragraph:fieldBegin@fieldid: value not allowed",
        "section | paragraph:fieldBegin@id: value not allowed",
        "section | paragraph:fieldBegin@metaTag: attribute not allowed",
        "section | paragraph:fieldBegin@type: value not allowed",
        "section | paragraph:fieldEnd@beginIDRef: value not allowed",
        "section | paragraph:fieldEnd@fieldid: value not allowed",
        "section | paragraph:footNote: element not expected",
        "section | paragraph:footNote@flag: attribute not allowed",
        "section | paragraph:footNote@instid: attribute not allowed",
        "section | paragraph:footNote@number: attribute not allowed",
        "section | paragraph:footNote@suffixChar: attribute not allowed",
        "section | paragraph:footNote@userChar: attribute not allowed",
        "section | paragraph:footer: element not expected",
        "section | paragraph:header: element not expected",
        "section | paragraph:headerApply: element not expected",
        "section | paragraph:inMargin: element not expected",
        "section | paragraph:indexmark: missing child",
        "section | paragraph:lineShape@color: value not allowed",
        "section | paragraph:linesegarray: element not expected",
        "section | paragraph:listItem: element not expected",
        "section | paragraph:markpenBegin: element not expected",
        "section | paragraph:memogroup: element not expected",
        "section | paragraph:newNum: missing child",
        "section | paragraph:noteLine@color: value not allowed",
        "section | paragraph:p: missing child",
        "section | paragraph:p: required attribute missing: 'id'",
        "section | paragraph:p@id: value not allowed",
        "section | paragraph:parameters: required attribute missing: 'cnt'",
        "section | paragraph:parameters@count: attribute not allowed",
        "section | paragraph:parameterset: element not expected",
        "section | paragraph:radioBtn@command: attribute not allowed",
        "section | paragraph:secPr@tabStop: attribute not allowed",
        "section | paragraph:shadow@type: value not allowed",
        "section | paragraph:subList@metatag: attribute not allowed",
        "section | paragraph:switch: element not expected",
        "section | paragraph:sz: element not expected",
        "section | paragraph:tab: required attribute missing: 'type'",
        "section | paragraph:tab@leader: value not allowed",
        "section | paragraph:tab@type: value not allowed",
        "section | paragraph:tbl: element not expected",
    }
)


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
    severity: str = "error"

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
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        """OK when there are no hard errors. Schema lint warnings do not fail."""

        return not self.errors

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

    # Serialize with lxml (not stdlib ET): the elements are lxml nodes, and
    # comment / processing-instruction children carry a callable ``.tag`` that
    # stdlib ``ET.tostring`` cannot serialize (raises TypeError). lxml's own
    # serializer handles them correctly.
    for header in document.oxml.headers:
        yield (
            header.part_name,
            etree.tostring(header.element, encoding="utf-8"),
            True,
        )
    for section in document.oxml.sections:
        yield (
            section.part_name,
            etree.tostring(section.element, encoding="utf-8"),
            False,
        )


def _deviation_signature(message: str) -> str:
    """A schema error with its values removed: element, attribute and the kind of error."""

    match = _SCHEMA_ERROR.match(message)
    if not match:
        return _QUOTED.sub("'…'", message)[:160]
    element, attribute, rest = match.groups()
    element = re.sub(r"\{[^}]*/(\w[\w-]*)\}", r"\1:", element)
    kind = rest
    if "is not a valid value" in rest or "is not an element of the set" in rest or "not accepted by the pattern" in rest:
        kind = "value not allowed"
    elif "This element is not expected" in rest:
        kind = "element not expected"
    elif "Missing child element" in rest:
        kind = "missing child"
    elif "The attribute" in rest and "is required" in rest:
        kind = "required attribute missing: " + (_QUOTED.findall(rest) or ["?"])[0]
    elif "is not allowed" in rest:
        kind = "attribute not allowed"
    elif "No matching global declaration" in rest:
        kind = "no global declaration"
    else:
        kind = _QUOTED.sub("'…'", rest)[:80]
    return f"{element}{'@' + attribute if attribute else ''}: {kind}"


@lru_cache(maxsize=None)
def _owpml_schema(kind: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(_DEFAULT_SCHEMA_DIR / _OWPML_SCHEMAS[kind])))


def _owpml_violations(payload: bytes, kind: str) -> list[tuple[str, int | None]]:
    """``(signature, line)`` of every full-schema violation of one part, known deviations included."""

    for old, new in _OWPML_NAMESPACES:
        payload = payload.replace(old, new)
    try:
        root = etree.fromstring(payload, etree.XMLParser(huge_tree=True))
    except etree.XMLSyntaxError:
        return []  # the part cannot be read at all -- reported by the parse check
    for sec_pr in root.iter(f"{_OWPML_PARAGRAPH}secPr"):
        children = list(sec_pr)
        ordered = sorted(children, key=lambda child: _SEC_PR_ORDER.get(etree.QName(child).localname, len(_SEC_PR_ORDER)))
        if ordered != children:
            for child in children:
                sec_pr.remove(child)
            sec_pr.extend(ordered)
    schema = _owpml_schema(kind)
    schema.validate(root)
    return [(_deviation_signature(entry.message), getattr(entry, "line", None)) for entry in schema.error_log]


def _owpml_issues(part_name: str, payload: bytes, kind: str) -> list[ValidationIssue]:
    """Warnings for the full-schema violations of one part that Hancom's own documents do not have."""

    found: Counter[str] = Counter()
    first_line: dict[str, int | None] = {}
    for signature, line in _owpml_violations(payload, kind):
        if f"{kind} | {signature}" in _KNOWN_OWPML_DEVIATIONS:
            continue
        found[signature] += 1
        first_line.setdefault(signature, line)
    return [
        ValidationIssue(
            part_name=part_name,
            message=f"OWPML schema: {signature}" + (f" ({count} times)" if count > 1 else ""),
            line=first_line[signature],
            severity="warning",
        )
        for signature, count in found.items()
    ]


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
                    severity="warning",
                )
            )
        if recorded:
            return issues
    issues.append(ValidationIssue(part_name=part_name, message=str(exc), severity="warning"))
    return issues


def validate_document(
    source: str | Path | bytes | BinaryIO,
    *,
    schema_dir: Path | None = None,
    header_schema: etree.XMLSchema | None = None,
    section_schema: etree.XMLSchema | None = None,
    full_schema: bool = True,
) -> ValidationReport:
    """Validate the header and section XML parts of an HWPX archive.

    With *full_schema* (the default) the parts are also checked against the full OWPML
    schema. Violations that documents Hancom opens also carry (its 2011 practice
    departing from the 2024 schema) are left out; the rest are warnings, so ``ok``
    still reflects hard errors only.
    """

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
        if full_schema:
            issues.extend(_owpml_issues(part_name, payload, "header" if is_header else "section"))
        try:
            validator(payload, schema=schema)
        except etree.DocumentInvalid as exc:
            # Schema-rule violations are lint warnings (the published OWPML schema
            # diverges from Hancom's real behavior — see docs/owpml-deviations.md).
            issues.extend(_issues_from_error(part_name, exc))
        except Exception as exc:
            # A non-DocumentInvalid failure (e.g. not-well-formed XML, load error)
            # is a genuine structural problem, not schema lint: keep it a hard error.
            issues.append(ValidationIssue(part_name=part_name, message=str(exc), severity="error"))

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
            print(f"{issue.severity.upper()}: {issue}")

    if not report.ok:
        return 1

    if report.warnings:
        print("Schema lint warnings found.")
    else:
        print("All schema validations passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
