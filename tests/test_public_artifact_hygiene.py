# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI lane
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_public_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_public_hygiene", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hygiene = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hygiene)
EXPECTED_PACKAGES = {
    "hwpx",
    "hwpx._document",
    "hwpx.data",
    "hwpx.equation",
    "hwpx.form_fit",
    "hwpx.ingest",
    "hwpx.layout",
    "hwpx.opc",
    "hwpx.oxml",
    "hwpx.plan",
    "hwpx.quality",
    "hwpx.tools",
    "hwpx.tools._schemas",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _wheel_bytes(member: str, payload: bytes) -> bytes:
    artifact = io.BytesIO()
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr(member, payload)
    return artifact.getvalue()


def _sdist_bytes(member: str, payload: bytes) -> bytes:
    artifact = io.BytesIO()
    with tarfile.open(fileobj=artifact, mode="w:gz") as archive:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return artifact.getvalue()


@pytest.fixture
def hygiene_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Hygiene Test")
    _git(repo, "config", "user.email", "hygiene@example.invalid")
    tracked = repo / "tracked.md"
    tracked.write_text("safe\n", encoding="utf-8")
    deleted = repo / "deleted.md"
    deleted.write_text(
        "/" + "Users" + "/private/deleted-before-commit\n",
        encoding="utf-8",
    )
    _git(repo, "add", "tracked.md", "deleted.md")
    _git(repo, "commit", "--quiet", "-m", "baseline")
    return repo


@pytest.fixture(scope="module")
def built_distributions(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    output = tmp_path_factory.mktemp("public-artifacts")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return next(output.glob("*.whl")), next(output.glob("*.tar.gz"))


def test_public_artifacts_have_no_internal_stage_codes_or_local_paths(
    built_distributions: tuple[Path, Path],
) -> None:
    failures: list[str] = []
    for artifact in built_distributions:
        if artifact.suffix == ".whl":
            import zipfile

            with zipfile.ZipFile(artifact) as archive:
                for name in archive.namelist():
                    failures.extend(
                        hygiene._artifact_text_failure(
                            artifact,
                            name,
                            archive.read(name),
                        )
                    )
        else:
            import tarfile

            with tarfile.open(artifact, "r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    extracted = archive.extractfile(member)
                    assert extracted is not None
                    failures.extend(
                        hygiene._artifact_text_failure(
                            artifact,
                            member.name,
                            extracted.read(),
                        )
                    )
    assert not failures, "\n".join(failures)


def test_built_artifacts_contain_zero_removed_module_paths(
    built_distributions: tuple[Path, Path],
) -> None:
    failures: list[str] = []
    wheel, sdist = built_distributions
    with zipfile.ZipFile(wheel) as archive:
        failures.extend(
            hygiene._removed_artifact_member_failures(
                wheel,
                archive.namelist(),
            )
        )
    with tarfile.open(sdist, "r:gz") as archive:
        failures.extend(
            hygiene._removed_artifact_member_failures(
                sdist,
                [member.name for member in archive.getmembers()],
            )
        )

    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(
    ("member", "expected_source"),
    (
        ("hwpx/form_fit/seal.py", "src/hwpx/form_fit/seal.py"),
        (
            "python_hwpx-5.0.0/src/hwpx/tools/report_parser.py",
            "src/hwpx/tools/report_parser.py",
        ),
    ),
)
def test_removed_module_member_normalization_fails_closed(
    tmp_path: Path,
    member: str,
    expected_source: str,
) -> None:
    artifact = tmp_path / (
        "fixture.whl" if member.startswith("hwpx/") else "fixture.tar.gz"
    )

    failures = hygiene._removed_artifact_member_failures(
        artifact,
        [member],
    )

    assert failures
    assert expected_source in failures[0]


def test_synthetic_wheel_with_removed_module_is_rejected(tmp_path: Path) -> None:
    wheel = tmp_path / "python_hwpx-5.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hwpx/form_fit/seal.py", "VALUE = 1\n")

    with zipfile.ZipFile(wheel) as archive:
        failures = hygiene._removed_artifact_member_failures(
            wheel,
            archive.namelist(),
        )

    assert failures
    assert "src/hwpx/form_fit/seal.py" in failures[0]


def test_synthetic_sdist_with_removed_module_is_rejected(tmp_path: Path) -> None:
    sdist = tmp_path / "python_hwpx-5.0.0.tar.gz"
    member_name = "python_hwpx-5.0.0/src/hwpx/tools/report_parser.py"
    payload = b"VALUE = 1\n"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(sdist, "r:gz") as archive:
        failures = hygiene._removed_artifact_member_failures(
            sdist,
            [member.name for member in archive.getmembers()],
        )

    assert failures
    assert "src/hwpx/tools/report_parser.py" in failures[0]


def test_artifact_hygiene_distinguishes_stage_codes_from_public_versions() -> None:
    artifact = ROOT / "dist" / "fixture.whl"
    assert not hygiene._artifact_text_failure(
        artifact,
        "CHANGELOG.md",
        b"public versions v4.1.0, v4.4.0 and 5.0.0 remain historical truth",
    )
    assert hygiene._artifact_text_failure(
        artifact,
        "module.py",
        b"internal execution label " + b"S-" + b"108",
    )
    assert hygiene._artifact_text_failure(
        artifact,
        "module.py",
        b"/" + b"Users" + b"/example/project/private.py",
    )
    assert hygiene._artifact_text_failure(
        artifact,
        "hwpx/tools/_schemas/section.xsd",
        b"<xs:documentation>internal " + b"S-" + b"108</xs:documentation>",
    )
    assert hygiene._artifact_text_failure(
        artifact,
        "receipt.md",
        b"internal " + b"STG-" + b"deadbeef",
    )
    assert not hygiene._artifact_text_failure(artifact, "image.png", b"S-" + b"108")


def test_artifact_hygiene_scans_text_members_nested_in_hwpx() -> None:
    package_bytes = io.BytesIO()
    with zipfile.ZipFile(package_bytes, "w") as package:
        package.writestr(
            "Contents/section0.xml",
            b"<note>internal " + b"STG-" + b"deadbeef</note>",
        )

    failures = hygiene._artifact_text_failure(
        ROOT / "dist" / "fixture.whl",
        "hwpx/data/Skeleton.hwpx",
        package_bytes.getvalue(),
    )
    assert failures
    assert "Skeleton.hwpx!Contents/section0.xml" in failures[0]


def test_moved_conformance_generator_is_forbidden_from_core() -> None:
    assert hygiene._forbidden_path("scripts/conformance_corpus_build.py", "core")


def test_setuptools_uses_an_exact_package_allowlist(
    built_distributions: tuple[Path, Path],
) -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = metadata["tool"]["setuptools"]
    assert isinstance(setuptools["packages"], list)
    assert set(setuptools["packages"]) == EXPECTED_PACKAGES
    assert "find" not in setuptools

    wheel = built_distributions[0]
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        python_members = [
            name for name in archive.namelist() if name.startswith("hwpx/") and name.endswith(".py")
        ]
    shipped_packages = {
        ".".join(Path(name).parent.parts)
        for name in python_members
    }
    assert shipped_packages <= EXPECTED_PACKAGES


def test_hygiene_reads_staged_add_from_index_when_worktree_file_is_gone(
    hygiene_git_repo: Path,
) -> None:
    staged = hygiene_git_repo / "staged-only.md"
    staged.write_text(
        "/" + "Users" + "/private/index-only\n",
        encoding="utf-8",
    )
    _git(hygiene_git_repo, "add", "staged-only.md")
    staged.unlink()

    files = hygiene._publication_files(hygiene_git_repo)
    failures = hygiene._source_text_failures(
        files,
        hygiene.WORKSTATION_PATH,
        [],
    )

    assert any(
        "staged-only.md [index]" in failure for failure in failures
    )


def test_hygiene_distinguishes_staged_and_worktree_modifications(
    hygiene_git_repo: Path,
) -> None:
    tracked = hygiene_git_repo / "tracked.md"
    tracked.write_text(
        "/" + "Users" + "/private/staged-version\n",
        encoding="utf-8",
    )
    _git(hygiene_git_repo, "add", "tracked.md")
    tracked.write_text("safe worktree version\n", encoding="utf-8")

    files = hygiene._publication_files(hygiene_git_repo)
    views = {
        file.origin: file.data
        for file in files
        if file.path == "tracked.md"
    }
    failures = hygiene._source_text_failures(
        files,
        hygiene.WORKSTATION_PATH,
        [],
    )

    assert views == {
        "index": (
            "/" + "Users" + "/private/staged-version\n"
        ).encode(),
        "worktree": b"safe worktree version\n",
    }
    assert any("tracked.md [index]" in failure for failure in failures)
    assert not any("tracked.md [worktree]" in failure for failure in failures)


def test_distribution_hygiene_reads_staged_only_wheel_snapshot(
    hygiene_git_repo: Path,
) -> None:
    dist = hygiene_git_repo / "dist"
    dist.mkdir()
    wheel = dist / "index-only.whl"
    wheel.write_bytes(
        _wheel_bytes(
            "hwpx/form_fit/seal.py",
            (
                "/" + "Users" + "/private/index-artifact.py\n"
            ).encode(),
        )
    )
    _git(hygiene_git_repo, "add", "dist/index-only.whl")
    wheel.unlink()

    files = hygiene._publication_files(hygiene_git_repo)
    failures = hygiene._distribution_failures(files, "core")

    assert any(
        "removed core module in public artifact: "
        "dist/index-only.whl [index]!hwpx/form_fit/seal.py"
        in failure
        for failure in failures
    )
    assert any(
        "workstation-shaped path in public artifact: "
        "dist/index-only.whl [index]!hwpx/form_fit/seal.py"
        in failure
        for failure in failures
    )


def test_distribution_hygiene_reads_gitignored_release_artifacts(
    hygiene_git_repo: Path,
) -> None:
    gitignore = hygiene_git_repo / ".gitignore"
    gitignore.write_text("dist/\n", encoding="utf-8")
    _git(hygiene_git_repo, "add", ".gitignore")
    _git(hygiene_git_repo, "commit", "--quiet", "-m", "ignore build output")
    dist = hygiene_git_repo / "dist"
    dist.mkdir()
    wheel = dist / "ignored.whl"
    wheel.write_bytes(
        _wheel_bytes(
            "hwpx/form_fit/seal.py",
            (
                "/" + "Users" + "/private/ignored-artifact.py\n"
            ).encode(),
        )
    )
    sdist = dist / "ignored.tar.gz"
    sdist.write_bytes(
        _sdist_bytes(
            "python_hwpx-5.0.0/src/hwpx/tools/report_parser.py",
            (
                "/" + "Users" + "/private/ignored-sdist.py\n"
            ).encode(),
        )
    )

    files = hygiene._publication_files(hygiene_git_repo)
    failures = hygiene._distribution_failures(files, "core")

    assert any(
        file.path == "dist/ignored.whl" and file.origin == "worktree"
        for file in files
    )
    assert any(
        file.path == "dist/ignored.tar.gz" and file.origin == "worktree"
        for file in files
    )
    assert any(
        "removed core module in public artifact: "
        "dist/ignored.whl [worktree]!hwpx/form_fit/seal.py"
        in failure
        for failure in failures
    )
    assert any(
        "removed core module in public artifact: "
        "dist/ignored.tar.gz [worktree]!"
        "python_hwpx-5.0.0/src/hwpx/tools/report_parser.py"
        in failure
        for failure in failures
    )
    assert any(
        "workstation-shaped path in public artifact: "
        "dist/ignored.whl [worktree]!hwpx/form_fit/seal.py"
        in failure
        for failure in failures
    )
    assert any(
        "workstation-shaped path in public artifact: "
        "dist/ignored.tar.gz [worktree]!"
        "python_hwpx-5.0.0/src/hwpx/tools/report_parser.py"
        in failure
        for failure in failures
    )


def test_distribution_hygiene_rejects_a_symlinked_dist_directory(
    hygiene_git_repo: Path,
) -> None:
    outside = hygiene_git_repo.parent / "outside-dist"
    outside.mkdir()
    os.symlink(outside, hygiene_git_repo / "dist")

    with pytest.raises(ValueError, match="dist must not be a symlink"):
        hygiene._publication_files(hygiene_git_repo)


def test_distribution_hygiene_reads_differing_worktree_sdist_snapshot(
    hygiene_git_repo: Path,
) -> None:
    dist = hygiene_git_repo / "dist"
    dist.mkdir()
    sdist = dist / "different.tar.gz"
    member = "python_hwpx-5.0.0/src/hwpx/safe.py"
    sdist.write_bytes(_sdist_bytes(member, b"VALUE = 'safe'\n"))
    _git(hygiene_git_repo, "add", "dist/different.tar.gz")
    sdist.write_bytes(
        _sdist_bytes(
            member,
            (
                "/" + "Users" + "/private/worktree-artifact.py\n"
            ).encode(),
        )
    )

    files = hygiene._publication_files(hygiene_git_repo)
    views = {
        file.origin
        for file in files
        if file.path == "dist/different.tar.gz"
    }
    failures = hygiene._distribution_failures(files, "core")

    assert views == {"index", "worktree"}
    assert any(
        "dist/different.tar.gz [worktree]!" in failure
        for failure in failures
    )
    assert not any(
        "dist/different.tar.gz [index]!" in failure
        for failure in failures
    )


def test_distribution_hygiene_does_not_scan_staged_deletion(
    hygiene_git_repo: Path,
) -> None:
    dist = hygiene_git_repo / "dist"
    dist.mkdir()
    wheel = dist / "deleted.whl"
    wheel.write_bytes(
        _wheel_bytes(
            "hwpx/leak.py",
            (
                "/" + "Users" + "/private/deleted-artifact.py\n"
            ).encode(),
        )
    )
    _git(hygiene_git_repo, "add", "dist/deleted.whl")
    _git(hygiene_git_repo, "commit", "--quiet", "-m", "add artifact")
    _git(hygiene_git_repo, "rm", "--quiet", "dist/deleted.whl")

    files = hygiene._publication_files(hygiene_git_repo)
    failures = hygiene._distribution_failures(files, "core")

    assert not any(file.path == "dist/deleted.whl" for file in files)
    assert not any("dist/deleted.whl" in failure for failure in failures)


def test_hygiene_does_not_scan_a_staged_deletion(
    hygiene_git_repo: Path,
) -> None:
    _git(hygiene_git_repo, "rm", "--quiet", "deleted.md")

    files = hygiene._publication_files(hygiene_git_repo)

    assert not any(file.path == "deleted.md" for file in files)


def test_hygiene_reads_symlink_target_without_following_it(
    hygiene_git_repo: Path,
) -> None:
    target = hygiene_git_repo / "outside.txt"
    target.write_text("outside contents\n", encoding="utf-8")
    link = hygiene_git_repo / "link.txt"
    os.symlink("outside.txt", link)

    files = hygiene._publication_files(hygiene_git_repo)

    link_view = next(
        file for file in files if file.path == "link.txt"
    )
    assert link_view.data == b"outside.txt"
