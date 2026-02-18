from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest


@pytest.mark.parametrize("distribution", ["wheel", "sdist"])
def test_py_typed_is_included_in_built_distributions(tmp_path: Path, distribution: str) -> None:
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

    if distribution == "wheel":
        wheel_path = next(tmp_path.glob("*.whl"))
        with ZipFile(wheel_path) as wheel_archive:
            wheel_members = set(wheel_archive.namelist())
        assert "hwpx/py.typed" in wheel_members
        return

    sdist_path = next(tmp_path.glob("*.tar.gz"))
    with tarfile.open(sdist_path, "r:gz") as sdist_archive:
        sdist_members = sdist_archive.getnames()
    assert any(name.endswith("/src/hwpx/py.typed") for name in sdist_members)
