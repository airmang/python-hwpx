# SPDX-License-Identifier: Apache-2.0
"""Typed read model for hp:switch/case/default (DEV-018, cycle 6.6 train 21).

Background: `ParagraphProperty.margin`/`.line_spacing` are populated by a
loop over `hh:paraPr`'s *direct* children only. Real Hancom output almost
never puts margin/lineSpacing there directly -- 236/237 files (99.6%) wrap
them one level deeper, inside `hp:switch > hp:case`/`hp:default` (a
version-compat branch with no schema declaration anywhere, see DEV-018).
Before this train, that meant `.margin`/`.line_spacing` came back `None`
for virtually every real document's paraPr entries -- a silent read-model
gap, not a byte-preservation bug (the untouched `hp:switch` subtree already
round-tripped fine as an opaque GenericElement, and the *editing* path in
header_part.py's `_apply_paragraph_margins`/`_apply_paragraph_line_spacing`
already walks into both branches -- DEV-018 confirmed that by reading the
code). This is read-only by design: the authoring/editing path is already
correct, so there is no `*_to_xml` writer for `ParagraphPropertyVersionSwitch`
-- `ParagraphProperty`'s general model has no round-trip serializer either
(header_part.py edits the live oxml tree directly, not through this
snapshot dataclass).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from hwpx.oxml.header import (
    ParagraphPropertyVersionBranch,
    ParagraphPropertyVersionSwitch,
    parse_header_element,
    parse_paragraph_property,
)
from hwpx.tools.roundtrip_diff import roundtrip_report

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
#: 실코퍼스 실측(DEV-018): 16개 hh:paraPr 전량이 margin/lineSpacing을
#: hp:switch 안에 둔다(직접 자식 0건) -- tool__blank.hwpx.
SWITCH_WRAPPED_SAMPLE = CORPUS / "tool__blank.hwpx"
#: 대조군: margin/lineSpacing이 직접 자식인(hp:switch 없는) 실 문서 -- 스위치
#: 분기 폴백이 "직접 자식이 없을 때만" 개입하는지 확인하는 데 쓴다.
DIRECT_CHILD_SAMPLE = CORPUS / "error__20240626__no_manifest.hwpx"
HH_NS = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _header_root(sample: Path) -> etree._Element:
    with zipfile.ZipFile(sample) as archive:
        name = next(n for n in archive.namelist() if n.endswith("header.xml"))
        return etree.fromstring(archive.read(name))


def _para_pr_elements(root: etree._Element) -> list[etree._Element]:
    return list(root.iter(f"{HH_NS}paraPr"))


def test_switch_wrapped_margin_is_none_before_the_fix_reproduces_on_real_source() -> None:
    """결함-부활: hp:switch 분기를 안 보는 예전 루프를 흉내내면(직접 자식만),
    실제로 16/16 전부 margin=None이 됐다는 걸 같은 실 소스로 재현한다."""

    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    para_prs = _para_pr_elements(root)
    assert para_prs, "expected at least one hh:paraPr in the fixture"

    def _old_direct_children_only_margin_present(node: etree._Element) -> bool:
        return any(child.tag == f"{HH_NS}margin" for child in node)

    reproduced_none = sum(
        1 for node in para_prs if not _old_direct_children_only_margin_present(node)
    )
    assert reproduced_none == len(para_prs), (
        "expected every paraPr in this fixture to lack a direct hh:margin child "
        "(the pre-fix loop would have left .margin=None for all of them)"
    )


def test_paragraph_property_margin_and_line_spacing_populated_from_switch() -> None:
    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    para_prs = _para_pr_elements(root)

    properties = [parse_paragraph_property(node) for node in para_prs]
    assert len(properties) == 16

    assert all(p.margin is not None for p in properties), (
        "margin should now be populated for every switch-wrapped paraPr, not None"
    )
    assert all(p.line_spacing is not None for p in properties), (
        "line_spacing should now be populated for every switch-wrapped paraPr, not None"
    )
    assert all(p.version_switch is not None for p in properties)

    first = properties[0]
    assert first.line_spacing.spacing_type == "PERCENT"
    assert first.line_spacing.value == 130


def test_version_switch_exposes_required_namespace_and_both_branches() -> None:
    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    node = _para_pr_elements(root)[0]

    prop = parse_paragraph_property(node)
    switch = prop.version_switch
    assert isinstance(switch, ParagraphPropertyVersionSwitch)

    assert switch.required_namespace == "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"
    assert isinstance(switch.case, ParagraphPropertyVersionBranch)
    assert isinstance(switch.default, ParagraphPropertyVersionBranch)
    # 실측(DEV-018): 두 분기 모두 자기 margin/lineSpacing을 갖는다(설계상
    # 값이 갈리는 실사례는 관측 안 됐지만, 접근 자체는 독립적이어야 한다).
    assert switch.case.margin is not None
    assert switch.default.margin is not None
    assert switch.case.line_spacing is not None
    assert switch.default.line_spacing is not None


def test_direct_children_still_take_priority_over_switch_fallback() -> None:
    """대조군: hp:switch가 없는 실 문서는 직접 자식 루프만으로 이미 정확했다
    (이 트레인 전에도 margin=None이 아니었다) -- 폴백 도입이 이 경로를
    바꾸지 않았는지 확인."""

    root = _header_root(DIRECT_CHILD_SAMPLE)
    para_prs = _para_pr_elements(root)
    assert para_prs

    node = para_prs[0]
    assert any(child.tag == f"{HH_NS}margin" for child in node), (
        "expected this fixture's first paraPr to carry a direct hh:margin child"
    )
    assert not any(
        child.tag == "{http://www.hancom.co.kr/hwpml/2011/paragraph}switch" for child in node
    ), "this is meant to be the no-switch control fixture"

    prop = parse_paragraph_property(node)
    assert prop.margin is not None
    assert prop.line_spacing is not None
    assert prop.version_switch is None


def test_full_header_parse_finds_all_switch_wrapped_properties() -> None:
    """단일 hh:paraPr 파서가 아니라 parse_header_element 전체 경로(실
    소비자: doc.styles.paragraph_property, form_fit.measure)로도 같은 결과인지."""

    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    header = parse_header_element(root)

    assert header.ref_list is not None
    assert header.ref_list.para_properties is not None
    properties = header.ref_list.para_properties.properties
    assert len(properties) == 16
    assert all(p.margin is not None and p.line_spacing is not None for p in properties)


def test_switch_wrapped_sample_roundtrip_has_no_a1_loss() -> None:
    """읽기 모델은 직렬화기가 없다(의도적 — 편집은 header_part.py가 살아있는
    트리를 직접 건드린다) -- 이 필드를 추가한 것 자체가 실 문서 open/save
    왕복에 아무 영향이 없어야 한다는 걸 구조적 태그 카운트로 확인."""

    rep = roundtrip_report(SWITCH_WRAPPED_SAMPLE)

    assert rep["reopened"] is True
    assert rep["lost_elements"] == {}
