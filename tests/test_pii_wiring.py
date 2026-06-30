# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_markdown, export_text
from hwpx.tools.mail_merge import mail_merge
from hwpx.tools.pii import DEFAULT_POLICY


RRN = "900101-2345678"
MASKED_RRN = "900101-2******"
PHONE = "010-1234-5678"
MASKED_PHONE = "010-****-****"
EMAIL = "a.b@example.com"
MASKED_EMAIL = "a****@example.com"


def _save_template(path: Path) -> None:
    doc = HwpxDocument.new()
    try:
        doc.add_paragraph("주민번호: {{rrn}}")
        doc.add_paragraph("연락처: {{phone}}")
        doc.add_paragraph("이메일: {{email}}")
        doc.save_to_path(path)
    finally:
        doc.close()


def _export_text(path: str | Path) -> str:
    doc = HwpxDocument.open(path)
    try:
        return doc.export_text()
    finally:
        doc.close()


def test_mail_merge_masks_pii_by_default(tmp_path: Path) -> None:
    template = tmp_path / "template.hwpx"
    _save_template(template)

    report = mail_merge(
        template,
        [{"rrn": RRN, "phone": PHONE, "email": EMAIL}],
        output_dir=tmp_path / "out",
    )

    text = _export_text(report["rows"][0]["filename"])
    assert MASKED_RRN in text
    assert MASKED_PHONE in text
    assert MASKED_EMAIL in text
    assert RRN not in text
    assert PHONE not in text
    assert EMAIL not in text
    assert set(report["rows"][0]["maskedFields"]) == {"email", "phone", "rrn"}


def test_mail_merge_can_disable_pii_masking(tmp_path: Path) -> None:
    template = tmp_path / "template.hwpx"
    _save_template(template)

    report = mail_merge(
        template,
        [{"rrn": RRN, "phone": PHONE, "email": EMAIL}],
        output_dir=tmp_path / "out",
        masking_policy=None,
    )

    text = _export_text(report["rows"][0]["filename"])
    assert RRN in text
    assert PHONE in text
    assert EMAIL in text
    assert MASKED_RRN not in text
    assert MASKED_PHONE not in text
    assert MASKED_EMAIL not in text
    assert report["rows"][0]["maskedFields"] == []


def test_export_text_and_markdown_mask_pii_only_when_requested() -> None:
    doc = HwpxDocument.new()
    try:
        doc.add_paragraph(f"연락처: {PHONE}")
        table = doc.add_paragraph("").add_table(1, 2)
        table.cell(0, 0).text = f"주민번호 {RRN}"
        table.cell(0, 1).text = f"이메일 {EMAIL}"

        plain_text = export_text(doc)
        plain_markdown = export_markdown(doc)
        assert PHONE in plain_text
        assert RRN in plain_text
        assert EMAIL in plain_markdown

        masked_text = export_text(doc, masking_policy=DEFAULT_POLICY)
        masked_markdown = export_markdown(doc, masking_policy=DEFAULT_POLICY)
        assert MASKED_PHONE in masked_text
        assert MASKED_RRN in masked_text
        assert MASKED_EMAIL in masked_markdown
        assert PHONE not in masked_text
        assert RRN not in masked_text
        assert EMAIL not in masked_markdown
    finally:
        doc.close()
