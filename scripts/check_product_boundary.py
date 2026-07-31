#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Enforce the closed python-hwpx ownership and dependency boundary."""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FORBIDDEN_LAYER_IMPORTS = ("hwpx_automation", "hwpx_mcp_server", "mcp")
FORBIDDEN_RUNTIME_IMPORTS = (
    "fitz",
    "PIL",
    "numpy",
    "win32com",
    "comtypes",
    "appscript",
    "Quartz",
    "objc",
    "pythoncom",
    "pymupdf",
    "pypdf",
    "pdfplumber",
    "pdf2image",
    "pikepdf",
    "AppKit",
    "Foundation",
    "ScriptingBridge",
    "PyObjCTools",
)
# Keep the pre-existing skill reverse-dependency guard separate so changing it
# remains an explicit decision.
FORBIDDEN_LEGACY_IMPORTS = ("hwpx_skill",)
FORBIDDEN_IMPORTS = (
    FORBIDDEN_LAYER_IMPORTS
    + FORBIDDEN_RUNTIME_IMPORTS
    + FORBIDDEN_LEGACY_IMPORTS
)
ALLOWED_THIRD_PARTY_IMPORTS = ("latex2mathml", "lxml", "openpyxl")
ALLOWED_ABSOLUTE_IMPORT_ROOTS = frozenset(sys.stdlib_module_names) | {
    "hwpx",
    *ALLOWED_THIRD_PARTY_IMPORTS,
}
FORBIDDEN_EXECUTION_IMPORT_ROOTS = ("ctypes", "subprocess")

LAZY_IMPORT_FILE = "src/hwpx/__init__.py"
LAZY_IMPORT_CALL_SITES = ((294, 23), (303, 23))
LAZY_IMPORT_CALL_SHA256 = (
    "ac0095b773833701563c10ffebd90bc9a961b47f4f1e41fb786a9534e97f62e4"
)
LAZY_GETATTR_SHA256 = (
    "f40a6478d266d6fabb89fc67504166abd9c195605f068d408eb29cd901dbba73"
)
IGNORED_EMPTY_AST_FIELDS = frozenset({"type_params"})
LAZY_EXPORT_MAP_COUNT = 15
LAZY_EXPORT_MAP_SHA256 = (
    "04b88786e99fb969153bb7a4bad54ed94599797a47a74c369acd6df4a9629fd1"
)

NON_CORE_DISPOSITIONS = ("mcp-migrate", "split", "dev-only", "undecided")
BASELINE_COMMIT = "f6b79f010d40a190fa6a8391eb212835022b3851"
BASELINE_SOURCE_ROOT = "src/hwpx"
BASELINE_PATH_FIXTURE = "docs/architecture/module-ownership-baseline-4.2.json"
BASELINE_PATH_COUNT = 176
BASELINE_PATH_SHA256 = (
    "0ef0006565f776b43fe978489db1eb5ca2e72b2e027d11ad9206ca9c0eb7131d"
)
BASELINE_FIXTURE_SCHEMA = "python-hwpx.module-ownership-baseline/v1"
BASELINE_CANONICAL_FORMAT = (
    "sorted repository-relative Python paths encoded as UTF-8 with a final LF"
)
REMOVED_PATH_FIXTURE = "docs/architecture/module-ownership-removed-5.0.json"
REMOVED_PATH_COUNT = 77
REMOVED_PATH_SHA256 = (
    "4b8b4da35b3cf44503eb0dba05e335de1894ca5dd0b2fb668692a69e21ae6172"
)
REMOVED_FIXTURE_SCHEMA = "python-hwpx.module-ownership-removed/v1"


