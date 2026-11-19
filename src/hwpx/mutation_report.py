# SPDX-License-Identifier: Apache-2.0
"""Safe Write Contract — ``hwpx.mutation-report/v1`` and its measurement spine.

The report is *measured, not asserted* (specs/032 §2, survey §6 risk 3). A save
serializes only its dirty parts (the "predeclared" set) and leaves every other
part's uncompressed payload verbatim; this module compares the built archive
against the pre-save part payloads to produce three separated preservation
layers — untouched part payloads, untouched local ZIP records, and (no-op only)
whole-package identity — plus the changed-part list that classifies each change
as a predeclared ``dirty-part`` or an ``unexpected`` one.

Byte-identity claims are scoped to *uncompressed per-part* content; whole-archive
byte-equality is never promised (deflate/producer differences, survey §2d).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from dataclasses import dataclass, field
from io import BytesIO
from .opc.security import guard_zip_file, open_archive, read_member
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence
from zipfile import ZipInfo

from .errors import HwpxError

if TYPE_CHECKING:
    from .opc.zip_records import ZipRecords
    from .quality.report import VisualCompleteReport
    from .tools.package_validator import EditorOpenSafetyReport

MUTATION_REPORT_SCHEMA = "hwpx.mutation-report/v1"
COORDINATE_SPACE = "uncompressed-part-bytes"

Mode = Literal["patch", "rebuild", "auto"]
Fallback = Literal["error", "rebuild"]
VerificationValue = Literal["passed", "failed", "not_performed"]

# The ZIP local-record fields a preserved (untouched) part is expected to carry
# through unchanged — exactly the set ``HwpxPackage._zip_info_for_write`` copies
# from the original entry. Content-derived fields (CRC, sizes) are excluded: an
# untouched part's uncompressed content is identical so they cannot drift, and
# ``compress_size`` legitimately varies with the deflater.
_PRESERVED_ZIP_FIELDS = (
    "date_time",
    "compress_type",
    "comment",
    "extra",
    "create_system",
    "create_version",
    "extract_version",
    "flag_bits",
    "volume",
    "internal_attr",
    "external_attr",
)


# --------------------------------------------------------------------------- #
# Shared member-diff spine (the agent layer's ``_member_diff`` reuses this).
# --------------------------------------------------------------------------- #
def read_archive_members(data: bytes) -> dict[str, bytes]:
    """Return the uncompressed content of every non-directory member of *data*."""

    with open_archive(data) as archive:
        guard_zip_file(archive)
        return {
            info.filename: read_member(archive, info)
            for info in archive.infolist()
            if not info.is_dir()
        }


def read_archive_infos(data: bytes) -> dict[str, ZipInfo]:
    """Return the :class:`ZipInfo` of every non-directory member of *data*."""

    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {info.filename: info for info in archive.infolist() if not info.is_dir()}


def diff_members(
    before: Mapping[str, bytes], after: Mapping[str, bytes]
) -> dict[str, Any]:
    """Compare two name→payload maps at uncompressed-content level."""

    old_names = set(before)
    new_names = set(after)
    shared = sorted(old_names & new_names)
    changed = [name for name in shared if before[name] != after[name]]
    unchanged = len(shared) - len(changed)
    return {
        "ok": True,
        "changedMembers": changed,
        "addedMembers": sorted(new_names - old_names),
        "removedMembers": sorted(old_names - new_names),
        "unchangedMemberCount": unchanged,
        "beforeMemberCount": len(old_names),
        "afterMemberCount": len(new_names),
    }


def member_diff_bytes(before: bytes, after: bytes) -> dict[str, Any]:
    """Diff two HWPX archives at uncompressed-member level, fail-soft on bad ZIPs."""

    try:
        return diff_members(read_archive_members(before), read_archive_members(after))
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# Report models (house convention: frozen dataclass, ok-property, camelCase
# to_dict).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ByteRange:
    """A spliced byte span inside a part's uncompressed payload."""

    start: int
    end: int
    coordinate_space: str = COORDINATE_SPACE

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "coordinateSpace": self.coordinate_space,
        }


