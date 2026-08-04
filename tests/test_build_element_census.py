# SPDX-License-Identifier: Apache-2.0
"""``scripts/build_element_census.py`` 계약 테스트.

2026-08-04 완전성 감사 §3-C1이 지목한 결함(census 생성기가 레포에 보존돼
있지 않아 재현·확장 불가능)의 수리 검증이다. 여기서 검증하는 것은 CI에서
완전히 재현 가능한 부분(vendored ``tests/fixtures/hwpxlib_corpus``)뿐이다
— 이 레포가 커밋한 ``docs/_extra/element-census.json`` 스냅샷은 소유자의
비공개 실문서 코퍼스도 섞여 있어 그 전체 재현은 소유자 환경에서만
가능하다(스냅샷 자체의 ``populationNote`` 참조).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_element_census.py"
HWPXLIB_CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"


def _module():
    spec = importlib.util.spec_from_file_location("build_element_census", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hwpxlib_only_run_is_deterministic() -> None:
    """같은 입력(vendored corpus만)으로 두 번 돌리면 바이트까지 같은
    census가 나온다 — 게이트 ②."""

    module = _module()
    family_to_prefix = module._family_to_prefix()
    first = module.build_census([HWPXLIB_CORPUS], [])
    second = module.build_census([HWPXLIB_CORPUS], [])
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["files"]["real"] == 47
    assert first["files"]["unknown"] == 0
    del family_to_prefix  # only needed to exercise the import path above


def test_unknown_files_are_recorded_not_silently_dropped(tmp_path: Path) -> None:
    """zip으로 못 여는 파일은 unknownFiles에 사유와 함께 남아야 한다 —
    denominator에서 조용히 빠지면 안 된다."""

    module = _module()
    corrupt = tmp_path / "not_actually_a_zip.hwpx"
    corrupt.write_bytes(b"this is not a zip file")

    census = module.build_census([tmp_path], [])
    assert census["files"]["unknown"] == 1
    assert census["unknownFiles"]["count"] == 1
    assert census["unknownFiles"]["reasons"]
    assert census["files"]["real"] == 0


def test_empty_zip_with_no_xml_part_is_unknown(tmp_path: Path) -> None:
    module = _module()
    empty = tmp_path / "no_xml_parts.hwpx"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Preview/PrvText.txt", "hello")

    census = module.build_census([tmp_path], [])
    assert census["files"]["unknown"] == 1
    assert "zip has no" in next(iter(census["unknownFiles"]["reasons"]))


def test_foreign_namespace_is_not_a_ledger_row(tmp_path: Path) -> None:
    """OWPML 밖 임베드 네임스페이스(OOXML DrawingML chart 등)는 요소 행이
    아니라 foreignNamespaces 카운터로만 나타난다."""

    module = _module()
    fixture = tmp_path / "embed.hwpx"
    with zipfile.ZipFile(fixture, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            '<?xml version="1.0"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:p id="0"/>'
            "</hs:sec>",
        )
        archive.writestr(
            "Chart/chart1.xml",
            '<?xml version="1.0"?>'
            '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>',
        )

    census = module.build_census([tmp_path], [])
    assert census["files"]["real"] == 1
    assert "hs:sec" in census["real_element_filecounts"]
    assert "hp:p" in census["real_element_filecounts"]
    assert census["foreignNamespaces"] == {
        "http://schemas.openxmlformats.org/drawingml/2006/chart": 1
    }
    # 외부 네임스페이스는 (prefix, name) 요소 키를 절대 만들지 않는다.
    assert not any(":chartSpace" in key for key in census["real_element_filecounts"])


def test_unnamespaced_element_is_tracked_separately(tmp_path: Path) -> None:
    """masterPage류(스키마는 네임스페이스를 선언하나 실문서는 bare 태그로
    방출)는 real_element_filecounts에 억지로 attribute되지 않는다."""

    module = _module()
    fixture = tmp_path / "bare_root.hwpx"
    with zipfile.ZipFile(fixture, "w") as archive:
        archive.writestr(
            "Contents/masterpage0.xml",
            '<?xml version="1.0"?><masterPage/>',
        )

    census = module.build_census([tmp_path], [])
    assert census["unnamespacedElements"] == {"masterPage": 1}
    assert not any(name == "masterPage" for key, name in
                    (k.split(":", 1) for k in census["real_element_filecounts"]))


def test_byte_identical_duplicates_are_deduped(tmp_path: Path) -> None:
    module = _module()
    fixture = tmp_path / "sub"
    fixture.mkdir()
    original = fixture / "a.hwpx"
    with zipfile.ZipFile(original, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            '<?xml version="1.0"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"/>',
        )
    backup = fixture / "a.BACKUP.hwpx"
    backup.write_bytes(original.read_bytes())

    census = module.build_census([fixture], [])
    assert census["files"]["real"] == 1
    assert census["duplicatesDropped"]["real"] == 1


def test_attribute_names_are_recorded_not_values(tmp_path: Path) -> None:
    module = _module()
    fixture = tmp_path / "attrs.hwpx"
    with zipfile.ZipFile(fixture, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            '<?xml version="1.0"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:p id="42" paraPrIDRef="secret-looking-value"/>'
            "</hs:sec>",
        )

    census = module.build_census([fixture], [])
    attrs = census["real_attribute_names_by_element"]["hp:p"]
    assert attrs == ["id", "paraPrIDRef"]
    assert "secret-looking-value" not in json.dumps(census)


def test_main_check_detects_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    out = tmp_path / "census.json"
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["build_element_census.py", "--output", str(out), "--check"],
    )
    # File does not exist yet -> drift.
    assert module.main() == 1
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["build_element_census.py", "--output", str(out)],
    )
    assert module.main() == 0
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["build_element_census.py", "--output", str(out), "--check"],
    )
    assert module.main() == 0
