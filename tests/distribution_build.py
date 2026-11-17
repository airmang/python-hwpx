# SPDX-License-Identifier: Apache-2.0
"""Build this checkout's wheel or sdist one at a time.

``python -m build`` writes ``build/`` and ``src/*.egg-info`` inside the checkout. Under ``pytest -n 2`` two tests
that build at once share those folders, and one build can remove what the other is still writing
(``test_no_hancom_execution_asset_ships_in_the_wheel`` clears ``build/`` before it builds), so the other fails
with ``CalledProcessError``. A lock file in the temp folder, named after the checkout, keeps the builds of
one checkout in turn (outside the checkout, so no test that looks at the working tree ever sees it).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
_LOCK = Path(tempfile.gettempdir()) / f"hwpx-build-{hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]}.lock"
_STALE_SECONDS = 1800  # a build that died without letting go


@contextmanager
def _one_build_at_a_time(timeout: float = 1800.0) -> Iterator[None]:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - _LOCK.stat().st_mtime > _STALE_SECONDS:
                    _LOCK.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"another distribution build holds {_LOCK}") from None
            time.sleep(0.5)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        try:
            _LOCK.unlink()
        except FileNotFoundError:
            pass


def build(outdir: Path, *kinds: str, clear_build_dir: bool = False, **run: object) -> subprocess.CompletedProcess:
    """``python -m build <kinds> --outdir outdir`` in this checkout, never at the same time as another."""
    with _one_build_at_a_time():
        if clear_build_dir:
            import shutil

            shutil.rmtree(ROOT / "build", ignore_errors=True)
        return subprocess.run(
            [sys.executable, "-m", "build", *kinds, "--outdir", str(outdir)], cwd=ROOT, check=True, **run
        )
