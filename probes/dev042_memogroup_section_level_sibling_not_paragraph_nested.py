#!/usr/bin/env python3
"""DEV-042 -- a memo's actual content (``hp:memogroup``) lives at *section*
level, as a sibling of ``hp:p`` elements -- never nested inside the
paragraph that anchors it. Distinct from DEV-034 (which records that
``hp:memo``/``hp:memogroup``/``hp:paraList`` are undeclared element *names*
in the schema) -- this entry is about *where* memogroup structurally sits
relative to paragraphs, a fact DEV-034 does not itself state and that
matters for any code operating on a paragraph subtree in isolation.

Schema claim: none (same root cause as DEV-034 -- the whole memo
subsystem is undeclared, so the schema has nothing to say about
memogroup's position either). This entry exists because "undeclared" does
not by itself warn a caller that memogroup is *structurally reachable only
from the section, not the paragraph* -- a real trap distinct from mere
name-invisibility.

Real-document measurement: live authoring (``doc.notes.add_memo(text,
anchor=paragraph)``) confirmed directly on the section element's own
children -- ``hp:memogroup`` is a direct child of ``hs:sec``, sibling to
the ``hp:p`` elements, never nested inside the anchoring paragraph. The
anchoring paragraph only carries a ``hp:fieldBegin type="MEMO"`` control
whose ``hp:parameters/hp:stringParam name="ID"`` value matches
``hp:memogroup/hp:memo/@id`` -- a cross-reference, not containment.

Our handling: found live while implementing document insertion/merge
(``hwpx.tools.document_merge``, cycle 6.9 train 33) -- that module copies
paragraphs, not whole sections, so naively copying a MEMO-anchoring
paragraph would silently carry the ``fieldBegin`` control across while
leaving the actual memo text (in the sibling ``hp:memogroup``, never
copied) behind. document_merge.py fail-closed rejects any
``fieldBegin type="MEMO"`` found in content being merged rather than risk
this silent loss (``docs/2026-08-08-document-merge-contract.md``'s "보류"
section has the full reasoning). ``doc.notes.add_memo`` itself is
unaffected -- it already operates at the section level, not the paragraph
subtree, so it never hits this gap.

Run: ``python probes/dev042_memogroup_section_level_sibling_not_paragraph_nested.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from hwpx.document import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def main() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("annotated text")
    doc.notes.add_memo("a comment", anchor=paragraph)

    section = doc.sections[0].element
    child_names = [child.tag.rsplit("}", 1)[-1] for child in section]
    print("section direct children:", child_names)
    assert "memogroup" in child_names, (
        "expected hp:memogroup as a direct child of the section -- "
        "DEV-042's premise no longer holds, recheck the deviation entry"
    )

    paragraph_descendant_names = {
        node.tag.rsplit("}", 1)[-1] for node in paragraph.element.iter()
    }
    assert "memogroup" not in paragraph_descendant_names, (
        "found hp:memogroup nested inside the anchoring paragraph -- "
        "DEV-042's premise (section-level sibling, not paragraph-nested) "
        "no longer holds"
    )
    assert "memo" not in paragraph_descendant_names, (
        "found hp:memo nested inside the anchoring paragraph -- same as above"
    )
    assert "fieldBegin" in paragraph_descendant_names, (
        "expected the anchoring paragraph to carry a fieldBegin control "
        "(the cross-reference to the sibling memogroup) even though the "
        "actual memo content itself is not there"
    )
    print(
        "confirmed: hp:memogroup is a section-level sibling of hp:p, "
        "never nested inside the anchoring paragraph -- only a "
        "fieldBegin type=MEMO cross-reference lives there"
    )


if __name__ == "__main__":
    main()
