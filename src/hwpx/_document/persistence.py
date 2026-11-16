# SPDX-License-Identifier: Apache-2.0
"""Save/validate/export domain owner behind the HwpxDocument facade."""

from __future__ import annotations

import functools
import hashlib
from os import PathLike
from typing import TYPE_CHECKING, Any, BinaryIO, Callable, Literal, Sequence, TypeVar

from ..errors import HwpxTypeError, HwpxValueError, SaveError, SaveTargetError
from ..mutation_report import (
    Fallback,
    Mode,
    MutationReport,
    PreservationDowngradeError,
    PreservationMeasurement,
    VerificationSummary,
    VerificationValue,
    measure_save,
)
from ..opc.security import sharing_archive_reads
from ..opc.package import _UNCHECKED_SAVE_TOKEN
from ..quality import QualityPolicy
from ..quality.report import OpenSafetyReport

#: The file formats a document saves to: HWPX, or HWP 5.0.
SaveFormat = Literal["hwpx", "hwp"]

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..quality import VisualCompleteReport
    from ..tools.validator import ValidationReport


_SaveFunction = TypeVar("_SaveFunction", bound=Callable[..., Any])


def _one_archive_read(save: _SaveFunction) -> _SaveFunction:
    """Run *save* so that its checks share one read of the archive it writes.

    The package check, the reopen, the preservation measurement and the quality
    gate all read the bytes the save has just built; see ``opc.security``.
    """

    @functools.wraps(save)
    def sharing(*args: Any, **kwargs: Any) -> Any:
        with sharing_archive_reads():
            return save(*args, **kwargs)

    return sharing  # type: ignore[return-value]


_SAVE_TARGET_ERRORS: dict[type[OSError], type[SaveTargetError]] = {}


def _save_target_error_type(base: type[OSError]) -> type[SaveTargetError]:
    if base is OSError or issubclass(base, SaveTargetError):
        return SaveTargetError
    found = _SAVE_TARGET_ERRORS.get(base)
    if found is None:
        found = type(f"SaveTarget{base.__name__}", (SaveTargetError, base), {"__module__": __name__})
        _SAVE_TARGET_ERRORS[base] = found
    return found


def _save_target_error(path: str | PathLike[str], error: OSError) -> SaveTargetError:
    import os

    target = os.path.abspath(os.fspath(path))
    parent = os.path.dirname(target)
    if os.path.isdir(target):
        message = f"Cannot save to {target}: it is a folder."
        code, suggestion = "save-target-is-folder", "Give a file path, for example a name ending in .hwpx inside that folder."
    elif not os.path.isdir(parent):
        message = f"Cannot save to {target}: the folder {parent} does not exist."
        code, suggestion = "save-target-folder-missing", "Create the folder first (Path(...).parent.mkdir(parents=True)) or save elsewhere."
    elif isinstance(error, PermissionError):
        message = f"Cannot save to {target}: permission denied (the file may be read-only or open in another program)."
        code, suggestion = "save-target-denied", "Close the file in Hancom or other programs, clear its read-only flag, or save under another name."
    else:
        message = f"Cannot save to {target}: {error.strerror or error}."
        code, suggestion = "save-target-unwritable", "Check the path, free disk space and permissions, or save elsewhere."
    return _save_target_error_type(type(error))(
        message,
        code=code,
        context={"path": target, "os_error": type(error).__name__, "errno": error.errno},
        suggestion=suggestion,
    )


def _check_save_target(path: str | PathLike[str]) -> None:
    """Refuse a target that cannot be a file before the document is serialized."""

    import os

    if not isinstance(path, (str, bytes, os.PathLike)):
        from ..errors import argument_type_error

        raise argument_type_error(
            "path", path, "a str or os.PathLike path",
            suggestion="Pass a file path, or use save_to_stream/to_bytes for a stream or bytes.",
        )
    target = os.fspath(path)
    if os.path.isdir(target):
        raise _save_target_error(path, IsADirectoryError(21, "Is a directory"))
    parent = os.path.dirname(os.path.abspath(target))
    if not os.path.isdir(parent):
        raise _save_target_error(path, FileNotFoundError(2, "No such file or directory"))


_MODES = ("auto", "patch", "rebuild")
_FALLBACKS = ("error", "rebuild")


