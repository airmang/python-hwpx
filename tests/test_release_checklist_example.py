# SPDX-License-Identifier: Apache-2.0
"""`examples/build_release_checklist.py`가 6.x 이름만으로 끝까지 도는지 본다."""

from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path

from hwpx import HwpxDocument

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "release_checklist_example", ROOT / "examples/build_release_checklist.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_runs_without_moved_names(tmp_path: Path) -> None:
    example = _load()
    output = tmp_path / "ReleaseChecklist.hwpx"
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert example.main(output) == output

    with HwpxDocument.open(output) as document:
        texts = [paragraph.text for paragraph in document.paragraphs]
        memos = document.notes.memos
        assert "DONE: 통합 테스트 결과 정리" in texts
        assert "문서 배포 전 QA 서명을 수집하세요." in texts
        assert len(memos) == 2
