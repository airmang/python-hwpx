#!/usr/bin/env python3
"""Fail when public repository hygiene regresses."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import NamedTuple

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
DISTRIBUTION_SUFFIXES = (".whl", ".tar.gz")
REMOVED_PATH_FIXTURE = (
    ROOT / "docs" / "architecture" / "module-ownership-removed-5.0.json"
)
REMOVED_PATH_COUNT = 77
REMOVED_PATH_SHA256 = (
    "4b8b4da35b3cf44503eb0dba05e335de1894ca5dd0b2fb668692a69e21ae6172"
)


class _PublicationFile(NamedTuple):
    path: str
    data: bytes
    origin: str

    @property
    def display(self) -> str:
        if self.origin == "index+worktree":
            return self.path
        return f"{self.path} [{self.origin}]"


def _git_paths(*args: str, root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", *args, "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def _git_index_entries(root: Path = ROOT) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    entries: list[tuple[str, str]] = []
    unmerged: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, raw_path = raw.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if stage != "0":
            unmerged.append(path)
            continue
        if mode == "160000":
            # A gitlink has no repository-local file blob to inspect.
            continue
        entries.append((path, object_id))
    if unmerged:
        joined = ", ".join(sorted(set(unmerged)))
        raise ValueError(f"unmerged index entries: {joined}")
    return entries


def _git_blobs(object_ids: list[str], root: Path = ROOT) -> dict[str, bytes]:
    unique_ids = list(dict.fromkeys(object_ids))
    if not unique_ids:
        return {}
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        check=True,
        input=("".join(f"{object_id}\n" for object_id in unique_ids)).encode(
            "ascii"
        ),
        capture_output=True,
    )
    output = result.stdout
    offset = 0
    blobs: dict[str, bytes] = {}
    for expected_id in unique_ids:
        header_end = output.index(b"\n", offset)
        object_id, object_type, raw_size = output[offset:header_end].decode(
            "ascii"
        ).split()
        if object_id != expected_id or object_type != "blob":
            raise ValueError(
                f"index object is not a blob: {expected_id} ({object_type})"
            )
        size = int(raw_size)
        data_start = header_end + 1
        data_end = data_start + size
        blobs[expected_id] = output[data_start:data_end]
        if output[data_end : data_end + 1] != b"\n":
            raise ValueError(f"malformed git cat-file output: {expected_id}")
        offset = data_end + 1
    return blobs


def _publication_files(root: Path = ROOT) -> list[_PublicationFile]:
    entries = _git_index_entries(root)
    object_data = _git_blobs([object_id for _, object_id in entries], root)
    index_files = {
        path: object_data[object_id] for path, object_id in entries
    }
    worktree_paths = set(
        _git_paths(
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            root=root,
        )
    )
    # Release artifacts are intentionally ignored by git, but they are exactly
    # what this gate must inspect immediately before publication. Restrict this
    # extra disk lane to direct wheel/sdist children of dist/ so unrelated
    # ignored caches and environments never enter the scan.
    dist = root / "dist"
    if dist.is_symlink():
        raise ValueError("dist must not be a symlink")
    if dist.is_dir():
        worktree_paths.update(
            candidate.relative_to(root).as_posix()
            for candidate in dist.iterdir()
            if (
                (candidate.is_file() or candidate.is_symlink())
                and candidate.name.endswith(DISTRIBUTION_SUFFIXES)
            )
        )
    worktree_files: dict[str, bytes] = {}
    for path in worktree_paths:
        candidate = root / path
        if candidate.is_symlink():
            worktree_files[path] = os.readlink(candidate).encode("utf-8")
        elif candidate.is_file():
            worktree_files[path] = candidate.read_bytes()

    files: list[_PublicationFile] = []
    for path in sorted(index_files.keys() | worktree_files.keys()):
        index_data = index_files.get(path)
        worktree_data = worktree_files.get(path)
        if index_data is not None and index_data == worktree_data:
            files.append(_PublicationFile(path, index_data, "index+worktree"))
            continue
        if index_data is not None:
            files.append(_PublicationFile(path, index_data, "index"))
        if worktree_data is not None:
            files.append(_PublicationFile(path, worktree_data, "worktree"))
    return files


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


def _text_data(data: bytes) -> bytes | None:
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


def _distribution_artifact(file: _PublicationFile) -> Path:
    """Return a display-only path that preserves the snapshot origin."""
    return ROOT / file.display


def _distribution_failures(
    files: list[_PublicationFile],
    kind: str,
) -> list[str]:
    failures: list[str] = []
    removed_paths = (
        _removed_source_paths()
        if kind == "core"
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
    for file in files:
        artifact_path = Path(file.path)
        if artifact_path.parent != Path("dist"):
            continue
        artifact = _distribution_artifact(file)
        if file.path.endswith(".whl"):
            with zipfile.ZipFile(io.BytesIO(file.data)) as archive:
                names = archive.namelist()
                failures.extend(
                    _removed_artifact_member_failures(
                        artifact,
                        names,
                        removed_paths,
                    )
                )
                for name in names:
                    if name.startswith(rejected) or any(
                        f"/{part}" in f"/{name}" for part in rejected
                    ):
                        failures.append(
                            f"{artifact.relative_to(ROOT)} contains {name}"
                        )
                for name in names:
                    if not name.endswith(".dist-info/METADATA"):
                        continue
                    requirements = [
                        line.casefold()
                        for line in archive.read(name)
                        .decode("utf-8", "replace")
                        .splitlines()
                        if line.startswith("Requires-Dist:")
                    ]
                    if any(
                        line.startswith(
                            "requires-dist: modelcontextprotocol"
                        )
                        for line in requirements
                    ):
                        failures.append(
                            f"{artifact.relative_to(ROOT)} declares "
                            "modelcontextprotocol"
                        )
                for name in names:
                    failures.extend(
                        _artifact_text_failure(
                            artifact,
                            name,
                            archive.read(name),
                        )
                    )
            continue
        if not file.path.endswith(".tar.gz"):
            continue
        with tarfile.open(fileobj=io.BytesIO(file.data), mode="r:gz") as archive:
            failures.extend(
                _removed_artifact_member_failures(
                    artifact,
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
                    _artifact_text_failure(
                        artifact,
                        member.name,
                        extracted.read(),
                    )
                )
    return failures


def _internal_qa_runtime_failures(
    files: list[_PublicationFile],
    kind: str,
) -> list[str]:
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
    for file in files:
        if not file.path.startswith("src/hwpx/") or not file.path.endswith(
            ".py"
        ):
            continue
        data = _text_data(file.data)
        if data is None:
            continue
        for label, marker in markers:
            if marker in data:
                failures.append(
                    f"internal QA runtime marker ({label}): {file.display}"
                )
    return failures


def _action_pin_failures(files: list[_PublicationFile]) -> list[str]:
    failures: list[str] = []
    action_ref = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
    for file in files:
        if not file.path.startswith(
            ".github/workflows/"
        ) or not file.path.endswith((".yml", ".yaml")):
            continue
        text = file.data.decode("utf-8", "replace")
        for action, ref in action_ref.findall(text):
            if action.startswith(("./", "docker://")):
                continue
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                failures.append(
                    f"mutable GitHub Action ref: {file.display}: {action}@{ref}"
                )
    return failures


def _hwpx_member_failures(
    files: list[_PublicationFile],
    workstation_path: re.Pattern[bytes],
    private_markers: list[bytes],
) -> list[str]:
    failures: list[str] = []
    for file in files:
        if not file.path.casefold().endswith(".hwpx"):
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(file.data)) as archive:
                for member in archive.namelist():
                    data = archive.read(member)
                    if workstation_path.search(data):
                        failures.append(
                            f"workstation-shaped path: {file.display}!{member}"
                        )
                    if any(marker in data for marker in private_markers):
                        failures.append(
                            f"private-origin marker: {file.display}!{member}"
                        )
        except zipfile.BadZipFile:
            # Some corruption fixtures are intentionally invalid packages.
            continue
    return failures


def _source_text_failures(
    files: list[_PublicationFile],
    workstation_path: re.Pattern[bytes],
    private_markers: list[bytes],
) -> list[str]:
    failures: list[str] = []
    for file in files:
        data = _text_data(file.data)
        if data is None:
            continue
        if workstation_path.search(data):
            failures.append(f"workstation-shaped path: {file.display}")
        if any(marker in data for marker in private_markers):
            failures.append(f"private-origin marker: {file.display}")
    return failures


def main() -> int:
    kind = _project_kind()
    files = _publication_files()
    publication_paths = sorted({file.path for file in files})
    failures = [
        f"forbidden tracked path: {path}"
        for path in publication_paths
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

    failures.extend(
        _source_text_failures(files, WORKSTATION_PATH, private_markers)
    )
    failures.extend(_hwpx_member_failures(files, WORKSTATION_PATH, private_markers))
    failures.extend(_action_pin_failures(files))
    failures.extend(_internal_qa_runtime_failures(files, kind))
    failures.extend(_distribution_failures(files, kind))
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print(
        f"[OK] public hygiene: {kind}; "
        f"{len(publication_paths)} paths / {len(files)} index-worktree views"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
