# SPDX-License-Identifier: Apache-2.0
"""Save/validate/export domain owner behind the HwpxDocument facade."""

from __future__ import annotations

import functools
import hashlib
from dataclasses import replace as dataclass_replace
from os import PathLike
from typing import TYPE_CHECKING, Any, BinaryIO, Callable, List, Literal, Optional, Sequence, Tuple, TypeVar, cast

from ..errors import HwpxTypeError, HwpxValueError, SaveError, SaveTargetError
from ..mutation_report import (
    HWP5_OUTPUT,
    Fallback,
    Mode,
    MutationReport,
    PreservationCounts,
    PreservationDowngradeError,
    PreservationMeasurement,
    PreservationSummary,
    VerificationSummary,
    VerificationValue,
    measure_save,
)
from ..opc.security import sharing_archive_reads
from ..opc.package import _UNCHECKED_SAVE_TOKEN
from ..quality import QualityPolicy, SavePipeline
from ..quality.report import OpenSafetyReport
from ..quality.save_pipeline import STREAM_NOT_READ_BACK

#: The file formats a document saves to: HWPX, or HWP 5.0.
SaveFormat = Literal["hwpx", "hwp"]

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..quality import VisualCompleteReport
    from ..tools.package_validator import EditorOpenSafetyReport
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