def _check_grade_arguments(mode: object, fallback: object) -> None:
    if mode not in _MODES:
        raise HwpxValueError(
            f"Unknown save mode {mode!r}; use 'auto', 'patch' or 'rebuild'.",
            code="save-mode-invalid",
            context={"mode": repr(mode)},
            suggestion="Leave mode out (the default 'auto'), or pass mode='patch' to keep untouched parts byte-identical.",
        )
    if fallback not in _FALLBACKS:
        raise HwpxValueError(
            f"Unknown save fallback {fallback!r}; use 'error' or 'rebuild'.",
            code="save-mode-invalid",
            context={"fallback": repr(fallback)},
            suggestion="Leave fallback out (the default 'error') or pass fallback='rebuild'.",
        )


_hwp5_write_warned = False


def _warn_about_target_format(path: str | PathLike[str]) -> None:
    """Say what a save to *path* writes when the name does not say it: once for the experimental
    HWP 5.0 writer, and every time for a name that is neither ``.hwpx`` nor ``.hwp``."""

    import os
    import warnings

    global _hwp5_write_warned
    suffix = os.path.splitext(os.fspath(path))[1].lower()
    if suffix == ".hwp":
        if not _hwp5_write_warned:
            _hwp5_write_warned = True
            warnings.warn(
                "Saving as .hwp uses the experimental HWP 5.0 writer; check the file in Hancom, "
                "and keep an .hwpx copy (save_to_path('….hwpx')) of anything that matters.",
                UserWarning,
                stacklevel=5,  # this, save_to_path, the archive-read wrapper, HwpxDocument.save_to_path
            )
    elif suffix != ".hwpx":
        warnings.warn(
            f"Saving HWPX data to a file named {os.path.basename(os.fspath(path))!r}: only .hwpx and .hwp "
            "choose a format, so this file holds HWPX and other programs may not open it by that name.",
            UserWarning,
            stacklevel=5,
        )


def _summarize_validation_issues(issues: Sequence[Any], *, limit: int = 5) -> str:
    selected = [str(issue) for issue in issues[:limit]]
    remaining = len(issues) - len(selected)
    summary = "; ".join(selected)
    if remaining > 0:
        summary += f" ... and {remaining} more"
    return summary


def export_text(doc: "HwpxDocument", **kwargs: object) -> str:
    """Export content as plain text.  Keyword args forwarded to :func:`~hwpx.tools.exporter.export_text`."""
    from ..tools.exporter import export_text
    return export_text(doc, **kwargs)  # type: ignore[arg-type]


def validate(doc: "HwpxDocument") -> "ValidationReport":
    """Validate the current document state, as ``hwpx-validate`` does.

    Checks the header and section XML against the schemas and warns about
    manifest drift; see :func:`~hwpx.tools.validator.validate_document`.
    Package structure is checked by
    :func:`~hwpx.tools.package_validator.validate_package`. This does
    **not** require ``validate_on_save`` to be enabled.
    """
    from ..tools.validator import validate_document

    return validate_document(_to_bytes_for_validation(doc))


def _run_pre_save_validation(doc: "HwpxDocument") -> None:
    """Raise if validate_on_save is enabled and the document is invalid."""
    if not doc.validate_on_save:
        return
    report = doc.validate()
    if not report.ok:
        msgs = _summarize_validation_issues(report.issues)
        raise SaveError(
            f"Document validation failed: {msgs}",
            code="document-validation-failed",
            context={"issueCount": len(report.issues), "issues": msgs},
            suggestion=(
                "Fix the reported schema issues, or disable validate_on_save if "
                "the validation is a false positive for your document."
            ),
        )


def _run_open_safety_validation(doc: "HwpxDocument", archive_bytes: bytes) -> None:
    """Raise if generated bytes are unsafe to hand to an HWPX editor.

    The package's own save already ran the same validation when it built
    these exact bytes (``HwpxPackage._save_to_zip`` records their digest), so
    the check is not repeated then. Bytes it did not verify are validated here.
    """

    from ..tools.package_validator import validate_editor_open_safety

    verified = getattr(doc._package, "_verified_archive_digest", None)
    if verified is not None and verified == hashlib.sha256(archive_bytes).digest():
        return
    report = validate_editor_open_safety(archive_bytes)
    if not report.ok:
        raise SaveError(
            "Generated HWPX package failed open-safety validation: "
            + report.summary,
            code="open-safety-failed",
            context={"summary": report.summary},
            suggestion=(
                "The serialized package would not reopen in an HWPX editor; "
                "inspect validate_editor_open_safety(...) for the failing checks."
            ),
        )


