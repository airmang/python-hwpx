#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""docs/의 계약 문서를 패키지 동봉본(src/hwpx/data/contract_docs/)으로 동기화.

`hwpx.capabilities.contract_document()`와 MCP 리소스가 서빙하는 것은 **동봉본**
이다. docs/가 진실 원천이고, 이 스크립트가 사본을 만들며,
tests/test_contract_docs_sync.py가 바이트 동일을 게이트한다(스킬 번들 싱크와
같은 패턴 — 고치면 재싱크, 안 하면 RED).

    python scripts/sync_contract_docs.py          # 동기화
    python scripts/sync_contract_docs.py --check  # 드리프트 검사만(비제로 exit)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
DEST = REPO / "src" / "hwpx" / "data" / "contract_docs"

#: 동봉 이름 → docs/ 원본. hwpx.capabilities._CONTRACT_DOCS와 이름이 같아야
#: 하며 테스트가 대조한다.
CONTRACT_DOCS: dict[str, str] = {
    "support-matrix.md": "support-matrix.md",
    "recipes-traversal.md": "recipes-traversal.md",
    "mutation-semantics.md": "mutation-semantics.md",
    "known-traps.md": "known-traps.md",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="드리프트 검사만")
    args = parser.parse_args()

    drift: list[str] = []
    DEST.mkdir(parents=True, exist_ok=True)
    for dest_name, src_name in sorted(CONTRACT_DOCS.items()):
        src = DOCS / src_name
        dest = DEST / dest_name
        if not src.is_file():
            print(f"MISSING SOURCE: {src}", file=sys.stderr)
            return 2
        want = src.read_bytes()
        have = dest.read_bytes() if dest.is_file() else None
        if have == want:
            continue
        if args.check:
            drift.append(dest_name)
        else:
            dest.write_bytes(want)
            print(f"synced: {dest.relative_to(REPO)}")

    if args.check and drift:
        print(
            "contract docs drift (run scripts/sync_contract_docs.py): "
            + ", ".join(drift),
            file=sys.stderr,
        )
        return 1
    if args.check:
        print("contract docs in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
