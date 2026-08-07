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

So unlike DEV-018 (prefer case, either branch works), the correct choice
here is prefer default: TabDefinition.tab_stops must return the value that
matches how real, unwrapped hh:tabPr already means "pos", not the
alternate-scale hp:case value. Getting this backwards would silently
produce tab stops at half their intended distance.

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
#: 대조군: 직속 hh:tabItem(hp:switch 없음)을 가진 실 문서 -- hp:default
#: 스케일이 "진짜" 스케일이라는 판정의 근거.
DIRECT_CHILD_SAMPLE = CORPUS / "error__20240626__no_manifest.hwpx"
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


def test_tab_definition_tab_stops_use_the_default_branch_scale() -> None:
    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    tab_prs = _tab_pr_elements(root)

    definitions = [parse_tab_definition(node) for node in tab_prs]
    with_switch = [d for d in definitions if d.version_switch is not None]
    assert len(with_switch) == 4

    for definition in with_switch:
        switch = definition.version_switch
        assert switch is not None
        assert switch.case is not None and switch.default is not None
        case_pos = [s.pos for s in switch.case.tab_stops]
        default_pos = [s.pos for s in switch.default.tab_stops]
        assert definition.tab_stops, "expected tab_stops to be populated, not empty"
        assert [s.pos for s in definition.tab_stops] == default_pos, (
            "tab_stops must match hp:default's scale, not hp:case's"
        )
        # DEV-022's core numeric claim: case is always exactly half of default.
        assert case_pos and default_pos
        for cp, dp in zip(case_pos, default_pos):
            assert dp == cp * 2, (cp, dp)


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
    """대조군: hp:switch가 없는 실 문서는 직접 자식 값이 이미 정확했다
    (이 트레인 전에도 tab_stops가 비지 않았다) -- 폴백 도입이 이 경로를
    바꾸지 않았는지 확인. 이 직속 값(8064·3216)이 §hp:default 스케일과
    일치한다는 사실 자체가 "default가 진짜 스케일" 판정의 근거였다."""

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
