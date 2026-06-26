import os
from pathlib import Path

import pytest

from hwpx.exam.compose import compose_exam_into_form
from hwpx.visual.oracle import MacHancomOracle

FIX = Path(__file__).parent / "fixtures" / "exam"
_SMOKE = bool(os.environ.get("HWPX_MAC_ORACLE_SMOKE")) and MacHancomOracle().available()


@pytest.mark.skipif(not _SMOKE, reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the exam render smoke")
def test_compose_sample_into_A_form_renders_clean(tmp_path):
    out = str(tmp_path / "composed.hwpx")
    md = (FIX / "sample_exam.md").read_text(encoding="utf-8")
    result = compose_exam_into_form(str(FIX / "A_form.hwpx"), md, out)
    assert result.render_checked is True
    assert result.splits == 0           # primary gate: no 문항 straddles a column/page
    assert result.overflow == 0
    assert result.placeholders_ok is True
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
