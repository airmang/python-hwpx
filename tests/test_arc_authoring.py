# SPDX-License-Identifier: Apache-2.0
"""``doc.shapes.add_arc`` — 사분원(호) 저작 (062-engine-surface 트레인 14).

실코퍼스(``hwpxlib_corpus/reader_writer__SimpleArc.hwpx``) 리버스: 스키마상
``hp:arc``(``ArcType``, ParaList XML schema.xml)는 좌표 3점(``center``/
``ax1``/``ax2``)뿐이고 각도 필드가 아예 없다. 유일한 실 예시는
``center=(0,0)``·``ax1=(0,height)``(center 바로 아래)·``ax2=(width,0)``
(center 바로 오른쪽)인 사분원 하나뿐이다 — 그 bbox가 자기 ``orgSz``와 정확히
일치한다(0..12450, 0..11225). 그 배치 하나만 점 단위로 실측 검증됐고, 나머지
세 모서리는 다른 모든 도형이 이미 쓰는 ``hp:flip`` 미러링으로 얻는다(새 점
계산 없음).

``hp:connectLine``은 이번 트레인에서도 정직 보류한다: 유일한 정본 예시
(``SimpleConnectLine.hwpx``)는 자유선이 아니라 ``subjectIDRef``로 다른 두
도형(rect·ellipse)을 잇는 "스마트 연결선"이라 ``offset``이 음수(부호 없는
32비트로 직렬화)·``curSz``≠``orgSz``·``scaMatrix``가 평행이동까지 얹은
비항등 행렬이고, 그 관계식을 재현할 근거가 없다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.objects import _ARC_CORNER_FLIPS, _create_arc_element

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "fixtures" / "hwpxlib_corpus"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

_GOLD_ONLY_CHILDREN = frozenset({"shapeComment"})


def _gold_arc():
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(CORPUS / "reader_writer__SimpleArc.hwpx") as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = ET.fromstring(archive.read(name))
    element = root.find(f".//{HP}arc")
    assert element is not None
    return element


def _contract_children(element) -> list[str]:
    return [
        child.tag
        for child in element
        if child.tag.split("}")[-1] not in _GOLD_ONLY_CHILDREN
    ]


def _points(element, *names) -> dict[str, tuple[str, str]]:
    result = {}
    for child in element:
        local = child.tag.split("}")[-1]
        if local in names:
            result[local] = (child.get("x"), child.get("y"))
    return result


# ============================================================================
# 게이트 ① 실문서 정합
# ============================================================================


def test_generated_arc_matches_gold_child_sequence() -> None:
    gold = _gold_arc()
    generated = _create_arc_element(12450, 11225, arc_type="PIE", fill_color="#F1CB7E")
    assert _contract_children(generated) == _contract_children(gold)


def test_generated_arc_geometry_matches_gold_point_for_point() -> None:
    """유일한 실 예시: center=(0,0)·ax1=(0,11225)·ax2=(12450,0), type=PIE."""

    gold = _gold_arc()
    assert gold.get("type") == "PIE"
    assert _points(gold, "center", "ax1", "ax2") == {
        "center": ("0", "0"),
        "ax1": ("0", "11225"),
        "ax2": ("12450", "0"),
    }

    generated = _create_arc_element(12450, 11225, arc_type="PIE")
    assert _points(generated, "center", "ax1", "ax2") == {
        "center": ("0", "0"),
        "ax1": ("0", "11225"),
        "ax2": ("12450", "0"),
    }


def test_arc_geometry_uses_the_core_namespace() -> None:
    element = _create_arc_element(14400, 7200)
    for local in ("center", "ax1", "ax2"):
        child = next(c for c in element if c.tag.split("}")[-1] == local)
        assert child.tag == f"{HC}{local}"


def test_arc_bounding_box_matches_gold_orgsz_relationship() -> None:
    gold = _gold_arc()
    org_sz = gold.find(f"{HP}orgSz")
    assert org_sz is not None
    assert (org_sz.get("width"), org_sz.get("height")) == ("12450", "11225")

    generated = _create_arc_element(12450, 11225)
    gen_org_sz = generated.find(f"{HP}orgSz")
    assert gen_org_sz is not None
    assert (gen_org_sz.get("width"), gen_org_sz.get("height")) == ("12450", "11225")


def test_arc_fill_brush_uses_the_core_namespace() -> None:
    element = _create_arc_element(14400, 7200, fill_color="#CCE5FF")
    assert element.find(f"{HP}fillBrush") is None
    brush = element.find(f"{HC}fillBrush/{HC}winBrush")
    assert brush is not None
    assert brush.get("faceColor") == "#CCE5FF"


# ============================================================================
# corner 미러링 — TOP_LEFT만 실측, 나머지 3개는 hp:flip 유도
# ============================================================================


@pytest.mark.parametrize(
    "corner, expected_flip",
    [
        ("TOP_LEFT", ("0", "0")),
        ("TOP_RIGHT", ("1", "0")),
        ("BOTTOM_LEFT", ("0", "1")),
        ("BOTTOM_RIGHT", ("1", "1")),
    ],
)
def test_arc_corner_selects_flip_not_new_points(corner, expected_flip) -> None:
    """네 모서리 전부 같은 점 3개를 쓰고, flip만 바뀐다 — 새 기하 계산 없음."""

    element = _create_arc_element(14400, 7200, corner=corner)
    flip = element.find(f"{HP}flip")
    assert flip is not None
    assert (flip.get("horizontal"), flip.get("vertical")) == expected_flip
    assert _points(element, "center", "ax1", "ax2") == {
        "center": ("0", "0"), "ax1": ("0", "7200"), "ax2": ("14400", "0"),
    }


def test_arc_corner_flip_table_covers_exactly_four_corners() -> None:
    assert set(_ARC_CORNER_FLIPS) == {
        "TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT",
    }


def test_arc_invalid_corner_is_a_typed_error() -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        _create_arc_element(14400, 7200, corner="MIDDLE")
    assert excinfo.value.code == "shape-arc-corner-invalid"


def test_arc_invalid_type_is_a_typed_error() -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        _create_arc_element(14400, 7200, arc_type="WEDGE")
    assert excinfo.value.code == "shape-arc-type-invalid"


# ============================================================================
# resize() — 기존 범용 스캔이 호도 커버하는지
# ============================================================================


def test_resize_moves_arc_axis_points() -> None:
    paragraph = HwpxDocument.new().add_paragraph("")
    shape = paragraph.add_arc(12450, 11225)

    shape.resize(24900, 22450)

    points = _points(shape.element, "center", "ax1", "ax2")
    assert points == {
        "center": ("0", "0"), "ax1": ("0", "22450"), "ax2": ("24900", "0"),
    }


# ============================================================================
# 게이트 — doc.shapes.add_arc 파사드
# ============================================================================


def test_add_arc_default_is_a_full_top_left_quarter() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    shape = doc.shapes.add_arc(section=0)
    assert shape.element.get("type") == "NORMAL"
    flip = shape.element.find(f"{HP}flip")
    assert flip is not None
    assert (flip.get("horizontal"), flip.get("vertical")) == ("0", "0")


def test_add_arc_all_corners_and_types_produce_open_safe_documents(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    for corner in ("TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"):
        for arc_type in ("NORMAL", "PIE", "CHORD"):
            doc.add_paragraph(f"{corner}/{arc_type}")
            doc.shapes.add_arc(
                12450, 11225, corner=corner, arc_type=arc_type,
                fill_color="#F1CB7E", section=0,
            )
    path = tmp_path / "arc-matrix.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# ============================================================================
# 게이트 ② 왕복 무손상
# ============================================================================


def test_arc_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    original = doc.shapes.add_arc(
        12450, 11225, corner="BOTTOM_RIGHT", arc_type="PIE",
        fill_color="#F1CB7E", section=0,
    )
    original_points = _points(original.element, "center", "ax1", "ax2")
    path = tmp_path / "arc.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    shapes = [
        s for section in reopened.oxml.sections for p in section.paragraphs for s in p.shapes
    ]
    arcs = [s for s in shapes if s.element.tag == f"{HP}arc"]
    assert len(arcs) == 1
    assert arcs[0].element.get("type") == "PIE"
    assert _points(arcs[0].element, "center", "ax1", "ax2") == original_points
    reopened.close()


# ============================================================================
# connectLine — 정직 보류 고정 (실측 근거만 기록, 저작 API 없음)
# ============================================================================


def test_connect_line_authoring_is_not_offered() -> None:
    """저작 API가 없다는 걸 스스로 고정한다 — 다음 트레인이 실수로 반쪽
    구현을 얹기 전에, 이 테스트가 먼저 깨져야 "의도적으로 없다"는 사실을
    다시 확인시킨다."""

    doc = HwpxDocument.new()
    assert not hasattr(doc.shapes, "add_connect_line")


def test_connect_line_gold_example_is_anchored_to_other_shapes() -> None:
    """정직 보류의 근거를 코드로 고정: 유일한 정본 예시는 자유선이 아니라
    subjectIDRef로 다른 두 도형을 잇는 스마트 연결선이다."""

    with zipfile.ZipFile(CORPUS / "reader_writer__SimpleConnectLine.hwpx") as archive:
        import xml.etree.ElementTree as ET

        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = ET.fromstring(archive.read(name))

    connect_line = root.find(f".//{HP}connectLine")
    assert connect_line is not None
    start_pt = connect_line.find(f"{HP}startPt")
    end_pt = connect_line.find(f"{HP}endPt")
    assert start_pt is not None and end_pt is not None
    # startPt/endPt 는 hp: 네임스페이스다 — hp:line 의 hc:startPt/hc:endPt 와
    # 다르다(도형마다 기하 네임스페이스를 개별 검증해야 한다는 실측).
    assert start_pt.tag == f"{HP}startPt"
    assert end_pt.tag == f"{HP}endPt"
    assert start_pt.get("subjectIDRef") not in (None, "0")
    assert end_pt.get("subjectIDRef") not in (None, "0")

    org_sz = connect_line.find(f"{HP}orgSz")
    cur_sz = connect_line.find(f"{HP}curSz")
    assert org_sz is not None and cur_sz is not None
    assert (org_sz.get("width"), org_sz.get("height")) != (
        cur_sz.get("width"), cur_sz.get("height"),
    )

    sca_matrix = connect_line.find(f"{HP}renderingInfo/{HC}scaMatrix")
    assert sca_matrix is not None
    identity = {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}
    assert dict(sca_matrix.attrib) != identity
