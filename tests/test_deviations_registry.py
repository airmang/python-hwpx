# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "owpml-deviations.md"
PROBES_DIR = ROOT / "probes"

# 6.1 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_1_DEVIATIONS = (
    "DEV-002",
    "DEV-003",
    "DEV-004",
    "DEV-005",
    "DEV-006",
    "DEV-007",
)

CYCLE_6_1_PROBES = (
    "dev002_tabitem_maxoccurs.py",
    "dev003_drawtext_child_order.py",
    "dev004_settings_xml_no_schema.py",
    "dev005_layout_compatibility_empty.py",
    "dev006_fontface_write_conventions.py",
    "dev007_masterpage_unnamespaced_root.py",
)

# 6.2 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_2_DEVIATIONS = (
    "DEV-008",
    "DEV-009",
    "DEV-010",
)

CYCLE_6_2_PROBES = (
    "dev008_newnum_autonumformat_omitted.py",
    "dev009_memopr_id_and_spelling_conventions.py",
    "dev010_markpen_malformed_placement_and_resave_loss.py",
)


def test_registry_exists_with_required_sections():
    text = DOC.read_text(encoding="utf-8")
    assert "# OWPML 편차 레지스트리" in text
    assert "## 네임스페이스 정합 (2011/2016 ↔ 2024)" in text
    # At least one deviation or compatibility strategy entry with an evidence pointer.
    assert "증거:" in text


def test_dev_001_entry_survives_untouched():
    """기존(사이클 6.1 이전) 항목이 이번 등재로 사라지지 않았는지 확인한다."""

    text = DOC.read_text(encoding="utf-8")
    assert "DEV-001" in text
    assert "2024 네임스페이스 중심 스키마" in text


@pytest.mark.parametrize("dev_id", CYCLE_6_1_DEVIATIONS)
def test_cycle_6_1_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_1_PROBES)
def test_cycle_6_1_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_1_PROBES)
def test_cycle_6_1_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_2_DEVIATIONS)
def test_cycle_6_2_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_2_PROBES)
def test_cycle_6_2_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_2_PROBES)
def test_cycle_6_2_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
