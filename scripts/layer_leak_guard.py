#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Find genre or policy logic hiding inside core-owned modules.

The ownership ledger (``docs/architecture/module-ownership.json``) classifies
whole files, so a core file can still carry application logic: a regex that
matches Korean official-document headings, an eval-plan caption pattern, or a
parser for the automation layer's document-plan schema. A path rule cannot
see any of these. This guard looks inside the functions.

It AST-scans every product module under ``src/hwpx`` (not ``data/`` and not
``_moved_modules.py``) for two signals:

- ``hangul-regex``: the pattern argument of ``re.compile``/``match``/
  ``search``/``fullmatch``/``sub``/``findall``/``finditer`` contains Hangul,
  either as a literal or as a module-level string constant passed by name.
- ``plan-schema-key``: a subscript or ``.get()`` with the string key
  ``"sections"`` or ``"blocks"``, the shape of the automation layer's
  document plan.

Existing hits are listed, with a reason, in
``tests/data/layer_leak_allowlist.json``, keyed by file, qualified function
name and signal, with an exact count. Hancom format vocabulary (field-type
tokens, numbering-format labels) is allowed there on purpose; the leftovers
of the layer audit are marked as known leaks scheduled to move in 7.0.

A hit that is not in the allowlist fails. So does an allowlist count that no
longer matches, so a fixed leak has to leave the list in the same change.

    python scripts/layer_leak_guard.py          # check against the allowlist
    python scripts/layer_leak_guard.py --list   # print every live hit
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "hwpx"
ALLOWLIST = ROOT / "tests" / "data" / "layer_leak_allowlist.json"

#: Paths under ``src/hwpx`` that are not product modules.
EXCLUDED = ("data/", "_moved_modules.py")

REGEX_FUNCTIONS = frozenset(
    {"compile", "match", "search", "fullmatch", "sub", "findall", "finditer"}
)
PLAN_SCHEMA_KEYS = frozenset({"sections", "blocks"})

GUIDANCE = (
    "Genre, institution or policy logic belongs to python-hwpx-automation or the "
    "plugin, not core: apply the feature-placement test in the layer-boundary "
    "guardrails (section 4, summarized in docs/architecture/product-boundary.md, "
    "'Function-level guards'). If the hit is Hancom format vocabulary that any "
    "HWPX user needs, add it to tests/data/layer_leak_allowlist.json with a reason "
    "in the same change."
)


def has_hangul(text: str) -> bool:
    """Hangul syllables, jamo, or compatibility jamo."""

    return any(
        0xAC00 <= ord(char) <= 0xD7A3
        or 0x1100 <= ord(char) <= 0x11FF
        or 0x3130 <= ord(char) <= 0x318F
        for char in text
    )


@dataclass(frozen=True)
class Hit:
    file: str
    qualname: str
    kind: str
    detail: str
    line: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.file, self.qualname, self.kind)


