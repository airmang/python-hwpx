# SPDX-License-Identifier: Apache-2.0
"""Keep current core manuals executable against the shipped core wheel."""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import re
import shutil
import subprocess
import symtable
import sys
import zipfile
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI lane
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
CURRENT_CORE_MANUALS = (
    Path("README.md"),
    Path("README_EN.md"),
    Path("docs/quickstart.md"),
    Path("docs/recipes-traversal.md"),
    Path("docs/mutation-semantics.md"),
    Path("docs/usage.md"),
    Path("docs/examples.md"),
    Path("docs/faq.md"),
    Path("docs/index.md"),
    Path("docs/safe-write-contract.md"),
    Path("docs/golden-api.md"),
)
PYTHON_FENCE = re.compile(
    r"^```(?:python|py)(?:[ \t]+[^\n]*)?\n(.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
EXPECTED_FENCE_COUNT = 117
EXPECTED_FENCE_SHA256 = (
    "334b65d84888b64fb104bfdc3a38793eedfdacf8df2496bd2e3c1b06b12a577c"
)
ALLOWED_IMPORT_ROOTS = frozenset(sys.stdlib_module_names) | {"hwpx"}
LEDGER = Path("docs/python-example-ledger.json")
STANDALONE_MARKER = "<!-- standalone-python-example -->"
CLASSIFICATIONS = frozenset(
    {
        "standalone",
        "context-fragment/external-input",
        "context-fragment/prior-state",
        "context-fragment/illustrative-signature",
    }
)
CANONICAL_STACK_TABLE = """\
| | 저장소 | 역할 |
|---|---|---|
| 📦 | [`python-hwpx`](https://github.com/airmang/python-hwpx) | HWPX 문서를 읽고·고치고·만드는 순수 파이썬 엔진 |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | 저작·양식 채움 워크플로, `hwpx` CLI, 선택형 MCP 서버 |
| 🎯 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | 에이전트가 알맞은 도구를 고르도록 돕는 플러그인/스킬 번들 |\
"""


def _python_fences() -> list[tuple[str, int, str]]:
    fences: list[tuple[str, int, str]] = []
    for relative in CURRENT_CORE_MANUALS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for ordinal, match in enumerate(PYTHON_FENCE.finditer(text), 1):
            fences.append((relative.as_posix(), ordinal, match.group(1)))
    return fences


def _standalone_markers() -> dict[str, bool]:
    markers: dict[str, bool] = {}
    for relative in CURRENT_CORE_MANUALS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for ordinal, match in enumerate(PYTHON_FENCE.finditer(text), 1):
            prefix = text[: match.start()].rstrip()
            markers[f"{relative.as_posix()}#{ordinal}"] = prefix.endswith(
                STANDALONE_MARKER
            )
    return markers


def _fence_digest(fences: list[tuple[str, int, str]]) -> str:
    payload = json.dumps(
        fences,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ledger() -> dict[str, object]:
    return json.loads((ROOT / LEDGER).read_text(encoding="utf-8"))


def _ledger_classifications() -> dict[str, str]:
    classifications = _ledger()["classifications"]
    assert isinstance(classifications, dict)
    return {
        example_id: classification
        for classification, record in classifications.items()
        for example_id in record["ids"]
    }


def _import_roots(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.partition(".")[0] for alias in node.names}
    if node.level:
        return {"<relative>"}
    assert node.module is not None
    return {node.module.partition(".")[0]}


def _external_names(code: str, example_id: str) -> list[str]:
    table = symtable.symtable(code, example_id, "exec")
    return sorted(
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_referenced()
        and not (
            symbol.is_assigned()
            or symbol.is_imported()
            or symbol.is_namespace()
            or symbol.is_parameter()
        )
        and symbol.get_name() not in dir(builtins)
    )


def _dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _in_memory_source_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or _dotted_name(value.func) not in {
            "BytesIO",
            "io.BytesIO",
        }:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _uses_external_input(tree: ast.Module) -> bool:
    in_memory_sources = _in_memory_source_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name in {"TextExtractor", "ObjectFinder", "HwpxPackage.open", "open"}:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "read_bytes",
            "read_text",
        }:
            return True
        if name != "HwpxDocument.open":
            continue
        source = node.args[0] if node.args else None
        if isinstance(source, ast.Name) and source.id in in_memory_sources:
            continue
        if isinstance(source, ast.Call) and _dotted_name(source.func) in {
            "BytesIO",
            "io.BytesIO",
        }:
            continue
        return True
    return False


def _is_illustrative_signature(tree: ast.Module) -> bool:
    if not tree.body:
        return False
    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        if len(statement.body) != 1:
            return False
        body = statement.body[0]
        if not (
            isinstance(body, ast.Expr)
            and isinstance(body.value, ast.Constant)
            and body.value.value is Ellipsis
        ):
            return False
    return True


def _mechanical_classification(code: str, example_id: str) -> str:
    tree = ast.parse(code, filename=example_id)
    if _external_names(code, example_id):
        return "context-fragment/prior-state"
    if _is_illustrative_signature(tree):
        return "context-fragment/illustrative-signature"
    if _uses_external_input(tree):
        return "context-fragment/external-input"
    return "standalone"


def _parsed_fences() -> list[tuple[str, int, ast.Module]]:
    parsed: list[tuple[str, int, ast.Module]] = []
    broken: list[str] = []
    for document, ordinal, code in _python_fences():
        try:
            tree = ast.parse(code, filename=f"{document}#python-{ordinal}")
        except SyntaxError as exc:
            broken.append(f"{document} fence {ordinal}: {exc.msg}")
            continue
        parsed.append((document, ordinal, tree))
    assert not broken, "current-manual Python fences do not parse:\n" + "\n".join(
        broken
    )
    return parsed


def test_current_core_manual_python_fence_census_is_frozen() -> None:
    fences = _python_fences()

    assert len(fences) == EXPECTED_FENCE_COUNT
    assert _fence_digest(fences) == EXPECTED_FENCE_SHA256
    assert {
        Path(document) for document, _ordinal, _code in fences
    } == set(CURRENT_CORE_MANUALS)


def test_current_core_manual_ledger_is_complete_and_mechanically_honest() -> None:
    fences = _python_fences()
    ledger = _ledger()
    classifications = ledger["classifications"]
    assert isinstance(classifications, dict)

    assert ledger["schemaVersion"] == "python-hwpx.documentation-examples/v1"
    assert ledger["manuals"] == [path.as_posix() for path in CURRENT_CORE_MANUALS]
    assert ledger["fenceCount"] == EXPECTED_FENCE_COUNT
    assert ledger["sourceSha256"] == EXPECTED_FENCE_SHA256
    assert ledger["manualSha256"] == {
        relative.as_posix(): hashlib.sha256(
            (ROOT / relative).read_bytes()
        ).hexdigest()
        for relative in CURRENT_CORE_MANUALS
    }
    assert set(classifications) == CLASSIFICATIONS

    example_ids = [
        f"{document}#{ordinal}" for document, ordinal, _code in fences
    ]
    classified = _ledger_classifications()
    assert len(classified) == EXPECTED_FENCE_COUNT
    assert list(classified) == [
        example_id
        for classification in classifications.values()
        for example_id in classification["ids"]
    ]
    assert set(classified) == set(example_ids)

    fence_by_id = {
        f"{document}#{ordinal}": code
        for document, ordinal, code in fences
    }
    assert {
        example_id: _mechanical_classification(code, example_id)
        for example_id, code in fence_by_id.items()
    } == classified

    for classification, record in classifications.items():
        if classification == "standalone":
            assert record["requiredContext"] == []
        else:
            assert record["requiredContext"]
    prior = classifications["context-fragment/prior-state"]
    assert set(prior["requiredSymbols"]) == set(prior["ids"])
    assert {
        example_id: _external_names(fence_by_id[example_id], example_id)
        for example_id in prior["ids"]
    } == prior["requiredSymbols"]

    markers = _standalone_markers()
    assert {
        example_id for example_id, marked in markers.items() if marked
    } == {
        example_id
        for example_id, classification in classified.items()
        if classification == "standalone"
    }


def test_current_manuals_explain_that_unmarked_blocks_are_context_fragments() -> None:
    for relative in CURRENT_CORE_MANUALS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "Python 블록 판정" in text or "Python-block status" in text or (
            "Every Python block" in text
            and "execution ledger" in text
        )
        assert "python-example-ledger.json" in text


def test_current_core_manual_imports_are_core_only() -> None:
    forbidden: list[str] = []
    for document, ordinal, tree in _parsed_fences():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            unexpected = sorted(_import_roots(node) - ALLOWED_IMPORT_ROOTS)
            if unexpected:
                forbidden.append(
                    f"{document} fence {ordinal}: {', '.join(unexpected)}"
                )
    assert not forbidden, (
        "current core manuals import application or undeclared third-party "
        "packages:\n" + "\n".join(forbidden)
    )


def test_every_standalone_current_manual_example_executes_from_installed_wheel(
    tmp_path: Path,
) -> None:
    pytest.importorskip("build")
    dist = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(dist),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
        assert "Provides-Extra: visual\n" in metadata
        assert not [
            line
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:")
            and "extra ==" in line
            and "visual" in line
        ]

    installed = tmp_path / "installed"
    uv = shutil.which("uv")
    assert uv is not None, "uv is required for the clean installed-wheel gate"
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--target",
            str(installed),
            str(wheel),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    environment = os.environ.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
    ):
        environment.pop(name, None)
    environment["PYTHONPATH"] = str(installed)
    environment["PYTHONNOUSERSITE"] = "1"

    classifications = _ledger_classifications()
    standalone = {
        example_id
        for example_id, classification in classifications.items()
        if classification == "standalone"
    }
    executed: set[str] = set()
    for document, ordinal, code in _python_fences():
        example_id = f"{document}#{ordinal}"
        if example_id not in standalone:
            continue
        case_root = tmp_path / "cases" / hashlib.sha256(
            example_id.encode("utf-8")
        ).hexdigest()[:12]
        case_root.mkdir(parents=True)
        probe = "\n".join(
            (
                "from pathlib import Path",
                "import hwpx as _wheel_hwpx",
                f"_installed = Path({str(installed)!r}).resolve()",
                "_origin = Path(_wheel_hwpx.__file__).resolve()",
                "assert _origin.is_relative_to(_installed), (_origin, _installed)",
                f"_code = {code!r}",
                f"_example_id = {example_id!r}",
                "exec(compile(_code, _example_id, 'exec'), {'__name__': '__main__'})",
                "for _output in Path.cwd().rglob('*.hwpx'):",
                "    with _wheel_hwpx.HwpxDocument.open(_output) as _document:",
                "        assert _document.sections, (_example_id, _output)",
            )
        )
        subprocess.run(
            [sys.executable, "-c", probe],
            cwd=case_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        executed.add(example_id)
    assert executed == standalone


def test_readme_uses_the_canonical_three_stack_table() -> None:
    assert CANONICAL_STACK_TABLE in (ROOT / "README.md").read_text(encoding="utf-8")


def test_empty_visual_extra_is_compatibility_only_and_documented() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["optional-dependencies"]["visual"] == []

    required_text = {
        Path("README.md"): ("python-hwpx[visual]", "extra는 비어", "설치하지 않습니다"),
        Path("README_EN.md"): (
            "python-hwpx[visual]",
            "extra is",
            "empty",
            "installs no",
        ),
        Path("docs/quickstart.md"): (
            "python-hwpx[visual]",
            "extra는 비어",
            "설치하지 않는다",
        ),
    }
    for relative, fragments in required_text.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert all(fragment in text for fragment in fragments)
        assert "python-hwpx-automation[oracle]" in text