def _warn_about_target_format(path: str | PathLike[str], format: SaveFormat, *, stated: bool = False) -> None:
    """Say what a save to *path* writes when the name does not say it: once for the experimental
    HWP 5.0 writer, and every time HWPX goes to a name that does not end in ``.hwpx`` -- unless the
    caller *stated* the format (``save(..., format="hwpx")``) and the name says no other one (a
    temporary ``.tmp`` name, say). HWPX stated for a ``.hwp`` name still warns: the name says HWP."""

    import os
    import warnings

    global _hwp5_write_warned
    suffix = os.path.splitext(os.fspath(path))[1].lower()
    if format == "hwpx" and stated and suffix != ".hwp":
        return
    if format == "hwp":
        if not _hwp5_write_warned:
            _hwp5_write_warned = True
            warnings.warn(
                "Saving as .hwp uses the experimental HWP 5.0 writer; check the file in Hancom, "
                "and keep an .hwpx copy (doc.save('….hwpx')) of anything that matters.",
                UserWarning,
                stacklevel=5,  # this, save, the archive-read wrapper, HwpxDocument.save
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


def _refuse_unlinked_master_pages(doc: "HwpxDocument") -> None:
    """Raise before writing anything when a master page made in this session is linked to no section.

    Hancom drops a master page part no section's ``hp:masterPage`` points at (``masterPageCnt="0"``):
    opened and saved again, the part and its text are gone (Hangul 2024, out/metrics7 ``page-00·03·06``).
    One the document was read with stays as it was read (an unedited save keeps every part).
    """

    master_pages = list(getattr(doc.oxml, "_master_pages", ()) or ())
    created = [page for page in master_pages if getattr(page, "_created_in_session", False)]
    if not created:
        return
    linked = {ref for section in doc.oxml.sections for ref in section.properties.master_page_refs}
    unlinked = [page for page in created if (page.element.get("id") or "") not in linked]
    if not unlinked:
        return
    from ..errors import HwpxValueError

    ids = [page.element.get("id") or page.part_name for page in unlinked]
    raise HwpxValueError(
        f"master page {', '.join(map(repr, ids))} is linked to no section; Hancom drops such a part when it saves",
        code="master-page-unlinked",
        context={"master_pages": ids},
        suggestion=(
            "Link it to a section: doc.page.set_master_page(master_page, section=0) (or create it with "
            "doc.parts.add_master_page(..., section=0)), or remove it: doc.parts.remove_master_page(master_page)."
        ),
    )


def _refuse_unanchored_memos(doc: "HwpxDocument") -> None:
    """Raise before writing anything when a memo made in this session is anchored by no MEMO field.

    Hancom keeps a memo only in its MEMO field (Hangul 2024 saves no ``hp:memogroup``; the public
    and test documents it saved with memos all hold them so), so a memo no field holds has nowhere
    Hancom reads it from. A memo is anchored by ``doc.notes.add_memo(..., paragraph=)`` or
    ``doc.notes.attach(paragraph, memo)``, which move it into the field. Memos the document was read
    with stay as they were read.
    """

    made = getattr(doc.oxml, "_session_memo_ids", None)
    if not made:
        return
    from ..oxml.namespaces import HP as _HP_NS

    pending = [
        memo.get("id") for section in doc.oxml.sections
        for memo in section.element.iter(f"{_HP_NS}memo") if memo.get("id") in made
    ]
    if not pending:
        return
    from ..errors import HwpxValueError

    raise HwpxValueError(
        f"memo {', '.join(map(repr, pending))} is not anchored to a paragraph; Hancom keeps a memo only in its "
        "MEMO field",
        code="note-memo-unanchored",
        context={"memos": pending},
        suggestion=(
            "Anchor it: doc.notes.attach(paragraph, memo) (or make it with doc.notes.add_memo(text, paragraph=...)), "
            "or remove it: doc.notes.remove_memo(memo)."
        ),
    )


#: What :func:`_move_section_properties_to_first` remembers of a section before it moves its settings:
#: the section, each element with the children it had, whether it was marked edited, and the part
#: payload the package held (``None`` when it holds none).
_SectionBeforeMove = Tuple[Any, List[Tuple[Any, List[Any]]], bool, Optional[bytes]]


def _remember_section(doc: "HwpxDocument", section: Any) -> _SectionBeforeMove:
    children = [(node, list(node)) for node in section.element.iter() if isinstance(node.tag, str)]
    files = getattr(doc._package, "_files", None)
    payload = files.get(section.part_name) if files is not None else None
    return section, children, bool(section.dirty), payload


def _put_moved_sections_back(doc: "HwpxDocument", moved: List[_SectionBeforeMove]) -> None:
    """Undo :func:`_move_section_properties_to_first` for a save that was refused after it.

    Each element of a moved section gets back the children it had, the same objects in the same
    order: the settings return to the paragraph they were in, the line caches to their paragraphs,
    and a run or control the move made is dropped. The section is marked edited or not as it was,
    and the package holds the part payload it held (a refused save may have serialized the moved
    tree into it). Wrappers that hold these elements stay valid.
    """

    files = getattr(doc._package, "_files", None)
    for section, children, was_dirty, payload in reversed(moved):
        for node, kids in children:
            if list(node) != kids:
                for child in list(node):
                    node.remove(child)
                node.extend(kids)
        if was_dirty:
            section.mark_dirty()
        else:
            section.reset_dirty()
        if files is not None and payload is not None:
            files[section.part_name] = payload


def _move_section_properties_to_first(doc: "HwpxDocument") -> List[_SectionBeforeMove]:
    """Before writing, move a section's ``hp:secPr`` from a later paragraph into its first one.

    Hancom reads a section's settings only from its first paragraph: Hangul 2024 opened such a
    section with default paper and margins and saved a default ``hp:secPr`` in the first paragraph
    (out/move8/sync/check ``secpr_second_paragraph``). The engine's own edits keep the settings in
    the first paragraph; this shape comes from XML edits (``.element``) and from files made that
    way, among them 6.x's ``section.insert_paragraphs(0, ...)``. 7.0.0 refused to save those, so a
    file 6.x made could not be saved again even unchanged. The settings now move as ``hwpx-repair``
    moves them (with the page-level controls of their paragraph, to the front of the first
    paragraph), every line layout cache of the section is dropped because its paper and margins
    change, and a :class:`UserWarning` naming ``section-properties-not-first`` says which section.
    The open-safety check still reports the shape as an error in a file read as it is.

    Returns what each moved section was like before, for :func:`_put_moved_sections_back`: the
    checks that can still refuse the save (validation, open safety, the preservation grade, the
    quality gate, the target, the stream) need the bytes of the moved tree, so they run after
    the move, and a save they refuse puts the document back (it used to stay moved, its line
    caches gone).
    """

    import warnings

    from ..oxml._paragraph_text_edit import move_section_settings
    from ..oxml.namespaces import HP as _HP_NS

    moved: List[_SectionBeforeMove] = []
    try:
        for index, section in enumerate(doc.oxml.sections):
            paragraphs = section.element.findall(f"{_HP_NS}p")
            if not paragraphs or paragraphs[0].find(f"{_HP_NS}run/{_HP_NS}secPr") is not None:
                continue
            holder = next((number for number, paragraph in enumerate(paragraphs[1:], start=1)
                           if paragraph.find(f"{_HP_NS}run/{_HP_NS}secPr") is not None), None)
            if holder is None:
                continue
            moved.append(_remember_section(doc, section))
            move_section_settings(paragraphs[holder], paragraphs[0])
            for paragraph in section.element.iter(f"{_HP_NS}p"):
                for cache in paragraph.findall(f"{_HP_NS}linesegarray"):
                    paragraph.remove(cache)
            section.mark_dirty()
            warnings.warn(
                f"section {index}'s settings (hp:secPr) were in its paragraph {holder}, where Hancom does not "
                "read them (it gives the section default paper and margins); the save moved them to the "
                "first paragraph and dropped the section's line layout caches (section-properties-not-first)",
                UserWarning,
                stacklevel=5,  # this, save/to_bytes, the archive-read wrapper, HwpxDocument.save
            )
    except BaseException:  # a warning turned into an error: no section stays half moved
        _put_moved_sections_back(doc, moved)
        raise
    return moved


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


def _run_open_safety_validation(doc: "HwpxDocument", archive_bytes: bytes) -> "EditorOpenSafetyReport | None":
    """Raise if generated bytes are unsafe to hand to an HWPX editor; else return the
    report that says they are (``MutationReport.editor_open_safety``).

    The package's own save already ran the same validation when it built
    these exact bytes (``HwpxPackage._save_to_zip`` records their digest), so
    the check is not repeated then and its report is returned. Bytes it did not
    verify are validated here.
    """

    from ..tools.package_validator import validate_editor_open_safety

    verified = getattr(doc._package, "_verified_archive_digest", None)
    if verified is not None and verified == hashlib.sha256(archive_bytes).digest():
        return cast("EditorOpenSafetyReport | None", getattr(doc._package, "_verified_archive_report", None))
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
    return report


def _gate_and_write(
    doc: "HwpxDocument",
    archive_bytes: bytes,
    *,
    output_path: str | PathLike[str] | None = None,
    output_stream: BinaryIO | None = None,
    quality: QualityPolicy | None = None,
    source_label: str,
    pipeline: SavePipeline | None = None,
) -> VisualCompleteReport:
    """Funnel a serialized archive through the SavePipeline gate and its single write.

    Without *quality* the gate is transparent: the serialize step already ran
    open-safety and raised on failure, so the gate performs the atomic write and
    returns the uniform report. With a :class:`QualityPolicy` the gate runs that
    policy (reference integrity, layout, the visual oracle when it renders) and
    writes only when it passes. A refused archive is not written and raises
    :class:`SaveError` (``quality-gate-failed``) carrying the report as ``.report``.

    *pipeline* is the gate to run (``doc.save(pipeline=...)``); ``None`` is a plain
    :class:`SavePipeline`, which renders nothing. Its oracle factory is called only
    when *quality* renders.
    """

    gate = pipeline if pipeline is not None else SavePipeline()
    if quality is None:
        report = gate.run(
            archive_bytes,
            output_path=output_path,
            output_stream=output_stream,
            quality=QualityPolicy.transparent(),
            open_safety=OpenSafetyReport.passed("validated during serialize"),
            publish="on_pass",
            source_label=source_label,
        )
    else:
        report = gate.run(
            archive_bytes,
            output_path=output_path,
            output_stream=output_stream,
            quality=quality,
            open_safety=_serialize_open_safety(doc, archive_bytes),
            publish="on_pass",
            reference_document=doc,
            source_label=source_label,
        )
    if not report.ok:
        errors = [str(error) for error in report.errors]
        unverified = not errors and report.visual_complete_status == "unverified"
        if unverified:  # nothing is wrong with the document: the policy asks for a render nobody could make
            detail = "the policy requires a rendered check (require_visual_complete) and none was made — " + (
                "; ".join(str(warning) for warning in report.visual.warnings) or "no render oracle"
            )
            suggestion = (
                "Nothing was written. python-hwpx does not render: pass a policy that does not ask for it, "
                "e.g. quality=QualityPolicy(require_visual_complete=False) (still checks open safety and "
                "references), or give the gate a render oracle (python-hwpx-automation)."
            )
        else:
            detail = "; ".join(errors)
            suggestion = (
                "The SavePipeline quality gate rejected the archive and nothing was written; "
                "read the gate's report (exc.report.errors) before retrying."
            )
        refusal = SaveError(
            f"Document save failed the quality gate: {detail}",
            code="quality-gate-failed",
            context={"errors": errors},
            suggestion=suggestion,
        )
        refusal.report = report
        raise refusal
    return report


def _build_measured(
    doc: "HwpxDocument", *, reset_dirty: bool
) -> tuple[bytes, PreservationMeasurement, "EditorOpenSafetyReport | None"]:
    """Serialize + open-safety validate exactly like ``_to_bytes_raw`` and measure
    the built archive's preservation against the pre-save part payloads. The third
    value is the open-safety report of the built archive.

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
    source_archive = getattr(package, "_source_archive", None)
    source_bytes = None if source_archive is None else source_archive.data
    updates = doc._root.serialize()
    predeclared = set(updates)
    if updates:
        for part_name, payload in updates.items():
            _set_serialized_part(package, part_name, payload)
    result = package._save_to_bytes(verify_open_safety=True, mark_clean=False)
    if not isinstance(result, bytes):
        raise HwpxTypeError(
            "package.save(None) must return bytes",
            code="save-package-contract-violated",
            suggestion="Check that the custom package implementation honours this contract.",
        )
    open_safety = doc._run_open_safety_validation(result)
    if reset_dirty:
        _mark_save_clean(doc)
    outcome = getattr(package, "_zip_records_outcome", None)
    rewritten = None if outcome is None or outcome.rewritten_reason == "no-source" else outcome.rewritten_reason
    measurement = measure_save(
        source_members,
        source_infos,
        result,
        predeclared,
        source_bytes=source_bytes,
        zip_records_rewritten=rewritten,
    )
    return result, measurement, open_safety


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


def _verification_summary(report: "VisualCompleteReport", *, hwp5: bool = False) -> VerificationSummary:
    """Reflect what the pipeline actually ran; never fabricate a pass (§2).

    *hwp5* is a save that wrote HWP 5.0: the four words are about that file, not about the HWPX
    it was made from. The file was read back with the engine's ``.hwp`` reader before it was
    written (:func:`_hwp5_bytes` raises when it does not read), which is what ``package`` (the
    compound file and its record streams) and ``reopen`` say. No open-safety check and no render
    exist for an HWP 5.0 file here, so those two are ``not_performed``; the ones that ran on the
    HWPX are the receipt's ``editor_open_safety`` and ``quality``.
    """

    if hwp5:
        return VerificationSummary(
            package="passed", open_safety="not_performed", reopen="passed", visual="not_performed"
        )
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
    quality: "VisualCompleteReport | None" = None,
    editor_open_safety: "EditorOpenSafetyReport | None" = None,
    hwp5: bool = False,
) -> MutationReport:
    return MutationReport(
        requested_mode=requested_mode,
        actual_mode=actual_mode,
        fallback_used=fallback_used,
        changed_parts=measurement.changed_parts,
        preservation=measurement.preservation,
        verification=_verification_summary(report, hwp5=hwp5),
        path=path,
        quality=quality,
        editor_open_safety=editor_open_safety,
    )


def _save_target(target: object) -> tuple[str | PathLike[str] | None, BinaryIO | None]:
    """Split a save *target* into ``(path, None)`` or ``(None, stream)``."""

    if isinstance(target, (str, PathLike)):
        return target, None
    if not isinstance(target, (bytes, bytearray)) and callable(getattr(target, "write", None)):
        return None, cast(BinaryIO, target)
    raise HwpxTypeError(
        f"doc.save() needs a path or a writable binary stream, not {type(target).__name__}.",
        code="save-target-invalid-type",
        context={"type": type(target).__name__},
        suggestion='Pass a file path (doc.save("out.hwpx")) or a binary stream (doc.save(io.BytesIO())); '
        "doc.to_bytes() returns the bytes.",
    )


def _target_format(path: str | PathLike[str] | None, format: object) -> SaveFormat:
    """*format*, or for ``None`` the one the name says: ``.hwp`` is HWP 5.0, anything else HWPX."""

    import os

    if format is None:
        if path is not None and os.path.splitext(os.fspath(path))[1].lower() == ".hwp":
            return "hwp"
        return "hwpx"
    _check_format(cast(str, format))
    return cast(SaveFormat, format)


@_one_archive_read
def save(
    doc: "HwpxDocument",
    target: str | PathLike[str] | BinaryIO,
    *,
    format: SaveFormat | None = None,
    mode: Mode = "auto",
    fallback: Fallback = "error",
    quality: QualityPolicy | None = None,
    pipeline: SavePipeline | None = None,
) -> MutationReport:
    """Persist pending changes to *target* (a path or a writable binary stream).

    Returns the :class:`~hwpx.mutation_report.MutationReport` receipt (``report.path``
    is the path written, ``None`` for a stream). ``mode`` and ``fallback`` are the Safe
    Write Contract grade controls — ``mode="patch"`` with ``fallback="error"`` raises
    :class:`PreservationDowngradeError` and writes nothing when the save cannot keep
    every untouched part byte-identical.

    *format* ``None`` writes HWP 5.0 to a path ending in ``.hwp`` and HWPX otherwise
    (a stream included); ``format="hwp"``/``"hwpx"`` says it outright. HWP 5.0 is
    written by the experimental HWP 5.0 writer (a warning says so once per process);
    HWPX to a name that does not end in ``.hwpx`` gets a warning, unless ``format="hwpx"``
    says it outright and the name is not ``.hwp`` (a temporary name such as
    ``out.hwpx.tmp`` then saves quietly; ``.hwp`` still warns). A target that cannot
    be written raises :class:`SaveTargetError`, which is also the :class:`OSError`
    subclass Python raised.

    *quality* (a :class:`~hwpx.quality.QualityPolicy`) runs that quality gate before
    the write; its :class:`~hwpx.quality.VisualCompleteReport` is ``report.quality``.
    Without it the gate is transparent and ``report.quality`` is ``None``. A refused
    archive is not written: :class:`SaveError` (``quality-gate-failed``) carries the
    gate's report as ``.report``.

    *pipeline* (a :class:`~hwpx.quality.SavePipeline`) runs the gate in place of a
    plain one, e.g. one built with an ``oracle_factory`` that renders; anything else
    is refused before the document is serialized (``save-pipeline-invalid-type``).
    """

    if pipeline is not None and not isinstance(pipeline, SavePipeline):
        raise HwpxTypeError(
            f"pipeline must be a hwpx.SavePipeline or None, got {type(pipeline).__name__}",
            code="save-pipeline-invalid-type",
            context={"type": type(pipeline).__name__},
            suggestion="Pass pipeline=SavePipeline(oracle_factory=...), or leave it out for the plain gate.",
        )
    path, stream = _save_target(target)
    resolved = _target_format(path, format)
    _check_grade_arguments(mode, fallback)
    if path is not None:
        _check_save_target(path)
        _refuse_hwp_overwrite(doc, path)
    if resolved == "hwp":
        _refuse_lossy_hwp5_save(doc)
    _refuse_unlinked_master_pages(doc)
    _refuse_unanchored_memos(doc)
    moved = _move_section_properties_to_first(doc)
    try:
        _run_pre_save_validation(doc)
        archive_bytes, measurement, open_safety = _build_measured(doc, reset_dirty=False)
        actual_mode, fallback_used = _resolve_grade(mode, fallback, measurement)
        if path is not None:
            _warn_about_target_format(path, resolved, stated=format is not None)
        # HWP 5.0 is made from the validated HWPX parts the gate checks; it raises before
        # anything is written when the HWP 5.0 writer cannot express the document.
        hwp5 = _hwp5_bytes(archive_bytes) if resolved == "hwp" else None
        try:
            report = _gate_and_write(
                doc,
                archive_bytes,
                output_path=path if hwp5 is None else None,
                output_stream=stream if hwp5 is None else None,
                quality=quality,
                source_label="document.save",
                pipeline=pipeline,
            )
            if hwp5 is not None:  # the gate passed: publish the HWP 5.0 file in its place
                if path is not None:
                    from ..quality.save_pipeline import write_bytes_atomically

                    write_bytes_atomically(path, hwp5)
                    report.output_path = str(path)
                else:
                    assert stream is not None
                    from ..quality.save_pipeline import write_stream_or_rollback

                    # As the .hwpx stream save: a short write is an error and the stream is put back as it
                    # was (stream.write(hwp5) alone returned a receipt for a file cut short).
                    if not write_stream_or_rollback(stream, hwp5):
                        report.warnings.append(STREAM_NOT_READ_BACK)
        except SaveTargetError:
            raise
        except OSError as error:
            if path is None:
                raise
            raise _save_target_error(path, error) from error
    except BaseException:
        # Refused after the settings moved (the gate, the grade, the target, the stream...):
        # nothing was written, so the document goes back to what it was before the call.
        _put_moved_sections_back(doc, moved)
        raise
    _mark_save_clean(doc)
    if hwp5 is not None:
        # The file written is HWP 5.0: it has no parts and no ZIP records to have kept, and it is not
        # the source's bytes. The counts measured on the HWPX it was made from do not describe it.
        measurement = dataclass_replace(
            measurement,
            preservation=PreservationSummary(
                untouched_part_payloads=PreservationCounts(verified=0, changed=0),
                untouched_local_zip_records=PreservationCounts(verified=0, changed=0),
                whole_package_identical=False,
                zip_records_rewritten=HWP5_OUTPUT,
            ),
        )
    if STREAM_NOT_READ_BACK in report.warnings:
        # What the stream holds was not read back: the receipt does not say it is the source file.
        measurement = dataclass_replace(
            measurement,
            preservation=dataclass_replace(
                measurement.preservation, whole_package_identical=False, output_read_back=False
            ),
        )
    return _compose_mutation_report(
        path=None if path is None else str(path),
        requested_mode=mode,
        actual_mode=actual_mode,
        fallback_used=fallback_used,
        measurement=measurement,
        report=report,
        quality=report if quality is not None else None,
        editor_open_safety=open_safety,
        hwp5=hwp5 is not None,
    )


def _refuse_hwp_overwrite(doc: "HwpxDocument", path: str | PathLike[str]) -> None:
    """Raise before a save to *path* that would write over the ``.hwp`` file the document was
    opened from (``hwp5-overwrite-source``) or over any other ``.hwp`` file that is already there
    (``hwp5-overwrite-existing``), whatever format is written.

    The file a document was opened from is the only original, and what a save writes is a file this
    library rebuilt: HWP 5.0 from the experimental writer, or -- with ``format="hwpx"`` -- an HWPX
    archive under the ``.hwp`` name, which through 7.0.1 was written and replaced the original with
    a ZIP. The same holds for every ``.hwp`` already on disk
    (:func:`hwpx.opc.package.refuse_existing_hwp_target`); a new ``.hwp`` name is written.
    """

    import os

    from ..hwp5.errors import Hwp5Error

    from ..opc.package import refuse_existing_hwp_target

    source = getattr(doc, "_hwp5_source_path", None)
    target = os.path.abspath(os.fspath(path))
    same = source is not None and os.path.normcase(target) == os.path.normcase(source)
    if source is not None and not same and os.path.exists(target) and os.path.exists(source):
        same = os.path.samefile(target, source)
    if same:
        copy = os.path.splitext(os.path.basename(target))[0] + ".hwpx"
        raise Hwp5Error(
            "Refusing to write over the .hwp file this document was opened from; it was not changed.",
            code="hwp5-overwrite-source",
            context={"path": target},
            suggestion=(
                f"Save under another file name: one ending in .hwpx (for example {copy!r}) keeps the "
                "edits as HWPX, and a new .hwp name writes HWP 5.0 (experimental). Another format for "
                "this same path is refused too."
            ),
        )
    refuse_existing_hwp_target(path)


def _refuse_lossy_hwp5_save(doc: "HwpxDocument") -> None:
    """Raise before an HWP 5.0 save that would lose content without saying so: a document whose
    ``conversion_report`` is not empty already lacks content of the original, so an ``.hwp``
    written from it would pass that loss on as if complete.
    """

    from ..hwp5.errors import Hwp5Error

    report = getattr(doc, "_hwp5_report", None)
    if report is not None and (report.unconverted or report.dropped):
        raise Hwp5Error(
            "Refusing to write .hwp: opening the original left some of its content out "
            "(see conversion_report), so the result would be missing it.",
            code="hwp5-write-lossy-source",
            context={"unconverted": dict(report.unconverted), "dropped": dict(report.dropped)},
            suggestion=(
                "Save as HWPX under a name ending in .hwpx, and keep the original .hwp for the content "
                "that was not converted."
            ),
        )


def _hwp5_bytes(archive_bytes: bytes) -> bytes:
    """The HWP 5.0 file for the validated HWPX parts of *archive_bytes*, read back before it is
    handed on.

    The engine's own ``.hwp`` reader reads the bytes the writer made (the compound file, its
    record streams, the conversion to parts): the reopen an ``.hwp`` save's receipt reports
    (``verification.reopen``). A file that does not read is not returned, so it is neither written
    nor given to the caller: :class:`Hwp5Error` (``hwp5-write-unsupported``, ``context["reason"]``
    ``"written-file-unreadable"``). Through 7.0.1 the receipt said ``reopen: passed`` for a file
    nothing had read.
    """

    import io
    import zipfile

    from ..hwp5 import package as hwp5_reader
    from ..hwp5.errors import Hwp5Error
    from ..hwp5.writer import write_hwp5

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    data = write_hwp5(files)
    try:
        hwp5_reader.convert(data)
    except Hwp5Error as error:
        raise Hwp5Error(
            "The HWP 5.0 file made for this document does not read back with the engine's .hwp "
            f"reader ({error}); nothing was written.",
            code="hwp5-write-unsupported",
            context={
                "reason": "written-file-unreadable",
                "reader_code": error.code,
                "reader_message": str(error),
            },
            suggestion=(
                "Save as HWPX under a name ending in .hwpx. The experimental HWP 5.0 writer made a file "
                "from this document that would not open; please report the document's shape."
            ),
        ) from error
    return data


def _check_format(format: str) -> None:
    if format not in ("hwpx", "hwp"):
        raise HwpxValueError(
            f"Unknown save format {format!r}; use 'hwpx' or 'hwp'.",
            code="save-format-unsupported",
            context={"format": format},
            suggestion="Pass format='hwpx' (the default) or format='hwp'.",
        )


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
    :func:`save`: ``mode="patch"`` with ``fallback="error"`` raises
    :class:`PreservationDowngradeError` before returning when the archive is not
    patch-grade. There is no receipt — the enforcement is via the typed
    exception, so the byte return stays unchanged. ``format="hwp"`` returns an
    HWP 5.0 file instead; the document stays unsaved when that cannot be written.
    """

    _check_format(format)
    _check_grade_arguments(mode, fallback)
    if format == "hwp":
        _refuse_lossy_hwp5_save(doc)
    _refuse_unlinked_master_pages(doc)
    _refuse_unanchored_memos(doc)
    moved = _move_section_properties_to_first(doc)
    try:
        _run_pre_save_validation(doc)
        archive_bytes, measurement, _open_safety = _build_measured(doc, reset_dirty=False)
        _resolve_grade(mode, fallback, measurement)
        data = _hwp5_bytes(archive_bytes) if format == "hwp" else archive_bytes
    except BaseException:
        _put_moved_sections_back(doc, moved)  # refused: the document is as it was before the call
        raise
    _mark_save_clean(doc)
    return data