def _string_value(node: ast.expr) -> str | None:
    """The text of a string constant, an implicit concatenation or ``+`` of
    constants, or an f-string's literal parts."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _string_value(node.left), _string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, relative: str, tree: ast.Module) -> None:
        self.relative = relative
        self.stack: list[str] = []
        self.hits: list[Hit] = []
        self.re_names = {"re"}
        self.direct_functions: set[str] = set()
        self.constants: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "re":
                        self.re_names.add(alias.asname or "re")
            elif isinstance(node, ast.ImportFrom) and node.module == "re":
                for alias in node.names:
                    if alias.name in REGEX_FUNCTIONS:
                        self.direct_functions.add(alias.asname or alias.name)
        for statement in tree.body:
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(statement, ast.Assign):
                targets, value = statement.targets, statement.value
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                targets, value = [statement.target], statement.value
            text = _string_value(value) if value is not None else None
            if text is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    self.constants[target.id] = text

    @property
    def qualname(self) -> str:
        return ".".join(self.stack) or "<module>"

    def _add(self, kind: str, detail: str, node: ast.AST) -> None:
        self.hits.append(
            Hit(self.relative, self.qualname, kind, detail, getattr(node, "lineno", 0))
        )

    def _scoped(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _scoped
    visit_AsyncFunctionDef = _scoped
    visit_ClassDef = _scoped

    def _assigned(self, node: ast.Assign | ast.AnnAssign) -> None:
        """A module-level ``NAME = re.compile(...)`` is reported under NAME,
        its qualified name, rather than one shared ``<module>`` bucket."""

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not self.stack and len(targets) == 1 and isinstance(targets[0], ast.Name):
            self.stack.append(targets[0].id)
            self.generic_visit(node)
            self.stack.pop()
        else:
            self.generic_visit(node)

    visit_Assign = _assigned
    visit_AnnAssign = _assigned

    def _is_regex_call(self, func: ast.expr) -> bool:
        if isinstance(func, ast.Attribute) and func.attr in REGEX_FUNCTIONS:
            return isinstance(func.value, ast.Name) and func.value.id in self.re_names
        return isinstance(func, ast.Name) and func.id in self.direct_functions

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_regex_call(node.func):
            pattern = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "pattern"), None
            )
            if pattern is not None:
                text = _string_value(pattern)
                if text is None and isinstance(pattern, ast.Name):
                    text = self.constants.get(pattern.id)
                if text is not None and has_hangul(text):
                    self._add("hangul-regex", text, node)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in PLAN_SCHEMA_KEYS
        ):
            self._add("plan-schema-key", f".get({node.args[0].value!r})", node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.slice, ast.Constant) and node.slice.value in PLAN_SCHEMA_KEYS:
            self._add("plan-schema-key", f"[{node.slice.value!r}]", node)
        self.generic_visit(node)


def product_modules(src: pathlib.Path = SRC) -> list[pathlib.Path]:
    modules = []
    for path in sorted(src.rglob("*.py")):
        relative = path.relative_to(src).as_posix()
        if "__pycache__" in relative or relative.startswith(EXCLUDED):
            continue
        modules.append(path)
    return modules


def scan_source(relative: str, source: str) -> list[Hit]:
    tree = ast.parse(source, filename=relative)
    scanner = _Scanner(relative, tree)
    scanner.visit(tree)
    return scanner.hits


def scan(src: pathlib.Path = SRC) -> list[Hit]:
    hits: list[Hit] = []
    for path in product_modules(src):
        relative = path.relative_to(src).as_posix()
        hits.extend(scan_source(relative, path.read_text(encoding="utf-8")))
    return hits


def load_allowlist(path: pathlib.Path = ALLOWLIST) -> dict[tuple[str, str, str], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(e["file"], e["qualname"], e["kind"]): e for e in data["entries"]}


def problems(hits: list[Hit], allowlist: dict[tuple[str, str, str], dict]) -> list[str]:
    """Every difference between the live hits and the allowlist."""

    counts = Counter(hit.key for hit in hits)
    found: list[str] = []
    for key, count in sorted(counts.items()):
        entry = allowlist.get(key)
        allowed = entry["count"] if entry else 0
        if count > allowed:
            examples = [h for h in hits if h.key == key]
            lines = ", ".join(f"line {h.line}: {h.detail[:60]!r}" for h in examples[:3])
            found.append(
                f"new {key[2]} in src/hwpx/{key[0]} {key[1]} "
                f"({count} found, {allowed} allowed; {lines})"
            )
    for key, entry in sorted(allowlist.items()):
        if counts.get(key, 0) < entry["count"]:
            found.append(
                f"stale allowlist entry src/hwpx/{key[0]} {key[1]} {key[2]}: "
                f"{entry['count']} allowed, {counts.get(key, 0)} found — lower or "
                "remove it in tests/data/layer_leak_allowlist.json"
            )
    return found


def defined_names(source: str) -> set[str]:
    """Module-level names and dotted qualnames of every def/class in *source*."""

    names: set[str] = set()

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(prefix + node.name)
                walk(node.body, f"{prefix}{node.name}.")
            elif not prefix and isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(t.id for t in targets if isinstance(t, ast.Name))

    walk(ast.parse(source).body, "")
    return names


def undetected_problems(path: pathlib.Path = ALLOWLIST, src: pathlib.Path = SRC) -> list[str]:
    """Known leaks the scan cannot see are listed by name; once one moves out
    of core its entry has to go too, so the list cannot rot."""

    data = json.loads(path.read_text(encoding="utf-8"))
    found = []
    for entry in data.get("undetected", []):
        module = src / entry["file"]
        if not module.exists() or entry["qualname"] not in defined_names(
            module.read_text(encoding="utf-8")
        ):
            found.append(
                f"undetected known leak src/hwpx/{entry['file']} {entry['qualname']} "
                "no longer exists — remove it from tests/data/layer_leak_allowlist.json"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print every live hit")
    args = parser.parse_args(argv)

    hits = scan()
    if args.list:
        for hit in hits:
            print(f"{hit.file}:{hit.line} {hit.qualname} {hit.kind} {hit.detail[:80]!r}")
        return 0
    found = problems(hits, load_allowlist()) + undetected_problems()
    if found:
        print("layer leak guard failed:\n  " + "\n  ".join(found), file=sys.stderr)
        print("\n" + GUIDANCE, file=sys.stderr)
        return 1
    print(f"layer leak guard ok — {len(hits)} allowlisted hit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
