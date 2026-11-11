# SPDX-License-Identifier: Apache-2.0
"""No file the package ships reaches 256 KiB.

The Claude plugin carries the released wheel unpacked, and its directory reads at most 256 KiB of one file
(hwpx-plugins ``scripts/vendor_claude_engine.py``, ``MAX_FILE_BYTES``). Two core files passed that in 6.9.0 and
6.10.0 and the plugin's engine stopped at 6.8.0 (hwpx-plugins issue 66); nothing in this repository showed it.

A file at or over the limit fails. A file over four fifths of it only warns: split it, or move its data out of
the source (as ``form_fit/_glyph_table.json.gz`` was), before it gets there. The plugin directory also reads at
most 512 files, so a split costs a file there: prefer one new module to several.
"""

from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "hwpx"
#: The most a plugin directory reads of one file.
LIMIT = 256 * 1024
#: The share of the limit past which a file is reported before it fails.
WARN_SHARE = 0.8


def size_problems(sizes: dict[str, int], limit: int = LIMIT, warn_share: float = WARN_SHARE
                  ) -> tuple[list[str], list[str]]:
    """(files at or over *limit*, files over *warn_share* of it), largest first, each as a line to show."""

    def line(name: str) -> str:
        return f"{name}: {sizes[name]:,} bytes, {sizes[name] / limit:.0%} of {limit:,}"

    largest = sorted(sizes, key=lambda name: (-sizes[name], name))
    over = [line(name) for name in largest if sizes[name] >= limit]
    near = [line(name) for name in largest if limit * warn_share < sizes[name] < limit]
    return over, near


def _check(sizes: dict[str, int], what: str) -> None:
    assert sizes, f"no files found in {what}"
    over, near = size_problems(sizes)
    if near:
        warnings.warn(
            f"{what}: {len(near)} file(s) over {WARN_SHARE:.0%} of the {LIMIT:,}-byte limit a plugin directory "
            "reads of one file; split or move data out before the limit:\n  " + "\n  ".join(near),
            stacklevel=2,
        )
    assert not over, (
        f"{what}: file(s) at or over the {LIMIT:,}-byte limit a plugin directory reads of one file "
        "(hwpx-plugins issue 66):\n  " + "\n  ".join(over)
    )


def test_no_source_file_of_the_package_reaches_the_limit() -> None:
    # As a release build ships them: text with LF line endings, whatever this checkout uses.
    sizes = {}
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        sizes[path.relative_to(PACKAGE.parent).as_posix()] = len(data if b"\0" in data else data.replace(b"\r\n", b"\n"))
    _check(sizes, "src/hwpx")


def test_no_file_of_the_built_wheel_reaches_the_limit(tmp_path: Path) -> None:
    pytest.importorskip("build")
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)], cwd=ROOT, check=True)
    with ZipFile(next(tmp_path.glob("*.whl"))) as wheel:
        sizes = {info.filename: info.file_size for info in wheel.infolist() if not info.is_dir()}
    assert "hwpx/form_fit/_glyph_table.json.gz" in sizes  # the glyph tables ship as data
    assert "hwpx/layout/_page_measure.py" in sizes
    _check(sizes, "the wheel")


def test_the_check_reports_a_file_over_the_limit_and_warns_before_it() -> None:
    sizes = {"hwpx/small.py": 10, "hwpx/near.py": 210_000, "hwpx/at.py": LIMIT, "hwpx/over.py": LIMIT + 1,
             "hwpx/edge.py": int(LIMIT * WARN_SHARE)}
    over, near = size_problems(sizes)
    assert [line.split(":")[0] for line in over] == ["hwpx/over.py", "hwpx/at.py"]
    assert [line.split(":")[0] for line in near] == ["hwpx/near.py"]
    with pytest.warns(UserWarning, match=r"hwpx/near\.py: 210,000 bytes, 80% of 262,144"):
        _check({"hwpx/near.py": 210_000}, "test")
    with pytest.warns(UserWarning), pytest.raises(AssertionError, match=r"hwpx/over\.py"):
        _check(sizes, "test")