def _gate_and_write(
    doc: "HwpxDocument",
    archive_bytes: bytes,
    *,
    output_path: str | PathLike[str] | None = None,
    output_stream: BinaryIO | None = None,
    source_label: str,
) -> VisualCompleteReport:
    """Funnel a serialized archive through the SavePipeline (transparent).

    ``_to_bytes_raw`` already ran open-safety and raised on failure, so the
    gate is transparent here — it performs the single atomic write and returns
    the uniform report. Raises if the gate unexpectedly rejects the bytes.
    """

    report = doc._save_pipeline.run(
        archive_bytes,
        output_path=output_path,
        output_stream=output_stream,
        quality=QualityPolicy.transparent(),
        open_safety=OpenSafetyReport.passed("validated during serialize"),
        publish="on_pass",
        source_label=source_label,
    )
    if not report.ok:
        detail = "; ".join(str(error) for error in report.errors)
        raise SaveError(
            f"Document save failed the quality gate: {detail}",
            code="quality-gate-failed",
            context={"errors": [str(error) for error in report.errors]},
            suggestion=(
                "The SavePipeline quality gate rejected the archive; inspect the "
                "returned report's errors before retrying."
            ),
        )
    return report


def _build_measured(
    doc: "HwpxDocument", *, reset_dirty: bool
) -> tuple[bytes, PreservationMeasurement]:
    """Serialize + open-safety validate exactly like ``_to_bytes_raw`` and measure
    the built archive's preservation against the pre-save part payloads.

    The pre-save snapshot is captured *before* the ``serialize()`` updates are
    applied so a per-save normalizer touching a part the editor never declared
    dirty surfaces as an ``unexpected`` change (Safe Write Contract §2).
    """

    package = doc._package
    # Measure against the OPEN-TIME baseline, not the current package state: a
    # low-level ``set_part`` applied before this save already lives in
    # ``_files``, and measuring against it would silently launder that change
    # through a ``mode="patch"`` grade (Safe Write Contract §1, fail-closed).
    source_members = dict(
        getattr(package, "_opened_members", None) or package._files
    )
    source_infos = dict(
        getattr(package, "_opened_zip_infos", None) or package._zip_infos
    )
    updates = doc._root.serialize()
    predeclared = set(updates)
    if updates:
        for part_name, payload in updates.items():
            package.set_part(part_name, payload)
    result = package._save_to_bytes(verify_open_safety=True, mark_clean=False)
    if not isinstance(result, bytes):
        raise HwpxTypeError(
            "package.save(None) must return bytes",
            code="save-package-contract-violated",
            suggestion="Check that the custom package implementation honours this contract.",
        )
    doc._run_open_safety_validation(result)
    if reset_dirty:
        _mark_save_clean(doc)
    measurement = measure_save(source_members, source_infos, result, predeclared)
    return result, measurement


def _resolve_grade(
    mode: Mode,
    fallback: Fallback,
    measurement: PreservationMeasurement,
) -> tuple[Literal["patch", "rebuild"], bool]:
    """Return ``(actual_mode, fallback_used)``; raise before any write when a
    requested ``patch`` grade is unmet and ``fallback="error"`` (§1)."""

    if mode == "patch" and not measurement.patch_grade_ok:
        if fallback == "error":
            raise PreservationDowngradeError(
                requested_mode=mode,
                achieved_grade=measurement.achieved_grade,
                offending_parts=measurement.offending_parts,
                suggestion=(
                    "route these edits through a byte-preserving primitive "
                    "(hwpx.patch/table_patch/body_patch) or pass fallback='rebuild'."
                ),
            )
        return "rebuild", True
    if mode == "auto":
        return measurement.achieved_grade, False
    if mode == "patch":
        return "patch", False
    return "rebuild", False


def _verification_summary(report: "VisualCompleteReport") -> VerificationSummary:
    """Reflect what the pipeline actually ran; never fabricate a pass (§2)."""

    package: VerificationValue = "passed" if report.ok else "failed"
    open_safety: VerificationValue = "passed" if report.open_safety.ok else "failed"
    # Open-safety validation (which includes the reopen probe) already ran during
    # serialize and raised on failure, so reaching here means reopen passed.
    reopen: VerificationValue = "passed"
    status = report.visual_complete_status
    visual: VerificationValue = (
        "passed"
        if status == "verified"
        else "failed"
        if status == "failed"
        else "not_performed"
    )
    return VerificationSummary(
        package=package, open_safety=open_safety, reopen=reopen, visual=visual
    )


