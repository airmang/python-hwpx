#!/usr/bin/env python3
"""DEV-030 -- a hyperlink's link-colored ``charPr`` applies only to the
display-text run; the ``fieldBegin``/``fieldEnd`` wrapper runs keep
whatever ``charPrIDRef`` surrounded the insertion point. The schema does
not require or even describe this 3-run split.

Schema claim: ``hp:fieldBegin``/``hp:fieldEnd`` are just one ``hp:ctrl``
child each of an ``hp:run`` -- the schema says nothing about hyperlinks
being conventionally split across 3 runs (start control / display text /
end control), nor which of those runs should carry the link's own
``charPrIDRef``.

Real-document measurement: ``oracle: not-applicable`` for the structural
rule itself (it is an authoring convention, not a render fact) --
supported by ``oracle: previously-verified`` real-Hancom gold-corpus
comparison (the 2026-08-01 repair train's "파랑 전염"/blue-contagion
regression history) that
originally surfaced why the wrapper runs must NOT inherit the link
charPr: a later paragraph appended after the link would otherwise inherit
link-blue styling from the fieldEnd wrapper run.

Our handling: ``paragraph.py``'s ``add_hyperlink`` (comment: "링크 서식
(charPr)은 표시 텍스트 런에만 싣고 fieldBegin/fieldEnd 런은 주변 서식을
유지한다") emits exactly this split. This probe builds a hyperlink live
and confirms the run-level charPrIDRef pattern directly.

Run: ``python probes/dev030_hyperlink_charpr_scope.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import tag_local_name

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    ambient_char_pr = "0"
    p.add_hyperlink(
        "https://example.com", "링크텍스트", char_pr_id_ref="9",
    )

    runs = [c for c in p.element if tag_local_name(c.tag) == "run"]
    assert len(runs) >= 3, f"expected at least 3 runs for a hyperlink, got {len(runs)}"

    kinds = []
    for run in runs:
        children = [tag_local_name(c.tag) for c in run]
        char_pr = run.get("charPrIDRef")
        kinds.append((children, char_pr))
    print("run structure (children, charPrIDRef):", kinds)

    ctrl_runs = [(children, cp) for children, cp in kinds if "ctrl" in children]
    text_runs = [(children, cp) for children, cp in kinds if "t" in children and "ctrl" not in children]

    assert ctrl_runs, "expected at least one hp:ctrl (fieldBegin/fieldEnd) wrapper run"
    assert text_runs, "expected at least one plain text run"

    link_text_runs = [cp for _children, cp in text_runs if cp == "9"]
    assert link_text_runs, "expected the display-text run to carry the requested link charPrIDRef"

    for _children, cp in ctrl_runs:
        assert cp == ambient_char_pr, (
            f"expected fieldBegin/fieldEnd wrapper runs to keep the ambient charPrIDRef "
            f"({ambient_char_pr!r}), not the link's own ({cp!r}) -- a wrapper run inheriting "
            f"the link style is exactly the 'blue contagion' regression the 2026-08-01 repair fixed"
        )

    print(f"confirmed {len(ctrl_runs)} fieldBegin/fieldEnd wrapper run(s) kept the ambient "
          f"charPrIDRef={ambient_char_pr!r} while the display-text run alone carries the "
          f"link's charPrIDRef=9")

    print("PASS: DEV-030 reproduced (live 3-run split + charPr scoping)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