def _serialize_open_safety(doc: "HwpxDocument", archive_bytes: bytes) -> OpenSafetyReport | None:
    """The open-safety verdict the package's save reached for exactly *archive_bytes*, in the form
    the SavePipeline composes from its own run; ``None`` when the package did not validate these
    bytes (the pipeline then validates them itself).

    The same validation of the same bytes gives the same report, so ``save(quality=...)`` hands
    the pipeline this one instead of running it a second time.
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
            _set_serialized_part(doc._package, part_name, payload)
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


def _set_serialized_part(package: Any, part_name: str, payload: bytes) -> None:
    """Write a part the document model serialized, keeping the part's own namespace declarations
    (``HwpxPackage._set_serialized_part``); a package without that writes it as given."""

    setter = getattr(package, "_set_serialized_part", None)
    if setter is None:
        package.set_part(part_name, payload)
    else:
        setter(part_name, payload)


def _mark_save_clean(doc: "HwpxDocument") -> None:
    doc._root.reset_dirty()
    doc._package.version_info.mark_clean()
    # The published archive is the new preservation baseline for any further
    # save on this document instance.
    package = doc._package
    package._opened_members = dict(package._files)
    package._opened_zip_infos = dict(package._zip_infos)
    adopt = getattr(package, "_adopt_last_archive", None)
    if adopt is not None:
        adopt()
