# SPDX-License-Identifier: Apache-2.0
"""llms.txt 표면의 내용 계약.

llms.txt는 훈련 데이터에 이 라이브러리가 없는 모델이 정확한 API를 배우는
표면이다. 설치 명령·핵심 이름·python-docx 습관 교정·문서 링크가 빠지면
모델은 다시 API를 지어낸다. 버전 문자열은 금지한다 — 릴리스마다 낡는
표면이 되면 안 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLMS = ROOT / "docs" / "_extra" / "llms.txt"
CONF = ROOT / "docs" / "conf.py"

REQUIRED_FRAGMENTS = (
    "pip install python-hwpx",
    "HwpxDocument.open",
    "HwpxDocument.new()",
    "save_to_path",
    "MutationReport",
    "PreservationDowngradeError",
    "TextExtractor",
    "ObjectFinder",
    "python-docx",
    "python-hwpx-automation",
    "https://airmang.github.io/python-hwpx/quickstart.html",
    "https://airmang.github.io/python-hwpx/support-matrix.html",
    "https://airmang.github.io/python-hwpx/migration-5.0.html",
)

LLMS_FULL_SOURCES = (
    Path("docs/_extra/llms.txt"),
    Path("docs/quickstart.md"),
    Path("docs/recipes-traversal.md"),
    Path("docs/mutation-semantics.md"),
    Path("docs/support-matrix.md"),
)


def test_llms_txt_contract() -> None:
    text = LLMS.read_text(encoding="utf-8")
    assert text.startswith("# python-hwpx\n")
    for fragment in REQUIRED_FRAGMENTS:
        assert fragment in text, f"llms.txt is missing: {fragment}"
    # 잘못된 습관을 교정하는 문장이 있어야 한다.
    assert "no" in text and "document.save()" in text
    # 릴리스 버전을 박지 않는다(낡은 안내 방지). x.y.z 꼴만 금지한다 —
    # "Python 3.10" 같은 두 자리 표기는 허용.
    assert re.search(r"\b\d+\.\d+\.\d+\b", text) is None


def test_llms_full_sources_exist_and_are_wired() -> None:
    conf = CONF.read_text(encoding="utf-8")
    assert 'html_extra_path = ["_extra"]' in conf
    assert "llms-full.txt" in conf
    for relative in LLMS_FULL_SOURCES:
        assert (ROOT / relative).is_file(), f"llms-full source missing: {relative}"
        assert relative.name in conf, f"conf.py hook does not list {relative.name}"
