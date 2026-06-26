import io
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HH

FIXTURE = Path(__file__).parent / "fixtures" / "glyph_overlap" / "slot_clean.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(document.to_bytes()))


def test_ensure_paragraph_format_writes_keep_together_break_setting():
    document = HwpxDocument.open(FIXTURE)
    header = document.oxml.headers[0]

    new_id = header.ensure_paragraph_format(
        break_setting={"keep_with_next": True, "keep_lines": True},
    )
    assert new_id is not None

    # The new paraPr must carry a breakSetting with the keep flags ON.
    para_pr = header.element.find(f".//{HH}paraPr[@id='{new_id}']")
    assert para_pr is not None
    break_setting = para_pr.find(f"{HH}breakSetting")
    assert break_setting is not None
    assert break_setting.get("keepWithNext") == "1"
    assert break_setting.get("keepLines") == "1"

    # Lossless: the flags survive a save/reopen round-trip.
    reopened = _reopen(document)
    rt = reopened.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{new_id}']")
    assert rt.find(f"{HH}breakSetting").get("keepWithNext") == "1"
    assert rt.find(f"{HH}breakSetting").get("keepLines") == "1"


def test_paragraph_can_carry_column_break():
    document = HwpxDocument.open(FIXTURE)
    section = document.sections[0]
    para = section.add_paragraph("다음 단으로", columnBreak="1")
    assert para.element.get("columnBreak") == "1"

    reopened = _reopen(document)
    last = reopened.sections[0].paragraphs[-1]
    assert last.element.get("columnBreak") == "1"
