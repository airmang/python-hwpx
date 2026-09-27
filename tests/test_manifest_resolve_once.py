"""Manifest items resolve against the package's part names normalized once, not per item."""

from __future__ import annotations

from lxml import etree

from hwpx.opc import relationships

_OPF = "http://www.idpf.org/2007/opf/"


def _manifest(hrefs: list[str]) -> etree._Element:
    items = "".join(
        f'<opf:item id="item{index}" href="{href}" media-type="image/png"/>' for index, href in enumerate(hrefs)
    )
    return etree.fromstring(
        f'<opf:package xmlns:opf="{_OPF}"><opf:manifest>{items}</opf:manifest><opf:spine/></opf:package>'
    )


def test_resolving_many_items_normalizes_each_part_name_once(monkeypatch) -> None:
    count = 300
    parts = [f"BinData/image{index}.png" for index in range(count)] + ["Contents/content.hpf"]
    manifest = _manifest([f"BinData/image{index}.png" for index in range(count)])
    calls = 0
    normalize = relationships.normalize_part_name

    def counting(path: str) -> str:
        nonlocal calls
        calls += 1
        return normalize(path)

    monkeypatch.setattr(relationships, "normalize_part_name", counting)
    result = relationships.parse_manifest_relationships(manifest, "Contents/content.hpf", known_parts=parts)

    assert [item.resolved_path for item in result.items] == [f"BinData/image{index}.png" for index in range(count)]
    # a few normalizations per item and per part; once per (item, part) pair was 90,000
    assert calls < 10 * count


def test_manifest_items_resolve_as_resolve_part_name_does() -> None:
    parts = ["BinData/a.png", "Contents/b.png", "Contents/section0.xml", "Contents/content.hpf"]
    hrefs = ["BinData/a.png", "b.png", "./b.png", "../BinData/a.png", "/BinData/a.png",
             "Contents\\section0.xml", "missing/c.png", "section0.xml"]

    result = relationships.parse_manifest_relationships(
        _manifest(hrefs), "Contents/content.hpf", known_parts=parts
    )

    assert [item.resolved_path for item in result.items] == [
        relationships.resolve_part_name("Contents/content.hpf", href, known_parts=parts) for href in hrefs
    ]
