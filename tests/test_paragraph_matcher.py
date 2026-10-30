# SPDX-License-Identifier: Apache-2.0
"""The per-ensure matcher preserves recursive structural comparison semantics."""
from copy import deepcopy
from random import Random
import xml.etree.ElementTree as ET

from lxml import etree

from hwpx import HwpxDocument
from hwpx.oxml import _document_primitives as primitives

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
EXT = "{urn:paragraph-matcher:unknown}"


def _tree(random: Random, depth: int = 0) -> ET.Element:
    node = ET.Element(random.choice((HH + "paraPr", HP + "switch", EXT + "unknown")))
    for key in random.sample(("id", "name", "value", EXT + "id", "level"), random.randrange(6)):
        node.set(key, str(random.randrange(4)))
    node.text, node.tail = str(random.randrange(4)), str(random.randrange(4))
    if depth < 3:
        for _ in range(random.randrange(4)):
            node.append(_tree(random, depth + 1))
    return node


def test_compiled_matcher_agrees_with_recursive_comparison_on_varied_trees() -> None:
    random = Random(607)
    for _ in range(150):
        target = _tree(random)
        for ignored in (frozenset(), frozenset({"id"}), frozenset({"id", "name"})):
            matcher = primitives._compile_element_matcher(target, ignore_attrs=ignored)
            for mode in range(7):
                candidate = deepcopy(target)
                nodes = list(candidate.iter())
                node = random.choice(nodes)
                if mode == 0:
                    for child in nodes:
                        child.set("id", "new-identity")
                elif mode == 1:
                    node.set("value", "different")
                elif mode == 2:
                    node.tag = EXT + "changed"
                elif mode == 3:
                    node.append(ET.Element(EXT + "new"))
                elif mode == 4 and len(node):
                    node.remove(node[0])
                elif mode == 5:
                    for child in nodes:
                        child.text, child.tail = "different text", "different tail"
                else:
                    node[:] = list(reversed(node))
                assert matcher(candidate) == primitives._elements_structurally_equal(
                    candidate, target, ignore_attrs=ignored)


def test_comments_and_processing_instructions_keep_their_existing_tag_contract() -> None:
    target = ET.Element(HH + "paraPr")
    target.extend((ET.Comment("first"), ET.ProcessingInstruction("target", "value")))
    candidate = deepcopy(target)
    candidate[0].text = "different"
    matcher = primitives._compile_element_matcher(target, ignore_attrs=frozenset({"id"}))
    assert matcher(candidate) == primitives._elements_structurally_equal(candidate, target, ignore_attrs=frozenset({"id"}))


def test_lookup_skips_matching_entries_without_an_id_and_keeps_the_first_usable_id() -> None:
    properties = ET.Element(HH + "paraProperties")
    target = ET.Element(HH + "paraPr", value="1")
    for id_ in (None, "", "7", "8"):
        candidate = deepcopy(target)
        if id_ is not None:
            candidate.set("id", id_)
        properties.append(candidate)
    assert primitives._find_matching_para_pr(properties, target) == "7"


def test_each_ensure_observes_direct_xml_mutations_and_preserves_unknown_switch_children() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0].element
    properties = header.find(f"{HH}refList/{HH}paraProperties")
    base = next(element for element in properties if element.get("id") == "0")
    extension = base.makeelement(EXT + "unknown", {"opaque": "1"})
    switch = base.makeelement(HP + "switch", {})
    switch.append(base.makeelement(HP + "default", {"opaque": "2"}))
    base.extend((extension, switch))
    before = etree.tostring(base)
    first = document.styles.ensure_paragraph_format(base_para_pr_id="0", margins={"left": 1234})
    chosen = next(element for element in properties if element.get("id") == first)
    assert chosen.find(EXT + "unknown") is not None
    chosen.find(EXT + "unknown").set("opaque", "mutated")
    second = document.styles.ensure_paragraph_format(base_para_pr_id="0", margins={"left": 1234})
    assert second != first
    chosen.find(EXT + "unknown").set("opaque", "1")
    assert document.styles.ensure_paragraph_format(base_para_pr_id="0", margins={"left": 1234}) == first
    assert etree.tostring(base) == before
    reopened = HwpxDocument.open(document.to_bytes())
    saved = next(element for element in reopened.oxml.headers[0].element.iter(HH + "paraPr") if element.get("id") == first)
    assert saved.find(EXT + "unknown").get("opaque") == "1"
    assert saved.findall(HP + "switch")[-1].find(HP + "default").get("opaque") == "2"