def _python_files(root: Path, source_root: str) -> list[Path]:
    return sorted((root / source_root).rglob("*.py"))


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _canonical_path_digest(paths: list[str]) -> str:
    payload = ("\n".join(paths) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validated_path_fixture(
    root: Path,
    *,
    fixture_path: str,
    fixture_schema: str,
    fixture_metadata: dict[str, str],
    path_count: int,
    path_sha256: str,
    label: str,
) -> set[str]:
    root = root.resolve()
    resolved_fixture = (root / fixture_path).resolve()
    try:
        resolved_fixture.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} fixture escapes the repository root") from exc
    fixture = json.loads(resolved_fixture.read_text(encoding="utf-8"))

    expected_fixture = {
        "schemaVersion": fixture_schema,
        "sourceRoot": BASELINE_SOURCE_ROOT,
        **fixture_metadata,
    }
    for key, expected in expected_fixture.items():
        if fixture.get(key) != expected:
            raise ValueError(
                f"{label} fixture {key} must remain {expected!r}; "
                f"got {fixture.get(key)!r}"
            )

    expected_canonicalization = {
        "format": BASELINE_CANONICAL_FORMAT,
        "pathCount": path_count,
        "pathListSha256": path_sha256,
    }
    if fixture.get("canonicalization") != expected_canonicalization:
        raise ValueError(
            f"{label} fixture canonicalization metadata does not match "
            "the code-pinned inventory"
        )

    paths = fixture.get("paths")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError(f"{label} fixture paths must be a list of strings")
    if paths != sorted(paths):
        raise ValueError(f"{label} fixture paths must remain canonically sorted")
    if len(paths) != len(set(paths)):
        raise ValueError(f"{label} fixture paths contain duplicates")
    if len(paths) != path_count:
        raise ValueError(
            f"{label} fixture must contain {path_count} paths; got {len(paths)}"
        )
    prefix = f"{BASELINE_SOURCE_ROOT}/"
    if any(not path.startswith(prefix) or not path.endswith(".py") for path in paths):
        raise ValueError(
            f"{label} fixture paths must be Python files below "
            f"{BASELINE_SOURCE_ROOT}"
        )
    digest = _canonical_path_digest(paths)
    if digest != path_sha256:
        raise ValueError(
            f"{label} fixture digest must remain {path_sha256}; got {digest}"
        )
    return set(paths)


def _baseline_files(root: Path, baseline: dict[str, Any]) -> set[str]:
    expected_ledger = {
        "commit": BASELINE_COMMIT,
        "sourceRoot": BASELINE_SOURCE_ROOT,
        "sourceFileCount": BASELINE_PATH_COUNT,
        "sourcePathListSha256": BASELINE_PATH_SHA256,
        "pathFixture": BASELINE_PATH_FIXTURE,
    }
    for key, expected in expected_ledger.items():
        if baseline.get(key) != expected:
            raise ValueError(
                f"baseline ledger {key} must remain {expected!r}; "
                f"got {baseline.get(key)!r}"
            )
    return _validated_path_fixture(
        root,
        fixture_path=BASELINE_PATH_FIXTURE,
        fixture_schema=BASELINE_FIXTURE_SCHEMA,
        fixture_metadata={"baselineCommit": BASELINE_COMMIT},
        path_count=BASELINE_PATH_COUNT,
        path_sha256=BASELINE_PATH_SHA256,
        label="baseline",
    )


def _removed_files(root: Path, inventory: dict[str, Any]) -> set[str]:
    expected_ledger = {
        "version": "5.0.0",
        "sourceRoot": BASELINE_SOURCE_ROOT,
        "pathCount": REMOVED_PATH_COUNT,
        "pathListSha256": REMOVED_PATH_SHA256,
        "pathFixture": REMOVED_PATH_FIXTURE,
    }
    for key, expected in expected_ledger.items():
        if inventory.get(key) != expected:
            raise ValueError(
                f"removed-path ledger {key} must remain {expected!r}; "
                f"got {inventory.get(key)!r}"
            )
    return _validated_path_fixture(
        root,
        fixture_path=REMOVED_PATH_FIXTURE,
        fixture_schema=REMOVED_FIXTURE_SCHEMA,
        fixture_metadata={
            "baselineCommit": BASELINE_COMMIT,
            "removalVersion": "5.0.0",
        },
        path_count=REMOVED_PATH_COUNT,
        path_sha256=REMOVED_PATH_SHA256,
        label="removed-path",
    )


def _classification(
    path: str,
    ledger: dict[str, Any],
) -> tuple[str | None, str | None]:
    for exception in ledger.get("exceptions", []):
        if exception["path"] == path:
            return exception["disposition"], "exception"
    for rule in ledger["rules"]:
        if fnmatch.fnmatchcase(path, rule["glob"]):
            return rule["disposition"], rule["glob"]
    return None, None


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_string(node.left)
        right = _literal_string(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                return None
            parts.append(value.value)
        return "".join(parts)
    return None


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted_name(node.value)
        if owner is not None:
            return f"{owner}.{node.attr}"
    return None


def _is_forbidden_absolute_import(name: str) -> bool:
    if name.startswith("."):
        return False
    root = name.partition(".")[0]
    return bool(root) and root not in ALLOWED_ABSOLUTE_IMPORT_ROOTS


def _is_lazy_import_file(path: Path) -> bool:
    normalized = path.as_posix()
    return normalized == LAZY_IMPORT_FILE or normalized.endswith(
        f"/{LAZY_IMPORT_FILE}"
    )


def _lazy_import_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _dotted_name(node.func) == "importlib.import_module"
    ]


