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
import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LEDGER = ROOT / "tests" / "data" / "application_owned_members.json"

#: 한컴 GUI/COM 자동화 자산. 포맷 라이브러리가 배송할 것이 아니다.
EXECUTION_ASSET_SUFFIXES = (".ps1", ".applescript", ".vbs", ".scpt")
EXPECTED_APPLICATION_MODULES = (
    "hwpx.form_fit.seal",
    "hwpx.form_fit.wordbox",
    "hwpx.visual",
    "hwpx.visual.block_splits",
    "hwpx.visual.detectors",
    "hwpx.visual.diff",
    "hwpx.visual.fixture_corpus",
    "hwpx.visual.hancom_worker",
    "hwpx.visual.oracle",
    "hwpx.visual.page_qa",
    "hwpx.visual.qa_contracts",
    "hwpx.visual.qa_metrics",
)
EXPECTED_APPLICATION_MEMBER_COUNT = 119
EXPECTED_APPLICATION_MEMBER_SHA256 = (
    "ec999a987be9eea0f9f97ff7dbeed245ace00969c830b633a5eda64da961fb72"
)


def _canonical_application_members(ledger: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{row['module']}:{member}"
            for row in ledger["modules"]
            for member in row["members"]
        )
    )


def _assert_complete_application_member_ledger(ledger: dict[str, Any]) -> None:
    assert ledger["schemaVersion"] == "python-hwpx.application-owned-members/v1"
    modules = tuple(row["module"] for row in ledger["modules"])
    assert modules == EXPECTED_APPLICATION_MODULES

    canonical_members = _canonical_application_members(ledger)
    assert len(canonical_members) == EXPECTED_APPLICATION_MEMBER_COUNT
    assert len(set(canonical_members)) == EXPECTED_APPLICATION_MEMBER_COUNT
    digest = hashlib.sha256(
        ("\n".join(canonical_members) + "\n").encode("utf-8")
    ).hexdigest()
    assert digest == EXPECTED_APPLICATION_MEMBER_SHA256

    assert ledger["canonicalization"] == {
        "format": "sorted '<module>:<member>' lines encoded as UTF-8 with a final LF",
        "moduleCount": len(EXPECTED_APPLICATION_MODULES),
        "memberCount": EXPECTED_APPLICATION_MEMBER_COUNT,
        "moduleList": list(EXPECTED_APPLICATION_MODULES),
        "memberListSha256": EXPECTED_APPLICATION_MEMBER_SHA256,
    }


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


def test_no_application_member_survives_in_core() -> None:
    """응용으로 판정된 member가 core에 남아 있으면 안 된다.

    모듈이 살아남는 것과 그 안의 응용 member가 살아남는 것은 다른 문제다.
    판정 대상 member 전부가 남아 있던 것이 이 게이트를 쓰게 된 이유다.
    """

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    _assert_complete_application_member_ledger(ledger)
    defined = _defined_names()

    survivors = [
        {"module": row["module"], "name": member}
        for row in ledger["modules"]
        for member in row["members"]
        if member in defined.get(row["module"], set())
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


def test_reduced_application_member_fixture_fails_even_if_metadata_is_rewritten() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    reduced = copy.deepcopy(ledger)
    reduced["modules"][0]["members"].pop()
    canonical_members = _canonical_application_members(reduced)
    reduced["canonicalization"]["memberCount"] = len(canonical_members)
    reduced["canonicalization"]["memberListSha256"] = hashlib.sha256(
        ("\n".join(canonical_members) + "\n").encode("utf-8")
    ).hexdigest()

    with pytest.raises(AssertionError):
        _assert_complete_application_member_ledger(reduced)


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


def test_no_hancom_execution_asset_ships_in_the_wheel(tmp_path: Path) -> None:
    """소스에 없어도 wheel에 실리면 사용자에게는 실린 것이다.

    예전에는 ``dist/*.whl``이 있을 때만 돌았다. 그러면 깨끗한 체크아웃에서
    게이트를 돌릴 때 조용히 건너뛰고, 배송물을 지키는 검사가 배송물이 없다는
    이유로 아무것도 지키지 않는다. 없으면 만든다.
    """
    pytest.importorskip("build")

    existing = sorted((ROOT / "dist").glob("*.whl"))
    if existing:
        wheel = existing[-1]
    else:
        import shutil
        import subprocess
        import sys

        shutil.rmtree(ROOT / "build", ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        wheel = sorted(tmp_path.glob("*.whl"))[-1]
    shipped = [
        name
        for name in zipfile.ZipFile(wheel).namelist()
        if name.endswith(EXECUTION_ASSET_SUFFIXES)
    ]
    assert not shipped, f"{wheel.name}이 한컴 실행 자산을 배송한다:\n  " + "\n  ".join(shipped)
