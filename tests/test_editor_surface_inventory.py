# SPDX-License-Identifier: Apache-2.0
"""편집기 표면 인벤토리(기능 축 측정기, cycle 6.8 train 29) 생성기 계약
테스트. ``tests/test_coverage_ledger.py``의 (a)/(b) 축과 같은 패턴 --
커밋된 문서의 자동 생성 구간이 재생성본과 일치하는지(``--check`` 그린)와
드리프트를 실제로 감지하는지.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "editor_surface_inventory.py"
INVENTORY = ROOT / "docs" / "editor-surface-inventory.md"


def _module():
    spec = importlib.util.spec_from_file_location("editor_surface_inventory", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_check_is_green() -> None:
    """커밋된 문서의 AUTO 구간이 재생성본과 일치한다 -- CI 게이트 본체."""

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "in sync" in proc.stdout


def test_check_fails_closed_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--check가 실제로 드리프트를 감지하는지 -- 위 그린 테스트의 대조군.

    커밋된 ``docs/editor-surface-inventory.md``는 절대 건드리지 않는다 --
    이 레포는 다른 에이전트와 공유하는 워크트리다(``test_coverage_ledger.py``
    의 같은 주석이 실제로 겪은 경합을 기록한다). ``INVENTORY_PATH``만
    tmp_path로 monkeypatch하고 ``main()``을 프로세스 안에서 직접 불러
    비교 대상만 격리한다 -- 나머지 입력(capabilities.py·support-matrix.md·
    coverage-ledger.json)은 실제 레포를 그대로 읽으므로 진짜 코드 경로를
    검증한다.
    """

    module = _module()
    auto_rows = module.generate_auto_rows()
    summary_line = module._summary_line()
    correct_block = f"{module.AUTO_BEGIN}\n\n{summary_line}\n{auto_rows}\n{module.AUTO_END}"

    fake_inventory = tmp_path / "editor-surface-inventory.md"
    stale_block = correct_block.replace("Render-verified", "STALE-Render-verified", 1)
    fake_inventory.write_text(
        f"# 편집기 표면 인벤토리 (테스트용)\n\n{stale_block}\n\n## 하단 섹션\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "INVENTORY_PATH", fake_inventory)
    monkeypatch.setattr(sys, "argv", ["editor_surface_inventory.py", "--check"])

    assert module.main() == 1


def test_regeneration_preserves_hand_authored_sections_outside_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """마커 밖 손 유지보수 섹션은 재생성 후에도 그대로 남는다."""

    module = _module()
    fake_inventory = tmp_path / "editor-surface-inventory.md"
    fake_inventory.write_text(
        f"# 헤더\n\n손으로 쓴 서문.\n\n{module.AUTO_BEGIN}\nSTALE\n{module.AUTO_END}\n\n"
        "## 손으로 쓴 하단 섹션\n표시가 살아남아야 한다.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "INVENTORY_PATH", fake_inventory)
    monkeypatch.setattr(sys, "argv", ["editor_surface_inventory.py"])

    assert module.main() == 0
    updated = fake_inventory.read_text(encoding="utf-8")
    assert "손으로 쓴 서문." in updated
    assert "## 손으로 쓴 하단 섹션" in updated
    assert "표시가 살아남아야 한다." in updated
    assert "STALE" not in updated


def test_every_registered_capability_area_has_a_category() -> None:
    """CATEGORY_MAP은 자동 소스가 없다(모듈 독스트링) -- 새 영역이 등록되면

    이 테스트가 조용히 누락되는 걸 막는다(스크립트 본문도 같은 걸 방어적으로
    검사하지만, 실행 경로를 안 타는 --check 실패 케이스에서도 놓치지 않게
    독립적으로도 확인).
    """

    from hwpx.capabilities import _CAPABILITY_AREAS

    module = _module()
    missing = [a["area"] for a in _CAPABILITY_AREAS if a["area"] not in module.CATEGORY_MAP]
    assert missing == [], f"CATEGORY_MAP is missing area(s): {missing}"


def test_inventory_has_the_auto_markers() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    assert "<!-- AUTO-GENERATED:BEGIN" in text
    assert "<!-- AUTO-GENERATED:END -->" in text
    assert text.index("<!-- AUTO-GENERATED:BEGIN") < text.index("<!-- AUTO-GENERATED:END -->")
