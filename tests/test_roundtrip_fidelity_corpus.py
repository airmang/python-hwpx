# SPDX-License-Identifier: Apache-2.0
"""왕복 충실도 로컬 절반의 상주 회귀 — 실질 구조 변화 0을 매 스위트가 재검한다.

`scripts/roundtrip_fidelity.py`의 분모(실한컴 provenance 증명 파일 전수)를
무편집 재직렬화(open→to_bytes)하고, 분류가 무해 범주(byte-identical /
zip-container-only / cosmetic)에만 속하는지 단언한다. substantive-structural-
change가 하나라도 나오면 이 테스트가 릴리스 전에 막는다 — 공개 지표
(docs/corpus-metrics.md 왕복 충실도 절)의 "실질 변화 0"이 주장이 아니라
게이트가 되게 하는 장치다. 실한컴 재개봉 판정(외부 관찰자 절반)은 별도
배치(automation `scripts/roundtrip_reopen_mac.py`) 소관이다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "roundtrip_fidelity", ROOT / "scripts" / "roundtrip_fidelity.py"
)
assert _spec and _spec.loader
rf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rf  # dataclass가 자기 모듈을 sys.modules에서 찾는다
_spec.loader.exec_module(rf)


def test_corpus_roundtrip_has_no_substantive_change(tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "OUTPUT_DIR", tmp_path / "roundtrip")

    included, excluded = rf.discover_corpus()
    assert included, "왕복 분모가 비었다 — 코퍼스 루트/자격 심사 확인"
    # 자격 심사 정직성: 알려진 제외 3건(비실한컴 1 + 실한컴 거부 픽스처 2)은
    # 반드시 사유와 함께 제외 목록에 있어야 한다.
    excluded_paths = {e.rel_path for e in excluded}
    assert set(rf.KNOWN_NON_ORACLE_EXCLUSIONS) <= excluded_paths

    offenders: list[str] = []
    for entry in included:
        result = rf.measure_file(entry)
        if result.overall_category.startswith("substantive"):
            offenders.append(f"{entry.rel_path}: {result.overall_category}")
    assert not offenders, (
        "무편집 왕복에서 실질 구조 변화 발생 — 수리 전 릴리스 금지:\n"
        + "\n".join(offenders)
    )
