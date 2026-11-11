# SPDX-License-Identifier: Apache-2.0
"""Check a document's formatting against a rule file.

An organisation that prescribes a house format ("body text 10pt in one of
these fonts, line spacing 160 %, no hyperlinks") writes the rule once and
checks every document against it. Only values stored in the file are read --
character shapes, paragraph shapes, tables, characters -- so nothing here is
an estimate.

The rule file uses the key names of Hancom's open-source checker
(`hancom-io/dvc <https://github.com/hancom-io/dvc>`_, Apache-2.0) and its
units, which are the units of the file: ``fontsize`` in 1/100 pt, lengths in
HWPUNIT (1/7200 inch), ``linespacingvalue`` in the unit of the line-spacing
type. A numeric rule is either one number or ``{"min": a, "max": b}``. The
supported subset is listed in :data:`SUPPORTED_RULES`; keys outside it are
reported in :attr:`FormatReport.unsupported_rules` and never silently skipped.

Violations are located by section, paragraph and text. No page or line
number is given: those are not stored in the file and would have to be
estimated.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any

from lxml import etree

from ..errors import HwpxValueError
from ..opc.package import HwpxPackage

__all__ = [
    "SUPPORTED_RULES",
    "FormatReport",
    "FormatViolation",
    "check_format",
    "load_rules",
    "main",
]

_LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
#: ``langtype`` spellings (dvc's Korean names, its index and the file's names).
_LANG_NAMES: dict[object, tuple[str, ...]] = {
    "대표": _LANGS, 0: _LANGS, "all": _LANGS,
    "한글": ("hangul",), 1: ("hangul",), "hangul": ("hangul",),
    "영문": ("latin",), 2: ("latin",), "latin": ("latin",),
    "한자": ("hanja",), 3: ("hanja",), "hanja": ("hanja",),
    "일어": ("japanese",), 4: ("japanese",), "japanese": ("japanese",),
    "외국어": ("other",), 5: ("other",), "other": ("other",),
    "기호": ("symbol",), 6: ("symbol",), "symbol": ("symbol",),
    "사용자": ("user",), 7: ("user",), "user": ("user",),
}
_ALIGN_NAMES: dict[object, str] = {
    "양쪽 정렬": "JUSTIFY", 0: "JUSTIFY", "JUSTIFY": "JUSTIFY", "BOTH": "JUSTIFY",
    "왼쪽 정렬": "LEFT", 1: "LEFT", "LEFT": "LEFT",
    "오른쪽 정렬": "RIGHT", 2: "RIGHT", "RIGHT": "RIGHT",
    "가운데 정렬": "CENTER", 3: "CENTER", "CENTER": "CENTER",
    "배분 정렬": "DISTRIBUTE", 4: "DISTRIBUTE", "DISTRIBUTE": "DISTRIBUTE",
    "나눔 정렬": "DISTRIBUTE_SPACE", 5: "DISTRIBUTE_SPACE", "DISTRIBUTE_SPACE": "DISTRIBUTE_SPACE",
}
_LINE_SPACING_NAMES: dict[object, str] = {
    "글자에 따라": "PERCENT", 0: "PERCENT", "PERCENT": "PERCENT",
    "고정값": "FIXED", 1: "FIXED", "FIXED": "FIXED",
    "여백만 지정": "BETWEEN_LINES", 2: "BETWEEN_LINES", "BETWEEN_LINES": "BETWEEN_LINES",
    "최소": "AT_LEAST", 3: "AT_LEAST", "AT_LEAST": "AT_LEAST",
}

#: Rule keys this checker evaluates, by category.
SUPPORTED_RULES: dict[str, frozenset[str]] = {
    "charshape": frozenset(
        {"langtype", "fontsize", "font", "ratio", "spacing", "r-size", "bold", "italic", "underline", "strikeout",
         "supscript", "subscript"}
    ),
    "parashape": frozenset(
        {"horizontal", "margin-left", "margin-right", "indent", "outdent", "linespacing", "linespacingvalue",
         "spacing-paraup", "spacing-parabottom"}
    ),
    "table": frozenset({"treatAsChar", "table-in-table"}),
    "specialcharacter": frozenset({"minimum", "maximum"}),
    "hyperlink": frozenset({"permission"}),
    "macro": frozenset({"permission"}),
}


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: Any, name: str) -> list[Any]:
    return [child for child in element if _local(child) == name]


def _descendants(element: Any, name: str) -> Iterable[Any]:
    return (node for node in element.iter() if _local(node) == name)


def _first(element: Any, name: str) -> Any:
    """The first ``name`` under *element*, looking through ``hp:switch`` the way Hangul reads it.

    A paragraph shape stores its margins twice, in ``hp:case`` and
    ``hp:default``; the first in document order is the ``hp:case`` branch,
    the one a current Hangul uses.
    """

    return next(iter(_descendants(element, name)), None)


def _attribute(element: Any, child: str, name: str, default: str = "NONE") -> str:
    node = _first(element, child)
    return (node.get(name) if node is not None else None) or default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class FormatViolation:
    """One place where the document departs from a rule."""

    #: ``category.key`` of the rule, e.g. ``charshape.fontsize``.
    rule: str
    #: What the rule allows, as written in the rule file.
    expected: object
    #: What the document has there.
    actual: object
    #: Zero-based section index; ``None`` for a document-wide rule (macro).
    section: int | None = None
    #: Zero-based index of the body paragraph that holds the place (the outer paragraph for text in a table).
    paragraph: int | None = None
    #: Whether the place is inside a table cell.
    in_table: bool = False
    #: The text at the place, shortened.
    text: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule, "expected": self.expected, "actual": self.actual, "section": self.section,
            "paragraph": self.paragraph, "inTable": self.in_table, "text": self.text, "message": self.message,
        }


@dataclass(frozen=True)
class FormatReport:
    """The result of :func:`check_format`."""

    violations: tuple[FormatViolation, ...]
    #: ``category.key`` names from the rule file that were evaluated.
    checked_rules: tuple[str, ...]
    #: ``category.key`` (or bare category) names from the rule file this checker does not evaluate.
    unsupported_rules: tuple[str, ...]
    #: Whether the violation list was cut at ``max_violations``.
    truncated: bool = False

    @property
    def ok(self) -> bool:
        """True when no checked rule is violated. Unsupported rules do not count either way."""

        return not self.violations

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "violationCount": len(self.violations),
            "truncated": self.truncated,
            "checkedRules": list(self.checked_rules),
            "unsupportedRules": list(self.unsupported_rules),
            "violations": [violation.to_dict() for violation in self.violations],
        }


@dataclass(frozen=True)
class _Range:
    low: float
    high: float
    written: object

    def holds(self, value: float) -> bool:
        return self.low <= value <= self.high


def _range(rule: str, value: object) -> _Range:
    if isinstance(value, bool):
        raise HwpxValueError(f"{rule}: expected a number or {{'min': a, 'max': b}}, got {value!r}")
    if isinstance(value, (int, float)):
        return _Range(float(value), float(value), value)
    if isinstance(value, Mapping) and isinstance(value.get("min"), (int, float)) and isinstance(value.get("max"), (int, float)):
        if value["min"] > value["max"]:
            raise HwpxValueError(f"{rule}: min is greater than max")
        return _Range(float(value["min"]), float(value["max"]), dict(value))
    raise HwpxValueError(f"{rule}: expected a number or {{'min': a, 'max': b}}, got {value!r}")


def _flag(rule: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise HwpxValueError(f"{rule}: expected true or false, got {value!r}")
    return value


def _named(rule: str, value: object, names: Mapping[object, Any]) -> Any:
    key = value.strip() if isinstance(value, str) else value
    if isinstance(key, bool) or key not in names:
        raise HwpxValueError(f"{rule}: unknown value {value!r}")
    return names[key]


def load_rules(source: Mapping[str, Any] | str | PathLike[str]) -> dict[str, Any]:
    """Return the rules in *source*: a mapping, or the path of a JSON rule file."""

    if isinstance(source, Mapping):
        rules: Any = dict(source)
    else:
        try:
            rules = json.loads(Path(source).read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise HwpxValueError(f"rule file is not valid JSON: {exc}") from exc
    if not isinstance(rules, Mapping):
        raise HwpxValueError("rules must be an object of categories")
    for category, body in rules.items():
        if not isinstance(body, Mapping):
            raise HwpxValueError(f"{category}: expected an object of rules")
    return dict(rules)


@dataclass
class _Header:
    char: dict[str, Any] = field(default_factory=dict)
    para: dict[str, Any] = field(default_factory=dict)
    fonts: dict[str, dict[str, str]] = field(default_factory=dict)


def _read_header(package: HwpxPackage) -> _Header:
    header = _Header()
    for name in package.files():
        if not (name.startswith("Contents/header") and name.endswith(".xml")):
            continue
        root = package.get_xml(name)
        for node in _descendants(root, "charPr"):
            header.char.setdefault(node.get("id", ""), node)
        for node in _descendants(root, "paraPr"):
            header.para.setdefault(node.get("id", ""), node)
        for face in _descendants(root, "fontface"):
            fonts = header.fonts.setdefault((face.get("lang") or "").lower(), {})
            for font in _children(face, "font"):
                fonts.setdefault(font.get("id", ""), font.get("face", ""))
    return header


class _CharRules:
    def __init__(self, body: Mapping[str, Any]) -> None:
        self.langs = _named("charshape.langtype", body.get("langtype", "대표"), _LANG_NAMES)
        self.size = _range("charshape.fontsize", body["fontsize"]) if "fontsize" in body else None
        fonts = body.get("font")
        if fonts is not None:
            fonts = [fonts] if isinstance(fonts, str) else fonts
            if not isinstance(fonts, Sequence) or not all(isinstance(name, str) for name in fonts):
                raise HwpxValueError("charshape.font: expected a font name or a list of font names")
        self.fonts = None if fonts is None else tuple(fonts)
        self.per_lang = {
            key: _range(f"charshape.{key}", body[key]) for key in ("ratio", "spacing", "r-size") if key in body
        }
        self.flags = {
            key: _flag(f"charshape.{key}", body[key])
            for key in ("bold", "italic", "underline", "strikeout", "supscript", "subscript") if key in body
        }

    def failures(self, node: Any, header: _Header) -> list[tuple[str, object, object]]:
        found: list[tuple[str, object, object]] = []
        if self.size is not None and not self.size.holds(_int(node.get("height"))):
            found.append(("fontsize", self.size.written, _int(node.get("height"))))
        if self.fonts is not None:
            refs = _first(node, "fontRef")
            for lang in self.langs:
                face = header.fonts.get(lang, {}).get(refs.get(lang, "") if refs is not None else "", "")
                if face not in self.fonts:
                    found.append(("font", list(self.fonts), face))
                    break
        for key, allowed in self.per_lang.items():
            element = _first(node, {"ratio": "ratio", "spacing": "spacing", "r-size": "relSz"}[key])
            for lang in self.langs:
                value = _int(element.get(lang) if element is not None else None, 100 if key != "spacing" else 0)
                if not allowed.holds(value):
                    found.append((key, allowed.written, value))
                    break
        actual = {
            "bold": _first(node, "bold") is not None,
            "italic": _first(node, "italic") is not None,
            "underline": _attribute(node, "underline", "type") != "NONE",
            "strikeout": _attribute(node, "strikeout", "shape") != "NONE",
            "supscript": _first(node, "supscript") is not None,
            "subscript": _first(node, "subscript") is not None,
        }
        found.extend((key, wanted, actual[key]) for key, wanted in self.flags.items() if actual[key] != wanted)
        return found


class _ParaRules:
    def __init__(self, body: Mapping[str, Any]) -> None:
        self.align = _named("parashape.horizontal", body["horizontal"], _ALIGN_NAMES) if "horizontal" in body else None
        self.spacing_type = (
            _named("parashape.linespacing", body["linespacing"], _LINE_SPACING_NAMES) if "linespacing" in body else None
        )
        self.ranges = {
            key: _range(f"parashape.{key}", body[key])
            for key in ("margin-left", "margin-right", "indent", "outdent", "linespacingvalue", "spacing-paraup",
                        "spacing-parabottom")
            if key in body
        }
        self.written = {"horizontal": body.get("horizontal"), "linespacing": body.get("linespacing")}

    def failures(self, node: Any) -> list[tuple[str, object, object]]:
        found: list[tuple[str, object, object]] = []
        align = _first(node, "align")
        horizontal = (align.get("horizontal") if align is not None else None) or "JUSTIFY"
        if self.align is not None and horizontal != self.align:
            found.append(("horizontal", self.written["horizontal"], horizontal))
        spacing = _first(node, "lineSpacing")
        spacing_type = (spacing.get("type") if spacing is not None else None) or "PERCENT"
        if self.spacing_type is not None and spacing_type != self.spacing_type:
            found.append(("linespacing", self.written["linespacing"], spacing_type))
        margin = _first(node, "margin")

        def length(name: str) -> int:
            child = _first(margin, name) if margin is not None else None
            return _int(child.get("value") if child is not None else None)

        first_line = length("intent")
        values = {
            "margin-left": length("left"),
            "margin-right": length("right"),
            # The file stores one signed first-line value: positive indents, negative hangs.
            "indent": max(first_line, 0),
            "outdent": max(-first_line, 0),
            "linespacingvalue": _int(spacing.get("value") if spacing is not None else None, 160),
            "spacing-paraup": length("prev"),
            "spacing-parabottom": length("next"),
        }
        found.extend(
            (key, allowed.written, values[key]) for key, allowed in self.ranges.items() if not allowed.holds(values[key])
        )
        return found


def _run_text(run: Any) -> str:
    parts: list[str] = []
    for text in _children(run, "t"):
        parts.append(text.text or "")
        for child in text.iter():
            if child is not text:
                parts.append(child.tail or "")
    return "".join(parts)


def _shorten(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _paragraph_text(paragraph: Any) -> str:
    return "".join(_run_text(run) for run in _children(paragraph, "run"))


def _inside(element: Any, name: str, stop: Any) -> bool:
    parent = element.getparent()
    while parent is not None and parent is not stop:
        if _local(parent) == name:
            return True
        parent = parent.getparent()
    return False


def check_format(
    document: str | PathLike[str] | bytes,
    rules: Mapping[str, Any] | str | PathLike[str],
    *,
    max_violations: int = 500,
) -> FormatReport:
    """Check *document* (an ``.hwpx`` path or its bytes) against *rules*.

    Every place a rule is broken becomes a :class:`FormatViolation`, up to
    *max_violations*. A character-shape rule is checked on every run that
    holds text; a paragraph-shape rule on every paragraph, including those
    in table cells and text boxes.
    """

    loaded = load_rules(rules)
    checked: list[str] = []
    unsupported: list[str] = []
    for category, body in loaded.items():
        known = SUPPORTED_RULES.get(category)
        if known is None:
            unsupported.append(category)
            continue
        for key in body:
            (checked if key in known else unsupported).append(f"{category}.{key}")

    char_rules = _CharRules(loaded["charshape"]) if "charshape" in loaded else None
    para_rules = _ParaRules(loaded["parashape"]) if "parashape" in loaded else None
    table_rules = loaded.get("table", {})
    for key in ("treatAsChar", "table-in-table"):
        if key in table_rules:
            _flag(f"table.{key}", table_rules[key])
    special = loaded.get("specialcharacter", {})
    low = _int(special["minimum"]) if "minimum" in special else None
    high = _int(special["maximum"]) if "maximum" in special else None
    links_allowed = _flag("hyperlink.permission", loaded["hyperlink"]["permission"]) \
        if "permission" in loaded.get("hyperlink", {}) else True
    macros_allowed = _flag("macro.permission", loaded["macro"]["permission"]) \
        if "permission" in loaded.get("macro", {}) else True

    package = HwpxPackage.open(document)
    header = _read_header(package)
    char_failures: dict[str, list[tuple[str, object, object]]] = {}
    para_failures: dict[str, list[tuple[str, object, object]]] = {}
    violations: list[FormatViolation] = []

    def add(**fields: Any) -> None:
        violations.append(FormatViolation(**fields))

    section_names = sorted(
        (name for name in package.files() if name.startswith("Contents/section") and name.endswith(".xml")),
        key=lambda name: _int("".join(ch for ch in name if ch.isdigit())),
    )
    for section_index, name in enumerate(section_names):
        root = package.get_xml(name)
        for body_index, body_paragraph in enumerate(_children(root, "p")):
            for paragraph in _descendants(body_paragraph, "p"):
                in_table = paragraph is not body_paragraph and _inside(paragraph, "tbl", body_paragraph)
                where = {"section": section_index, "paragraph": body_index, "in_table": in_table}
                if para_rules is not None:
                    ref = paragraph.get("paraPrIDRef", "")
                    shape = header.para.get(ref)
                    if ref not in para_failures:
                        para_failures[ref] = para_rules.failures(shape) if shape is not None else []
                    for key, expected, actual in para_failures[ref]:
                        add(rule=f"parashape.{key}", expected=expected, actual=actual,
                            text=_shorten(_paragraph_text(paragraph)), **where)
                for run in _children(paragraph, "run"):
                    text = _run_text(run)
                    if char_rules is not None and text.strip():
                        ref = run.get("charPrIDRef", "")
                        shape = header.char.get(ref)
                        if ref not in char_failures:
                            char_failures[ref] = char_rules.failures(shape, header) if shape is not None else []
                        for key, expected, actual in char_failures[ref]:
                            add(rule=f"charshape.{key}", expected=expected, actual=actual, text=_shorten(text), **where)
                    if low is not None or high is not None:
                        for ch in text:
                            code = ord(ch)
                            if ch in "\t\n\r":
                                continue
                            if (low is not None and code < low) or (high is not None and code > high):
                                add(rule="specialcharacter.minimum" if low is not None and code < low
                                    else "specialcharacter.maximum",
                                    expected={"minimum": low, "maximum": high}, actual=f"U+{code:04X}",
                                    text=_shorten(text), **where)
                                break
                    if not links_allowed:
                        for begin in _descendants(run, "fieldBegin"):
                            if (begin.get("type") or "").upper() == "HYPERLINK" and begin.getparent().getparent() is run:
                                add(rule="hyperlink.permission", expected=False, actual=True,
                                    text=_shorten(_paragraph_text(paragraph)), **where)
            for table in _descendants(body_paragraph, "tbl"):
                nested = _inside(table, "tbl", body_paragraph)
                where = {"section": section_index, "paragraph": body_index, "in_table": nested}
                first_cell = next(iter(_descendants(table, "t")), None)
                text = _shorten((first_cell.text or "") if first_cell is not None else "")
                if "treatAsChar" in table_rules:
                    position = next(iter(_children(table, "pos")), None)
                    inline = position is not None and position.get("treatAsChar") == "1"
                    if inline != table_rules["treatAsChar"]:
                        add(rule="table.treatAsChar", expected=table_rules["treatAsChar"], actual=inline, text=text, **where)
                if table_rules.get("table-in-table") is False and nested:
                    add(rule="table.table-in-table", expected=False, actual=True, text=text, **where)
    if not macros_allowed:
        scripts = [name for name in package.files() if name.lower().startswith("scripts/")]
        if scripts:
            add(rule="macro.permission", expected=False, actual=True, message=f"script parts: {', '.join(sorted(scripts))}")

    truncated = len(violations) > max_violations
    return FormatReport(
        violations=tuple(violations[:max_violations]),
        checked_rules=tuple(checked),
        unsupported_rules=tuple(unsupported),
        truncated=truncated,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """``hwpx-check-format RULES DOCUMENT``: exit 0 when the document follows the rules, 1 when it does not."""

    parser = argparse.ArgumentParser(
        prog="hwpx-check-format",
        description="Check an HWPX document's formatting against a rule file (dvc-style JSON).",
    )
    parser.add_argument("rules", help="rule file (JSON)")
    parser.add_argument("document", help="HWPX document")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--max-violations", type=int, default=500)
    args = parser.parse_args(argv)
    try:
        report = check_format(args.document, args.rules, max_violations=args.max_violations)
    except (OSError, ValueError, etree.XMLSyntaxError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for violation in report.violations:
            place = "document" if violation.section is None else (
                f"section {violation.section} paragraph {violation.paragraph}" + (" (table)" if violation.in_table else "")
            )
            print(f"{violation.rule}: expected {violation.expected!r}, found {violation.actual!r} at {place}"
                  + (f" — {violation.text}" if violation.text else ""))
        for name in report.unsupported_rules:
            print(f"not checked (unsupported rule): {name}")
        print(f"{'OK' if report.ok else 'FAILED'}: {len(report.violations)} violation(s)"
              + (" (list truncated)" if report.truncated else ""))
    return 0 if report.ok else 1
