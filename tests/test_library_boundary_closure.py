# SPDX-License-Identifier: Apache-2.0
"""python-hwpx가 실제로 포맷 라이브러리인지 검사한다.

5.0은 응용 모듈 50개를 지웠지만 **모듈 단위로만** 지웠다. split 판정을 받은
모듈들은 살아남았고, 그 안에서 응용 member를 빼는 일은 하지 않았다. P5의
fate 대조는 그걸 못 잡았는데, 잡도록 짜여 있지 않았기 때문이다 — split 행은
"모듈이 아직 있는가"만 보고 통과시켰고, member 문제는 다른 검사가 볼 거라고
적어두고 그 다른 검사가 실제로 보는지는 확인하지 않았다.

여기 두 게이트는 그 구멍을 정면으로 막는다. 지금은 실패해야 정상이고,
경계 마감(P7)이 끝나야 통과한다.
"""

from __future__ import annotations

import ast
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LEDGER = ROOT.parent / ".harness" / "evidence" / "049" / "p2" / "member-adjudication-after.json"

#: 응용 계층으로 판정된 fate. 이 이름들이 core에 정의돼 있으면 경계가 안 끝난 것이다.
APPLICATION_FATES = {"move-mcp", "dev-only-consumer"}

#: 한컴 GUI/COM 자동화 자산. 포맷 라이브러리가 배송할 것이 아니다.
EXECUTION_ASSET_SUFFIXES = (".ps1", ".applescript", ".vbs", ".scpt")


def _defined_names() -> dict[str, set[str]]:
    """core 소스가 실제로 정의하는 이름 (import·재내보내기 아닌 정의만)."""
    defined: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        module = (
            str(path.relative_to(SRC))
            .removesuffix(".py")
            .replace("/", ".")
            .removesuffix(".__init__")
        )
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 문법 오류는 다른 게이트가 잡는다
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.setdefault(module, set()).add(node.name)
    return defined


@pytest.mark.skipif(not LEDGER.exists(), reason="member 판정표는 harness 체크아웃에만 있다")
def test_no_application_member_survives_in_core() -> None:
    """응용으로 판정된 member가 core에 남아 있으면 안 된다.

    모듈이 살아남는 것과 그 안의 응용 member가 살아남는 것은 다른 문제다.
    121개 전부가 남아 있던 것이 이 게이트를 쓰게 된 이유다.
    """

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    defined = _defined_names()

    survivors = [
        member
        for member in ledger["members"]
        if member["proposedFate"] in APPLICATION_FATES
        and member["name"] in defined.get(member["module"], set())
    ]

    if survivors:
        by_module: dict[str, int] = {}
        for member in survivors:
            by_module[member["module"]] = by_module.get(member["module"], 0) + 1
        detail = "\n".join(
            f"  {module}: {count}개" for module, count in sorted(by_module.items())
        )
        pytest.fail(
            f"응용으로 판정된 member {len(survivors)}개가 아직 core에 정의돼 있다:\n{detail}"
        )


def test_no_hancom_execution_asset_is_in_the_source_tree() -> None:
    """한컴을 조종하는 스크립트가 core 소스에 있으면 안 된다.

    ``verify_redline``이 오라클을 스스로 찾지 않게 만든 것과, 오라클 자체를
    배송하지 않는 것은 다른 이야기다. 5.0 마이그레이션 가이드는 "core는 더 이상
    한컴 설치를 찾지 않는다"고 적었는데, 자동 해석을 안 할 뿐 PowerShell과
    AppleScript는 wheel에 그대로 실려 있었다. 좁게는 참이고 넓게는 오해다.
    """

    assets = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*")
        if path.suffix in EXECUTION_ASSET_SUFFIXES
    )
    assert not assets, "한컴 실행 자산이 core 소스에 남아 있다:\n  " + "\n  ".join(assets)


@pytest.mark.skipif(
    not list((ROOT / "dist").glob("*.whl")), reason="빌드된 wheel이 있을 때만 검사"
)
def test_no_hancom_execution_asset_ships_in_the_wheel() -> None:
    """소스에 없어도 wheel에 실리면 사용자에게는 실린 것이다."""

    wheel = sorted((ROOT / "dist").glob("*.whl"))[-1]
    shipped = [
        name
        for name in zipfile.ZipFile(wheel).namelist()
        if name.endswith(EXECUTION_ASSET_SUFFIXES)
    ]
    assert not shipped, f"{wheel.name}이 한컴 실행 자산을 배송한다:\n  " + "\n  ".join(shipped)
