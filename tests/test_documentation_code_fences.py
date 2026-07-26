# SPDX-License-Identifier: Apache-2.0
"""Keep current core manuals executable against the shipped core wheel."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
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
EXPECTED_FENCE_COUNT = 109
EXPECTED_FENCE_SHA256 = (
    "0bb23c94abb0daadcc01a53d5b43986b5a2862e70bc51c5e8cc4c4fb2a78458c"
)
ALLOWED_IMPORT_ROOTS = frozenset(sys.stdlib_module_names) | {"hwpx"}


def _python_fences() -> list[tuple[str, int, str]]:
    fences: list[tuple[str, int, str]] = []
    for relative in CURRENT_CORE_MANUALS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for ordinal, match in enumerate(PYTHON_FENCE.finditer(text), 1):
            fences.append((relative.as_posix(), ordinal, match.group(1)))
    return fences


def _fence_digest(fences: list[tuple[str, int, str]]) -> str:
    payload = json.dumps(
        fences,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _import_roots(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.partition(".")[0] for alias in node.names}
    if node.level:
        return {"<relative>"}
    assert node.module is not None
    return {node.module.partition(".")[0]}


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


def test_every_current_core_manual_import_executes_from_clean_wheel(
    tmp_path: Path,
) -> None:
    pytest.importorskip("build")
    parsed = _parsed_fences()
    imports: list[tuple[str, str]] = []
    forbidden: list[str] = []
    for document, ordinal, tree in parsed:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            roots = _import_roots(node)
            unexpected = sorted(roots - ALLOWED_IMPORT_ROOTS)
            if unexpected:
                forbidden.append(
                    f"{document} fence {ordinal}: {', '.join(unexpected)}"
                )
            imports.append((f"{document} fence {ordinal}", ast.unparse(node)))
    assert not forbidden, (
        "current core manuals import application or undeclared third-party "
        "packages:\n" + "\n".join(forbidden)
    )

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
    wheel_root = tmp_path / "wheel"
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
        archive.extractall(wheel_root)

    probe = "\n".join(
        (
            "from pathlib import Path",
            "import hwpx as _wheel_hwpx",
            f"_wheel_root = Path({str(wheel_root)!r}).resolve()",
            "_origin = Path(_wheel_hwpx.__file__).resolve()",
            "assert _origin.is_relative_to(_wheel_root), (_origin, _wheel_root)",
            f"_imports = {imports!r}",
            "for _location, _statement in _imports:",
            "    try:",
            "        exec(_statement, {})",
            "    except Exception as _exc:",
            "        raise AssertionError(f'{_location}: {_statement}: {_exc}') from _exc",
        )
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
    environment["PYTHONPATH"] = str(wheel_root)
    environment["PYTHONNOUSERSITE"] = "1"
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


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
