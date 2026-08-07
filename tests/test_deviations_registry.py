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

# 6.3 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_3_DEVIATIONS = (
    "DEV-011",
)

CYCLE_6_3_PROBES = (
    "dev011_parameterset_schema_absence.py",
)

# 6.4 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_4_DEVIATIONS = (
    "DEV-012",
    "DEV-013",
    "DEV-014",
    "DEV-015",
)

CYCLE_6_4_PROBES = (
    "dev012_startpt_endpt_namespace_duality.py",
    "dev013_connectline_smart_connector_relationship.py",
    "dev014_arc_three_point_no_angle_contract.py",
    "dev015_version_xml_root_and_spelling.py",
)

# 6.5 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_5_DEVIATIONS = (
    "DEV-016",
    "DEV-017",
    "DEV-018",
)

CYCLE_6_5_PROBES = (
    "dev016_container_member_offset_transmatrix_sync.py",
    "dev017_run_choice_atoms_t_nesting_convention.py",
    "dev018_switch_case_default_schema_absence.py",
)

# 6.6 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_6_DEVIATIONS = (
    "DEV-019",
    "DEV-020",
    "DEV-021",
)

CYCLE_6_6_PROBES = (
    "dev019_autospacing_switch_non_nesting.py",
    "dev020_document_options_schema_wide_real_narrow.py",
    "dev021_switch_as_inline_object_alternate.py",
)

# 6.7 사이클에서 새로 등재한 항목 — 각각 실행 가능한 프로브를 동반해야 한다.
CYCLE_6_7_DEVIATIONS = (
    "DEV-022",
    "DEV-023",
)

CYCLE_6_7_PROBES = (
    "dev022_tabpr_switch_case_default_scale_mismatch.py",
    "dev023_label_avery_layout_schema_match.py",
)

# 6.7 트레인㉗ — 별도 편차 조사(17항목)에서 이 공개 레지스트리에 아직 없던
# 항목을 이식. 조사 원문 자신의 번호(DEV-002~018)는 이 공개 레지스트리가
# 이미 다른 주제로 선점하고 있어(numbering collision) DEV-024부터 재번호.
# 조사 원문의 한 항목(hp:run 안 switch/case/default 차트/OLE 폴백)은 기존
# DEV-021과 같은 픽스처·같은 결론이라 중복 등재하지 않고 DEV-021에 상호
# 참조만 추가했다(신규 항목 아님).
CYCLE_6_7_TRAIN_27_DEVIATIONS = (
    "DEV-024",
    "DEV-025",
    "DEV-026",
    "DEV-027",
    "DEV-028",
    "DEV-029",
    "DEV-030",
    "DEV-031",
    "DEV-032",
    "DEV-033",
    "DEV-034",
    "DEV-035",
    "DEV-036",
    "DEV-037",
    "DEV-038",
    "DEV-039",
)

CYCLE_6_7_TRAIN_27_PROBES = (
    "dev024_shape_point_family_core_namespace.py",
    "dev025_fillbrush_core_namespace.py",
    "dev026_trackchageconfig_typo.py",
    "dev027_lineseg_cache_undeclared.py",
    "dev028_subscript_offset_sign_convention.py",
    "dev029_resize_geometry_over_sz.py",
    "dev030_hyperlink_charpr_scope.py",
    "dev031_toc_dirty_next_open_trigger.py",
    "dev032_toc_contentsstyles_collection_command.py",
    "dev033_header_footer_apply_undeclared.py",
    "dev034_memo_subsystem_undeclared.py",
    "dev035_bindata_manifest_undeclared.py",
    "dev036_version_xml_manifest_omission.py",
    "dev037_clickhere_command_length_prefix_format.py",
    "dev038_toc_fiexde_typo_replication.py",
    "dev039_crossref_vs_toc_recompute_asymmetry.py",
)

# 6.7 정리 트레인 — 갭 지도 v2 §D가 다음 라운드 후보로 남긴 두 항목을 확인:
# hp:switch의 4번째 부모-태그 맥락(전수 스캔, 결과=없음, 등재 대상 아님)과
# hh:typeInfo/hh:metaTag(전수 미조사분). typeInfo는 이미 정확히 분류돼
# 있었다(신규 등재 없음); metaTag는 진짜 신규 발견(JSON mixed-content 규약).
CYCLE_6_7_CLEANUP_DEVIATIONS = (
    "DEV-040",
)

CYCLE_6_7_CLEANUP_PROBES = (
    "dev040_metatag_json_mixed_content.py",
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


@pytest.mark.parametrize("dev_id", CYCLE_6_3_DEVIATIONS)
def test_cycle_6_3_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_3_PROBES)
def test_cycle_6_3_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_3_PROBES)
def test_cycle_6_3_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_4_DEVIATIONS)
def test_cycle_6_4_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_4_PROBES)
def test_cycle_6_4_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_4_PROBES)
def test_cycle_6_4_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_5_DEVIATIONS)
def test_cycle_6_5_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_5_PROBES)
def test_cycle_6_5_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_5_PROBES)
def test_cycle_6_5_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_6_DEVIATIONS)
def test_cycle_6_6_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_6_PROBES)
def test_cycle_6_6_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_6_PROBES)
def test_cycle_6_6_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_7_DEVIATIONS)
def test_cycle_6_7_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_7_PROBES)
def test_cycle_6_7_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_7_PROBES)
def test_cycle_6_7_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_7_TRAIN_27_DEVIATIONS)
def test_cycle_6_7_train_27_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_7_TRAIN_27_PROBES)
def test_cycle_6_7_train_27_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_7_TRAIN_27_PROBES)
def test_cycle_6_7_train_27_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dev_id", CYCLE_6_7_CLEANUP_DEVIATIONS)
def test_cycle_6_7_cleanup_deviation_is_registered(dev_id: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert dev_id in text


@pytest.mark.parametrize("probe_name", CYCLE_6_7_CLEANUP_PROBES)
def test_cycle_6_7_cleanup_probe_file_exists_and_is_referenced(probe_name: str) -> None:
    probe_path = PROBES_DIR / probe_name
    assert probe_path.exists(), f"probe script missing: {probe_path}"
    text = DOC.read_text(encoding="utf-8")
    assert probe_name in text, f"{probe_name} not referenced from the registry table"


@pytest.mark.parametrize("probe_name", CYCLE_6_7_CLEANUP_PROBES)
def test_cycle_6_7_cleanup_probe_runs_clean(probe_name: str) -> None:
    """각 프로브는 단독 실행 가능해야 한다(근거 파일이 없으면 SKIP=exit 0)."""

    result = subprocess.run(
        [sys.executable, str(PROBES_DIR / probe_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
