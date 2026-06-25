# SPDX-License-Identifier: Apache-2.0
"""Regression: the reader must tolerate XML comment / PI nodes.

``irb_form_blank.hwpx`` is a real, hand-authored IRB form whose ``section0.xml``
contains ``<!-- ... -->`` comments as direct children of ``<hs:sec>``. lxml keeps
comment nodes in the tree and exposes their ``.tag`` as a callable
(``etree.Comment``) rather than a string. Iterating section children and calling
``tag_local_name(child.tag)`` therefore used to crash with::

    AttributeError: '_cython_3_0_12.cython_function_or_method' object
    has no attribute 'startswith'

Comments are not part of the OWPML content model, so the reader must skip them
and still surface the real paragraphs.
"""
from pathlib import Path

from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.oxml import body
from hwpx.oxml.namespaces import tag_local_name, tag_namespace

FIXTURE = Path(__file__).parent / "fixtures" / "reader_robustness" / "irb_form_blank.hwpx"

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def test_open_file_with_comment_nodes_does_not_crash() -> None:
    doc = HwpxDocument.open(FIXTURE)

    # Section children include comment nodes; paragraph enumeration must skip
    # them rather than raise AttributeError.
    section = doc.sections[0]
    paragraphs = section.paragraphs
    assert paragraphs, "expected real <hp:p> paragraphs to be enumerated"

    # The hand-authored comments must not be mistaken for content paragraphs.
    text = doc.export_text()
    assert "연구계획서" in text
    assert "제목 단락" not in text  # comment body must never leak into text


def test_tag_helpers_tolerate_non_string_tags() -> None:
    # Comment / PI nodes expose a callable ``tag``; the helpers must not raise.
    from lxml import etree

    comment = etree.Comment("hello")
    pi = etree.ProcessingInstruction("target", "data")

    assert tag_local_name(comment.tag) == ""
    assert tag_namespace(comment.tag) is None
    assert tag_local_name(pi.tag) == ""
    assert tag_namespace(pi.tag) is None


def test_paragraph_with_comment_child_round_trips() -> None:
    # A comment directly inside <hp:p> used to crash on serialize: the comment
    # became a GenericElement whose callable ``tag`` could not be re-emitted.
    node = etree.fromstring(
        f'<hp:p xmlns:hp="{HP}"><!-- c --><hp:run/></hp:p>'.encode()
    )
    paragraph = body.parse_paragraph_element(node)

    out = body.serialize_paragraph(paragraph)  # must not raise
    children = list(out)
    assert children[0].tag is etree.Comment
    assert children[0].text == " c "
    assert tag_local_name(children[1].tag) == "run"


def test_section_with_comment_and_pi_children_round_trip() -> None:
    # The <hp:sec> equivalent: comment and processing-instruction children land
    # in ``other_children`` and must serialize back faithfully.
    node = etree.fromstring(
        f'<hp:sec xmlns:hp="{HP}"><!-- hello --><?php echo 1?><hp:p/></hp:sec>'.encode()
    )
    section = body.parse_section_element(node)

    serialized = [body._preserved_element_to_xml(child) for child in section.other_children]
    assert serialized[0].tag is etree.Comment
    assert serialized[0].text == " hello "
    assert serialized[1].tag is etree.PI
    assert serialized[1].target == "php"
    assert serialized[1].text == "echo 1"
