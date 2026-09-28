# SPDX-License-Identifier: Apache-2.0
"""Typed read model for hh:tabPr's hp:switch wrapping (DEV-022, cycle 6.7
train 25).

Background: cycle 6.6 train 21 fixed the same "hp:switch not visible to the
typed read model" shape for hh:paraPr's margin/lineSpacing (DEV-018). While
investigating whether the same pattern applied elsewhere, hh:tabPr turned
out to have the same structural problem -- but a *different* contract.
DEV-018's two branches hold the *same* semantic value (case/default are
redundant copies for version-compat clients); hh:tabPr's do not: hp:case's
hh:tabItem/@pos is consistently exactly half of hp:default's (34/34 pairs
across the vendored corpus), and only hp:case's tabItem carries an explicit
unit="HWPUNIT" attribute (449/449) while hp:default's and every real
unwrapped (non-switch) tabItem never do (0/483). A real unwrapped document
(error__20240626__no_manifest.hwpx) settles which branch is the "real"
scale: its direct tabItem positions (8064, 3216) match hp:default's values
exactly, not hp:case's halved ones.

Hancom 13.60 settles it the other way: it lays a stop out at hp:case's
position (HWPUNIT), reads an unwrapped hh:tabItem in HWPUNIT too, and saves
such an item as a switch of that position in hp:case and twice it in
hp:default (tab_bare_right_saved.hwpx). The unwrapped control document's
values are the doubled scale an older Hancom wrote. So TabDefinition.tab_stops
reads hp:case, as DEV-018 does. Hancom wraps each stop in its own hp:switch;
the read model gathers the stops of every switch.

This is worse than DEV-018 pre-fix in one respect: margin/lineSpacing
became None when unread (an absent value, not a wrong one). Here the
uncorrected read returns tab_stops=[] -- "no custom tab stops" -- for a
tabPr that genuinely has them, actively misinforming the caller rather
than just omitting information.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from hwpx.oxml.header import (
    TabDefinitionVersionBranch,
    TabDefinitionVersionSwitch,
    parse_tab_definition,
)
from hwpx.tools.roundtrip_diff import roundtrip_report

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
#: 실코퍼스 실측(DEV-022): id=1~4 4개 tabPr 전량이 hp:switch로 감싸이고,
#: hp:case pos가 hp:default의 정확히 절반이다.
SWITCH_WRAPPED_SAMPLE = CORPUS / "error__20230413__test.hwpx"
#: 대조군: 직속 hh:tabItem(hp:switch 없음)을 가진 실 문서. 값은 옛 한/글이 쓴
#: 두 배 스케일이다.
DIRECT_CHILD_SAMPLE = CORPUS / "error__20240626__no_manifest.hwpx"
#: python-hwpx가 맨 hh:tabItem pos=42520(150mm, 오른쪽 점선 탭)으로 쓴 문서를
#: 한/글이 저장한 것 -- hp:case 42520(HWPUNIT)과 hp:default 85040으로 나눠 썼다.
BARE_RIGHT_TAB_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "tab_bare_right_saved.hwpx"
HP_NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH_NS = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _header_root(sample: Path) -> etree._Element:
    with zipfile.ZipFile(sample) as archive:
        name = next(n for n in archive.namelist() if n.endswith("header.xml"))
        return etree.fromstring(archive.read(name))


def _tab_pr_elements(root: etree._Element) -> list[etree._Element]:
    return list(root.iter(f"{HH_NS}tabPr"))


def test_switch_wrapped_tab_stops_are_empty_before_the_fix_reproduces_on_real_source() -> None:
    """결함-부활: hp:switch 분기를 안 보는 예전 계산을 흉내내면(직속 자식만),
    실제로 4개 전부 tab_stops=[]가 됐다는 걸 같은 실 소스로 재현한다."""

    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    tab_prs = _tab_pr_elements(root)
    assert tab_prs, "expected at least one hh:tabPr in the fixture"

    def _old_direct_children_only_has_tab_item(node: etree._Element) -> bool:
        return any(child.tag == f"{HH_NS}tabItem" for child in node)

    switch_wrapped = [tp for tp in tab_prs if tp.find(f"{{{'http://www.hancom.co.kr/hwpml/2011/paragraph'}}}switch") is not None]
    assert switch_wrapped, "expected at least one hh:tabPr wrapping hp:switch"
    reproduced_empty = sum(
        1 for node in switch_wrapped if not _old_direct_children_only_has_tab_item(node)
    )
    assert reproduced_empty == len(switch_wrapped), (
        "expected every switch-wrapped tabPr in this fixture to lack a direct "
        "hh:tabItem child (the pre-fix logic would have left tab_stops=[] for all)"
    )


def test_tab_definition_tab_stops_are_the_case_positions_of_every_switch() -> None:
    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    tab_prs = [tp for tp in _tab_pr_elements(root) if tp.find(f"{HP_NS}switch") is not None]
    assert len(tab_prs) == 4

    for node in tab_prs:
        definition = parse_tab_definition(node)
        switch = definition.version_switch
        assert switch is not None
        assert switch.case is not None and switch.default is not None
        case_pos = [s.pos for s in switch.case.tab_stops]
        default_pos = [s.pos for s in switch.default.tab_stops]
        # Hancom wraps each stop in its own switch: one stop per switch.
        assert len(definition.tab_stops) == len(node.findall(f"{HP_NS}switch")) > 1
        assert [s.pos for s in definition.tab_stops] == case_pos
        assert all(s.attributes.get("unit") == "HWPUNIT" for s in definition.tab_stops)
        # DEV-022's numeric claim: hp:default is always twice hp:case.
        assert default_pos == [pos * 2 for pos in case_pos]


def test_hancom_reads_a_bare_tab_item_in_hwpunit() -> None:
    # python-hwpx wrote one bare tabItem pos=42520 (a 150 mm right tab with a dotted leader); Hancom laid it
    # out at 150 mm and saved it as hp:case 42520 unit=HWPUNIT and hp:default 85040.
    root = _header_root(BARE_RIGHT_TAB_SAVED)
    node = next(tp for tp in _tab_pr_elements(root) if tp.find(f"{HP_NS}switch") is not None)

    definition = parse_tab_definition(node)

    assert [(s.pos, s.type, s.leader) for s in definition.tab_stops] == [(42520, "RIGHT", "DOT")]
    assert definition.version_switch is not None and definition.version_switch.default is not None
    assert [s.pos for s in definition.version_switch.default.tab_stops] == [85040]


def test_a_tab_definition_is_written_as_hancom_writes_it() -> None:
    import xml.etree.ElementTree as ET

    from hwpx.document import HwpxDocument

    def shape(node) -> list:
        return [(child.tag.rsplit("}", 1)[-1], sorted((k.rsplit("}", 1)[-1], v) for k, v in child.attrib.items()))
                for child in node.iter() if child is not node]

    hancom = next(tp for tp in _tab_pr_elements(_header_root(BARE_RIGHT_TAB_SAVED))
                  if tp.find(f"{HP_NS}switch") is not None)
    doc = HwpxDocument.new()
    header = doc.oxml.headers[0]
    tab_id = header.ensure_tab_definition(tab_stops=[{"pos": 42520, "type": "RIGHT", "leader": "DOT"}])
    ours = next(tp for tp in header.element.iter(f"{HH_NS}tabPr") if tp.get("id") == tab_id)

    assert shape(etree.fromstring(ET.tostring(ours))) == shape(hancom)

    saved = HwpxDocument.open(BARE_RIGHT_TAB_SAVED.read_bytes())
    saved_header = saved.oxml.headers[0]
    count = len(list(saved_header.element.iter(f"{HH_NS}tabPr")))
    assert saved_header.ensure_tab_definition(
        tab_stops=[{"pos": 42520, "type": "RIGHT", "leader": "DOT"}]
    ) == hancom.get("id")
    assert len(list(saved_header.element.iter(f"{HH_NS}tabPr"))) == count


def test_version_switch_exposes_required_namespace_and_unit_attribute() -> None:
    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    node = next(
        tp
        for tp in _tab_pr_elements(root)
        if tp.find(f"{{{'http://www.hancom.co.kr/hwpml/2011/paragraph'}}}switch") is not None
    )

    definition = parse_tab_definition(node)
    switch = definition.version_switch
    assert isinstance(switch, TabDefinitionVersionSwitch)
    assert switch.required_namespace == "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"
    assert isinstance(switch.case, TabDefinitionVersionBranch)
    assert isinstance(switch.default, TabDefinitionVersionBranch)

    # DEV-022: only hp:case's tabItem explicitly declares unit="HWPUNIT";
    # hp:default's never does.
    assert switch.case.tab_stops[0].attributes.get("unit") == "HWPUNIT"
    assert "unit" not in switch.default.tab_stops[0].attributes


def test_direct_children_still_take_priority_over_switch_fallback() -> None:
    """대조군: hp:switch가 없는 실 문서는 직속 값을 그대로 읽는다(한/글도 맨
    hh:tabItem을 HWPUNIT으로 읽는다). 이 문서의 값(8064·3216)은 옛 한/글이 쓴
    두 배 스케일이다."""

    root = _header_root(DIRECT_CHILD_SAMPLE)
    tab_prs = _tab_pr_elements(root)
    node = next(tp for tp in tab_prs if tp.find(f"{HH_NS}tabItem") is not None)

    assert node.find(f"{{{'http://www.hancom.co.kr/hwpml/2011/paragraph'}}}switch") is None, (
        "this is meant to be the no-switch control fixture"
    )

    definition = parse_tab_definition(node)
    assert definition.tab_stops
    assert definition.version_switch is None


def test_real_consumer_accessor_finds_all_switch_wrapped_tab_definitions() -> None:
    """단일 hh:tabPr 파서가 아니라 실 소비 경로(HwpxOxmlHeader.tab_properties
    / doc.styles.tab_properties, header_part.py:1438)로도 같은 결과인지 --
    이게 바로 이 트레인이 수리한 그 경로다(갭 지도 v2 §B.3)."""

    import xml.etree.ElementTree as ET

    from hwpx.oxml.header_part import HwpxOxmlHeader

    with zipfile.ZipFile(SWITCH_WRAPPED_SAMPLE) as archive:
        header_xml = archive.read(next(n for n in archive.namelist() if n.endswith("header.xml")))
    stdlib_root = ET.fromstring(header_xml)
    header = HwpxOxmlHeader("header.xml", stdlib_root)

    tab_props = header.tab_properties
    assert len(tab_props) == 5
    populated = [d for d in tab_props.values() if d.tab_stops]
    assert len(populated) == 4, "expected the 4 switch-wrapped tabPr to have real tab_stops"

    # RefList.tab_properties (the *other*, unrelated snapshot path via
    # parse_header_element/parse_ref_list) is intentionally out of this
    # train's scope -- it still returns opaque GenericElement (gap-map v2
    # §B.3 lists it as lower priority since it has no real consumer, unlike
    # this accessor).
    from hwpx.oxml.header import TabProperties, parse_header_element

    full_snapshot = parse_header_element(_header_root(SWITCH_WRAPPED_SAMPLE))
    assert isinstance(full_snapshot.ref_list.tab_properties, TabProperties)


def test_switch_wrapped_sample_roundtrip_has_no_a1_loss() -> None:
    """읽기 모델은 직렬화기가 없다(파라그래프 스위치와 같은 이유 -- 편집은
    header_part.py의 살아있는 트리를 직접 건드린다) -- 이 필드를 추가한 것
    자체가 실 문서 open/save 왕복에 아무 영향이 없어야 한다."""

    rep = roundtrip_report(SWITCH_WRAPPED_SAMPLE)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}
