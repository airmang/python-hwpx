# SPDX-License-Identifier: Apache-2.0
"""``doc.shapes.add_container`` — 그룹 개체 저작 (사이클 6.5 트레인 18).

실코퍼스(``hwpxlib_corpus/reader_writer__SimpleContainer.hwpx`` 3부재 +
``error__20230818__test.hwpx``/``error__20250808__...hwpx`` 두 실문서 71개
컨테이너, 총 74개 표본) 리버스: 그룹 부재는 독립 도형과 완전히 같은 구조
(offset/orgSz/curSz/flip/rotationInfo/renderingInfo + 도형별 기하)를 유지하되
``AbstractShapeObjectType`` 꼬리(sz/pos/outMargin/shapeComment — 그룹만
가짐)는 없고, ``groupLevel``이 ``"1"``(그룹 자신은 ``"0"``), 부재의
``renderingInfo``/``transMatrix`` 이동성분(e3/e6)이 자기 ``offset``과 정확히
일치한다. 74개 표본 전량 ``numberingType="PICTURE"``. 그룹 자신의 ``orgSz``는
부재들의 (offset, orgSz) 합집합 bbox다.

``pic``/``arc``/``line``/``connectLine``/중첩 ``container`` 부재는 이번
트레인 범위 밖(뒤 셋은 같은 패턴으로 자연 확장 가능, ``pic``은 media 배선이
추가로 필요) — 곡선류 트레인이 curve/connectLine을 정직 보류한 것과 같은
원칙.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml import ContainerMember
from hwpx.oxml.objects import _create_container_element, _missing_shape_children

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "fixtures" / "hwpxlib_corpus"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

_MEMBER_TAGS = {"pic", "line", "rect", "ellipse", "polygon", "arc", "connectLine", "container"}


def _gold_container():
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(CORPUS / "reader_writer__SimpleContainer.hwpx") as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = ET.fromstring(archive.read(name))
    element = root.find(f".//{HP}container")
    assert element is not None
    return element


def _local(tag: str) -> str:
    return tag.split("}")[-1]


# ============================================================================
# 게이트 ① 실문서 정합 — 생성물 대 실한컴 산출물
# ============================================================================


def test_gold_container_has_three_members_and_no_own_geometry() -> None:
    """SimpleContainer.hwpx의 골드 컨테이너: pic·pic·line 3부재, 컨테이너
    자신은 기하 자식이 없다(부재가 곧 페이로드)."""

    gold = _gold_container()
    member_tags = [_local(child.tag) for child in gold if _local(child.tag) in _MEMBER_TAGS]
    assert member_tags == ["pic", "pic", "line"]


def test_gold_container_is_numbering_type_picture() -> None:
    """74개 표본(SimpleContainer 1 + 실문서 2종 71개) 전량 관측된 값."""

    gold = _gold_container()
    assert gold.get("numberingType") == "PICTURE"
    assert gold.get("groupLevel") == "0"


def test_gold_container_members_have_group_level_one_and_no_shape_object_tail() -> None:
    """부재는 groupLevel="1"이고, 컨테이너 전용인 sz/pos/outMargin을 안 갖는다
    (컨테이너 자신에게만 있다)."""

    gold = _gold_container()
    members = [child for child in gold if _local(child.tag) in _MEMBER_TAGS]
    assert len(members) == 3
    for member in members:
        assert member.get("groupLevel") == "1"
        assert member.find(f"{HP}sz") is None
        assert member.find(f"{HP}pos") is None
        assert member.find(f"{HP}outMargin") is None
    # 컨테이너 자신은 셋 다 갖는다(그룹 배치를 담당).
    assert gold.find(f"{HP}sz") is not None
    assert gold.find(f"{HP}pos") is not None
    assert gold.find(f"{HP}outMargin") is not None
    assert gold.find(f"{HP}shapeComment") is not None


def test_gold_container_member_offset_matches_transmatrix_translation() -> None:
    """실측: 두 번째 hp:pic의 offset=(8650, 300), transMatrix e3/e6도 같은 값
    — 부재를 재배치할 때 둘 다 같이 갱신해야 한다는 계약의 근거."""

    gold = _gold_container()
    pics = [child for child in gold if _local(child.tag) == "pic"]
    assert len(pics) == 2
    second = pics[1]
    offset = second.find(f"{HP}offset")
    assert offset is not None
    assert (offset.get("x"), offset.get("y")) == ("8650", "300")
    trans = second.find(f"{HP}renderingInfo/{HC}transMatrix")
    assert trans is not None
    assert (trans.get("e3"), trans.get("e6")) == ("8650", "300")


# ============================================================================
# 게이트 ② 생성물 구조 — _create_container_element
# ============================================================================


def test_create_container_element_computes_union_bounding_box() -> None:
    element = _create_container_element([
        ContainerMember.rect(0, 0, 5000, 3000),
        ContainerMember.ellipse(6000, 500, 4000, 4000),
    ])
    org_sz = element.find(f"{HP}orgSz")
    assert org_sz is not None
    # max_x = 6000+4000=10000, max_y = 500+4000=4500; min both 0.
    assert (org_sz.get("width"), org_sz.get("height")) == ("10000", "4500")


def test_create_container_element_translates_members_when_min_is_not_zero() -> None:
    """부재 오프셋이 (0,0)에서 시작하지 않아도, 그룹 로컬 좌표는 좌상단이
    (0,0)이 되도록 평행이동한다(polygon의 자기 bbox 원점 관례와 동형)."""

    element = _create_container_element([
        ContainerMember.rect(1000, 2000, 3000, 1000),
        ContainerMember.rect(4000, 2000, 1000, 1000),
    ])
    members = [c for c in element if _local(c.tag) in _MEMBER_TAGS]
    offsets = [
        (m.find(f"{HP}offset").get("x"), m.find(f"{HP}offset").get("y"))
        for m in members
    ]
    assert offsets == [("0", "0"), ("3000", "0")]
    org_sz = element.find(f"{HP}orgSz")
    assert (org_sz.get("width"), org_sz.get("height")) == ("4000", "1000")


def test_create_container_element_sets_group_level_and_shared_member_id() -> None:
    element = _create_container_element([ContainerMember.rect(0, 0, 1000, 1000)])
    assert element.get("groupLevel") == "0"
    assert element.get("numberingType") == "PICTURE"
    member = next(c for c in element if _local(c.tag) in _MEMBER_TAGS)
    assert member.get("groupLevel") == "1"
    # 실측: 대다수 표본(74건 중 71건)이 부재 id를 "0"으로 공유한다.
    assert member.get("id") == "0"


def test_create_container_element_strips_member_shape_object_tail() -> None:
    """부재를 만드는 _create_rectangle_element 등은 자기 완결형 도형이라
    sz/pos/outMargin을 이미 갖고 있다 — 컨테이너로 들어갈 때 그 꼬리를
    제거해야 골드와 일치한다."""

    element = _create_container_element([ContainerMember.rect(0, 0, 1000, 1000)])
    member = next(c for c in element if _local(c.tag) in _MEMBER_TAGS)
    assert member.find(f"{HP}sz") is None
    assert member.find(f"{HP}pos") is None
    assert member.find(f"{HP}outMargin") is None
    # 컨테이너 자신은 셋 다 + shapeComment까지 갖는다.
    assert element.find(f"{HP}sz") is not None
    assert element.find(f"{HP}pos") is not None
    assert element.find(f"{HP}outMargin") is not None
    assert element.find(f"{HP}shapeComment") is not None


def test_create_container_element_rejects_empty_members() -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        _create_container_element([])
    assert excinfo.value.code == "shape-container-no-members"


def test_create_container_element_preserves_member_fill_and_geometry() -> None:
    """그룹으로 감싸도 부재 자신의 기하·서식은 그대로다."""

    element = _create_container_element([
        ContainerMember.rect(0, 0, 5000, 3000, fill_color="#CCE5FF"),
    ])
    member = next(c for c in element if _local(c.tag) == "rect")
    brush = member.find(f"{HC}fillBrush/{HC}winBrush")
    assert brush is not None
    assert brush.get("faceColor") == "#CCE5FF"
    pts = [c for c in member if _local(c.tag) == "pt0"]
    assert len(pts) == 1


# ============================================================================
# 게이트 ③ doc.shapes.add_container 파사드
# ============================================================================


def test_add_container_returns_a_shape_wrapper() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    shape = doc.shapes.add_container(
        [
            ContainerMember.rect(0, 0, 5000, 3000),
            ContainerMember.polygon(6000, 0, [(0, 0), (4000, 0), (2000, 4000)]),
        ],
        section=0,
    )
    assert shape.element.tag == f"{HP}container"
    members = [c for c in shape.element if _local(c.tag) in _MEMBER_TAGS]
    assert [_local(m.tag) for m in members] == ["rect", "polygon"]


def test_add_container_appears_in_paragraph_shapes() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.shapes.add_container(
        [ContainerMember.rect(0, 0, 1000, 1000)], paragraph=paragraph,
    )
    tags = [_local(s.element.tag) for s in paragraph.shapes]
    assert "container" in tags


# ============================================================================
# 게이트 ④ 왕복 무손상 — save/reopen + open-safety
# ============================================================================


def test_container_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.shapes.add_container(
        [
            ContainerMember.rect(0, 0, 5000, 3000, fill_color="#CCE5FF"),
            ContainerMember.ellipse(6000, 500, 4000, 4000),
        ],
        section=0,
    )
    path = tmp_path / "container.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    shapes = [
        s
        for section in reopened.oxml.sections
        for p in section.paragraphs
        for s in p.shapes
    ]
    containers = [s for s in shapes if s.element.tag == f"{HP}container"]
    assert len(containers) == 1
    members = [c for c in containers[0].element if _local(c.tag) in _MEMBER_TAGS]
    assert [_local(m.tag) for m in members] == ["rect", "ellipse"]
    reopened.close()


def test_resize_updates_container_size_but_not_member_layout() -> None:
    """정직한 현재 한계 기록: ``HwpxOxmlShape.resize()``의 ``_scale_geometry``는
    직속 자식 중 ``_SHAPE_POINT_LOCAL_NAMES``(``pt``/``center``/``startPt``
    등)에 속한 태그만 훑는다 — 컨테이너의 직속 자식은 부재 도형 전체
    (``rect``/``ellipse``/...)라 그 이름 집합에 없다. 그래서 컨테이너를
    resize하면 컨테이너 자신의 orgSz/sz/curSz는 바뀌지만, 부재의 offset·
    orgSz는 그대로 남아 더 이상 컨테이너의 실제 bbox와 일치하지 않는다 —
    polygon의 "resize()가 변경 없이 이미 적용된다" 사례와 달리, 여기서는
    적용되지 않는다는 사실이 계약이다. 부재별로 개별 ``resize()``를 부르는
    것이 현재의 올바른 사용법이다(다음 트레인 후보)."""

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    shape = doc.shapes.add_container(
        [
            ContainerMember.rect(0, 0, 5000, 3000),
            ContainerMember.ellipse(6000, 0, 4000, 4000),
        ],
        paragraph=paragraph,
    )
    member_before = [
        (dict(m.find(f"{HP}offset").attrib), dict(m.find(f"{HP}orgSz").attrib))
        for m in shape.element
        if _local(m.tag) in _MEMBER_TAGS
    ]

    shape.resize(20000, 9000)

    org_sz = shape.element.find(f"{HP}orgSz")
    assert (org_sz.get("width"), org_sz.get("height")) == ("20000", "9000")
    member_after = [
        (dict(m.find(f"{HP}offset").attrib), dict(m.find(f"{HP}orgSz").attrib))
        for m in shape.element
        if _local(m.tag) in _MEMBER_TAGS
    ]
    assert member_after == member_before


def test_authored_container_passes_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    shape = doc.shapes.add_container(
        [
            ContainerMember.rect(0, 0, 5000, 3000, fill_color="#CCE5FF"),
            ContainerMember.polygon(6000, 0, [(0, 0), (4000, 0), (2000, 4000)]),
        ],
        section=0,
    )
    assert _missing_shape_children(shape.element) == []
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True
