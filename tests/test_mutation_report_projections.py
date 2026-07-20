"""Safe Write Contract (S-089 P2) — ``as_mutation_report()`` projections.

Each write-path result model projects its own evidence onto the shared
``hwpx.mutation-report/v1`` spine without asserting a layer it never measured
(specs/032 §3, survey §7/§9). These tests pin the field mapping, the tri-state
honesty (an unverified visual is ``not_performed``, never a silent pass), the
real byte ranges a source-backed byte-splice projection produces, and — as
characterization — that the pre-existing ``to_dict()`` outputs are unchanged.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hwpx.agent.model import AgentBatchResult
from hwpx.body_patch import BodyOpsResult
from hwpx.mutation_report import (
    MUTATION_REPORT_SCHEMA,
    MutationReport,
    verification_value,
    visual_value_from_status,
)
from hwpx.patch import BytePreservingPatchResult, paragraph_patch
from hwpx.table_patch import CellFillResult, fill_cells

FORM_002 = Path(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"

_FULL_OPEN_SAFETY = {
    "ok": True,
    "validatePackage": {"ok": True},
    "validateDocument": {"ok": True},
    "reopen": {"ok": True, "error": None},
}


# --------------------------------------------------------------------------- #
# Shared verification helpers — the tri-state honesty in isolation.
# --------------------------------------------------------------------------- #
def test_verification_value_tristate() -> None:
    assert verification_value(True) == "passed"
    assert verification_value(False) == "failed"
    assert verification_value(None) == "not_performed"


def test_visual_value_never_promotes_unverified() -> None:
    assert visual_value_from_status("verified") == "passed"
    assert visual_value_from_status("failed") == "failed"
    # "unverified" (render did not run) and an absent status are NOT a pass.
    assert visual_value_from_status("unverified") == "not_performed"
    assert visual_value_from_status(None) == "not_performed"


# --------------------------------------------------------------------------- #
# BytePreservingPatchResult — byte-splice, patch-grade, real unverified visual.
# --------------------------------------------------------------------------- #
def test_patch_projection_real_ranges_and_measured_preservation() -> None:
    source = FORM_002.read_bytes()
    result = paragraph_patch(
        source,
        [{"section_path": "Contents/section0.xml", "paragraph_index": 0, "text": "테스트"}],
    )
    assert result.applied and not result.skipped

    report = result.as_mutation_report(source=source)
    assert isinstance(report, MutationReport)
    assert report.requested_mode == "patch"
    assert report.actual_mode == "patch"
    assert report.fallback_used is False

    # A single spliced paragraph => one changed part with a real byte span.
    (part,) = report.changed_parts
    assert part.path == "Contents/section0.xml"
    assert part.reason == "dirty-part"
    assert part.ranges is not None
    (span,) = part.ranges
    assert 0 <= span.start < span.end
    assert span.coordinate_space == "uncompressed-part-bytes"

    # Preservation is measured against the source, not asserted.
    assert report.preservation.untouched_part_payloads.changed == 0
    assert report.preservation.untouched_part_payloads.verified > 0
    assert report.preservation.whole_package_identical is False

    # The transparent byte path never renders, so visual is honestly not_performed.
    assert result.visual_complete is not None
    assert result.visual_complete.visual_complete_status == "unverified"
    assert report.verification.visual == "not_performed"
    assert report.verification.open_safety == "passed"


def test_patch_projection_without_source_degrades_honestly() -> None:
    result = BytePreservingPatchResult(
        data=b"PK\x05\x06" + b"\x00" * 18,
        applied=(),
        skipped=(),
        changed_parts=("Contents/section0.xml",),
        byte_identical=False,
        zip_method="deflate",
        open_safety=_FULL_OPEN_SAFETY,
        visual_complete=None,
    )
    report = result.as_mutation_report()
    (part,) = report.changed_parts
    # No source => the model only knows the part name; ranges stay honestly None.
    assert part.ranges is None
    # Untouched layers were never measured => zero-verified, not a claimed pass.
    assert report.preservation.untouched_part_payloads.verified == 0
    assert report.preservation.untouched_local_zip_records.verified == 0
    # wholePackageIdentical still reflects the model's own byte_identical evidence.
    assert report.preservation.whole_package_identical is False
    assert report.verification.visual == "not_performed"


# --------------------------------------------------------------------------- #
# CellFillResult — real form_002 fill projects real ranges (the P2 exemplar).
# --------------------------------------------------------------------------- #
def test_cell_fill_projection_real_ranges_from_form_002() -> None:
    source = FORM_002.read_bytes()
    result = fill_cells(source, [{"table_index": 0, "row": 1, "col": 1, "text": "채움값"}])
    assert result.applied and not result.skipped

    report = result.as_mutation_report(source=source)
    assert report.actual_mode == "patch"
    (part,) = report.changed_parts
    assert part.path == "Contents/section0.xml"
    assert part.ranges is not None
    (span,) = part.ranges
    assert span.start < span.end
    assert span.coordinate_space == "uncompressed-part-bytes"
    # A byte splice leaves every other part byte-identical — and that is measured.
    assert report.preservation.untouched_part_payloads.verified > 0
    assert report.preservation.untouched_part_payloads.changed == 0
    assert report.preservation.untouched_local_zip_records.changed == 0
    assert report.verification.visual == "not_performed"

    # camelCase to_dict survives a JSON round-trip.
    payload = report.to_dict()
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert payload["schemaVersion"] == MUTATION_REPORT_SCHEMA
    assert payload["changedParts"][0]["ranges"][0]["coordinateSpace"] == (
        "uncompressed-part-bytes"
    )


def test_cell_fill_projection_without_source_degrades_honestly() -> None:
    result = CellFillResult(
        data=b"PK\x05\x06" + b"\x00" * 18,
        applied=(),
        skipped=(),
        changed_parts=("Contents/section0.xml",),
        byte_identical=False,
        zip_method="deflate",
        open_safety=_FULL_OPEN_SAFETY,
    )
    report = result.as_mutation_report()
    assert report.changed_parts[0].ranges is None
    assert report.preservation.untouched_part_payloads.verified == 0
    assert report.preservation.whole_package_identical is False
    assert report.verification.visual == "not_performed"


# --------------------------------------------------------------------------- #
# BodyOpsResult — byte-splice, patch-grade, never renders.
# --------------------------------------------------------------------------- #
def test_body_ops_projection() -> None:
    result = BodyOpsResult(
        data=b"PK\x05\x06" + b"\x00" * 18,
        skipped=(),
        transcript=({"op": "replace_text", "hits": 1},),
        changed_parts=("Contents/section0.xml",),
        byte_identical=False,
        open_safety=_FULL_OPEN_SAFETY,
    )
    report = result.as_mutation_report()
    assert report.actual_mode == "patch"
    assert report.fallback_used is False
    assert report.changed_parts[0].path == "Contents/section0.xml"
    assert report.changed_parts[0].ranges is None
    assert report.verification.package == "passed"
    assert report.verification.visual == "not_performed"


# --------------------------------------------------------------------------- #
# AgentBatchResult — rebuild-grade transaction, preservation from _member_diff.
# --------------------------------------------------------------------------- #
def _revision(seed: bytes) -> str:
    return "sha256:" + hashlib.sha256(seed).hexdigest()


def _agent_result(*, real_hancom_status: str) -> AgentBatchResult:
    verification = {
        "bytePreservation": {
            "ok": True,
            "changedMembers": ["Contents/section0.xml"],
            "addedMembers": [],
            "removedMembers": [],
            "unchangedMemberCount": 11,
            "beforeMemberCount": 12,
            "afterMemberCount": 12,
        },
        "openSafety": _FULL_OPEN_SAFETY,
        "realHancom": {
            "required": False,
            "ok": real_hancom_status == "verified",
            "status": real_hancom_status,
            "renderChecked": real_hancom_status != "unverified",
        },
    }
    return AgentBatchResult(
        ok=True,
        rolled_back=False,
        dry_run=False,
        input_revision=_revision(b"in"),
        document_revision=_revision(b"out"),
        output_filename="out.hwpx",
        verification_report=verification,
    )


def test_agent_batch_projection_is_rebuild_grade() -> None:
    report = _agent_result(real_hancom_status="unverified").as_mutation_report()
    assert report.requested_mode == "rebuild"
    assert report.actual_mode == "rebuild"
    assert report.fallback_used is False
    assert report.path == "out.hwpx"

    # Changed members become rebuild-grade changed parts (whole part re-serialized
    # => ranges are None by contract).
    (part,) = report.changed_parts
    assert part.path == "Contents/section0.xml"
    assert part.ranges is None

    # Preservation comes from the already-measured _member_diff.
    assert report.preservation.untouched_part_payloads.verified == 11
    assert report.preservation.untouched_part_payloads.changed == 0
    # _member_diff never inspects ZIP records => that layer stays zero-verified.
    assert report.preservation.untouched_local_zip_records.verified == 0
    assert report.preservation.whole_package_identical is False

    # An unverified oracle is not a silent visual pass.
    assert report.verification.visual == "not_performed"
    assert report.verification.package == "passed"
    assert report.verification.reopen == "passed"


def test_agent_batch_projection_verified_hancom_is_visual_pass() -> None:
    report = _agent_result(real_hancom_status="verified").as_mutation_report()
    assert report.verification.visual == "passed"


def test_agent_batch_projection_missing_evidence_not_performed() -> None:
    # A failure/rolled-back result may carry no verification evidence at all.
    result = AgentBatchResult(
        ok=True,
        rolled_back=False,
        dry_run=True,
        input_revision=_revision(b"in"),
        document_revision=_revision(b"out"),
        output_filename="dry.hwpx",
    )
    report = result.as_mutation_report()
    assert report.changed_parts == ()
    assert report.preservation.untouched_part_payloads.verified == 0
    assert report.preservation.whole_package_identical is False
    assert report.verification.package == "not_performed"
    assert report.verification.open_safety == "not_performed"
    assert report.verification.reopen == "not_performed"
    assert report.verification.visual == "not_performed"


# --------------------------------------------------------------------------- #
# Characterization — the projection is additive; existing to_dict is unchanged.
# --------------------------------------------------------------------------- #
def test_byte_preserving_patch_result_to_dict_unchanged() -> None:
    result = BytePreservingPatchResult(
        data=b"PK",
        applied=(),
        skipped=(),
        changed_parts=("Contents/section0.xml",),
        byte_identical=False,
        zip_method="deflate",
        open_safety={"ok": True},
        visual_complete=None,
    )
    assert result.to_dict() == {
        "ok": True,
        "applied": [],
        "skipped": [],
        "changedParts": ["Contents/section0.xml"],
        "byteIdentical": False,
        "zipMethod": "deflate",
        "openSafety": {"ok": True},
        "visualComplete": None,
    }


def test_cell_fill_result_to_dict_unchanged() -> None:
    result = CellFillResult(
        data=b"PK",
        applied=(),
        skipped=(),
        changed_parts=("Contents/section0.xml",),
        byte_identical=False,
        zip_method="deflate",
        open_safety={"ok": True},
    )
    # No transcript => the key is intentionally absent (byte-for-byte unchanged).
    assert result.to_dict() == {
        "ok": True,
        "applied": [],
        "skipped": [],
        "changedParts": ["Contents/section0.xml"],
        "byteIdentical": False,
        "zipMethod": "deflate",
        "openSafety": {"ok": True},
    }
