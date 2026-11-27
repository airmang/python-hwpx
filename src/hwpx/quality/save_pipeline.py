# SPDX-License-Identifier: Apache-2.0
"""``SavePipeline`` — the gate the document save and the byte patches funnel through (plan §2 B).

Stages (plan task 2): integrity → XML well-formedness → OPC/ref/ID → semantic /
form assertions → layout lint → open-safety → visual oracle (Phase A, when
available/required) → compose ``VisualCompleteReport`` → atomic save or rollback.

The pipeline has an atomic writer for HWPX output (:func:`write_bytes_atomically`),
and :meth:`SavePipeline.run` is the gate the document save and the byte patches
(``hwpx.patch`` and those built on it) write through. It is not the only way bytes
reach a destination. As of 7.0.2 these write outside ``run``:
``HwpxPackage.save`` (``opc/package.py``, its own temp file + ``os.replace``), the
edit plan (``plan/_execute.py``, which calls :func:`write_bytes_atomically` after
its own open-safety check), the HWP 5.0 (``.hwp``) save in ``_document/persistence.py``
(the same function, once the gate has passed), and ``hwpx-repair`` / ``hwpx-pack``
(``tools/repair.py``, ``tools/archive_cli.py``, each with its own temp file +
``os.replace``). No test asserts a "zero bypass" property now: the one that did
(``tests/test_save_pipeline_no_bypass.py``) was removed in 5.0. Restoring a
write-path ratchet and reducing the atomic writers to one is issue #828.

Assurance is tiered and never blurred (plan §0.0): ``visual_complete`` is ``True``
only on the oracle-verified tier; off-oracle the gate degrades to a labelled
structural pass (``visual_complete_status == "unverified"``), never a silent pass.
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from os import PathLike
from pathlib import Path
from typing import Any, BinaryIO, Literal
from xml.etree import ElementTree as ET

from .ledger import DirtyLayoutLedger
from .policy import QualityPolicy
from .rendering import (
    EditMask,
    RenderBackend,
    VisualReport,
    unavailable_render_backend,
)
from .report import (
    OPEN_SAFETY_FAILED,
    REFERENCE_INTEGRITY_FAILED,
    RENDER_ORACLE_UNAVAILABLE,
    VISUAL_COMPLETE_FAILED,
    AestheticReport,
    FormReport,
    LayoutReport,
    OpenSafetyReport,
    QualityError,
    SemanticReport,
    VisualCompleteReport,
    VisualCompleteStatus,
)
from ..opc.package import refuse_existing_hwp_target
from ..opc.security import guard_zip_file, is_known_well_formed, open_archive, parse_xml_stdlib, read_member

PublishMode = Literal["on_pass", "always", "never"]

_XML_SUFFIXES = (".xml", ".rels")
_XML_NAMES = ("[Content_Types].xml",)

#: The warning a save adds to its report when the stream it wrote to could not be read back, so the
#: bytes it holds were not checked (only that it ends where the document does).
STREAM_NOT_READ_BACK = (
    "output-stream-not-read-back: the stream refused to be read, so what it holds was not checked "
    "against the document written (only its length was); save to a path or a readable stream to have it checked"
)


# --------------------------------------------------------------------------- #
# The pipeline's atomic writer (other write paths keep their own: see the module docstring).
# --------------------------------------------------------------------------- #
def write_bytes_atomically(path: str | PathLike[str], data: bytes) -> None:
    """Write *data* to *path* via a temp file + ``os.replace`` (crash-safe).

    An ``.hwp`` file that is already at *path* is not written over
    (:func:`hwpx.opc.package.refuse_existing_hwp_target`, ``hwp5-overwrite-existing``).
    """

    refuse_existing_hwp_target(path)
    target = Path(path)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".hwpx.tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_fh:
            tmp_fh.write(data)
        os.replace(tmp_path, str(target))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _capture_stream_checkpoint(stream: BinaryIO) -> tuple[int, bytes, int | None] | None:
    """Where the stream stands, what it holds from there, and where it ends: what a failed save puts
    back. The end is its own value: a stream standing past its end (``seek(6)`` on three bytes) holds
    nothing from there, and putting it back by its position alone left it three zero bytes longer.
    ``None`` for an end that cannot be known: a stream that does not seek to its end and reads nothing
    from where it stands may end there or before."""

    try:
        position = stream.tell()
    except (AttributeError, OSError):
        return None
    try:
        tail = stream.read()
    except (AttributeError, OSError):
        try:
            end_position = stream.seek(0, os.SEEK_END)
        except (AttributeError, OSError):
            return None
        try:
            stream.seek(position)
        except (AttributeError, OSError):
            return None
        if end_position == position:
            return position, b"", end_position
        return None
    end: int | None
    try:
        end = stream.seek(0, os.SEEK_END)
    except (AttributeError, OSError, ValueError):
        # A stream that seeks to a position and not to its end: it ends after what was read, and at 0
        # when it stands there. Otherwise where it ends is not known.
        end = position + len(tail) if tail or position == 0 else None
    try:
        stream.seek(position)
    except (AttributeError, OSError, ValueError):
        return None
    return position, tail, end


def _rollback_stream(stream: BinaryIO, checkpoint: tuple[int, bytes, int | None] | None) -> bool:
    """Put back what *checkpoint* holds. False when the stream could not be put back (it refused the
    write, the cut or the seek): the caller says so on the error it raises."""

    if checkpoint is None:
        return False
    position, tail, end = checkpoint
    try:
        stream.seek(position)
        counted = True  # every write said how much it took
        if tail:
            offset = 0
            while offset < len(tail):  # a stream that takes a part of what it is given is given the rest
                chunk = tail if offset == 0 else tail[offset:offset + 65536]
                taken = stream.write(chunk)
                if taken is None:
                    counted = False
                    taken = len(chunk)
                if taken <= 0:
                    return False
                offset += min(taken, len(chunk))  # a count past what it was given is the chunk
        # where it ended: before the position when the stream stood past its end; at the position when
        # the end is not known (what the stream held before it cannot then be told from what it holds)
        stream.truncate(position if end is None else end)
        stream.seek(position)
    except (AttributeError, OSError, ValueError):  # ValueError: the stream closed itself when it failed
        return False
    if end is None:
        return False  # cut where it stood; whether it ended there before is not known
    # What it holds now, read back where it can be: a write that reports nothing (``None``) may have
    # taken nothing, and "put back" was said over a stream that still held a part of the new document.
    try:
        held = stream.read()
    except (AttributeError, OSError, ValueError):
        # Not readable: the cut went through, and the writes when each said what it took. A write that
        # said nothing cannot be taken for done without reading back. The read may have moved the
        # stream before it failed: it is put back where it stood, or the restore is not called done.
        try:
            stream.seek(position)
        except (AttributeError, OSError, ValueError):
            return False
        return counted
    try:
        stream.seek(position)
    except (AttributeError, OSError, ValueError):
        return False  # its content is back, and it does not stand where it stood
    return held == tail


def _rollback_or_say_so(
    stream: BinaryIO, checkpoint: tuple[int, bytes, int | None] | None, error: BaseException
) -> None:
    """Put the stream back after *error*; when that fails too, *error* says so: ``stream_restored`` is
    ``False`` on it, and its notes tell what the stream may hold. The failed restore used to be silent."""

    restored = _rollback_stream(stream, checkpoint)
    try:
        error.stream_restored = restored  # type: ignore[attr-defined]
    except AttributeError:  # an exception type with __slots__: nowhere to say it
        return
    if not restored and hasattr(error, "add_note"):  # Python 3.11+
        error.add_note(
            "the stream could not be put back as it was: it may hold a part of the new document "
            "(stream_restored is False on this error)"
        )


def settle_written_stream(stream: BinaryIO, position: int, data: bytes, tail: bytes) -> bool:
    """After *data* was written at *position* over *tail* (what the stream held from there), make the
    stream hold exactly *data* from *position* to its end and check that it does.

    Bytes of the old content past the new end are cut off (``truncate``): a shorter document saved into a
    stream that held a longer one must not keep the old archive's end after it -- the stream would not
    open. A stream that cannot be cut short is refused (``OSError``; the caller puts the old content
    back). The check reads back what the stream now holds from *position*; a stream that cannot be read
    back must at least end where the document does. Returns whether the stream was read back (``False``:
    only where it ends was checked)."""

    end = position + len(data)
    if len(tail) > len(data):
        try:
            stream.truncate(end)
        except (AttributeError, OSError) as exc:
            raise OSError(
                "the stream held more bytes than the saved document and cannot be cut short "
                f"(truncate failed: {exc}); save to a path, or to an empty stream"
            ) from exc
    try:
        stream.seek(position)
        held: bytes | None = stream.read()
    except (AttributeError, OSError):
        held = None
    if held is None:
        try:
            stream_end = stream.seek(0, os.SEEK_END)
        except (AttributeError, OSError):
            stream_end = end
        if stream_end != end:
            raise OSError(
                f"after the save the stream ends at {stream_end}, not at the document's end {end}"
            )
    elif held != data:
        raise OSError(
            "after the save the stream does not hold the document that was written "
            f"({len(held)} bytes from position {position}, the document is {len(data)})"
        )
    stream.seek(end)
    return held is not None


def write_stream_or_rollback(stream: BinaryIO, data: bytes) -> bool:
    """Write *data* to *stream* and make the stream end with it (:func:`settle_written_stream`),
    restoring the prior tail on failure. Returns whether what the stream holds was read back and
    checked."""

    checkpoint = _capture_stream_checkpoint(stream)
    if checkpoint is None:
        raise OSError(
            "stream save requires a checkpointable stream; "
            "save to a path (doc.save(path)) for non-seekable outputs"
        )
    try:
        written = stream.write(data)
        if written is not None and written != len(data):
            raise OSError(
                "short write while saving to a stream: "
                f"wrote {written} of {len(data)} bytes"
            )
        read_back = settle_written_stream(stream, checkpoint[0], data, checkpoint[1])
    except BaseException as error:
        _rollback_or_say_so(stream, checkpoint, error)
        raise
    return read_back


class SavePipeline:
    """Runs the quality gate over output bytes and performs the atomic write.

    A pipeline is cheap to construct; reuse one or make one per save. Pass an
    explicit ``oracle`` (a renderer-neutral :class:`RenderBackend`) to keep tests
    deterministic. A standalone core installation has no renderer discovery:
    companion applications inject a backend factory, while core-only use
    degrades honestly to ``unverified``.
    """

    def __init__(
        self,
        *,
        oracle: RenderBackend | None = None,
        oracle_factory: Any = unavailable_render_backend,
    ) -> None:
        self._oracle = oracle
        self._oracle_factory = oracle_factory

    # -- public API ------------------------------------------------------- #
    def run(
        self,
        data: bytes,
        *,
        output_path: str | PathLike[str] | None = None,
        output_stream: BinaryIO | None = None,
        quality: QualityPolicy | None = None,
        before: str | PathLike[str] | None = None,
        edit_mask: EditMask | None = None,
        ledger: DirtyLayoutLedger | None = None,
        open_safety: OpenSafetyReport | None = None,
        semantic: SemanticReport | None = None,
        form: FormReport | None = None,
        layout: LayoutReport | None = None,
        aesthetic: AestheticReport | None = None,
        publish: PublishMode = "on_pass",
        debug_dir: str | PathLike[str] | None = None,
        source_label: str = "document",
        reference_document: Any | None = None,
        required_fields: set[str] | None = None,
    ) -> VisualCompleteReport:
        """Gate *data*, compose a :class:`VisualCompleteReport`, save or roll back.

        *required_fields* (field ids/names that must be filled) is forwarded to the
        layout lint so an empty declared-required form field is a hard fail under a
        strict ``layout_lint`` (plan §2 D). It is opt-in: with no set, plain
        templates with intentionally-blank fields are never flagged.
        """

        quality = quality or QualityPolicy()
        warnings: list[str] = []
        errors: list[QualityError] = []

        # 1-2. integrity + XML well-formedness (cheap floor, always run).
        well_formed = self._check_well_formed(data, errors)

        # 3. OPC / reference / ID integrity (strict policy only).
        reference_ok = self._check_reference_integrity(
            data, quality, warnings, errors, reference_document
        )

        # 4-5. semantic / form / layout assertions. Semantic/form ride in from the
        # editing layer (Phase C); the layout smoke (Phase D) runs here unless the
        # caller supplied its own report or the policy disables it.
        semantic = semantic or SemanticReport.passed()
        form = form or FormReport.passed()
        aesthetic = aesthetic or AestheticReport.passed()
        if layout is None:
            layout = self._check_layout(
                data, quality, ledger, form, errors, warnings,
                reference_document, required_fields,
            )

        # 6. open-safety. A caller that already validated during serialize (the
        # legacy document savers) may pass a precomputed report to avoid re-running.
        if open_safety is None:
            open_safety = self._check_open_safety(data, quality, errors)

        # 7. visual oracle (Phase A) — only when the policy renders.
        visual, status = self._check_visual(
            data, before, edit_mask, quality, warnings, errors, debug_dir
        )
        visual_complete = status == "verified"

        structural_ok = (
            well_formed
            and (open_safety.ok or not quality.require_open_safety)
            and (reference_ok or not quality.require_reference_integrity)
            and semantic.ok
            and form.ok
            and layout.ok
        )
        visual_ok = (not quality.require_visual_complete) or visual_complete
        if not visual_ok and quality.allow_expert_unsafe:
            visual_ok = True
            warnings.append(
                "allow_expert_unsafe: visual_complete is "
                f"{status!r} (not verified) but accepted by policy."
            )
        ok = structural_ok and visual_ok

        # 8-9. compose + atomic save or rollback (debug artifact only).
        written_path: str | None = None
        debug_path: str | None = None
        should_publish = publish == "always" or (publish == "on_pass" and ok)
        if should_publish and (output_path is not None or output_stream is not None):
            written_path, read_back = self._publish(data, output_path, output_stream)
            if not read_back:
                warnings.append(STREAM_NOT_READ_BACK)
        elif not ok and debug_dir is not None:
            debug_path = self._write_debug(data, debug_dir, source_label)
            warnings.append(
                f"gate failed ({source_label}): output withheld; "
                f"debug artifact written to {debug_path}"
            )

        report = VisualCompleteReport(
            ok=ok,
            output_path=written_path,
            visual_complete=visual_complete,
            open_safety=open_safety,
            semantic=semantic,
            form=form,
            layout=layout,
            visual=visual,
            aesthetic=aesthetic,
            warnings=warnings,
            errors=errors,
            visual_complete_status=status,
            render_checked=visual.render_checked,
            debug_path=debug_path,
            policy=self._policy_dict(quality),
        )
        return report

    # -- stages ----------------------------------------------------------- #
    def _check_well_formed(self, data: bytes, errors: list[QualityError]) -> bool:
        """Integrity floor: the archive opens and every XML part parses."""

        try:
            with open_archive(data) as archive:
                guard_zip_file(archive)
                names = [info.filename for info in archive.infolist() if not info.is_dir()]
                for name in names:
                    base = os.path.basename(name)
                    if name.endswith(_XML_SUFFIXES) or base in _XML_NAMES:
                        if is_known_well_formed(archive, name):
                            continue  # the save's package check parsed these same bytes
                        try:
                            parse_xml_stdlib(read_member(archive, name), part_name=name)
                        except ET.ParseError as exc:
                            errors.append(
                                QualityError(
                                    REFERENCE_INTEGRITY_FAILED,
                                    f"malformed XML in {name}: {exc}",
                                )
                            )
                            return False
        except (zipfile.BadZipFile, OSError) as exc:
            errors.append(
                QualityError(
                    REFERENCE_INTEGRITY_FAILED,
                    f"output is not a readable ZIP/OPC package: {exc}",
                )
            )
            return False
        return True

    def _check_reference_integrity(
        self,
        data: bytes,
        quality: QualityPolicy,
        warnings: list[str],
        errors: list[QualityError],
        reference_document: Any | None,
    ) -> bool:
        if not quality.require_reference_integrity:
            return True

        ok = True
        from hwpx.tools.package_validator import validate_package

        package_report = validate_package(data)
        if not package_report.ok:
            ok = False
            detail = "; ".join(str(issue) for issue in package_report.errors[:5])
            errors.append(
                QualityError(
                    REFERENCE_INTEGRITY_FAILED,
                    f"OPC/package validation failed: {detail}",
                )
            )
        warnings.extend(str(issue) for issue in package_report.warnings[:5])

        try:
            from hwpx.tools.id_integrity import check_id_integrity

            document = reference_document
            close_after = False
            if document is None:
                from hwpx.document import HwpxDocument

                document = HwpxDocument.open(data)
                close_after = True
            try:
                id_report = check_id_integrity(document)
            finally:
                if close_after:
                    document.close()
            if not id_report.ok:
                ok = False
                # An orphan BinData asset alone also fails the report; name it
                # too, or the message ends in nothing.
                problems = [*id_report.dangling, *id_report.orphan_bin_data]
                errors.append(
                    QualityError(
                        REFERENCE_INTEGRITY_FAILED,
                        "ID/reference integrity failed: "
                        + ", ".join(str(item) for item in problems[:5]),
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive: never crash the gate
            # Never crash the gate, but never launder "could not check" into
            # "checked and fine" either. When the caller explicitly required
            # reference integrity, an unverified check is not a satisfied one.
            reason = f"{type(exc).__name__}: {exc}"
            warnings.append(f"id-integrity check unverified: {reason}")
            if quality.require_reference_integrity:
                ok = False
                errors.append(
                    QualityError(
                        REFERENCE_INTEGRITY_FAILED,
                        "ID/reference integrity was required but could not be "
                        f"verified: {reason}",
                    )
                )
        return ok

    def _check_open_safety(
        self, data: bytes, quality: QualityPolicy, errors: list[QualityError]
    ) -> OpenSafetyReport:
        from hwpx.tools.package_validator import validate_editor_open_safety

        report = validate_editor_open_safety(data)
        if not report.ok and quality.require_open_safety:
            errors.append(
                QualityError(
                    OPEN_SAFETY_FAILED,
                    "Generated HWPX package failed open-safety validation: "
                    + report.summary,
                )
            )
        return OpenSafetyReport(ok=report.ok, summary=report.summary, detail=report.to_dict())

    def _check_layout(
        self,
        data: bytes,
        quality: QualityPolicy,
        ledger: DirtyLayoutLedger | None,
        form: FormReport,
        errors: list[QualityError],
        warnings: list[str],
        reference_document: Any | None,
        required_fields: set[str] | None = None,
    ) -> LayoutReport:
        """Renderer-less layout smoke (plan §2 Phase D), policy-gated.

        ``layout_lint="strict"`` lets provable defects (stale lineseg, malformed
        table, dirty/lineseg leak, gross overflow under overflow=fail) block the
        save; ``"warn"`` surfaces them without blocking; ``"off"`` skips entirely.
        """

        if quality.layout_lint == "off":
            return LayoutReport.unverified("layout_lint policy is 'off'")

        from hwpx.layout.lint import (
            STALE_LINESEG_DETECTED,
            TABLE_STRUCTURE_INVALID,
            lint_layout,
        )

        try:
            lint = lint_layout(
                data,
                ledger=ledger,
                form=form,
                document=reference_document,
                overflow_policy=quality.overflow_policy,
                required_fields=required_fields,
            )
        except Exception as exc:  # pragma: no cover - defensive: never crash the gate
            # Do not crash the gate, but do not report a pass either. A caller
            # who asked for strict linting and received "passed" because the
            # linter threw has been told something untrue.
            reason = f"layout lint raised {type(exc).__name__}: {exc}"
            warnings.append(f"layout lint unverified: {reason}")
            return LayoutReport.unverified(reason)

        if quality.layout_lint == "warn":
            lint = lint.demote_errors()

        if not lint.ok:
            # Don't double-count a defect another stage already surfaced: when
            # reference/open-safety run, they own the stale-lineseg and table
            # codes (under their own codes), so only add the lint-unique ones to
            # the flat error list. The full set stays on ``report.layout``.
            covered_elsewhere = (
                quality.require_reference_integrity or quality.require_open_safety
            )
            structural = {STALE_LINESEG_DETECTED, TABLE_STRUCTURE_INVALID}
            for code in lint.error_codes:
                if code in structural and covered_elsewhere:
                    continue
                message = next((str(f) for f in lint.errors if f.code == code), code)
                errors.append(QualityError(code, message))
        return lint.to_quality_report()

    def _check_visual(
        self,
        data: bytes,
        before: str | PathLike[str] | None,
        edit_mask: EditMask | None,
        quality: QualityPolicy,
        warnings: list[str],
        errors: list[QualityError],
        debug_dir: str | PathLike[str] | None,
    ) -> tuple[VisualReport, VisualCompleteStatus]:
        if not quality.renders:
            return (
                VisualReport(
                    ok=True,
                    render_checked=False,
                    warnings=["visual gate disabled (render_check=off)"],
                ),
                "unverified",
            )

        oracle = self._oracle if self._oracle is not None else self._oracle_factory(
            dpi=quality.dpi
        )
        if oracle is None or not oracle.available():
            message = (
                "RENDER_ORACLE_UNAVAILABLE: no Hancom reachable; structural degrade "
                "-- visual_complete is unverified, not confirmed."
            )
            if quality.render_check == "required":
                errors.append(QualityError(RENDER_ORACLE_UNAVAILABLE, message))
                return (
                    VisualReport(ok=False, render_checked=False, errors=[message]),
                    "unverified",
                )
            warnings.append(message)
            return VisualReport(ok=True, render_checked=False, warnings=[message]), "unverified"

        work = Path(tempfile.mkdtemp(prefix="hwpx-save-visual-"))
        keep = debug_dir is not None
        try:
            after_path = work / "after.hwpx"
            after_path.write_bytes(data)
            report = oracle.check(
                str(before) if before is not None else None,
                str(after_path),
                edit_mask=edit_mask,
                diff_eps=quality.diff_eps,
                dpi=quality.dpi,
                work_dir=str(work) if keep else None,
                keep_artifacts=keep,
            )
        finally:
            if not keep:
                import shutil

                shutil.rmtree(work, ignore_errors=True)

        if not report.render_checked:
            warnings.extend(report.warnings)
            return report, "unverified"
        if report.ok:
            return report, "verified"
        errors.append(
            QualityError(
                VISUAL_COMPLETE_FAILED,
                "Hancom render shows a visual defect: "
                + "; ".join(
                    label
                    for label, flag in (
                        ("overlap", report.overlap_detected),
                        ("overflow", report.overflow_detected),
                        ("out-of-mask change", report.unexpected_diff_outside_mask),
                        ("page-count change", report.page_count_changed),
                    )
                    if flag
                )
                or "see VisualReport",
            )
        )
        return report, "failed"

    # -- publish ---------------------------------------------------------- #
    def _publish(
        self,
        data: bytes,
        output_path: str | PathLike[str] | None,
        output_stream: BinaryIO | None,
    ) -> tuple[str | None, bool]:
        """Write *data*; returns the path written (``None`` for a stream) and whether a stream written
        was read back (a path is written through the file system and counts as checked)."""

        read_back = True
        if output_stream is not None:
            read_back = write_stream_or_rollback(output_stream, data)
            if output_path is None:
                return None, read_back
        if output_path is not None:
            write_bytes_atomically(output_path, data)
            return str(output_path), read_back
        return None, read_back

    def _write_debug(
        self, data: bytes, debug_dir: str | PathLike[str], source_label: str
    ) -> str:
        directory = Path(debug_dir)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{source_label}.rejected.hwpx"
        target.write_bytes(data)
        return str(target)

    @staticmethod
    def _policy_dict(quality: QualityPolicy) -> dict[str, Any]:
        return {
            "require_open_safety": quality.require_open_safety,
            "require_visual_complete": quality.require_visual_complete,
            "require_reference_integrity": quality.require_reference_integrity,
            "render_check": quality.render_check,
            "xsd_mode": quality.xsd_mode,
            "overflow_policy": quality.overflow_policy,
            "layout_lint": quality.layout_lint,
            "allow_expert_unsafe": quality.allow_expert_unsafe,
        }


__all__ = [
    "SavePipeline",
    "PublishMode",
    "STREAM_NOT_READ_BACK",
    "write_bytes_atomically",
    "settle_written_stream",
    "write_stream_or_rollback",
]
