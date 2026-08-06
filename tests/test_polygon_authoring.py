# SPDX-License-Identifier: Apache-2.0
"""``doc.shapes.add_polygon`` — 다각형 저작 (062-engine-surface 트레인 13).

실코퍼스(``hwpxlib_corpus/reader_writer__SimplePolygon.hwpx``) 리버스: 꼭짓점은
``hc:pt``(core 네임스페이스 — rect/ellipse와 같은 기하 네임스페이스 계약, 5.0.0
도형 네임스페이스 결함 수리와 동일 축) 목록이고, 그 목록의 bbox가 자기
``orgSz``와 정확히 일치한다(8개 꼭짓점이 (0,0)-(17925,13425)를 정확히 span).
즉 정점은 도형 자신의 좌상단 원점 로컬 좌표계에 산다 — 페이지 배치는
``offset``/``pos``가 한다. ``add_polygon``은 호출자가 준 mm 좌표를 그 로컬
좌표계로 평행이동한다(자기 bbox의 min을 원점으로).

curve(``hp:curve``/``hp:seg``)는 이번 트레인에서 의도적으로 보류한다: 유일한
실 예시(``SimpleCurve.hwpx``)에서 앵커점 bbox(15225×20500)가 곡선 자신의
``orgSz``(16636×21360)보다 뚜렷이 작다 — 스플라인이 앵커점 밖으로 부풀어
오르는 실측이고, 한컴의 정확한 곡선 적합 알고리즘 근거 없이 bbox를 추정하면
침묵 오류가 된다.
"""

from __future__ import annotations

import math
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.objects import _create_polygon_element

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "fixtures" / "hwpxlib_corpus"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

# 골드 파일에만 있고 기하 계약 밖인 것들(캡션·주석) — 실코퍼스는 이미지 채움
# 다각형이라 fillBrush 도 imgBrush 를 갖는데, 우리 add_polygon 은 solid 채움만
# 저작하므로 fillBrush 내부까지는 비교하지 않는다.
_GOLD_ONLY_CHILDREN = frozenset({"shapeComment"})


def _gold_polygon():
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(CORPUS / "reader_writer__SimplePolygon.hwpx") as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = ET.fromstring(archive.read(name))
    element = root.find(f".//{HP}polygon")
    assert element is not None
    return element


def _contract_children(element) -> list[str]:
    return [
        child.tag
        for child in element
        if child.tag.split("}")[-1] not in _GOLD_ONLY_CHILDREN
    ]


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if "section" in name and name.endswith(".xml")
        )


# ============================================================================
# 게이트 ① 실문서 정합 — 생성물 대 실한컴 산출물
# ============================================================================


def test_generated_polygon_matches_gold_child_sequence() -> None:
    """SimplePolygon.hwpx 는 8개 꼭짓점을 가진 실한컴 산출물 — 자식 태그
    순서(offset·orgSz·curSz·flip·rotationInfo·renderingInfo·lineShape·
    fillBrush·shadow·pt×N·sz·pos·outMargin)가 우리 생성물과 정확히 일치해야
    한다."""

    gold = _gold_polygon()
    gold_points = [
        (int(pt.get("x", "0")), int(pt.get("y", "0")))
        for pt in gold
        if pt.tag == f"{HC}pt"
    ]
    generated = _create_polygon_element(gold_points, fill_color="#A0BEE0")
    assert _contract_children(generated) == _contract_children(gold)


def test_generated_polygon_vertex_count_matches_gold() -> None:
    gold = _gold_polygon()
    gold_points = [pt for pt in gold if pt.tag == f"{HC}pt"]
    assert len(gold_points) == 8


def test_polygon_vertices_use_the_core_namespace() -> None:
    """Hancom 은 기하가 ``hp:`` 에 있으면 문서 전체를 거부한다(5.0.0 결함)."""

    element = _create_polygon_element([(0, 0), (14400, 0), (7200, 7200)])
    pts = [child for child in element if child.tag.split("}")[-1] == "pt"]
    assert len(pts) == 3
    assert all(pt.tag == f"{HC}pt" for pt in pts)