@dataclass(frozen=True)
class ChangedPart:
    """One part whose uncompressed payload changed on this save.

    ``ranges`` is ``None`` for rebuild-grade parts (fully re-serialized — the
    whole payload is the change); a byte-splice family fills it with the spliced
    spans. ``reason`` is ``"dirty-part"`` when the part was predeclared by
    ``serialize()`` and ``"unexpected"`` otherwise.
    """

    path: str
    reason: str
    ranges: tuple[ByteRange, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "ranges": (
                None if self.ranges is None else [r.to_dict() for r in self.ranges]
            ),
        }


@dataclass(frozen=True)
class PreservationCounts:
    """Verified-vs-changed tally for one preservation layer."""

    verified: int
    changed: int

    def to_dict(self) -> dict[str, Any]:
        return {"verified": self.verified, "changed": self.changed}


@dataclass(frozen=True)
class PreservationSummary:
    """The three separated preservation guarantees (specs/032 §2).

    Measured against the source archive's bytes (a document opened from a file), ``untouched_local_zip_records``
    counts the untouched parts whose whole local ZIP record -- header, compressed bytes, data descriptor -- is
    the source's byte for byte, and ``whole_package_identical`` is whether the written file is the source file.
    ``zip_records_rewritten`` is set when the save could not keep the source's records at all and compressed
    every entry again; it says why (``"zip64"``, ``"duplicate-entry-names"``, ...). ``to_dict()`` adds a
    ``zipRecordsRewritten`` key only then.

    ``output_read_back`` is ``False`` when the save wrote to a stream that refused to be read back: what
    the stream holds was not checked, so ``whole_package_identical`` is ``False`` too (it is never claimed
    unchecked). ``to_dict()`` adds ``"outputReadBack": false`` only then."""

    untouched_part_payloads: PreservationCounts
    untouched_local_zip_records: PreservationCounts
    whole_package_identical: bool
    zip_records_rewritten: str | None = None
    output_read_back: bool = True

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "untouchedPartPayloads": self.untouched_part_payloads.to_dict(),
            "untouchedLocalZipRecords": self.untouched_local_zip_records.to_dict(),
            "wholePackageIdentical": self.whole_package_identical,
        }
        if self.zip_records_rewritten is not None:
            data["zipRecordsRewritten"] = self.zip_records_rewritten
        if not self.output_read_back:
            data["outputReadBack"] = False
        return data


@dataclass(frozen=True)
class VerificationSummary:
    """What the save pipeline actually ran, as passed/failed/not_performed.

    ``not_performed`` is never blurred into a silent pass (specs/032 §2, No
    Silent True).
    """

    package: VerificationValue
    open_safety: VerificationValue
    reopen: VerificationValue
    visual: VerificationValue

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "openSafety": self.open_safety,
            "reopen": self.reopen,
            "visual": self.visual,
        }


@dataclass(frozen=True)
class MutationReport:
    """The ``hwpx.mutation-report/v1`` receipt for one save.

    ``quality`` is the :class:`~hwpx.quality.VisualCompleteReport` of the quality
    gate a ``doc.save(..., quality=policy)`` ran (``None`` when the save ran the
    transparent gate). ``to_dict()`` adds a ``quality`` key only when it is set,
    so the schema's required keys stay as they are.

    ``editor_open_safety`` is the :class:`~hwpx.EditorOpenSafetyReport` the save
    reached for the archive it wrote -- what ``validate_editor_open_safety`` gives
    for those bytes, without running it again (for an ``.hwp`` save, the HWPX it
    was made from). A save that returns has passed it; ``verification.open_safety``
    says so in one word. ``None`` only for a receipt not made by ``doc.save``.
    ``to_dict()`` leaves it out (``report.editor_open_safety.to_dict()`` gives it).
    """

    requested_mode: Mode
    actual_mode: Literal["patch", "rebuild"]
    fallback_used: bool
    changed_parts: tuple[ChangedPart, ...]
    preservation: PreservationSummary
    verification: VerificationSummary
    path: str | None = None
    quality: "VisualCompleteReport | None" = None
    editor_open_safety: "EditorOpenSafetyReport | None" = field(default=None, compare=False)
    schema_version: str = field(default=MUTATION_REPORT_SCHEMA, init=False)

    @property
    def ok(self) -> bool:
        return "failed" not in (
            self.verification.package,
            self.verification.open_safety,
            self.verification.reopen,
            self.verification.visual,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "ok": self.ok,
            "path": self.path,
            "requestedMode": self.requested_mode,
            "actualMode": self.actual_mode,
            "fallbackUsed": self.fallback_used,
            "changedParts": [part.to_dict() for part in self.changed_parts],
            "preservation": self.preservation.to_dict(),
            "verification": self.verification.to_dict(),
        }
        if self.quality is not None:
            data["quality"] = self.quality.to_dict()
        return data