def _compose_mutation_report(
    *,
    path: str | None,
    requested_mode: Mode,
    actual_mode: Literal["patch", "rebuild"],
    fallback_used: bool,
    measurement: PreservationMeasurement,
    report: "VisualCompleteReport",
) -> MutationReport:
    return MutationReport(
        requested_mode=requested_mode,
        actual_mode=actual_mode,
        fallback_used=fallback_used,
        changed_parts=measurement.changed_parts,
        preservation=measurement.preservation,
        verification=_verification_summary(report),
        path=path,
    )


@_one_archive_read
def save_to_path(
    doc: "HwpxDocument",
    path: str | PathLike[str],
    *,
    mode: Mode = "auto",
    fallback: Fallback = "error",
    return_report: bool = False,
) -> str | PathLike[str] | MutationReport:
    """Persist pending changes to *path*.

    Returns *path* by default; ``return_report=True`` returns the
    :class:`~hwpx.mutation_report.MutationReport` receipt instead. ``mode`` and
    ``fallback`` are the Safe Write Contract grade controls — ``mode="patch"``
    with ``fallback="error"`` raises :class:`PreservationDowngradeError` and
    writes nothing when the save cannot keep every untouched part byte-identical.

    An ``.hwp`` path is written by the experimental HWP 5.0 writer (a warning says so
    once per process); any name other than ``.hwpx`` or ``.hwp`` still gets HWPX data,
    with a warning. A target that cannot be written raises :class:`SaveTargetError`,
    which is also the :class:`OSError` subclass Python raised.
    """

    _check_grade_arguments(mode, fallback)
    _check_save_target(path)
    if str(path).lower().endswith(".hwp"):
        _refuse_lossy_hwp5_save(doc, path)
    _run_pre_save_validation(doc)
    archive_bytes, measurement = _build_measured(doc, reset_dirty=False)
    actual_mode, fallback_used = _resolve_grade(mode, fallback, measurement)
    _warn_about_target_format(path)
    try:
        if str(path).lower().endswith(".hwp"):
            # An .hwp target is written as HWP 5.0 from the validated HWPX parts;
            # the gate still checks those parts, and nothing is written when the
            # HWP 5.0 writer cannot express the document.
            report = _gate_and_write(doc, archive_bytes, source_label="document.save_to_path")
            _write_hwp5(path, archive_bytes)
        else:
            report = _gate_and_write(
                doc, archive_bytes, output_path=path, source_label="document.save_to_path"
            )
    except SaveTargetError:
        raise
    except OSError as error:
        raise _save_target_error(path, error) from error
    _mark_save_clean(doc)
    if return_report:
        return _compose_mutation_report(
            path=str(path),
            requested_mode=mode,
            actual_mode=actual_mode,
            fallback_used=fallback_used,
            measurement=measurement,
            report=report,
        )
    return path


def _write_hwp5(path: str | PathLike[str], archive_bytes: bytes) -> None:
    from ..quality.save_pipeline import write_bytes_atomically

    write_bytes_atomically(path, _hwp5_bytes(archive_bytes))


def _refuse_lossy_hwp5_save(doc: "HwpxDocument", path: str | PathLike[str] | None = None) -> None:
    """Raise before an HWP 5.0 save that would lose content without saying so.

    Two cases are refused. Writing over the ``.hwp`` file the document was opened
    from would replace the only original with a file this library rebuilt. And a
    document whose ``conversion_report`` is not empty already lacks content of the
    original, so an ``.hwp`` written from it would pass that loss on as if complete.
    """

    import os

    from ..hwp5.errors import Hwp5Error

    source = getattr(doc, "_hwp5_source_path", None)
    if path is not None and source is not None:
        target = os.path.abspath(os.fspath(path))
        same = os.path.normcase(target) == os.path.normcase(source)
        if not same and os.path.exists(target) and os.path.exists(source):
            same = os.path.samefile(target, source)
        if same:
            raise Hwp5Error(
                "Refusing to overwrite the .hwp file this document was opened from.",
                code="hwp5-overwrite-source",
                context={"path": target},
                suggestion="Save to a different path, or save as .hwpx and keep the original.",
            )
    report = getattr(doc, "_hwp5_report", None)
    if report is not None and (report.unconverted or report.dropped):
        raise Hwp5Error(
            "Refusing to write .hwp: opening the original left some of its content out "
            "(see conversion_report), so the result would be missing it.",
            code="hwp5-write-lossy-source",
            context={"unconverted": dict(report.unconverted), "dropped": dict(report.dropped)},
            suggestion="Save as .hwpx, and keep the original .hwp for the content that was not converted.",
        )


