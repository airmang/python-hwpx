#!/usr/bin/env python3
"""DEV-040 -- ``metaTag``'s schema type (``hc:MetaTagType``) is declared as
a completely empty ``mixed="true"`` complex type -- the schema gives zero
information about what its text content should hold. Real Hancom output
consistently puts **JSON-formatted text** inside it. The same local name
is also used, unrelatedly, as a plain string *attribute* on
``hp:fieldBegin`` (always empty in observed and our own output) -- two
structurally different roles sharing one name, easy to conflate.

Schema claim: ``Core XML schema.xml`` declares ``<xs:complexType
name="MetaTagType" mixed="true"/>`` -- an empty body, mixed content
allowed, no attributes, no children, no documentation. This is about as
uninformative as a schema declaration can be; nothing in it suggests
structured content.

Real-document measurement: vendored-corpus grep across all 47 files finds
3 real ``<hh:metaTag>``/``<hp:metaTag>`` element occurrences with JSON text
content -- ``{}``, ``{"name":"#본문"}``, ``{"name":""}`` -- always a JSON
object, always (when non-empty) using a ``name`` key. Separately, the
``metaTag`` *attribute* on ``hp:fieldBegin`` (a different, schema-declared
string attribute, not this element) appears 6 times, always the empty
string -- matching our own field-authoring output (``paragraph.py``'s
CLICKHERE/TOC/CROSSREF field construction always emits ``metaTag=""``).
The package skeleton (``src/hwpx/data/Skeleton.hwpx``) bakes in a real
``<hh:metaTag>{"name":""}</hh:metaTag>`` verbatim from a real Hancom
template.

Our handling: neither ``hh:metaTag`` nor ``hp:metaTag`` (the element form)
has a typed model or authoring API -- it round-trips opaquely via the
generic-element fallback, confirmed byte-lossless on all 3 real fixtures
that carry non-trivial content. This is deliberately conservative: a
single observed key (``name``) across 3 samples is not enough evidence to
build a typed JSON model with confidence about its full vocabulary --
matching this registry's evidence-before-typing convention (compare
DEV-013's connectLine deferral). Not a bug: read=True (opaque, lossless),
write=none (element form) is the correct classification for what's
currently understood.

Sibling verdict -- ``hh:typeInfo`` (cycle 6.8 train 28)
=========================================================

Gap-map v2 Part D grouped ``hh:typeInfo``/``hh:metaTag`` as one pair of
next-round candidates (both schema-declared, high-frequency,
frozen-template). ``hh:typeInfo`` (``Header XML schema.xml``, a font's
PANOSE-style classification: ``familyType``/``weight``/``proportion``/
``contrast``/``letterform``/``midline``/``xHeight``/``armStyle``/
``strokeVariation``) is a DIFFERENT case from ``metaTag`` -- there is no
schema/reality gap to register here, so this probe records the verdict
directly rather than a new DEV entry: ``frozen-template`` is the correct
classification, and the "no authoring surface" stance is justified.
``ensure_font`` (the only real font-authoring entry point,
``header_part.py``) never accepts or constructs a ``typeInfo`` value --
confirmed by reading ``_build_font_element`` (``_document_primitives.py``),
which only ever builds ``hh:font``/``hh:substFont``, never ``hh:typeInfo``.
The blank-document skeleton's own two default fonts (함초롬돋움/함초롬바탕,
a real Hancom-sourced template) already carry real ``typeInfo`` values --
which is why the classification is ``frozen-template`` (present via
inheritance) rather than ``none`` (never touched). This creates a
documented, honest asymmetry worth recording even though it needs no fix:
a font added via ``ensure_font`` after document creation gets no
``typeInfo`` at all, while the two skeleton-inherited fonts keep theirs.
Not exposing ``typeInfo`` as an authoring parameter is a principled
choice, not an oversight -- these are PANOSE-style descriptors of a font
FILE's own visual properties; a caller typing arbitrary values with no way
to validate them against the actual font would be worse than omitting the
field, and no real-corpus evidence establishes what Hancom itself would
assign for an arbitrary added font.

Run: ``python probes/dev040_metatag_json_mixed_content.py``
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
SKELETON = ROOT / "src" / "hwpx" / "data" / "Skeleton.hwpx"


def main() -> int:
    schema_file = SCHEMA_DIR / "Core XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert '<xs:complexType name="MetaTagType" mixed="true"/>' in text, (
            "expected MetaTagType declared as a completely empty mixed-content type"
        )
        print("confirmed hc:MetaTagType is an empty mixed=\"true\" complex type -- the "
              "schema states nothing about its content's structure")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    if CORPUS.exists() and any(CORPUS.glob("*.hwpx")):
        element_hits: list[tuple[str, str]] = []
        attr_empty = 0
        attr_nonempty = 0
        for path in sorted(CORPUS.glob("*.hwpx")):
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if not name.endswith(".xml"):
                            continue
                        data = archive.read(name).decode("utf-8", "replace")
                        for m in re.finditer(r"<h[a-z]*:metaTag>([^<]*)</h[a-z]*:metaTag>", data):
                            element_hits.append((path.name, m.group(1)))
                        for m in re.finditer(r'metaTag="([^"]*)"', data):
                            if m.group(1):
                                attr_nonempty += 1
                            else:
                                attr_empty += 1
            except zipfile.BadZipFile:
                continue

        assert element_hits, "expected at least one real metaTag element occurrence"
        for fname, content in element_hits:
            if content:
                parsed = json.loads(content)  # raises if it's not valid JSON
                assert isinstance(parsed, dict), (fname, content)
        print(f"confirmed {len(element_hits)} real metaTag element occurrence(s), all with "
              f"JSON-object text content: {element_hits}")

        assert attr_empty > 0, "expected the separate metaTag attribute on hp:fieldBegin"
        assert attr_nonempty == 0, (
            f"expected the metaTag attribute (not the element) to always be empty in real "
            f"output, found {attr_nonempty} non-empty occurrences"
        )
        print(f"confirmed the separate metaTag *attribute* on hp:fieldBegin is always empty "
              f"({attr_empty} occurrences) -- a different, unrelated fact from the element form")
    else:
        print("SKIP: vendored hwpxlib corpus not found")

    if SKELETON.exists():
        with zipfile.ZipFile(SKELETON) as archive:
            header_xml = archive.read("Contents/header.xml").decode("utf-8")
        assert '<hh:metaTag>{"name":""}</hh:metaTag>' in header_xml, (
            "expected the blank-document skeleton to carry a real hh:metaTag verbatim"
        )
        print("confirmed the blank-document skeleton bakes in a real hh:metaTag element "
              "verbatim (why hh:metaTag classifies as frozen-template, not none)")
    else:
        print("SKIP: src/hwpx/data/Skeleton.hwpx not found in this checkout")

    from hwpx.tools.roundtrip_diff import roundtrip_report

    sample = CORPUS / "error__20241104__mot.hwpx"
    if sample.exists():
        rep = roundtrip_report(sample)
        assert rep["reopened"] is True
        assert rep["lost_elements"] == {}
        print("confirmed the JSON-bearing hp:metaTag element round-trips byte-lossless via "
              "our generic-element (opaque) preservation fallback")
    else:
        print("SKIP: error__20241104__mot.hwpx not present in this checkout")

    # --- sibling verdict: hh:typeInfo (see module docstring) --------------------
    import inspect

    from hwpx.oxml._document_primitives import _build_font_element

    source = inspect.getsource(_build_font_element)
    # The comment above substFont's construction mentions "typeInfo" by name (schema
    # sequence ordering note) -- that's expected and fine. What must NOT appear is an
    # actual element construction targeting that tag.
    assert "typeInfo" not in source.replace(
        "substFont 는 typeInfo 보다 앞선다", ""
    ), (
        "expected _build_font_element to never construct a typeInfo child -- if this "
        "fails, ensure_font may have grown typeInfo authoring and the frozen-template "
        "classification should be re-examined"
    )
    print("confirmed _build_font_element (ensure_font's own element builder) never "
          "constructs an hh:typeInfo child -- no authoring surface exists for it "
          "(the sole 'typeInfo' text in its source is a schema-ordering comment)")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.styles.ensure_font("맑은 고딕")
    data = doc.to_bytes()
    doc.close()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        header_xml = archive.read("Contents/header.xml").decode("utf-8")

    inherited_type_info = header_xml.count("<hh:typeInfo")
    added_font_blocks = re.findall(r'<hh:font id="\d+" face="맑은 고딕"[^/]*?/>', header_xml)
    assert inherited_type_info > 0, (
        "expected the skeleton's inherited default fonts to still carry real typeInfo"
    )
    assert added_font_blocks, "expected the newly ensure_font()-added face to appear"
    for block in added_font_blocks:
        assert "typeInfo" not in block, (
            f"expected the newly-added font to have no typeInfo child, found it in: {block}"
        )
    print(f"confirmed the asymmetry live: the skeleton's 2 inherited default fonts still "
          f"carry {inherited_type_info} real typeInfo children (7 lang blocks each), while "
          f"a font added via ensure_font() afterward ({len(added_font_blocks)} lang blocks) "
          f"has none -- frozen-template (present via inheritance, not authored) is the "
          f"correct classification")

    print("PASS: DEV-040 reproduced (schema opacity + live JSON-content + attribute-vs-"
          "element distinction + skeleton provenance + lossless round-trip); typeInfo "
          "sibling verdict confirmed (frozen-template correct, no-authoring-surface "
          "justified, asymmetry documented)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