class PreservationDowngradeError(HwpxError):
    """Raised when a requested preservation grade is not achieved and
    ``fallback="error"`` — before any output is written (specs/032 §1).

    Structured on the :class:`~hwpx.errors.HwpxError` base: ``code`` is the stable
    ``"preservation-downgrade"`` identifier, ``context`` carries the measured
    modes and offending parts, and ``suggestion`` is the actionable next step.
    The historical positional attributes (``requested_mode``/``achieved_grade``/
    ``offending_parts``/``suggestion``) are preserved so existing handlers still
    read them.
    """

    default_code = "preservation-downgrade"

    def __init__(
        self,
        *,
        requested_mode: Mode,
        achieved_grade: Literal["patch", "rebuild"],
        offending_parts: tuple[str, ...],
        suggestion: str,
    ) -> None:
        self.requested_mode = requested_mode
        self.achieved_grade = achieved_grade
        self.offending_parts = offending_parts
        parts = ", ".join(offending_parts) if offending_parts else "(none)"
        super().__init__(
            f"requested mode {requested_mode!r} needs patch-grade preservation but "
            f"the save achieved {achieved_grade!r}; offending parts: {parts}. "
            f"{suggestion}",
            code=self.default_code,
            context={
                "requestedMode": requested_mode,
                "achievedGrade": achieved_grade,
                "offendingParts": list(offending_parts),
            },
            suggestion=suggestion,
        )


# --------------------------------------------------------------------------- #
# Measurement — build a report body from a source snapshot + the built archive.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PreservationMeasurement:
    """Post-build measurement decoupled from the write/verification outcome."""

    changed_parts: tuple[ChangedPart, ...]
    preservation: PreservationSummary
    offending_parts: tuple[str, ...]

    @property
    def patch_grade_ok(self) -> bool:
        return (
            self.preservation.untouched_part_payloads.changed == 0
            and not self.offending_parts
        )

    @property
    def achieved_grade(self) -> Literal["patch", "rebuild"]:
        return "patch" if self.patch_grade_ok else "rebuild"


def measure_save(
    source_members: Mapping[str, bytes],
    source_infos: Mapping[str, ZipInfo],
    built_bytes: bytes,
    predeclared: set[str],
    *,
    source_bytes: bytes | None = None,
    zip_records_rewritten: str | None = None,
) -> PreservationMeasurement:
    """Measure preservation of *built_bytes* against the pre-save source.

    ``source_members`` is the package's part payloads captured *before* this
    save applied its ``serialize()`` updates; ``predeclared`` is that update's
    key set. Changed parts inside ``predeclared`` are ``dirty-part``; any other
    change is ``unexpected`` (e.g. a per-save normalizer touching a part the
    editor never declared dirty).

    With *source_bytes* (the archive the document was opened from) the record layer compares each untouched
    part's whole local record byte for byte and the whole-package layer compares the files; without it, the
    record layer compares the preserved ZipInfo fields and the whole-package layer the part contents.
    *zip_records_rewritten* is the reason the save could not keep the source's records, if it could not.
    """

    built_members = read_archive_members(built_bytes)
    built_infos = read_archive_infos(built_bytes)

    diff = diff_members(source_members, built_members)
    changed_names = list(diff["changedMembers"])
    added_names = list(diff["addedMembers"])
    removed_names = list(diff["removedMembers"])

    changed_parts: list[ChangedPart] = []
    offending: list[str] = []
    for name in changed_names + added_names + removed_names:
        predeclared_hit = name in predeclared
        reason = "dirty-part" if predeclared_hit else "unexpected"
        changed_parts.append(ChangedPart(path=name, reason=reason, ranges=None))
        if not predeclared_hit:
            offending.append(name)

    # Untouched layer = shared parts the save did not predeclare. Their
    # uncompressed payload and their preserved ZIP-record metadata must survive.
    shared = set(source_members) & set(built_members)
    untouched = sorted(shared - predeclared)
    payload_changed = sum(
        1 for name in untouched if source_members[name] != built_members[name]
    )
    source_records, built_records = _records_or_none(source_bytes), _records_or_none(built_bytes)
    if source_records is not None and built_records is not None:
        record_changed = sum(
            1
            for name in untouched
            if not _local_record_kept(source_records, built_records, name)
        )
    elif source_bytes is not None:
        # An archive the record reader refuses (ZIP64, bytes before the first record, ...): the records
        # are still compared byte for byte, sliced where zipfile places them, so "verified" never stands
        # for a comparison of ZipInfo fields while the bytes moved.
        before_spans, after_spans = _zipfile_records(source_bytes), _zipfile_records(built_bytes)
        record_changed = sum(
            1
            for name in untouched
            if before_spans is None or after_spans is None
            or name not in before_spans or before_spans[name] != after_spans.get(name)
        )
    else:
        record_changed = sum(
            1
            for name in untouched
            if not _zip_record_preserved(source_infos.get(name), built_infos.get(name))
        )

    if source_bytes is not None:
        whole_package_identical = built_bytes == source_bytes
    else:
        whole_package_identical = not (changed_names or added_names or removed_names)

    preservation = PreservationSummary(
        untouched_part_payloads=PreservationCounts(
            verified=len(untouched) - payload_changed, changed=payload_changed
        ),
        untouched_local_zip_records=PreservationCounts(
            verified=len(untouched) - record_changed, changed=record_changed
        ),
        whole_package_identical=whole_package_identical,
        zip_records_rewritten=zip_records_rewritten,
    )
    return PreservationMeasurement(
        changed_parts=tuple(changed_parts),
        preservation=preservation,
        offending_parts=tuple(offending),
    )


