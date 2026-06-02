# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "owpml-deviations.md"


def test_registry_exists_with_required_sections():
    text = DOC.read_text(encoding="utf-8")
    assert "# OWPML 편차 레지스트리" in text
    assert "## 네임스페이스 정합 (2011/2016 ↔ 2024)" in text
    # At least one deviation or compatibility strategy entry with an evidence pointer.
    assert "증거:" in text
