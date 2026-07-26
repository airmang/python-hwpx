#!/usr/bin/env python3
"""Fail when public repository hygiene regresses."""

from __future__ import annotations

import io
import hashlib
import json
import os
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERNAL_WORK_CODE = re.compile(
    rb"(?<![A-Za-z0-9])(?:S-[0-9]{3}(?![0-9])|STG-[A-Za-z0-9][A-Za-z0-9_-]*)"
)
WORKSTATION_PATH = re.compile(
    ("/" + "Users" + r"/[^/\s]+/").encode()
    + b"|"
    + ("/" + "home" + r"/[^/\s]+/").encode()
    + b"|[A-Za-z]:\\\\[Uu]sers\\\\"
)
TEXT_ARTIFACT_SUFFIXES = (
    ".applescript",
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".xml",
    ".xsd",
    ".yaml",
    ".yml",
)
REMOVED_PATH_FIXTURE = (
    ROOT / "docs" / "architecture" / "module-ownership-removed-5.0.json"
)
REMOVED_PATH_COUNT = 77
REMOVED_PATH_SHA256 = (
    "4b8b4da35b3cf44503eb0dba05e335de1894ca5dd0b2fb668692a69e21ae6172"
)


def _git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args, "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def _project_kind() -> str:
    if (ROOT / "packaging" / "hosts.json").is_file():
        return "plugin"
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    automation_names = (
        'name = "python-hwpx-automation"',
        'name = "hwpx-mcp-server"',
    )
    return "mcp" if any(name in metadata for name in automation_names) else "core"


def _forbidden_path(path: str, kind: str) -> bool:
    common_prefixes = (".harness/", ".omx/",)
    if path.startswith(common_prefixes):
        return True
    if kind == "core":
        return path in {
            "scripts/conformance_corpus_build.py",
            "src/hwpx/practice.py",
        } or path.startswith(
            (
                "shared/hwpx/",
                "docs/superpowers/",
                "tests/evidence/",
                "examples/out/",
                "src/hwpx/practice/",
            )
        ) or bool(re.fullmatch(r"tests/test_practice_.*\.py", path))
    if kind == "mcp":
        return (
            path.startswith("docs/superpowers/")
            or bool(re.fullmatch(r"tests/(?:.*report.*|.*evidence.*)\.md", path))
        )
    generated_s070 = {
        "adjudication.json",
        "final-manifest.json",
        "private-routing.json",
        "result-manifest.json",
    }
    if path.startswith(("docs/", "tests/evidence/", "examples/out/")):
        return True
    if "/examples/s070_fixture_benchmark/" in path and path.startswith("plugins/"):
        return True
    prefix = "examples/s070_fixture_benchmark/"
    if path.startswith(prefix):
        tail = path.removeprefix(prefix)
        return tail.startswith(("blind/", "public/")) or tail in generated_s070
    return False


def _text_bytes(path: Path) -> bytes | None:
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data


def _artifact_text_failure(
    artifact: Path,
    member: str,
    data: bytes,
) -> list[str]:
    if member.casefold().endswith(".hwpx"):
        failures: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                for nested_member in package.namelist():
                    failures.extend(
                        _artifact_text_failure(
                            artifact,
                            f"{member}!{nested_member}",
                            package.read(nested_member),
                        )
                    )
        except zipfile.BadZipFile:
            pass
        return failures

    basename = Path(member).name
    if not (
        member.casefold().endswith(TEXT_ARTIFACT_SUFFIXES)
        or basename in {"METADATA", "PKG-INFO"}
    ):
        return []
    failures: list[str] = []
    try:
        artifact_name = artifact.relative_to(ROOT)
    except ValueError:
        artifact_name = artifact
    display = f"{artifact_name}!{member}"
    if INTERNAL_WORK_CODE.search(data):
        failures.append(f"internal work code in public artifact: {display}")
    if WORKSTATION_PATH.search(data):
        failures.append(f"workstation-shaped path in public artifact: {display}")
    return failures


def _removed_source_paths() -> frozenset[str]:
    fixture = json.loads(REMOVED_PATH_FIXTURE.read_text(encoding="utf-8"))
    paths = fixture.get("paths")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError("removed-path fixture paths must be a list of strings")
    digest = hashlib.sha256(
        ("\n".join(paths) + "\n").encode("utf-8")
    ).hexdigest()
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or len(paths) != REMOVED_PATH_COUNT
        or digest != REMOVED_PATH_SHA256
    ):
        raise ValueError("removed-path fixture differs from the public-hygiene pin")
    return frozenset(paths)


def _artifact_source_path(member: str) -> str | None:
    normalized = member.replace("\\", "/").lstrip("./")
    if normalized.startswith("hwpx/") and normalized.endswith(".py"):
        return f"src/{normalized}"
    marker = "src/hwpx/"
    index = normalized.find(marker)
    if index >= 0 and normalized.endswith(".py"):
        return normalized[index:]
    return None


def _removed_artifact_member_failures(
    artifact: Path,
    members: list[str],
    removed_paths: frozenset[str] | None = None,
) -> list[str]:
    removed_paths = (
        _removed_source_paths() if removed_paths is None else removed_paths
    )
    failures: list[str] = []
    try:
        artifact_name = artifact.relative_to(ROOT)
    except ValueError:
        artifact_name = artifact
    for member in members:
        source_path = _artifact_source_path(member)
        if source_path in removed_paths:
            failures.append(
                f"removed core module in public artifact: "
                f"{artifact_name}!{member} ({source_path})"
            )
    return failures


