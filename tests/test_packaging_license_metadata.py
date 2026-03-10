from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest


LICENSE_EXPRESSION = "LicenseRef-python-hwpx-NonCommercial"


def _build_distribution(tmp_path: Path, distribution: str) -> Path:
    pytest.importorskip("build")

    project_root = Path(__file__).resolve().parents[1]
    build_args = [
        sys.executable,
        "-m",
        "build",
        f"--{distribution}",
        "--outdir",
        str(tmp_path),
    ]
    subprocess.run(build_args, cwd=project_root, check=True)

    pattern = "*.whl" if distribution == "wheel" else "*.tar.gz"
    return next(tmp_path.glob(pattern))


@pytest.mark.parametrize("distribution", ["wheel", "sdist"])
def test_built_distributions_expose_custom_license_metadata(
    tmp_path: Path, distribution: str
) -> None:
    artifact = _build_distribution(tmp_path, distribution)

    if distribution == "wheel":
        with ZipFile(artifact) as wheel_archive:
            members = set(wheel_archive.namelist())
            metadata_name = next(
                name for name in members if name.endswith(".dist-info/METADATA")
            )
            metadata = wheel_archive.read(metadata_name).decode("utf-8")

        assert f"License-Expression: {LICENSE_EXPRESSION}" in metadata
        assert "License-File: LICENSE" in metadata
        assert "Classifier: License ::" not in metadata
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in members)
        return

    with tarfile.open(artifact, "r:gz") as sdist_archive:
        members = sdist_archive.getnames()
        pkg_info_name = next(name for name in members if name.endswith("/PKG-INFO"))
        pkg_info_member = sdist_archive.extractfile(pkg_info_name)
        assert pkg_info_member is not None
        metadata = pkg_info_member.read().decode("utf-8")

    assert f"License-Expression: {LICENSE_EXPRESSION}" in metadata
    assert "License-File: LICENSE" in metadata
    assert "Classifier: License ::" not in metadata
    assert any(name.endswith("/LICENSE") for name in members)