def test_polygon_fill_brush_uses_the_core_namespace() -> None:
    """rect/ellipse 와 같은 계약: ``hp:fillBrush`` 는 파싱되지만 무채색으로
    렌더된다 — 색은 반드시 ``hc:fillBrush`` 에 있어야 한다."""

    element = _create_polygon_element(
        [(0, 0), (14400, 0), (7200, 7200)], fill_color="#CCE5FF",
    )
    assert element.find(f"{HP}fillBrush") is None
    brush = element.find(f"{HC}fillBrush/{HC}winBrush")
    assert brush is not None
    assert brush.get("faceColor") == "#CCE5FF"


def test_polygon_bounding_box_matches_the_gold_orgsz_relationship() -> None:
    """골드 다각형의 정점 bbox는 그 자신의 ``orgSz`` 와 정확히 같다(0..17925,
    0..13425) — 우리 생성물도 같은 관계를 지켜야 한다."""

    gold = _gold_polygon()
    org_sz = gold.find(f"{HP}orgSz")
    assert org_sz is not None
    gold_points = [
        (int(pt.get("x", "0")), int(pt.get("y", "0")))
        for pt in gold
        if pt.tag == f"{HC}pt"
    ]
    xs = [x for x, _y in gold_points]
    ys = [y for _x, y in gold_points]
    assert (max(xs) - min(xs), max(ys) - min(ys)) == (
        int(org_sz.get("width", "0")), int(org_sz.get("height", "0")),
    )

    generated = _create_polygon_element([(1000, 2000), (5000, 2000), (3000, 6000)])
    gen_org_sz = generated.find(f"{HP}orgSz")
    assert gen_org_sz is not None
    gen_points = [
        (int(pt.get("x", "0")), int(pt.get("y", "0")))
        for pt in generated
        if pt.tag == f"{HC}pt"
    ]
    gxs = [x for x, _y in gen_points]
    gys = [y for _x, y in gen_points]
    assert (max(gxs) - min(gxs), max(gys) - min(gys)) == (
        int(gen_org_sz.get("width", "0")), int(gen_org_sz.get("height", "0")),
    )


def test_polygon_points_are_translated_to_their_own_bounding_box_origin() -> None:
    """호출자가 준 점이 자기 자신의 원점에 있지 않아도(예: 전부 큰 양수),
    도형 로컬 좌표는 좌상단이 (0, 0)이어야 한다(rect의 pt0=(0,0) 관례와 동형)."""

    element = _create_polygon_element([(1000, 2000), (5000, 2000), (3000, 6000)])
    points = [
        (int(pt.get("x", "0")), int(pt.get("y", "0")))
        for pt in element
        if pt.tag == f"{HC}pt"
    ]
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    assert min(xs) == 0
    assert min(ys) == 0
    # 순서는 보존된다(다각형은 꼭짓점 순서가 모양을 정의한다).
    assert points == [(0, 0), (4000, 0), (2000, 4000)]


# ============================================================================
# resize() — 기존 범용 스캔이 다각형도 커버하는지
# ============================================================================


def test_resize_moves_polygon_vertices() -> None:
    """HwpxOxmlShape.resize()는 ``pt`` 로컬명을 이미 범용으로 스캔한다 —
    다각형을 위한 코드 변경 없이도 적용돼야 한다."""

    paragraph = HwpxDocument.new().add_paragraph("")
    shape = paragraph.add_polygon([(0, 0), (14400, 0), (7200, 7200)])

    shape.resize(28800, 14400)

    points = [
        (pt.get("x"), pt.get("y"))
        for pt in shape.element
        if pt.tag == f"{HC}pt"
    ]
    assert points == [("0", "0"), ("28800", "0"), ("14400", "14400")]


# ============================================================================
# 게이트 — doc.shapes.add_polygon 파사드(mm 입력·검증)
# ============================================================================


def test_add_polygon_converts_millimetres_to_hwpunit() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    shape = doc.shapes.add_polygon(
        [(0.0, 0.0), (50.0, 0.0), (25.0, 50.0)], section=0,
    )
    points = [
        (int(pt.get("x", "0")), int(pt.get("y", "0")))
        for pt in shape.element
        if pt.tag == f"{HC}pt"
    ]
    # 7200 hwpunit/inch, 25.4mm/inch → 50mm = round(50 * 7200 / 25.4)
    expected_50mm = round(50.0 * 7200 / 25.4)
    xs = [x for x, _y in points]
    assert max(xs) == expected_50mm