def _stable_ast_value(value: Any) -> Any:
    """Return a version-neutral, structure-complete AST representation.

    ``ast.dump`` changed its empty-field rendering in Python 3.13, while
    Python 3.12 added empty ``type_params`` fields to function/class nodes.
    Those parser-only differences must not make an identical source tree fail
    on a supported Python minor.  All real syntax remains represented:
    ``type_params`` is omitted only when empty and therefore still changes the
    fingerprint if generic syntax is introduced.
    """

    if isinstance(value, ast.AST):
        fields: list[list[Any]] = []
        for name, child in ast.iter_fields(value):
            if name in IGNORED_EMPTY_AST_FIELDS and child == []:
                continue
            fields.append([name, _stable_ast_value(child)])
        return [type(value).__name__, fields]
    if isinstance(value, list):
        return [_stable_ast_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _stable_ast_dump(node: ast.AST) -> str:
    return json.dumps(
        _stable_ast_value(node),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _lazy_call_fingerprint(
    calls: list[ast.Call],
) -> tuple[tuple[tuple[int, int], ...], str]:
    rows = sorted(
        (
            node.lineno,
            node.col_offset,
            _stable_ast_dump(node),
        )
        for node in calls
    )
    payload = (
        "\n".join(f"{line}:{column}:{dump}" for line, column, dump in rows) + "\n"
    )
    return (
        tuple((line, column) for line, column, _dump in rows),
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def _function_fingerprint(tree: ast.Module, name: str) -> str | None:
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(functions) != 1:
        return None
    payload = _stable_ast_dump(functions[0])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _literal_export_maps(tree: ast.Module) -> list[str] | None:
    expected_names = {"_EXPERIMENTAL_EXPORTS", "_DEPRECATED_EXPORTS"}
    found: dict[str, dict[str, str]] = {}
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if (
            not isinstance(target, ast.Name)
            or target.id not in expected_names
            or value is None
        ):
            continue
        try:
            literal = ast.literal_eval(value)
        except (ValueError, TypeError):
            return None
        if not isinstance(literal, dict) or not all(
            isinstance(key, str) and isinstance(module, str)
            for key, module in literal.items()
        ):
            return None
        found[target.id] = literal
    if set(found) != expected_names:
        return None
    return sorted(
        f"{map_name}:{key}={module}"
        for map_name, entries in found.items()
        for key, module in entries.items()
    )


def _approved_lazy_imports(
    path: Path,
    tree: ast.Module,
) -> tuple[set[int], list[str]]:
    calls = _lazy_import_calls(tree)
    if not _is_lazy_import_file(path):
        return set(), [
            "unapproved importlib.import_module capability" for _call in calls
        ]

    failures: list[str] = []
    sites, digest = _lazy_call_fingerprint(calls)
    if sites != LAZY_IMPORT_CALL_SITES or digest != LAZY_IMPORT_CALL_SHA256:
        failures.append(
            "lazy import callsites must remain the two code-pinned "
            f"{LAZY_IMPORT_FILE} exports"
        )
    if _function_fingerprint(tree, "__getattr__") != LAZY_GETATTR_SHA256:
        failures.append(
            "lazy __getattr__ must retain its code-pinned internal-target guards"
        )

    rows = _literal_export_maps(tree)
    if rows is None:
        failures.append("lazy export maps must remain literal dictionaries")
    else:
        map_digest = hashlib.sha256(
            ("\n".join(rows) + "\n").encode("utf-8")
        ).hexdigest()
        if len(rows) != LAZY_EXPORT_MAP_COUNT or map_digest != LAZY_EXPORT_MAP_SHA256:
            failures.append("lazy export maps differ from the code-pinned inventory")
        if any(
            target != "hwpx" and not target.startswith("hwpx.")
            for row in rows
            if (target := row.partition("=")[2])
        ):
            failures.append("lazy export map targets must remain inside hwpx")

    if failures:
        return set(), failures
    return {id(call) for call in calls}, []


def _closed_capability_failures(path: Path, tree: ast.Module) -> list[str]:
    approved_calls, failures = _approved_lazy_imports(path, tree)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    importlib_base = [
        node
        for node in imports
        if any(alias.name == "importlib" for alias in node.names)
    ]
    if _is_lazy_import_file(path):
        exact_import = (
            len(importlib_base) == 1
            and len(importlib_base[0].names) == 1
            and importlib_base[0].names[0].name == "importlib"
            and importlib_base[0].names[0].asname is None
        )
        if not exact_import:
            failures.append("lazy export module must keep one exact 'import importlib'")
    elif importlib_base:
        failures.extend(
            "importlib base capability is reserved for the pinned lazy exports"
            for _node in importlib_base
        )

    parent: dict[int, ast.AST] = {
        id(child): node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }
    os_aliases = {
        alias.asname or "os"
        for node in imports
        for alias in node.names
        if alias.name == "os"
    }
    builtins_aliases = {
        alias.asname or "builtins"
        for node in imports
        for alias in node.names
        if alias.name == "builtins"
    }
    resource_aliases = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == "importlib"
        for alias in node.names
        if alias.name == "resources" and alias.asname is None
    }
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            source_name: str | None = None
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                source_name = node.value.id
                targets = list(node.targets)
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.value, ast.Name)
            ):
                source_name = node.value.id
                targets = [node.target]
            if source_name not in os_aliases:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in os_aliases:
                    os_aliases.add(target.id)
                    changed = True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name.partition(".")[0] == "importlib"
                    and alias.name != "importlib"
                ):
                    failures.append(
                        f"importlib loader capability is forbidden: {alias.name}"
                    )
                if alias.name == "builtins":
                    failures.append("builtins module capability is forbidden")
                if alias.name.partition(".")[0] in FORBIDDEN_EXECUTION_IMPORT_ROOTS:
                    failures.append(
                        f"execution runtime import is forbidden: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "importlib":
                exact_resources = (
                    len(node.names) == 1
                    and node.names[0].name == "resources"
                    and node.names[0].asname is None
                )
                if not exact_resources:
                    failures.append(
                        "only exact 'from importlib import resources' is allowed"
                    )
            elif node.module == "importlib.metadata":
                allowed_metadata = all(
                    alias.name in {"PackageNotFoundError", "version"}
                    and (
                        alias.name == "version"
                        or alias.asname is None
                    )
                    for alias in node.names
                ) and all(alias.name != "*" for alias in node.names)
                if not allowed_metadata:
                    failures.append(
                        "only PackageNotFoundError/version metadata imports "
                        "are allowed"
                    )
            elif node.module.partition(".")[0] == "importlib":
                failures.append(
                    f"importlib loader capability is forbidden: {node.module}"
                )
            if node.module == "builtins" and any(
                alias.name in {"__import__", "eval", "exec"} for alias in node.names
            ):
                failures.append("dynamic execution builtin import is forbidden")
            if node.module == "os" and any(
                alias.name in {"system", "popen"} for alias in node.names
            ):
                failures.append("os.system/os.popen capability is forbidden")
            if node.module.partition(".")[0] in FORBIDDEN_EXECUTION_IMPORT_ROOTS:
                failures.append(
                    f"execution runtime import is forbidden: {node.module}"
                )
        elif isinstance(node, ast.Attribute):
            dotted = _dotted_name(node)
            if dotted and dotted.startswith("importlib."):
                owner = parent.get(id(node))
                approved_loader = (
                    dotted == "importlib.import_module"
                    and isinstance(owner, ast.Call)
                    and owner.func is node
                    and id(owner) in approved_calls
                )
                if not approved_loader:
                    failures.append(
                        f"importlib capability is not approved: {dotted}"
                    )
            root, _separator, attribute = (dotted or "").partition(".")
            if (
                root in builtins_aliases | {"__builtins__"}
                and attribute in {"__import__", "eval", "exec"}
            ):
                failures.append("dynamic execution builtin capability is forbidden")
            if root in os_aliases and attribute in {"system", "popen"}:
                failures.append("os.system/os.popen capability is forbidden")
            if (
                root in os_aliases
                and attribute.split(".", 1)[0] in {"__dict__", "__getattribute__"}
            ):
                failures.append("reflective os capability lookup is forbidden")
            if (
                root in resource_aliases
                and attribute.split(".", 1)[0]
                in {"import_module", "__dict__", "__getattribute__"}
            ):
                failures.append(
                    "importlib.resources loader/reflection capability is forbidden"
                )
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in {"__import__", "eval", "exec", "__builtins__"}:
                failures.append(
                    f"dynamic execution capability is forbidden: {node.id}"
                )
            if node.id == "importlib":
                owner = parent.get(id(node))
                owner_parent = parent.get(id(owner)) if owner is not None else None
                approved_base = (
                    isinstance(owner, ast.Attribute)
                    and owner.value is node
                    and owner.attr == "import_module"
                    and isinstance(owner_parent, ast.Call)
                    and owner_parent.func is owner
                    and id(owner_parent) in approved_calls
                )
                if not approved_base:
                    failures.append("importlib base capability escape is forbidden")
        elif isinstance(node, ast.Subscript):
            owner = _dotted_name(node.value)
            key = _literal_string(node.slice)
            if (
                owner in builtins_aliases | {"__builtins__"}
                and key in {"__import__", "eval", "exec"}
            ):
                failures.append("dynamic execution builtin capability is forbidden")
        elif isinstance(node, ast.Call):
            dotted = _dotted_name(node.func)
            root, _separator, attribute = (dotted or "").partition(".")
            if root in os_aliases and attribute in {"system", "popen"}:
                failures.append("os.system/os.popen capability is forbidden")
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                owner = _dotted_name(node.args[0])
                attribute_name = _literal_string(node.args[1])
                if owner == "importlib":
                    failures.append("dynamic importlib capability lookup is forbidden")
                if (
                    owner in builtins_aliases | {"__builtins__"}
                    and attribute_name in {"__import__", "eval", "exec"}
                ):
                    failures.append(
                        "dynamic execution builtin capability is forbidden"
                    )
                if owner in os_aliases and attribute_name in {
                    "system",
                    "popen",
                    "__dict__",
                    "__getattribute__",
                }:
                    failures.append("reflective os capability lookup is forbidden")
                if owner in resource_aliases and attribute_name in {
                    "import_module",
                    "__dict__",
                    "__getattribute__",
                }:
                    failures.append(
                        "importlib.resources loader/reflection capability is "
                        "forbidden"
                    )
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "vars"
                and node.args
            ):
                owner = _dotted_name(node.args[0])
                if owner in os_aliases:
                    failures.append("reflective os capability lookup is forbidden")
                if owner in resource_aliases:
                    failures.append(
                        "importlib.resources loader/reflection capability is "
                        "forbidden"
                    )
    return failures