def _hwp5_bytes(archive_bytes: bytes) -> bytes:
    """The HWP 5.0 file for the validated HWPX parts of *archive_bytes*."""

    import io
    import zipfile

    from ..hwp5.writer import write_hwp5

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    return write_hwp5(files)


def _check_format(format: str) -> None:
    if format not in ("hwpx", "hwp"):
        raise HwpxValueError(
            f"Unknown save format {format!r}; use 'hwpx' or 'hwp'.",
            code="save-format-unsupported",
            context={"format": format},
            suggestion="Pass format='hwpx' (the default) or format='hwp'.",
        )


@_one_archive_read
def save_to_stream(
    doc: "HwpxDocument",
    stream: BinaryIO,
    *,
    mode: Mode = "auto",
    fallback: Fallback = "error",
    return_report: bool = False,
    format: SaveFormat = "hwpx",
) -> BinaryIO | MutationReport:
    """Persist pending changes to *stream*.

    Returns *stream* by default; ``return_report=True`` returns the
    :class:`~hwpx.mutation_report.MutationReport` receipt instead. See
    :func:`save_to_path` for the ``mode``/``fallback`` grade semantics.
    ``format="hwp"`` writes HWP 5.0 the way an ``.hwp`` path does.
    """

    _check_format(format)
    _check_grade_arguments(mode, fallback)
    if format == "hwp":
        _refuse_lossy_hwp5_save(doc)
    _run_pre_save_validation(doc)
    archive_bytes, measurement = _build_measured(doc, reset_dirty=False)
    actual_mode, fallback_used = _resolve_grade(mode, fallback, measurement)
    if format == "hwp":
        # As for an .hwp path: the gate checks the HWPX parts, and nothing is
        # written when the HWP 5.0 writer cannot express the document.
        report = _gate_and_write(doc, archive_bytes, source_label="document.save_to_stream")
        stream.write(_hwp5_bytes(archive_bytes))
    else:
        report = _gate_and_write(
            doc, archive_bytes, output_stream=stream, source_label="document.save_to_stream"
        )
    _mark_save_clean(doc)
    if return_report:
        return _compose_mutation_report(
            path=None,
            requested_mode=mode,
            actual_mode=actual_mode,
            fallback_used=fallback_used,
            measurement=measurement,
            report=report,
        )
    return stream


@_one_archive_read
def save_report(
    doc: "HwpxDocument",
    path_or_stream: str | PathLike[str] | BinaryIO | None = None,
    *,
    quality: QualityPolicy | None = None,
    before: str | PathLike[str] | None = None,
    edit_mask: Any | None = None,
    ledger: Any | None = None,
) -> VisualCompleteReport:
    """Save through the SavePipeline and return the full ``VisualCompleteReport``.

    This is the canonical Phase-B write: it funnels through the one gate and
    returns the uniform report (open-safety, reference integrity, and — when
    the policy renders and a Hancom oracle is reachable — the visual verdict).
    ``quality`` defaults to :meth:`QualityPolicy.transparent` so the call is a
    drop-in for ``save_to_path`` that simply also hands back the report; pass
    ``QualityPolicy.strict()`` (or ``render_check="required"``) to demand the
    oracle-verified ``visual_complete`` tier (plan §0.0).

    Like the legacy savers it raises only if the serialize step's open-safety
    check fails; all other gate outcomes are returned in the report. An ``.hwp``
    path is written as HWP 5.0, as :func:`save_to_path` writes it.
    """

    output_path: str | PathLike[str] | None = None
    output_stream: BinaryIO | None = None
    if isinstance(path_or_stream, (str, PathLike)):
        output_path = path_or_stream
        _check_save_target(output_path)
    elif path_or_stream is not None:
        output_stream = path_or_stream

    _run_pre_save_validation(doc)
    archive_bytes = doc._to_bytes_raw(reset_dirty=False)
    # An .hwp target gets HWP 5.0 made from the HWPX parts the gate checks; it raises before anything is
    # written when the HWP 5.0 writer cannot express the document.
    hwp5 = None
    if output_path is not None and str(output_path).lower().endswith(".hwp"):
        _refuse_lossy_hwp5_save(doc, output_path)
        hwp5 = _hwp5_bytes(archive_bytes)

    try:
        report = doc._save_pipeline.run(
            archive_bytes,
            output_path=None if hwp5 is not None else output_path,
            output_stream=output_stream,
            quality=quality or QualityPolicy.transparent(),
            before=before,
            edit_mask=edit_mask,
            ledger=ledger,
            open_safety=_serialize_open_safety(doc, archive_bytes),
            reference_document=doc,
            source_label="document.save_report",
        )
        if hwp5 is not None and report.ok:  # the gate passed: publish the HWP 5.0 file in its place
            from ..quality.save_pipeline import write_bytes_atomically

            assert output_path is not None
            write_bytes_atomically(output_path, hwp5)
            report.output_path = str(output_path)
    except SaveTargetError:
        raise
    except OSError as error:
        if output_path is None:
            raise
        raise _save_target_error(output_path, error) from error
    if report.ok:
        _mark_save_clean(doc)
    return report