def _records_or_none(data: bytes | None) -> "ZipRecords | None":
    if data is None:
        return None
    from .opc.zip_records import ZipRecordsUnsupported, read_records

    try:
        return read_records(data)
    except ZipRecordsUnsupported:
        return None


def _zipfile_records(data: bytes) -> dict[str, bytes] | None:
    """Each entry's whole local record (its header up to the next header, or the central directory), as
    ``zipfile`` places them -- which reads ZIP64 and archives with bytes before the first record too.
    ``None`` when the archive cannot be read so, or holds a name twice (no record stands for the name)."""

    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = sorted(archive.infolist(), key=lambda info: info.header_offset)
            ends = [info.header_offset for info in entries[1:]] + [archive.start_dir]
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    names = [info.filename for info in entries]
    if len(set(names)) != len(names):
        return None
    return {info.filename: data[info.header_offset:end] for info, end in zip(entries, ends)}


def _local_record_kept(before: "ZipRecords", after: "ZipRecords", name: str) -> bool:
    """True when *name*'s whole local record (header, compressed bytes, data descriptor) is the same bytes."""

    old, new = before.by_name.get(name), after.by_name.get(name)
    if old is None or new is None:
        return False
    return before.local_record(old) == after.local_record(new)


def _zip_record_preserved(before: ZipInfo | None, after: ZipInfo | None) -> bool:
    """True when the preserved local-record fields are byte-for-byte equal."""

    if before is None or after is None:
        return before is after
    return all(
        getattr(before, name) == getattr(after, name) for name in _PRESERVED_ZIP_FIELDS
    )


# --------------------------------------------------------------------------- #
# Projection helpers — turn an existing result model's own evidence into a
# MutationReport without asserting a layer the model never measured (specs/032
# §3, survey §7/§9). ``not_performed`` and ``ranges=None`` are the honest
# defaults; a silent pass is never fabricated.
# --------------------------------------------------------------------------- #
def verification_value(ok: bool | None) -> VerificationValue:
    """``True→passed``, ``False→failed``, ``None→not_performed`` (No Silent True)."""

    if ok is True:
        return "passed"
    if ok is False:
        return "failed"
    return "not_performed"


def visual_value_from_status(status: str | None) -> VerificationValue:
    """Map a ``VisualCompleteReport`` tri-state to a verification value.

    ``"unverified"`` (render did not run) maps to ``not_performed``, never to a
    silent pass (survey §9). Mirrors ``persistence._verification_summary``.
    """

    if status == "verified":
        return "passed"
    if status == "failed":
        return "failed"
    return "not_performed"


def _nested_ok(value: Any) -> bool | None:
    """The ``ok`` verdict of an open-safety sub-report, or ``None`` if absent."""

    if isinstance(value, Mapping):
        ok = value.get("ok")
        return ok if isinstance(ok, bool) else None
    if isinstance(value, bool):
        return value
    return None