def _reverse_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [f"could not inspect imports: {exc}"]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_absolute_import(alias.name):
                    found.append(alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and _is_forbidden_absolute_import(node.module)
        ):
            found.append(node.module)
    found.extend(_closed_capability_failures(path, tree))
    return found


def evaluate(
    root: Path,
    ledger: dict[str, Any],
    *,
    baseline_files: set[str] | None = None,
    removed_files: set[str] | None = None,
) -> dict[str, Any]:
    source_root = ledger["baseline"]["sourceRoot"]
    baseline_files = baseline_files if baseline_files is not None else _baseline_files(
        root,
        ledger["baseline"],
    )
    removed_files = removed_files if removed_files is not None else _removed_files(
        root,
        ledger["removedPathInventory"],
    )
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0})
    violations: list[str] = []
    classified: dict[str, str] = {}

    for file_path in _python_files(root, source_root):
        relative = _relative(root, file_path)
        if relative in removed_files:
            violations.append(f"removed core module resurrected: {relative}")
        disposition, matched_by = _classification(relative, ledger)
        if disposition is None:
            violations.append(f"unclassified core module: {relative}")
            continue
        classified[relative] = disposition
        totals[disposition]["files"] += 1
        totals[disposition]["loc"] += len(
            file_path.read_text(encoding="utf-8").splitlines()
        )

        if relative not in baseline_files and matched_by != "exception":
            violations.append(
                f"new module lacks explicit ownership exception: {relative} "
                f"(fell through {matched_by})"
            )
        for imported in _reverse_imports(file_path):
            violations.append(
                f"core reverse dependency: {relative} imports {imported}"
            )

    for disposition in NON_CORE_DISPOSITIONS:
        current = totals[disposition]
        if current["files"] != 0 or current["loc"] != 0:
            violations.append(
                f"{disposition} disposition must be exactly zero: "
                f"{current['files']} file(s), {current['loc']} LOC"
            )

    for disposition in ("core", *NON_CORE_DISPOSITIONS):
        totals.setdefault(disposition, {"files": 0, "loc": 0})

    return {
        "ok": not violations,
        "baselineCommit": ledger["baseline"]["commit"],
        "classifiedFiles": len(classified),
        "removedPathCount": len(removed_files),
        "totals": dict(sorted(totals.items())),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/architecture/module-ownership.json"),
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    ledger_path = args.ledger if args.ledger.is_absolute() else root / args.ledger
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    report = evaluate(root, ledger)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
