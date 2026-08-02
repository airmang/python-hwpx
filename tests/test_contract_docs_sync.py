# SPDX-License-Identifier: Apache-2.0
"""패키지 동봉 계약 문서 ↔ docs/ 원본 바이트 동일 게이트 (specs/059 §7).

docs/가 진실 원천, ``src/hwpx/data/contract_docs/``가 동봉 사본이다.
스킬 번들 싱크와 같은 규율: 원본을 고치면 ``scripts/sync_contract_docs.py``로
재싱크해야 하고, 안 하면 이 게이트가 RED다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hwpx.capabilities import _CONTRACT_DOCS

REPO = Path(__file__).resolve().parent.parent


def test_contract_docs_are_in_sync() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "sync_contract_docs.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_sync_script_and_capabilities_name_the_same_documents() -> None:
    import sync_contract_docs  # scripts/는 pytest pythonpath에 있다

    script_names = {name.removesuffix(".md") for name in sync_contract_docs.CONTRACT_DOCS}
    assert script_names == set(_CONTRACT_DOCS), (
        "sync 스크립트와 hwpx.capabilities가 서로 다른 문서 목록을 말합니다"
    )


def test_bundled_copies_exist() -> None:
    dest = REPO / "src" / "hwpx" / "data" / "contract_docs"
    for filename in _CONTRACT_DOCS.values():
        assert (dest / filename).is_file(), filename