def _distribution_failures() -> list[str]:
    failures: list[str] = []
    removed_paths = (
        _removed_source_paths()
        if _project_kind() == "core"
        else frozenset()
    )
    rejected = (
        "tests/",
        "shared/hwpx/",
        "docs/superpowers/",
        "examples/out/",
        ".harness/",
        ".omx/",
        "hwpx/practice.py",
        "hwpx/practice/",
    )
    for wheel in sorted((ROOT / "dist").glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            failures.extend(
                _removed_artifact_member_failures(wheel, names, removed_paths)
            )
            for name in names:
                if name.startswith(rejected) or any(f"/{part}" in f"/{name}" for part in rejected):
                    failures.append(f"{wheel.relative_to(ROOT)} contains {name}")
            for name in names:
                if not name.endswith(".dist-info/METADATA"):
                    continue
                requirements = [
                    line.casefold()
                    for line in archive.read(name).decode("utf-8", "replace").splitlines()
                    if line.startswith("Requires-Dist:")
                ]
                if any(line.startswith("requires-dist: modelcontextprotocol") for line in requirements):
                    failures.append(f"{wheel.relative_to(ROOT)} declares modelcontextprotocol")
            for name in names:
                failures.extend(
                    _artifact_text_failure(wheel, name, archive.read(name))
                )
    for sdist in sorted((ROOT / "dist").glob("*.tar.gz")):
        with tarfile.open(sdist, "r:gz") as archive:
            failures.extend(
                _removed_artifact_member_failures(
                    sdist,
                    [member.name for member in archive.getmembers()],
                    removed_paths,
                )
            )
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                failures.extend(
                    _artifact_text_failure(sdist, member.name, extracted.read())
                )
    return failures


def _internal_qa_runtime_failures(tracked: list[str], kind: str) -> list[str]:
    if kind != "core":
        return []

    markers = (
        ("practice namespace", b"hwpx." + b"practice"),
        ("relative practice import", b"from " + b".practice"),
        ("private-corpus schema", b"hwpx." + b"private-corpus"),
        ("synthetic dossier schema", b"hwpx." + b"synthetic-dossier"),
        ("controlled mutation schema", b"hwpx." + b"controlled-mutation"),
        ("private practice domain", b"private_" + b"practice"),
        ("unavailable campaign sentinel", b"CAMPAIGN_" + b"UNAVAILABLE"),
    )
    failures: list[str] = []
    for rel in tracked:
        if not rel.startswith("src/hwpx/") or not rel.endswith(".py"):
            continue
        data = _text_bytes(ROOT / rel)
        if data is None:
            continue
        for label, marker in markers:
            if marker in data:
                failures.append(f"internal QA runtime marker ({label}): {rel}")
    return failures


def _action_pin_failures(tracked: list[str]) -> list[str]:
    failures: list[str] = []
    action_ref = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
    for rel in tracked:
        if not rel.startswith(".github/workflows/") or not rel.endswith((".yml", ".yaml")):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for action, ref in action_ref.findall(text):
            if action.startswith(("./", "docker://")):
                continue
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                failures.append(f"mutable GitHub Action ref: {rel}: {action}@{ref}")
    return failures


def _hwpx_member_failures(
    tracked: list[str],
    workstation_path: re.Pattern[bytes],
    private_markers: list[bytes],
) -> list[str]:
    failures: list[str] = []
    for rel in tracked:
        if not rel.casefold().endswith(".hwpx"):
            continue
        try:
            with zipfile.ZipFile(ROOT / rel) as archive:
                for member in archive.namelist():
                    data = archive.read(member)
                    if workstation_path.search(data):
                        failures.append(f"workstation-shaped path: {rel}!{member}")
                    if any(marker in data for marker in private_markers):
                        failures.append(f"private-origin marker: {rel}!{member}")
        except zipfile.BadZipFile:
            # Some corruption fixtures are intentionally invalid packages.
            continue
    return failures


def main() -> int:
    kind = _project_kind()
    tracked = [
        path
        for path in _git_paths("ls-files", "--cached", "--others", "--exclude-standard")
        if (ROOT / path).is_file()
    ]
    failures = [
        f"forbidden tracked path: {path}"
        for path in tracked
        if _forbidden_path(path, kind)
    ]

    tracked_ignored = _git_paths("ls-files", "-ci", "--exclude-standard")
    failures.extend(f"tracked file is ignored: {path}" for path in tracked_ignored)

    private_markers = [b">" + b"ko" + b"kyu" + b"<"]
    private_markers.extend(
        value.strip().encode("utf-8")
        for value in os.environ.get("HWPX_PRIVATE_PII_NEEDLES", "").split(",")
        if value.strip()
    )

    for rel in tracked:
        data = _text_bytes(ROOT / rel)
        if data is None:
            continue
        if WORKSTATION_PATH.search(data):
            failures.append(f"workstation-shaped path: {rel}")
        if any(marker in data for marker in private_markers):
            failures.append(f"private-origin marker: {rel}")

    failures.extend(_hwpx_member_failures(tracked, WORKSTATION_PATH, private_markers))
    failures.extend(_action_pin_failures(tracked))
    failures.extend(_internal_qa_runtime_failures(tracked, kind))
    failures.extend(_distribution_failures())
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print(f"[OK] public hygiene: {kind}; {len(tracked)} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
