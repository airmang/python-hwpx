# SPDX-License-Identifier: Apache-2.0
"""``add_control``은 문서에 예제가 있었고 한 번도 동작하지 않았다.

``ET.SubElement``는 stdlib Element만 받는데 이 패키지의 트리는 lxml이다. 그래서
호출하면 언제나 ``TypeError``였다 — 새 문서든 열어둔 문서든, 어떤 control_type
이든. 문서(``examples.md``·``usage.md``)는 그 API를 계속 안내하고 있었다.

스위트가 이걸 못 잡은 이유는 단순하다. **부르는 테스트가 없었다.**
"""

from __future__ import annotations

import io
import zipfile

import pytest

from hwpx import HwpxDocument


def _section_xml(payload: bytes) -> str:
    """HWPX 안의 본문 XML을 모아 돌려준다."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.startswith("Contents/section")
        )


@pytest.mark.parametrize("control_type", ["LINE", "RECTANGLE", "ELLIPSE"])
def test_add_control_creates_an_element_of_the_tree_s_own_kind(control_type: str) -> None:
    document = HwpxDocument.new()
    try:
        document.add_paragraph("도형이 붙을 문단")
        # 자식 없는 <hp:ctrl>은 한컴이 열지 못한다 — 만들어지되 경고한다.
        with pytest.warns(UserWarning, match="no control child"):
            obj = document.add_control(
                section=document.sections[0],
                control_type=control_type,
                attributes={"id": f"guide-{control_type}", "type": control_type},
            )
        assert obj is not None
        # 만들어만 놓고 트리에 안 붙으면 직렬화에서 사라진다. HWPX는 ZIP이라
        # 원시 바이트를 뒤지면 압축 때문에 언제나 못 찾는다 — 열어서 봐야 한다.
        assert control_type in _section_xml(document.to_bytes())
    finally:
        document.close()


def test_add_control_survives_a_save_and_reopen(tmp_path) -> None:
    """붙인 control이 저장·재오픈 뒤에도 남아야 한다."""
    path = tmp_path / "control.hwpx"
    document = HwpxDocument.new()
    try:
        document.add_paragraph("본문")
        with pytest.warns(UserWarning, match="no control child"):
            document.add_control(
                section=document.sections[0],
                control_type="LINE",
                attributes={"id": "keepme", "type": "LINE"},
            )
        document.save_to_path(path)
    finally:
        document.close()

    reopened = HwpxDocument.open(path)
    try:
        assert "keepme" in _section_xml(reopened.to_bytes())
    finally:
        reopened.close()