def verification_from_open_safety(
    open_safety: Mapping[str, Any] | None,
    *,
    visual: VerificationValue = "not_performed",
) -> VerificationSummary:
    """Project the byte-splice family's ``open_safety`` dict onto a summary.

    The dict is an ``EditorOpenSafetyReport.to_dict()`` (``ok`` +
    ``validatePackage``/``reopen`` sub-verdicts) or the small ``{"ok", "summary"}``
    fallback. Any sub-verdict the dict does not carry stays ``not_performed`` —
    an absent measurement is never promoted to a pass.
    """

    data = open_safety or {}
    overall = data.get("ok")
    return VerificationSummary(
        package=verification_value(_nested_ok(data.get("validatePackage"))),
        open_safety=verification_value(overall if isinstance(overall, bool) else None),
        reopen=verification_value(_nested_ok(data.get("reopen"))),
        visual=visual,
    )


def changed_ranges_in_part(before: bytes, after: bytes) -> tuple[ByteRange, ...]:
    """The minimal contiguous changed span, in *after* coordinates, between two
    versions of one part's uncompressed payload.

    Returns the smallest ``[start, end)`` outside which *before* and *after* are
    byte-identical — exact for a single contiguous splice, a tight bounding span
    when several edits land in one part. Empty when the payloads are identical.
    The byte-splice result models do not retain their spliced offsets, so this
    reconstructs the span from the original source the caller still holds.
    """

    if before == after:
        return ()
    limit = min(len(before), len(after))
    prefix = 0
    while prefix < limit and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1
    return (ByteRange(start=prefix, end=len(after) - suffix),)


def project_byte_splice(
    *,
    data: bytes,
    changed_part_names: Sequence[str],
    byte_identical: bool,
    open_safety: Mapping[str, Any] | None,
    visual: VerificationValue = "not_performed",
    source: bytes | str | Path | None = None,
) -> MutationReport:
    """Project a byte-splice result (patch/table_patch/body_patch) onto v1.

    ``actualMode`` is ``"patch"`` — a byte splice is patch-grade by nature. When
    the caller supplies the original *source*, preservation is fully **measured**
    against it (reusing :func:`measure_save`) and each changed shared part carries
    real ranges; without *source* the three preservation layers degrade honestly
    (``wholePackageIdentical`` from the model's ``byte_identical``, the untouched
    counts left at zero-verified) and ranges are ``None``.
    """

    if source is not None:
        if not isinstance(source, bytes):
            source = Path(source).read_bytes()
        before_members = read_archive_members(source)
        before_infos = read_archive_infos(source)
        after_members = read_archive_members(data)
        measurement = measure_save(
            before_members, before_infos, data, set(changed_part_names), source_bytes=source
        )
        changed_parts = tuple(
            ChangedPart(
                path=part.path,
                reason=part.reason,
                ranges=(
                    changed_ranges_in_part(
                        before_members[part.path], after_members[part.path]
                    )
                    if part.path in before_members and part.path in after_members
                    else None
                ),
            )
            for part in measurement.changed_parts
        )
        preservation = measurement.preservation
    else:
        changed_parts = tuple(
            ChangedPart(path=name, reason="dirty-part", ranges=None)
            for name in changed_part_names
        )
        preservation = PreservationSummary(
            untouched_part_payloads=PreservationCounts(verified=0, changed=0),
            untouched_local_zip_records=PreservationCounts(verified=0, changed=0),
            whole_package_identical=byte_identical,
        )
    return MutationReport(
        requested_mode="patch",
        actual_mode="patch",
        fallback_used=False,
        changed_parts=changed_parts,
        preservation=preservation,
        verification=verification_from_open_safety(open_safety, visual=visual),
        path=None,
    )


__all__ = [
    "MUTATION_REPORT_SCHEMA",
    "COORDINATE_SPACE",
    "ByteRange",
    "ChangedPart",
    "PreservationCounts",
    "PreservationSummary",
    "VerificationSummary",
    "MutationReport",
    "PreservationDowngradeError",
    "PreservationMeasurement",
    "measure_save",
    "read_archive_members",
    "read_archive_infos",
    "diff_members",
    "member_diff_bytes",
    "verification_value",
    "visual_value_from_status",
    "verification_from_open_safety",
    "changed_ranges_in_part",
    "project_byte_splice",
]
