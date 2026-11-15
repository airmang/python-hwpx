"""rich Markdown 내보내기의 이름 지정 순회가 예전(모든 요소의 이름 비교)과 같은 요소를 고른다."""

from __future__ import annotations

from lxml import etree

from hwpx.tools import markdown_export as me

_XML = b"""<root xmlns:hp="urn:hp" xmlns:x="urn:x">
  <hp:p id="1"><hp:run><hp:t>a</hp:t></hp:run><!-- note --><?pi x?>
    <x:p id="2"/>
    <p id="3"/>
  </hp:p>
  <hp:run/>
</root>"""


def _old_descendants(element, name):
    return [c for c in element.iter() if c is not element and me._local_name(c) == name]


def _old_children(element, name):
    return [c for c in list(element) if me._local_name(c) == name]


def test_descendants_match_every_namespace_and_none() -> None:
    root = etree.fromstring(_XML)
    for name in ("p", "run", "t", "missing"):
        assert me._descendants(root, name) == _old_descendants(root, name)
        assert me._direct_children(root, name) == _old_children(root, name)
    outer = root[0]
    # 요소 자신은 고르지 않는다
    assert outer not in me._descendants(outer, "p")
    assert [p.get("id") for p in me._descendants(outer, "p")] == ["2", "3"]
    assert me._first_descendant(outer, "p").get("id") == "2"
    assert me._first_descendant(outer, "missing") is None
