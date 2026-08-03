# SPDX-License-Identifier: Apache-2.0
"""Positive and negative fixtures for the product-boundary ratchet."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI lane
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_product_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_product_boundary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
boundary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boundary)

BASELINE_FIXTURE = (
    ROOT / "docs" / "architecture" / "module-ownership-baseline-4.2.json"
)
REMOVED_FIXTURE = (
    ROOT / "docs" / "architecture" / "module-ownership-removed-5.0.json"
)
EXPECTED_BASELINE_PATH_COUNT = 176
EXPECTED_BASELINE_PATH_SHA256 = (
    "0ef0006565f776b43fe978489db1eb5ca2e72b2e027d11ad9206ca9c0eb7131d"
)
EXPECTED_REMOVED_PATH_COUNT = 77
EXPECTED_REMOVED_PATH_SHA256 = (
    "4b8b4da35b3cf44503eb0dba05e335de1894ca5dd0b2fb668692a69e21ae6172"
)
EXPECTED_FORBIDDEN_LAYER_IMPORTS = ("hwpx_automation", "hwpx_mcp_server", "mcp")
EXPECTED_FORBIDDEN_RUNTIME_IMPORTS = (
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
EXPECTED_ALLOWED_THIRD_PARTY_IMPORTS = ("latex2mathml", "lxml", "openpyxl")


def _ledger() -> dict:
    return json.loads(
        (ROOT / "docs" / "architecture" / "module-ownership.json").read_text(
            encoding="utf-8"
        )
    )


def _baseline_fixture() -> dict:
    return json.loads(BASELINE_FIXTURE.read_text(encoding="utf-8"))


def _removed_fixture() -> dict:
    return json.loads(REMOVED_FIXTURE.read_text(encoding="utf-8"))


def _copy_real_tree_for_cli(destination: Path) -> None:
    shutil.copytree(ROOT / "src" / "hwpx", destination / "src" / "hwpx")
    (destination / "scripts").mkdir()
    shutil.copy2(SCRIPT, destination / "scripts" / SCRIPT.name)
    architecture = destination / "docs" / "architecture"
    architecture.mkdir(parents=True)
    shutil.copy2(
        ROOT / "docs" / "architecture" / "module-ownership.json",
        architecture / "module-ownership.json",
    )
    shutil.copy2(
        BASELINE_FIXTURE,
        architecture / BASELINE_FIXTURE.name,
    )
    shutil.copy2(
        REMOVED_FIXTURE,
        architecture / REMOVED_FIXTURE.name,
    )


def test_baseline_path_fixture_is_exactly_code_and_ledger_pinned() -> None:
    ledger = _ledger()
    fixture = _baseline_fixture()
    paths = fixture["paths"]

    assert boundary.BASELINE_PATH_COUNT == EXPECTED_BASELINE_PATH_COUNT
    assert boundary.BASELINE_PATH_SHA256 == EXPECTED_BASELINE_PATH_SHA256
    assert ledger["baseline"]["sourceFileCount"] == EXPECTED_BASELINE_PATH_COUNT
    assert (
        ledger["baseline"]["sourcePathListSha256"]
        == EXPECTED_BASELINE_PATH_SHA256
    )
    assert fixture["canonicalization"]["pathCount"] == EXPECTED_BASELINE_PATH_COUNT
    assert (
        fixture["canonicalization"]["pathListSha256"]
        == EXPECTED_BASELINE_PATH_SHA256
    )
    assert len(paths) == EXPECTED_BASELINE_PATH_COUNT
    assert len(set(paths)) == EXPECTED_BASELINE_PATH_COUNT
    assert paths == sorted(paths)
    assert (
        hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8")).hexdigest()
        == EXPECTED_BASELINE_PATH_SHA256
    )


def test_removed_path_fixture_is_exactly_code_and_ledger_pinned() -> None:
    ledger = _ledger()
    fixture = _removed_fixture()
    paths = fixture["paths"]
    inventory = ledger["removedPathInventory"]

    assert boundary.REMOVED_PATH_COUNT == EXPECTED_REMOVED_PATH_COUNT
    assert boundary.REMOVED_PATH_SHA256 == EXPECTED_REMOVED_PATH_SHA256
    assert inventory["pathCount"] == EXPECTED_REMOVED_PATH_COUNT
    assert inventory["pathListSha256"] == EXPECTED_REMOVED_PATH_SHA256
    assert inventory["pathFixture"] == boundary.REMOVED_PATH_FIXTURE
    assert fixture["canonicalization"]["pathCount"] == EXPECTED_REMOVED_PATH_COUNT
    assert (
        fixture["canonicalization"]["pathListSha256"]
        == EXPECTED_REMOVED_PATH_SHA256
    )
    assert len(paths) == EXPECTED_REMOVED_PATH_COUNT
    assert len(set(paths)) == EXPECTED_REMOVED_PATH_COUNT
    assert paths == sorted(paths)
    assert (
        hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8")).hexdigest()
        == EXPECTED_REMOVED_PATH_SHA256
    )
    assert boundary._removed_files(ROOT, inventory) == set(paths)


def test_removed_inventory_is_the_exact_baseline_minus_current_tree() -> None:
    baseline = set(_baseline_fixture()["paths"])
    removed = set(_removed_fixture()["paths"])
    current = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "hwpx").rglob("*.py")
    }

    assert removed == baseline - current
    assert not removed & current


def test_real_tree_satisfies_ownership_ratchet() -> None:
    report = boundary.evaluate(ROOT, _ledger())
    assert report["ok"], report["violations"]
    assert boundary.FORBIDDEN_LAYER_IMPORTS == EXPECTED_FORBIDDEN_LAYER_IMPORTS
    assert boundary.FORBIDDEN_RUNTIME_IMPORTS == EXPECTED_FORBIDDEN_RUNTIME_IMPORTS
    assert (
        boundary.ALLOWED_THIRD_PARTY_IMPORTS
        == EXPECTED_ALLOWED_THIRD_PARTY_IMPORTS
    )

    # Every module is classified, rather than at least N are. The old floor was a
    # literal that had to be edited downward on every removal — a check whose
    # failure mode is "update the number" is not a check. Coverage is the property
    # worth holding: an unclassified module already becomes a violation above, and
    # this states the same invariant in a form that removal cannot erode.
    source_files = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "src" / "hwpx").rglob("*.py")
        if "__pycache__" not in path.parts
    }
    assert report["classifiedFiles"] == len(source_files), (
        f"{len(source_files) - report['classifiedFiles']} module(s) went unclassified"
    )
    for disposition in boundary.NON_CORE_DISPOSITIONS:
        assert report["totals"][disposition] == {"files": 0, "loc": 0}
    reverse_imports = {
        str(path.relative_to(ROOT)): imported
        for path in (ROOT / "src" / "hwpx").rglob("*.py")
        if (imported := boundary._reverse_imports(path))
    }
    assert reverse_imports == {}

    absolute_roots: set[str] = set()
    for path in (ROOT / "src" / "hwpx").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                absolute_roots.update(alias.name.partition(".")[0] for alias in node.names)
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
            ):
                absolute_roots.add(node.module.partition(".")[0])
    third_party_roots = (
        absolute_roots - set(sys.stdlib_module_names) - {"hwpx"}
    )
    assert third_party_roots == set(EXPECTED_ALLOWED_THIRD_PARTY_IMPORTS)


def test_runtime_import_allowlist_matches_declared_runtime_extras() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = list(project["project"]["dependencies"])
    optional = project["project"]["optional-dependencies"]
    dependencies.extend(optional["xlsx"])
    dependencies.extend(optional["preview"])
    declared_roots = {
        re.split(r"[\[<>=!~;\s]", requirement, maxsplit=1)[0].replace("-", "_")
        for requirement in dependencies
    }
    assert declared_roots == set(EXPECTED_ALLOWED_THIRD_PARTY_IMPORTS)


def test_real_tree_gate_runs_from_a_gitless_source_copy(tmp_path: Path) -> None:
    _copy_real_tree_for_cli(tmp_path)
    assert not (tmp_path / ".git").exists()

    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "scripts" / SCRIPT.name),
            "--root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["ok"]
    # 5.6: +6 — hwpx.plan 패키지 5 + hwpx.capabilities (ownership exceptions 등재).
    # 6.0: +18 — 062-engine-surface WP-A. model.py 1 + objects 1 + _document
    # 3(_legacy·_resolve·headings) + _document/ns 13(__init__·_base·11 네임스페이스).
    # 6.0: +5 — 062-engine-surface WP-C. objects/ 반환 규약 소유 모듈
    # 5종(checkbox·form_field·tracked·binary_item·results).
    # 전부 module-ownership.json 에 개별 rationale 과 함께 등재돼 있다.
    assert report["classifiedFiles"] == 131


def test_gitless_cli_reproduces_literal_dynamic_import_failure_without_mutating_source(
    tmp_path: Path,
) -> None:
    original_path = ROOT / "src" / "hwpx" / "document.py"
    original_bytes = original_path.read_bytes()
    _copy_real_tree_for_cli(tmp_path)
    mutated_path = tmp_path / "src" / "hwpx" / "document.py"
    mutated_path.write_text(
        mutated_path.read_text(encoding="utf-8")
        + "\nfrom importlib.util import find_spec as locate_runtime\n"
        + 'locate_runtime("Quartz")\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "scripts" / SCRIPT.name),
            "--root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert not report["ok"]
    assert any(
        "importlib loader capability is forbidden" in violation
        for violation in report["violations"]
    )
    assert mutated_path.read_bytes() != original_bytes
    assert original_path.read_bytes() == original_bytes


def test_reduced_baseline_fixture_fails_if_fixture_and_ledger_metadata_are_forged(
    tmp_path: Path,
) -> None:
    ledger = copy.deepcopy(_ledger())
    fixture = copy.deepcopy(_baseline_fixture())
    fixture["paths"].pop()
    forged_count = len(fixture["paths"])
    forged_digest = boundary._canonical_path_digest(fixture["paths"])
    fixture["canonicalization"]["pathCount"] = forged_count
    fixture["canonicalization"]["pathListSha256"] = forged_digest
    ledger["baseline"]["sourceFileCount"] = forged_count
    ledger["baseline"]["sourcePathListSha256"] = forged_digest

    fixture_path = tmp_path / boundary.BASELINE_PATH_FIXTURE
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must remain"):
        boundary._baseline_files(tmp_path, ledger["baseline"])


def test_reduced_removed_fixture_fails_if_fixture_and_ledger_metadata_are_forged(
    tmp_path: Path,
) -> None:
    ledger = copy.deepcopy(_ledger())
    fixture = copy.deepcopy(_removed_fixture())
    fixture["paths"].pop()
    forged_count = len(fixture["paths"])
    forged_digest = boundary._canonical_path_digest(fixture["paths"])
    fixture["canonicalization"]["pathCount"] = forged_count
    fixture["canonicalization"]["pathListSha256"] = forged_digest
    inventory = ledger["removedPathInventory"]
    inventory["pathCount"] = forged_count
    inventory["pathListSha256"] = forged_digest

    fixture_path = tmp_path / boundary.REMOVED_PATH_FIXTURE
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must remain"):
        boundary._removed_files(tmp_path, inventory)


@pytest.mark.parametrize("removed_path", _removed_fixture()["paths"])
def test_every_removed_module_path_fails_on_empty_resurrection(
    tmp_path: Path,
    removed_path: str,
) -> None:
    path = tmp_path / removed_path
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files=set(_baseline_fixture()["paths"]),
        removed_files=set(_removed_fixture()["paths"]),
    )

    assert not report["ok"]
    assert f"removed core module resurrected: {removed_path}" in report["violations"]


def test_removed_module_fails_even_as_a_new_core_implementation(tmp_path: Path) -> None:
    removed_path = "src/hwpx/form_fit/seal.py"
    path = tmp_path / removed_path
    path.parent.mkdir(parents=True)
    path.write_text(
        "def seal_document(document):\n"
        '    """A fresh implementation must still live in automation."""\n'
        "    return document\n",
        encoding="utf-8",
    )

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files=set(_baseline_fixture()["paths"]),
        removed_files=set(_removed_fixture()["paths"]),
    )

    assert f"removed core module resurrected: {removed_path}" in report["violations"]


def test_gitless_cli_rejects_a_removed_module_resurrection(tmp_path: Path) -> None:
    _copy_real_tree_for_cli(tmp_path)
    removed_path = "src/hwpx/form_fit/seal.py"
    path = tmp_path / removed_path
    path.write_text("VALUE = 1\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "scripts" / SCRIPT.name),
            "--root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stderr or result.stdout
    assert (
        f"removed core module resurrected: {removed_path}"
        in json.loads(result.stdout)["violations"]
    )


def test_new_application_module_fails_closed(tmp_path) -> None:
    source = tmp_path / "src" / "hwpx" / "agent"
    source.mkdir(parents=True)
    (source / "new_workflow.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files=set(),
        removed_files=set(),
    )

    assert not report["ok"]
    assert any("new module lacks explicit ownership" in item for item in report["violations"])


@pytest.mark.parametrize("module_name", EXPECTED_FORBIDDEN_LAYER_IMPORTS)
def test_core_reverse_layer_dependency_fails_closed(
    tmp_path: Path,
    module_name: str,
) -> None:
    source = tmp_path / "src" / "hwpx"
    source.mkdir(parents=True)
    path = source / "document.py"
    path.write_text(f"import {module_name}.sentinel\n", encoding="utf-8")

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files={"src/hwpx/document.py"},
        removed_files=set(),
    )

    assert not report["ok"]
    assert any(
        f"core reverse dependency: src/hwpx/document.py imports {module_name}.sentinel"
        in item
        for item in report["violations"]
    )


@pytest.mark.parametrize("module_name", ("fitz", "win32com.client"))
def test_core_forbidden_runtime_dependency_fails_closed(
    tmp_path: Path,
    module_name: str,
) -> None:
    source = tmp_path / "src" / "hwpx"
    source.mkdir(parents=True)
    path = source / "document.py"
    path.write_text(f"import {module_name}\n", encoding="utf-8")

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files={"src/hwpx/document.py"},
        removed_files=set(),
    )

    assert not report["ok"]
    assert any(
        f"core reverse dependency: src/hwpx/document.py imports {module_name}" in item
        for item in report["violations"]
    )


@pytest.mark.parametrize(
    ("source_text", "expected_fragment"),
    (
        (
            'import importlib\nimportlib.import_module("mcp")\n',
            "importlib base capability",
        ),
        (
            'import importlib as loader\nloader.import_module("mcp")\n',
            "importlib base capability",
        ),
        (
            "from importlib import import_module as load_module\n"
            'load_module("mcp")\n',
            "only exact 'from importlib import resources'",
        ),
        (
            'import importlib.util\nimportlib.util.find_spec("mcp")\n',
            "importlib loader capability",
        ),
        (
            "from importlib.util import find_spec as locate\nlocate('mcp')\n",
            "importlib loader capability",
        ),
        (
            "from importlib.machinery import SourceFileLoader\n",
            "importlib loader capability",
        ),
        (
            "from importlib.metadata import import_module\n"
            "import_module('mcp')\n",
            "only PackageNotFoundError/version",
        ),
        (
            "import importlib.metadata as md\nmd.import_module('mcp')\n",
            "importlib loader capability",
        ),
        (
            "from importlib import metadata as md\nmd.import_module('mcp')\n",
            "only exact 'from importlib import resources'",
        ),
        (
            "import importlib.metadata\n"
            "importlib.metadata.import_module('mcp')\n",
            "importlib loader capability",
        ),
        (
            "import importlib.metadata as md\n"
            "vars(md)['import_module']('mcp')\n",
            "importlib loader capability",
        ),
        (
            "from importlib import resources\nresources.import_module('mcp')\n",
            "importlib.resources loader/reflection",
        ),
        ('__import__("mcp")\n', "dynamic execution capability"),
        (
            "from builtins import __import__ as load_builtin\nload_builtin('mcp')\n",
            "dynamic execution builtin import",
        ),
        (
            "import builtins as runtime\nruntime.__import__('mcp')\n",
            "dynamic execution builtin capability",
        ),
        (
            "import builtins\ngetattr(builtins, '__import__')('mcp')\n",
            "dynamic execution builtin capability",
        ),
        (
            "getattr(__builtins__, '__import__')('mcp')\n",
            "dynamic execution capability",
        ),
        ("eval(\"__import__('mcp')\")\n", "dynamic execution capability"),
        ("exec(\"import mcp\")\n", "dynamic execution capability"),
        ("import subprocess\n", "execution runtime import"),
        ("from ctypes import CDLL\n", "execution runtime import"),
        ("import os\nos.system('true')\n", "os.system/os.popen"),
        ("import os as platform\nplatform.popen('true')\n", "os.system/os.popen"),
        ("from os import system\nsystem('true')\n", "os.system/os.popen"),
        (
            "import os\ngetattr(os, 'system')('true')\n",
            "reflective os capability",
        ),
        (
            "import os\nos.__dict__['system']('true')\n",
            "reflective os capability",
        ),
        (
            "import os as operating\n"
            "operating.__dict__['popen']('true')\n",
            "reflective os capability",
        ),
        (
            "import os\nvars(os)['system']('true')\n",
            "reflective os capability",
        ),
        (
            "import os\nos.__getattribute__('popen')('true')\n",
            "reflective os capability",
        ),
        (
            "import os\noperating = os\noperating.system('true')\n",
            "os.system/os.popen",
        ),
    ),
)
def test_loader_and_execution_capabilities_fail_closed(
    tmp_path: Path,
    source_text: str,
    expected_fragment: str,
) -> None:
    path = tmp_path / "src" / "hwpx" / "document.py"
    path.parent.mkdir(parents=True)
    path.write_text(source_text, encoding="utf-8")

    failures = boundary._reverse_imports(path)

    assert any(expected_fragment in failure for failure in failures), failures


@pytest.mark.parametrize(
    "module_name",
    (
        *EXPECTED_FORBIDDEN_LAYER_IMPORTS,
        *EXPECTED_FORBIDDEN_RUNTIME_IMPORTS,
        "requests",
    ),
)
def test_unknown_absolute_import_roots_fail_closed(
    tmp_path: Path,
    module_name: str,
) -> None:
    path = tmp_path / "src" / "hwpx" / "document.py"
    path.parent.mkdir(parents=True)
    path.write_text(f"import {module_name}.sentinel\n", encoding="utf-8")

    assert module_name + ".sentinel" in boundary._reverse_imports(path)


def test_closed_gate_allows_only_declared_imports_and_local_loader_methods(
    tmp_path: Path,
) -> None:
    path = tmp_path / "src" / "hwpx" / "document.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        '''"""Strings may mention importlib.import_module("mcp") and eval()."""
import json
import latex2mathml
import openpyxl
from importlib import resources
from importlib.metadata import version
from lxml import etree
from . import package
import hwpx.package

class LocalLoader:
    def import_module(self, name):
        return name

    def __import__(self, name):
        return name

    def system(self, command):
        return command

local_loader = LocalLoader()
local_loader.import_module("mcp")
local_loader.__import__("mcp")
local_loader.system("true")
local_loader.__dict__["system"]
module_name = "hwpx_automation"
example = 'importlib.util.find_spec("hwpx_automation")'
''',
        encoding="utf-8",
    )

    assert boundary._reverse_imports(path) == []


def test_real_lazy_loader_is_exactly_pinned_and_internally_guarded() -> None:
    path = ROOT / boundary.LAZY_IMPORT_FILE
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = boundary._lazy_import_calls(tree)

    assert boundary._lazy_call_fingerprint(calls) == (
        boundary.LAZY_IMPORT_CALL_SITES,
        boundary.LAZY_IMPORT_CALL_SHA256,
    )
    assert (
        boundary._function_fingerprint(tree, "__getattr__")
        == boundary.LAZY_GETATTR_SHA256
    )
    assert boundary._reverse_imports(path) == []


def test_ast_fingerprint_normalizes_only_empty_parser_version_fields() -> None:
    path = ROOT / boundary.LAZY_IMPORT_FILE
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__"
    )
    baseline = boundary._stable_ast_dump(function)

    simulated_new_parser = copy.deepcopy(function)
    if "type_params" not in simulated_new_parser._fields:
        simulated_new_parser._fields = (
            *simulated_new_parser._fields,
            "type_params",
        )
    simulated_new_parser.type_params = []
    assert boundary._stable_ast_dump(simulated_new_parser) == baseline

    simulated_new_parser.type_params = [
        ast.Name(id="UnsafeGenericParameter", ctx=ast.Load())
    ]
    assert boundary._stable_ast_dump(simulated_new_parser) != baseline


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            "import importlib\n",
            "import importlib as loader\n",
        ),
        (
            "return getattr(importlib.import_module(module_name), name)",
            "return getattr(importlib.import_module('hwpx.package'), name)",
        ),
        (
            '"ConversionAttempt": "hwpx.ingest",\n',
            '"ConversionAttempt": "os",\n',
        ),
        (
            '"ConversionAttempt": "hwpx.ingest",\n',
            "",
        ),
        (
            "        warnings.warn(_experimental_message(name)",
            "\n        warnings.warn(_experimental_message(name)",
        ),
        (
            '        if module_name != "hwpx" and not module_name.startswith("hwpx."):\n'
            "            raise AttributeError(\n"
            '                "hwpx lazy-export targets must remain inside the '
            "'hwpx' package\"\n"
            "            )\n",
            "\n\n\n\n",
        ),
    ),
)
def test_any_pinned_lazy_loader_drift_fails_closed(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    source = (ROOT / boundary.LAZY_IMPORT_FILE).read_text(encoding="utf-8")
    assert old in source
    path = tmp_path / boundary.LAZY_IMPORT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(source.replace(old, new, 1), encoding="utf-8")

    assert boundary._reverse_imports(path)


def test_extra_lazy_loader_call_fails_closed(tmp_path: Path) -> None:
    source = (ROOT / boundary.LAZY_IMPORT_FILE).read_text(encoding="utf-8")
    path = tmp_path / boundary.LAZY_IMPORT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(
        source + "\n_EXTRA = importlib.import_module('hwpx.package')\n",
        encoding="utf-8",
    )

    assert boundary._reverse_imports(path)


@pytest.mark.parametrize(
    "leak",
    (
        "_LEAK = vars(importlib)['import_module']\n",
        "_LEAK = [importlib]\n",
        "def _leak_importlib():\n    return importlib\n",
        "_LEAK = importlib.__dict__['import_module']\n",
        "_LEAK = importlib.__getattribute__('import_module')\n",
    ),
)
def test_pinned_lazy_importlib_object_cannot_escape(
    tmp_path: Path,
    leak: str,
) -> None:
    source = (ROOT / boundary.LAZY_IMPORT_FILE).read_text(encoding="utf-8")
    path = tmp_path / boundary.LAZY_IMPORT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(source + "\n" + leak, encoding="utf-8")

    failures = boundary._reverse_imports(path)
    assert any("importlib" in failure for failure in failures), failures


@pytest.mark.parametrize(
    ("map_name", "probe_name"),
    (
        ("_EXPERIMENTAL_EXPORTS", "_unsafe_experimental_probe"),
        ("_DEPRECATED_EXPORTS", "_unsafe_deprecated_probe"),
    ),
)
def test_mutated_lazy_map_cannot_import_outside_hwpx_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
    map_name: str,
    probe_name: str,
) -> None:
    import hwpx

    export_map = getattr(hwpx, map_name)
    monkeypatch.setitem(export_map, probe_name, "os")
    attempted: list[str] = []

    def record_import(module_name: str) -> object:
        attempted.append(module_name)
        raise AssertionError("external import must not be attempted")

    monkeypatch.setattr(hwpx.importlib, "import_module", record_import)

    with pytest.raises(AttributeError, match="targets must remain inside"):
        getattr(hwpx, probe_name)
    assert attempted == []


@pytest.mark.parametrize("disposition", boundary.NON_CORE_DISPOSITIONS)
def test_any_non_core_disposition_fails_even_with_self_consistent_ownership(
    tmp_path,
    disposition: str,
) -> None:
    relative = f"src/hwpx/synthetic_{disposition.replace('-', '_')}.py"
    source = tmp_path / Path(relative).parent
    source.mkdir(parents=True)
    path = tmp_path / relative
    path.write_text("VALUE = 1\n", encoding="utf-8")
    ledger = copy.deepcopy(_ledger())
    ledger["exceptions"].insert(
        0,
        {
            "path": relative,
            "disposition": disposition,
            "approvedBy": "mutation-test",
            "rationale": "prove every non-core disposition fails closed",
        },
    )

    report = boundary.evaluate(
        tmp_path,
        ledger,
        baseline_files={relative},
        removed_files=set(),
    )

    assert not report["ok"]
    assert report["totals"][disposition]["files"] == 1
    assert any("must be exactly zero" in item for item in report["violations"])


def test_unpublished_house_style_surface_is_absent_from_core() -> None:
    import hwpx

    assert importlib.util.find_spec("hwpx.house_style") is None
    assert "build_section_chip" not in hwpx.__all__
    assert not hasattr(hwpx, "build_section_chip")
