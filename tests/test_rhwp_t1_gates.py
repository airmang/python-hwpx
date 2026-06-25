"""T1 correctness gates absorbed from the rhwp competitive analysis.

Covers five changes:
  1. Bug fix: validator accepts HWP201X target + head version 1.5 (our own
     Skeleton/fixtures use these, so blank docs no longer self-warn).
  2. Bug fix: font isEmbedded reader tolerant of the single-d 'isEmbeded' spelling.
  3. Two-round idempotence (fixed-point) gate.
  4. Builder Document.verify() dry, no-disk pre-write verification.
  5. FIDELITY_CONTRACT allow-list surfaced in reports.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from hwpx.document import HwpxDocument

HEAD = "http://www.hancom.co.kr/hwpml/2011/head"


# --------------------------------------------------------------------------- #
# 1. Bug: HWP201X target + head version 1.5 must not warn (self-contradiction) #
# --------------------------------------------------------------------------- #
from hwpx.tools import package_validator as pv


def _head(target: str | None, version: str | None) -> ET.Element:
    root = ET.Element(f"{{{HEAD}}}head")
    if version is not None:
        root.set("version", version)
    if target is not None:
        compat = ET.SubElement(root, f"{{{HEAD}}}compatibleDocument")
        compat.set("targetProgram", target)
    else:
        ET.SubElement(root, f"{{{HEAD}}}compatibleDocument")
    return root


def _header_warnings(target: str | None, version: str | None) -> list[str]:
    issues: list[pv.PackageValidationIssue] = []
    pv._check_header_editor_acceptance(issues, pv.HEADER_PATH, _head(target, version))
    return [str(i) for i in issues]


def test_accepted_target_and_version_sets() -> None:
    assert "HWP201X" in pv.ACCEPTED_HANCOM_TARGETS
    assert "HWP2018" in pv.ACCEPTED_HANCOM_TARGETS
    assert "1.5" in pv.ACCEPTED_HEAD_VERSIONS
    assert "1.4" in pv.ACCEPTED_HEAD_VERSIONS


@pytest.mark.parametrize("target", ["HWP201X", "HWP2018"])
@pytest.mark.parametrize("version", ["1.4", "1.5"])
def test_known_target_and_version_do_not_warn(target: str, version: str) -> None:
    warnings = _header_warnings(target, version)
    assert not any("targetProgram" in w for w in warnings), warnings
    assert not any("head version" in w for w in warnings), warnings


def test_unknown_target_and_version_still_warn() -> None:
    warnings = _header_warnings("HWP9999", "9.9")
    assert any("targetProgram" in w for w in warnings), warnings
    assert any("head version" in w for w in warnings), warnings


# --------------------------------------------------------------------------- #
# 2. Bug: font isEmbedded reader tolerant of single-d 'isEmbeded' spelling     #
# --------------------------------------------------------------------------- #
from lxml import etree as let  # noqa: E402

from hwpx.oxml.header import parse_font, parse_font_substitution  # noqa: E402


def _font(attr: str | None) -> let._Element:
    node = let.Element(f"{{{HEAD}}}font", id="1", face="Batang")
    if attr is not None:
        node.set(attr, "1")
    return node


def test_font_embed_flag_double_d_spelling() -> None:
    assert parse_font(_font("isEmbedded")).is_embedded is True


def test_font_embed_flag_single_d_spelling() -> None:
    # Hancom/OWPML reference uses the single-d 'isEmbeded' on some output.
    assert parse_font(_font("isEmbeded")).is_embedded is True


def test_font_embed_flag_absent_defaults_false() -> None:
    assert parse_font(_font(None)).is_embedded is False


def test_subst_font_embed_flag_single_d_spelling() -> None:
    node = let.Element(f"{{{HEAD}}}substFont", face="Gulim", type="ttf")
    node.set("isEmbeded", "1")
    assert parse_font_substitution(node).is_embedded is True


# --------------------------------------------------------------------------- #
# 3 + 4 + 5. Idempotence gate, verify(), and fidelity contract via the builder #
# --------------------------------------------------------------------------- #
def _sample_document():
    from hwpx.builder import Document, Heading, Paragraph, Section, Table

    return Document(
        sections=[
            Section(
                children=[
                    Heading(text="제목", level=1),
                    Paragraph(text="첫 문단"),
                    Table(rows=[["A", "B"], ["1", "2"]]),
                    Paragraph(text="끝 문단"),
                ]
            )
        ]
    )


def test_check_save_idempotent_on_builder_output() -> None:
    from hwpx.tools.idempotence import IdempotenceReport, check_save_idempotent

    data = _sample_document().lower().to_bytes()
    report = check_save_idempotent(data)
    assert isinstance(report, IdempotenceReport)
    assert report.ok, report.summary()
    assert report.changed_parts == ()
    assert report.added_parts == ()
    assert report.removed_parts == ()
    # round-trippable to_dict
    assert report.to_dict()["ok"] is True


def test_check_save_idempotent_accepts_document_object() -> None:
    from hwpx.tools.idempotence import check_save_idempotent

    document = _sample_document().lower()
    assert check_save_idempotent(document).ok


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_check_idempotent_pair_identical_is_ok() -> None:
    from hwpx.tools.idempotence import check_idempotent_pair

    blob = _zip_bytes([("a.xml", b"<a/>"), ("b.xml", b"<b/>")])
    assert check_idempotent_pair(blob, blob).ok


def test_check_idempotent_pair_detects_changed_added_removed() -> None:
    from hwpx.tools.idempotence import check_idempotent_pair

    first = _zip_bytes([("a.xml", b"<a/>"), ("b.xml", b"<b/>")])
    second = _zip_bytes([("a.xml", b"<a CHANGED/>"), ("c.xml", b"<c/>")])
    report = check_idempotent_pair(first, second)
    assert not report.ok
    assert report.changed_parts == ("a.xml",)
    assert report.added_parts == ("c.xml",)
    assert report.removed_parts == ("b.xml",)


@pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")
def test_check_idempotent_pair_flags_duplicate_entry_names() -> None:
    # A duplicate ZIP entry name must not silently collapse into a pass.
    from hwpx.tools.idempotence import check_idempotent_pair

    clean = _zip_bytes([("a.xml", b"<a/>")])
    dup = _zip_bytes([("a.xml", b"<a/>"), ("a.xml", b"<a/>")])
    report = check_idempotent_pair(clean, dup)
    assert not report.ok
    assert "a.xml" in report.changed_parts


def test_builder_verify_is_green() -> None:
    document = _sample_document()
    report = document.verify()

    assert report.ok
    assert report.reopen_ok
    assert report.package_ok
    assert report.document_ok
    assert report.editor_open_safety_ok
    assert report.id_integrity_ok
    assert report.idempotent
    assert report.section_count >= 1
    assert report.paragraph_count >= 1
    assert report.byte_length > 0
    assert report.reopen_error is None
    assert report.serialize_error is None


def test_builder_verify_is_dry_never_writes(monkeypatch) -> None:
    # verify() must reach a verdict without ever going through a file-save path.
    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("verify() must not write a file")

    monkeypatch.setattr(HwpxDocument, "save_to_path", _boom)
    monkeypatch.setattr(HwpxDocument, "save_to_stream", _boom)
    report = _sample_document().verify()
    assert report.ok


def test_builder_verify_reports_serialize_failure_instead_of_raising(monkeypatch) -> None:
    # A document whose serialization fails must yield ok=False, not an exception.
    def _raise(self):
        raise ValueError("synthetic open-safety rejection")

    monkeypatch.setattr(HwpxDocument, "to_bytes", _raise)
    report = _sample_document().verify()
    assert report.ok is False
    assert report.serialize_error is not None
    assert "ValueError" in report.serialize_error


def test_builder_verify_to_dict_carries_fidelity_contract() -> None:
    payload = _sample_document().verify().to_dict()
    assert payload["ok"] is True
    contract = payload["fidelity_contract"]
    assert contract["proves"]
    assert contract["does_not_prove"]
    assert any("idempotent" in line for line in contract["proves"])
    assert any("visual" in line.lower() for line in contract["does_not_prove"])


def test_save_report_to_dict_carries_fidelity_contract(tmp_path) -> None:
    path = tmp_path / "builder-fidelity.hwpx"
    report = _sample_document().save_to_path(path)
    payload = report.to_dict()
    assert "fidelity_contract" in payload
    assert payload["fidelity_contract"]["proves"]
    assert payload["fidelity_contract"]["does_not_prove"]


def test_fidelity_contract_constant_shape() -> None:
    from hwpx.builder import FIDELITY_CONTRACT

    assert set(FIDELITY_CONTRACT) == {"proves", "does_not_prove"}
    assert all(isinstance(line, str) for line in FIDELITY_CONTRACT["proves"])
    assert all(isinstance(line, str) for line in FIDELITY_CONTRACT["does_not_prove"])


# --------------------------------------------------------------------------- #
# Canonical OWPML default "traps" — single audited, test-locked table          #
# --------------------------------------------------------------------------- #
def test_canonical_default_traps_are_locked() -> None:
    from hwpx.oxml import canonical_defaults as cd

    # The four non-obvious defaults that silently corrupt if emitted wrong.
    assert cd.CHAR_PR_ID_REF_UNSET == 0xFFFFFFFF == 4294967295
    assert cd.CELL_COL_SPAN_DEFAULT == 1
    assert cd.CELL_ROW_SPAN_DEFAULT == 1
    assert cd.PARA_SHAPE_SNAP_TO_GRID_DEFAULT is True
    assert cd.NUMBERING_START_DEFAULT == 1
    # FONTFACELANGTYPE ordinal order is load-bearing.
    assert cd.FONTFACE_LANGS[0] == "HANGUL"
    assert cd.FONTFACE_LANGS[1] == "LATIN"


def test_id_integrity_sentinel_sourced_from_canonical_defaults() -> None:
    # The charPrIDRef "unset" sentinel must come from the single audited table,
    # not a scattered magic literal.
    from hwpx.oxml.canonical_defaults import CHAR_PR_ID_REF_UNSET
    from hwpx.tools.id_integrity import _ALLOWED_SENTINELS

    assert str(CHAR_PR_ID_REF_UNSET) in _ALLOWED_SENTINELS["charPrIDRef"]