@_one_archive_read
def to_bytes(
    doc: "HwpxDocument",
    *,
    mode: Mode = "auto",
    fallback: Fallback = "error",
    format: SaveFormat = "hwpx",
) -> bytes:
    """Serialize pending changes and return the HWPX archive as bytes.

    ``mode``/``fallback`` enforce the Safe Write Contract grade the same way as
    :func:`save_to_path`: ``mode="patch"`` with ``fallback="error"`` raises
    :class:`PreservationDowngradeError` before returning when the archive is not
    patch-grade. There is no ``return_report`` — the enforcement is via the typed
    exception, so the byte return stays unchanged. ``format="hwp"`` returns an
    HWP 5.0 file instead; the document stays unsaved when that cannot be written.
    """

    _check_format(format)
    _check_grade_arguments(mode, fallback)
    if format == "hwp":
        _refuse_lossy_hwp5_save(doc)
    _run_pre_save_validation(doc)
    archive_bytes, measurement = _build_measured(doc, reset_dirty=False)
    _resolve_grade(mode, fallback, measurement)
    data = _hwp5_bytes(archive_bytes) if format == "hwp" else archive_bytes
    _mark_save_clean(doc)
    return data


def _serialize_open_safety(doc: "HwpxDocument", archive_bytes: bytes) -> OpenSafetyReport | None:
    """The open-safety verdict the package's save reached for exactly *archive_bytes*, in the form
    the SavePipeline composes from its own run; ``None`` when the package did not validate these
    bytes (the pipeline then validates them itself).

    The same validation of the same bytes gives the same report, so ``save_report`` hands the
    pipeline this one instead of running it a second time.
    """

    package = doc._package
    report = getattr(package, "_verified_archive_report", None)
    digest = getattr(package, "_verified_archive_digest", None)
    if report is None or digest is None or not report.ok:
        return None
    if digest != hashlib.sha256(archive_bytes).digest():
        return None
    return OpenSafetyReport(ok=report.ok, summary=report.summary, detail=report.to_dict())


def _to_bytes_raw(
    doc: "HwpxDocument",
    *,
    reset_dirty: bool = True,
) -> bytes:
    """Serialize and run editor-open safety validation.

    When ``reset_dirty`` is ``False``, the document remains marked as
    modified after the archive snapshot is generated.
    """
    updates = doc._root.serialize()
    if updates:
        for part_name, payload in updates.items():
            doc._package.set_part(part_name, payload)
    result = doc._package._save_to_bytes(
        verify_open_safety=True,
        mark_clean=False,
    )
    if isinstance(result, bytes):
        doc._run_open_safety_validation(result)
        if reset_dirty:
            _mark_save_clean(doc)
        return result
    raise HwpxTypeError(
            "package.save(None) must return bytes",
            code="save-package-contract-violated",
            suggestion="Check that the custom package implementation honours this contract.",
        )


def _to_bytes_for_validation(doc: "HwpxDocument") -> bytes:
    """Serialize current state for document validation without handing bytes to callers."""

    updates = doc._root.serialize()
    return doc._package._save_bytes_unchecked(
        updates,
        _unchecked_token=_UNCHECKED_SAVE_TOKEN,
    )


def _mark_save_clean(doc: "HwpxDocument") -> None:
    doc._root.reset_dirty()
    doc._package.version_info.mark_clean()
    # The published archive is the new preservation baseline for any further
    # save on this document instance.
    package = doc._package
    package._opened_members = dict(package._files)
    package._opened_zip_infos = dict(package._zip_infos)