def test_add_polygon_rejects_fewer_than_three_points() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    with pytest.raises(HwpxValueError) as excinfo:
        doc.shapes.add_polygon([(0.0, 0.0), (10.0, 0.0)], section=0)
    assert excinfo.value.code == "shape-polygon-too-few-points"
    assert excinfo.value.context["count"] == 2


def test_add_polygon_accepts_exactly_three_points() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    shape = doc.shapes.add_polygon(
        [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)], section=0,
    )
    points = [pt for pt in shape.element if pt.tag == f"{HC}pt"]
    assert len(points) == 3


# ============================================================================
# 게이트 ② 왕복 무손상 — save/reopen
# ============================================================================


def test_polygon_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    original = doc.shapes.add_polygon(
        [(0.0, 0.0), (50.0, 0.0), (25.0, 50.0)],
        fill_color="#CCE5FF",
        section=0,
    )
    original_points = [
        (pt.get("x"), pt.get("y")) for pt in original.element if pt.tag == f"{HC}pt"
    ]
    path = tmp_path / "polygon.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    shapes = [s for section in reopened.oxml.sections for p in section.paragraphs for s in p.shapes]
    polygons = [s for s in shapes if s.element.tag == f"{HP}polygon"]
    assert len(polygons) == 1
    reopened_points = [
        (pt.get("x"), pt.get("y")) for pt in polygons[0].element if pt.tag == f"{HC}pt"
    ]
    assert reopened_points == original_points
    reopened.close()


def test_authored_polygon_passes_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.shapes.add_polygon(
        [(0.0, 0.0), (50.0, 0.0), (25.0, 50.0)], fill_color="#CCE5FF", section=0,
    )
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# ============================================================================
# 게이트 ③ 신규 저작 — 삼각형·오각형·별형 (mm 좌표 → 실 XML 정합 → 재개봉 읽기)
# ============================================================================


def _regular_polygon_points_mm(
    *, sides: int, radius_mm: float, center_mm: tuple[float, float] = (40.0, 40.0),
) -> list[tuple[float, float]]:
    cx, cy = center_mm
    return [
        (
            cx + radius_mm * math.sin(2 * math.pi * i / sides),
            cy - radius_mm * math.cos(2 * math.pi * i / sides),
        )
        for i in range(sides)
    ]


def _star_points_mm(
    *, points: int, outer_mm: float, inner_mm: float,
    center_mm: tuple[float, float] = (40.0, 40.0),
) -> list[tuple[float, float]]:
    cx, cy = center_mm
    vertices: list[tuple[float, float]] = []
    for i in range(points * 2):
        radius = outer_mm if i % 2 == 0 else inner_mm
        angle = math.pi * i / points
        vertices.append((cx + radius * math.sin(angle), cy - radius * math.cos(angle)))
    return vertices


@pytest.mark.parametrize(
    "name, points_mm",
    [
        ("triangle", _regular_polygon_points_mm(sides=3, radius_mm=30.0)),
        ("pentagon", _regular_polygon_points_mm(sides=5, radius_mm=30.0)),
        ("star", _star_points_mm(points=5, outer_mm=30.0, inner_mm=12.0)),
    ],
)
def test_new_authoring_shape_is_structurally_valid_and_rereadable(
    name, points_mm, tmp_path,
) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph(f"{name} 도형")
    shape = doc.shapes.add_polygon(points_mm, fill_color="#F1CB7E", section=0)

    # XML 정합: 필수 자식이 전부 있어야 한다(open_safety 와 별개로, 저작
    # 직후 구조 확인).
    from hwpx.oxml.objects import _missing_shape_children

    assert _missing_shape_children(shape.element) == []
    vertex_count = len([pt for pt in shape.element if pt.tag == f"{HC}pt"])
    assert vertex_count == len(points_mm)

    path = tmp_path / f"{name}.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    shapes = [
        s
        for section in reopened.oxml.sections
        for p in section.paragraphs
        for s in p.shapes
    ]
    polygons = [s for s in shapes if s.element.tag == f"{HP}polygon"]
    assert len(polygons) == 1
    assert len([pt for pt in polygons[0].element if pt.tag == f"{HC}pt"]) == len(points_mm)

    from hwpx.tools.package_validator import validate_editor_open_safety

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True
    reopened.close()
