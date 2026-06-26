import os
from pathlib import Path

import pytest

from hwpx.exam.compose import compose_exam_into_form
from hwpx.visual.oracle import MacHancomOracle

FIX = Path(__file__).parent / "fixtures" / "exam"
_SMOKE = bool(os.environ.get("HWPX_MAC_ORACLE_SMOKE")) and MacHancomOracle().available()


@pytest.mark.skipif(not _SMOKE, reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the exam render smoke")
def test_compose_sample_into_A_form_is_honestly_unverified(tmp_path):
    # The real 원안지 form exports its body text as vector curves, so the
    # text-glyph gate cannot extract the composed 문항 (measured: 0 of 14 found).
    # The honest contract (Constitution V) is render_checked=True (Hancom DID
    # render) + splits=None (UNVERIFIABLE, never a silent 0) + needs_review, with
    # the reason recorded. The composition itself is verified VISUALLY (the
    # rendered image under specs/003-exam-typesetting/evidence/p2-composer-render/).
    out = str(tmp_path / "composed.hwpx")
    md = (FIX / "sample_exam.md").read_text(encoding="utf-8")
    result = compose_exam_into_form(str(FIX / "A_form.hwpx"), md, out)
    assert result.render_checked is True       # Hancom opened + rendered (no 손상)
    assert result.splits is None               # curve-export form: never a silent 0
    assert result.needs_review is True
    assert any("UNVERIFIABLE" in n or "curve-export" in n for n in result.notes)
    assert Path(out).exists()


def test_compose_without_oracle_is_honest_unverified(tmp_path):
    out = str(tmp_path / "composed.hwpx")
    md = (FIX / "sample_exam.md").read_text(encoding="utf-8")
    from hwpx.visual.oracle import NullOracle
    result = compose_exam_into_form(str(FIX / "A_form.hwpx"), md, out, oracle=NullOracle())
    assert result.render_checked is False
    assert result.needs_review is True
    assert result.splits is None        # never a silent 0
    assert Path(out).exists()           # keepWithNext composition still produced a file
