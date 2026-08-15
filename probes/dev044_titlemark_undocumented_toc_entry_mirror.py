#!/usr/bin/env python3
"""DEV-044 -- ``hp:titleMark`` *is* declared in the schema (as a legal
``hp:t`` choice-group child, right alongside ``markpenBegin``/``tab``) but
carries zero documentation -- no ``xs:documentation``, nothing hinting at
what it means or which paragraphs it belongs in. The real corpus's 14
occurrences all live inside TOC entry paragraphs, mirroring heading text --
not inside the heading's own paragraph in the body -- which is exactly the
kind of semantic fact a documented schema would normally carry.

Schema claim: ``ParaList XML schema.xml`` declares ``hp:titleMark`` as one
of ``hp:t``'s choice-group children (``minOccurs="1"``, single attribute
``ignore: xs:boolean, default="false"``). Structurally this matches real
output exactly (self-closing child of ``hp:t``). But unlike its neighbor
``tab`` (which carries an ``xs:documentation`` note), ``titleMark`` has none
-- the schema is silent on semantics even though it isn't silent on shape.

Real-document measurement: the vendored corpus's only file containing
``hp:titleMark`` (``error__20250808__2015년_12월_재난안전종합상황_분석_및_
전망.hwpx``) has 14 occurrences, all ``ignore="1"``. Structurally, every
one sits as a self-closing child of ``hp:t``, immediately before a run
that mirrors real heading text -- inside a TOC-page entry paragraph
(several carry paragraph id ``2147483648``, an overflow/sentinel value),
often alongside a numbering-prefix run and a tab-leader/page-number-suffix
run that do NOT get the mark. This differs entirely from what team-lead's
clean GUI re-probe captured (2026-08-11, 3 rounds): applying "차례
숨기기"/"제목 차례 표시" to a document with no existing TOC page inserts
the mark into the section-defining paragraph (a degenerate location) with
a confirmed but context-limited polarity (hide=ignore="0", show=
ignore="1") -- see docs/owpml-deviations.md's DEV-044 entry and
docs/editor-menu-reverse-map.md's "차례 숨기기 / 제목 차례 표시" row for
the full narrative.

Our handling: no dedicated read model, generic ``GenericElement`` opaque
preservation round-trips this element losslessly (unchanged since 6.13).
Authoring stayed deferred through 6.13/6.14 -- not because the sample count
was too small (DEV-021's reason) but because macOS GUI automation has no
way to place the caret inside the paragraph that real usage targets (no
canvas click, no keystroke reaches the document). 6.15 resolved this:
team-lead's Windows box COM pipeline can place the caret via
``SetPos(section, paragraph, pos)``, and three variants confirmed the mark
always lands exactly in the caret's own paragraph (never always p0 -- the
earlier macOS finding was the degenerate case of a caret that couldn't
move). ``HwpxOxmlParagraph.add_title_mark(*, in_toc: bool)`` now exists --
see ``tests/test_title_mark.py`` for the authoring contract.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "hwpxlib_corpus"
    / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
)
SCHEMA_FILE = REPO_ROOT / "DevDoc" / "OWPML SCHEMA" / "ParaList XML schema.xml"

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_XS = "{http://www.w3.org/2001/XMLSchema}"


def _find_titlemark_declaration() -> ET._Element:
    tree = ET.parse(str(SCHEMA_FILE))
    for element in tree.getroot().iter(f"{_XS}element"):
        if element.get("name") == "titleMark":
            return element
    raise AssertionError(
        "hp:titleMark element declaration not found in the vendored schema "
        "-- DEV-044's premise no longer holds, recheck the deviation entry"
    )


def main() -> None:
    declaration = _find_titlemark_declaration()

    ignore_attr = declaration.find(f".//{_XS}attribute[@name='ignore']")
    assert ignore_attr is not None
    assert ignore_attr.get("type") == "xs:boolean"
    assert ignore_attr.get("default") == "false"
    print(
        "confirmed: schema declares hp:titleMark with a single ignore "
        "attribute (xs:boolean, default=false)"
    )

    annotations = declaration.findall(f".//{_XS}annotation")
    assert not annotations, (
        "expected zero xs:annotation/xs:documentation on titleMark's "
        "declaration -- DEV-044's premise (schema declares shape but is "
        "silent on semantics) no longer holds"
    )
    print("confirmed: titleMark's declaration carries no xs:documentation at all")

    with zipfile.ZipFile(FIXTURE) as archive:
        section_xml = archive.read("Contents/section0.xml")
    tree = ET.parse(io.BytesIO(section_xml))
    root = tree.getroot()

    marks = [el for el in root.iter(f"{_HP}titleMark")]
    assert len(marks) == 14, (
        f"expected exactly 14 hp:titleMark occurrences in the real corpus "
        f"file, found {len(marks)} -- DEV-044's premise no longer holds, "
        "recheck the deviation entry"
    )
    print(f"real Hancom output: {len(marks)} hp:titleMark occurrences")

    ignore_values = {mark.get("ignore") for mark in marks}
    assert ignore_values == {"1"}, (
        f"expected all 14 occurrences to have ignore='1', observed values "
        f"{ignore_values} -- DEV-044's premise no longer holds"
    )
    print("confirmed: all 14 occurrences have ignore=\"1\"")

    # Structural check: every titleMark is a self-closing child of hp:t,
    # and the mirrored heading text follows it -- either later in the SAME
    # hp:t (mixed content, one occurrence does this) or in a following
    # sibling run's hp:t (the other 13 do this).
    mirror_found = 0
    for mark in marks:
        t_parent = mark.getparent()
        assert t_parent is not None and t_parent.tag == f"{_HP}t"
        assert mark.text is None and len(mark) == 0  # self-closing, no content

        own_tail_text = (mark.tail or "").strip()
        if own_tail_text:
            mirror_found += 1
            continue

        run = t_parent.getparent()
        assert run is not None and run.tag == f"{_HP}run"
        paragraph = run.getparent()
        assert paragraph is not None and paragraph.tag == f"{_HP}p"
        siblings = list(paragraph)
        run_index = siblings.index(run)
        following_runs = [
            el for el in siblings[run_index + 1 :] if el.tag == f"{_HP}run"
        ]
        assert following_runs, "expected a following run mirroring heading text"
        mirror_text_el = following_runs[0].find(f"{_HP}t")
        if mirror_text_el is not None and (mirror_text_el.text or "").strip():
            mirror_found += 1

    assert mirror_found == 14, (
        f"expected all 14 titleMark occurrences to precede text mirroring "
        f"a heading, only {mirror_found} did -- DEV-044's premise no "
        "longer holds"
    )
    print(
        "confirmed: all 14 occurrences sit inside a TOC-entry paragraph, "
        "immediately before text mirroring a heading (13 as a following "
        "sibling run, 1 as mixed content in the same hp:t)"
    )

    # Confirm our handling: read stays opaque preservation (no dedicated
    # read model); authoring now exists on the paragraph itself (6.15 --
    # caret-paragraph targeting confirmed via Windows box COM SetPos,
    # see docs/owpml-deviations.md DEV-044's updated status).
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    assert not hasattr(doc.page, "add_title_mark")
    assert not hasattr(doc.page, "set_title_mark")
    paragraph = doc.add_paragraph("제목")
    assert hasattr(paragraph, "add_title_mark")
    result = paragraph.add_title_mark(in_toc=True)
    mark_tag = f"{_HP}titleMark"
    assert result.element.tag == mark_tag
    assert result.element.get("ignore") == "1"
    print(
        "confirmed: read stays opaque preservation (doc.page has no "
        "titleMark verb), authoring now lives on the paragraph itself "
        "(add_title_mark, 6.15)"
    )


if __name__ == "__main__":
    main()
