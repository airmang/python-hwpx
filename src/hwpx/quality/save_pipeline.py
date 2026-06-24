# SPDX-License-Identifier: Apache-2.0
"""``SavePipeline`` — the one gate every write/save funnels through (plan §2 B).

Stages (plan task 2): integrity → XML well-formedness → OPC/ref/ID → semantic /
form assertions → layout lint → open-safety → visual oracle (Phase A, when
available/required) → compose ``VisualCompleteReport`` → atomic save or rollback.

The pipeline owns the **single atomic writer** for HWPX output. No public write
path writes serialized HWPX bytes to a destination except through
:meth:`SavePipeline.run` — that "zero bypass" property is what stops lineseg-style
drift (the ``patch.py`` byte-path leak was exactly such a bypass) and is asserted
by ``tests/test_save_pipeline_no_bypass.py``.

Assurance is tiered and never blurred (plan §0.0): ``visual_complete`` is ``True``
only on the oracle-verified tier; off-oracle the gate degrades to a labelled
structural pass (``visual_complete_status == "unverified"``), never a silent pass.
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile
from os import PathLike
from pathlib import Path
from typing import Any, BinaryIO, Literal
from xml.etree import ElementTree as ET

from hwpx.visual.masks import EditMask
from hwpx.visual.oracle import RenderBackend, resolve_oracle, visual_check
from hwpx.visual.report import VisualReport

from .ledger import DirtyLayoutLedger
from .policy import QualityPolicy
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

PublishMode = Literal["on_pass", "always", "never"]

_XML_SUFFIXES = (".xml", ".rels")
_XML_NAMES = ("[Content_Types].xml",)


# --------------------------------------------------------------------------- #
# The single atomic writer (moved here so the pipeline is the sole writer).
# --------------------------------------------------------------------------- #
def write_bytes_atomically(path: str | PathLike[str], data: bytes) -> None:
    """Write *data* to *path* via a temp file + ``os.replace`` (crash-safe)."""

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


def _capture_stream_checkpoint(stream: BinaryIO) -> tuple[int, bytes] | None:
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
            return position, b""
        return None
    try:
        stream.seek(position)
    except (AttributeError, OSError):
        return None
    return position, tail


def _rollback_stream(stream: BinaryIO, checkpoint: tuple[int, bytes] | None) -> None:
    if checkpoint is None:
        return
    position, tail = checkpoint
    try:
        stream.seek(position)
        if tail:
            stream.write(tail)
            stream.truncate(position + len(tail))
        else:
            stream.truncate(position)
        stream.seek(position)
    except (AttributeError, OSError):
        return


def write_stream_or_rollback(stream: BinaryIO, data: bytes) -> None:
    """Write *data* to *stream*, restoring the prior tail on failure."""

    checkpoint = _capture_stream_checkpoint(stream)
    if checkpoint is None:
        raise OSError(
            "HWPX stream save requires a checkpointable stream; "
            "use save_to_path() for non-seekable outputs"
        )
    try:
        written = stream.write(data)
        if written is not None and written != len(data):
            raise OSError(
                "short write while saving HWPX stream: "
                f"wrote {written} of {len(data)} bytes"
            )
    except BaseException:
        _rollback_stream(stream, checkpoint)
        raise


class SavePipeline:
    """Runs the quality gate over output bytes and performs the atomic write.

    A pipeline is cheap to construct; reuse one or make one per save. Pass an
    explicit ``oracle`` (e.g. a fake or :class:`NullOracle`) to keep tests
    deterministic; otherwise the best reachable backend is resolved lazily and
    only when a policy actually renders.
    """

    def __init__(
        self,
        *,
        oracle: RenderBackend | None = None,
        oracle_factory: Any = resolve_oracle,
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
            written_path = self._publish(data, output_path, output_stream)
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
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [info.filename for info in archive.infolist() if not info.is_dir()]
                for name in names:
                    base = os.path.basename(name)
                    if name.endswith(_XML_SUFFIXES) or base in _XML_NAMES:
                        try:
                            ET.fromstring(archive.read(name))
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
                errors.append(
                    QualityError(
                        REFERENCE_INTEGRITY_FAILED,
                        "ID/reference integrity failed: "
                        + ", ".join(str(item) for item in id_report.dangling[:5]),
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive: never crash the gate
            warnings.append(f"id-integrity check skipped: {type(exc).__name__}: {exc}")
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
            return LayoutReport.passed()

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
            warnings.append(f"layout lint skipped: {type(exc).__name__}: {exc}")
            return LayoutReport.passed()

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
            report = visual_check(
                str(before) if before is not None else None,
                str(after_path),
                oracle=oracle,
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
    ) -> str | None:
        if output_stream is not None:
            write_stream_or_rollback(output_stream, data)
            if output_path is None:
                return None
        if output_path is not None:
            write_bytes_atomically(output_path, data)
            return str(output_path)
        return None

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
    "write_bytes_atomically",
    "write_stream_or_rollback",
]
