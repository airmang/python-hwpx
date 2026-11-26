#!/usr/bin/env python3
"""DEV-030 -- a hyperlink's ``fieldBegin`` run keeps whatever ``charPrIDRef``
surrounded the insertion point; the display text and the ``fieldEnd`` run carry
the link's own ``charPrIDRef`` (Hangul puts the ``fieldEnd`` in the link text's
run). The schema does not require or even describe this split.

Schema claim: ``hp:fieldBegin``/``hp:fieldEnd`` are just one ``hp:ctrl``
child each of an ``hp:run`` -- the schema says nothing about hyperlinks
being conventionally split across runs (start control / display text /
end control), nor which of those runs should carry the link's own
``charPrIDRef``.

Real-document measurement: Hangul 2024 importing a Word document with links
(``tests/fixtures/hancom_saved/hyperlink_field_runs_word_import.hwpx``) writes
the ``fieldBegin`` in the run of the text before the link and the ``fieldEnd``
in the link text's run, 4 links out of 4. The 2026-08-01 repair train's
"파랑 전염"/blue-contagion regression (a later paragraph taking the link's
blue) is guarded separately: text appended after the link takes the
paragraph's look, not the fieldEnd run's (python-hwpx 7.0.3 moved the
fieldEnd into the link's shape; up to 7.0.2 it kept the ambient shape).

Our handling: ``paragraph.py``'s ``add_hyperlink`` emits this split. This
probe builds a hyperlink live, confirms the run-level charPrIDRef pattern
and that a run appended after it keeps the ambient shape.

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

    begin_shape = ctrl_runs[0][1]
    end_shape = ctrl_runs[-1][1]
    assert begin_shape == ambient_char_pr, (
        f"expected the fieldBegin run to keep the ambient charPrIDRef ({ambient_char_pr!r}), got {begin_shape!r}"
    )
    assert end_shape == "9", f"expected the fieldEnd run in the link's charPrIDRef (as Hangul writes it), got {end_shape!r}"

    p.add_run(" after")
    appended = [c for c in p.element if tag_local_name(c.tag) == "run"][-1]
    assert appended.get("charPrIDRef") == ambient_char_pr, (
        f"text appended after the link took {appended.get('charPrIDRef')!r} -- the 'blue contagion' "
        f"regression the 2026-08-01 repair fixed"
    )

    print(f"confirmed fieldBegin run charPrIDRef={begin_shape!r}, link text and fieldEnd run "
          f"charPrIDRef=9, appended text {ambient_char_pr!r}")

    print("PASS: DEV-030 reproduced (live run split + charPr scoping, no contagion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
