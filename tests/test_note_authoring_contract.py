from __future__ import annotations

import io
from pathlib import Path

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return HwpxDocument.open(buffer)


class TestGoldShapedEmission:
    """Real-Hancom footnote contract (specs/058 gold reverse): without the
    ctrl wrapper, autoNum, and note styles Hancom does not render notes."""

    def test_note_is_ctrl_wrapped_inside_the_host_run(self) -> None:
        doc = HwpxDocument.new()
        para = doc.add_paragraph("본문 앵커 문장")
        para.add_footnote("각주 본문")
        host_run = para.element.findall(f"{HP}run")[-1]
        ctrl = host_run.find(f"{HP}ctrl")
        assert ctrl is not None
        assert ctrl.find(f"{HP}footNote") is not None
        assert host_run.find(f"{HP}footNote") is None

    def test_note_numbering_is_continuous_per_type(self) -> None:
        doc = HwpxDocument.new()
        p1 = doc.add_paragraph("첫 문단")
        p2 = doc.add_paragraph("둘째 문단")
        f1 = p1.add_footnote("하나")
        f2 = p2.add_footnote("둘")
        e1 = p2.add_endnote("미주 하나")
        assert f1.element.get("number") == "1"
        assert f2.element.get("number") == "2"
        assert e1.element.get("number") == "1"

    def test_note_body_carries_style_autonum_and_suffix(self) -> None:
        doc = HwpxDocument.new()
        para = doc.add_paragraph("앵커")
        note = para.add_footnote("각주 텍스트")
        el = note.element
        assert el.get("suffixChar") == "41"
        sub = el.find(f"{HP}subList")
        assert sub.get("vertAlign") == "TOP"
        body_p = sub.find(f"{HP}p")
        assert body_p.get("styleIDRef") == "15"
        assert body_p.get("paraPrIDRef") == "10"
        run = body_p.find(f"{HP}run")
        assert run.get("charPrIDRef") == "3"
        auto = run.find(f"{HP}ctrl/{HP}autoNum")
        assert auto.get("numType") == "FOOTNOTE"
        assert auto.get("num") == "1"
        fmt = auto.find(f"{HP}autoNumFormat")
        assert fmt.get("suffixChar") == ")"

    def test_endnote_uses_endnote_style_and_numtype(self) -> None:
        doc = HwpxDocument.new()
        note = doc.add_paragraph("앵커").add_endnote("미주")
        body_p = note.element.find(f"{HP}subList/{HP}p")
        assert body_p.get("styleIDRef") == "16"
        auto = body_p.find(f"{HP}run/{HP}ctrl/{HP}autoNum")
        assert auto.get("numType") == "ENDNOTE"

    def test_text_setter_preserves_the_gold_body(self) -> None:
        doc = HwpxDocument.new()
        note = doc.add_paragraph("앵커").add_footnote("원래 텍스트")
        note.text = "고친 텍스트"
        body_p = note.element.find(f"{HP}subList/{HP}p")
        assert body_p.get("styleIDRef") == "15"
        run = body_p.find(f"{HP}run")
        assert run.find(f"{HP}ctrl/{HP}autoNum") is not None
        assert run.find(f"{HP}t").text == "고친 텍스트"


class TestReaderCoversBothShapes:
    # The two Markdown readers of this class moved to python-hwpx-automation in 7.0.

    def test_notes_survive_roundtrip_and_are_discoverable(self) -> None:
        doc = HwpxDocument.new()
        para = doc.add_paragraph("앵커 문장")
        para.add_footnote("왕복 각주")
        reopened = _roundtrip(doc)
        notes = [
            el
            for section in reopened.sections
            for el in section.element.iter(f"{HP}footNote")
        ]
        assert len(notes) == 1
        assert notes[0].get("number") == "1"


class TestNoteNumberFollowsItsSection:
    """A new note's number shape is its section's, as Hancom writes it.

    ``hancom_saved/note_number_section_shape.hwpx``: Hangul 2024 inserted a footnote (its public
    automation, ``InsertFootnote``) in a document whose section numbers footnotes ``[i``
    raised. The note says ``prefixChar="91"`` and no ``suffixChar``, and its ``hp:autoNum``
    carries the section's shape. The notes used to say ``1)`` whatever the section said.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "hancom_saved" / "note_number_section_shape.hwpx"

    @staticmethod
    def _note_shape(section_element) -> tuple[dict[str, str], dict[str, str]]:
        note = next(section_element.iter(f"{HP}footNote"))
        attributes = {key: value for key, value in note.attrib.items() if key in ("number", "prefixChar", "suffixChar")}
        fmt = note.find(f"{HP}subList/{HP}p/{HP}run/{HP}ctrl/{HP}autoNum/{HP}autoNumFormat")
        return attributes, dict(fmt.attrib)

    def test_a_footnote_takes_the_section_shape_as_hancom_writes_it(self) -> None:
        hancom = HwpxDocument.open(self.FIXTURE)
        expected = self._note_shape(hancom.sections[0].element)
        assert expected == (
            {"number": "1", "prefixChar": "91"},
            {"type": "ROMAN_SMALL", "userChar": "", "prefixChar": "[", "suffixChar": "", "supscript": "1"},
        )
        doc = HwpxDocument.new()
        paragraph = doc.add_paragraph("Footnote host sentence")
        doc.page.set_footnote_shape(number_format="ROMAN_SMALL", prefix="[", suffix="", superscript=True)
        doc.notes.add_footnote("note", paragraph=paragraph)
        assert self._note_shape(_roundtrip(doc).sections[0].element) == expected

    def test_superscript_digits_without_a_suffix(self) -> None:
        # what Hangul gives a converted Word document (plain raised digits)
        doc = HwpxDocument.new()
        paragraph = doc.add_paragraph("host")
        doc.page.set_endnote_shape(number_format="DIGIT", prefix="", suffix="", superscript=True)
        note = doc.notes.add_endnote("note", paragraph=paragraph)
        assert "suffixChar" not in note.element.attrib and "prefixChar" not in note.element.attrib
        fmt = note.element.find(f"{HP}subList/{HP}p/{HP}run/{HP}ctrl/{HP}autoNum/{HP}autoNumFormat")
        assert (fmt.get("suffixChar"), fmt.get("supscript")) == ("", "1")

    def test_the_default_section_still_numbers_one_paren(self) -> None:
        doc = HwpxDocument.new()
        note = doc.add_paragraph("host").add_footnote("note")
        assert note.element.get("suffixChar") == "41"
        fmt = note.element.find(f"{HP}subList/{HP}p/{HP}run/{HP}ctrl/{HP}autoNum/{HP}autoNumFormat")
        assert dict(fmt.attrib) == {"type": "DIGIT", "userChar": "", "prefixChar": "", "suffixChar": ")",
                                    "supscript": "0"}
