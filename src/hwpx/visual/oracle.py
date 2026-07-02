# SPDX-License-Identifier: Apache-2.0
"""The reusable VisualComplete render gate.

The oracle is the *renderer*, not the *transport*: any reachable Hancom (한글)
is a faithful backend (implementation plan §0.0). This module ships two, behind
one interface, plus a resolver that picks the best reachable one:

* :class:`WindowsComOracle` — Hancom COM via a packaged PowerShell backend.
  Canonical for CI/scale: fast, deterministic, batchable.
* :class:`MacHancomOracle` — ``Hancom Office HWP.app`` driven through the GUI
  (no AppleScript dictionary / headless CLI on that build), via a packaged
  AppleScript that scripts the menus. Same render engine; ideal for
  dev/spot-check, but slower and brittle (modal dialogs, single GUI session) —
  renders are serialized.
* :class:`NullOracle` — ``available() == False``; the degrade sentinel when no
  Hancom is reachable.

``resolve_oracle()`` returns the first reachable backend (Windows → Mac → Null).
``RenderOracle`` is a backward-compatible alias of :class:`WindowsComOracle`.

``visual_check`` renders a before/after ``.hwpx`` pair through whichever backend
it is given, scores the result with :mod:`hwpx.visual.diff`, and returns a
:class:`hwpx.visual.report.VisualReport`. It only needs ``available()`` and
``render_many()``, so it is backend-agnostic.

Assurance is tiered and never blurred (implementation plan §0.0): off-oracle, or
without the imaging stack, ``visual_check`` degrades to ``render_checked=False``
with a warning — it never raises and never silently claims a visual pass.

CLI::

    python -m hwpx.visual.oracle --before a.hwpx --after b.hwpx --out report/
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

from dataclasses import dataclass

from . import detectors, diff
from .masks import EditMask
from .report import VisualReport
from hwpx.form_fit.wordbox import WordBox

_BACKEND_SCRIPT = "_render_hwpx.ps1"
_OPEN_RATE_SCRIPT = "_hancom_open_rate.ps1"
_MAC_BACKEND_SCRIPT = "_render_hwpx_mac.applescript"
_MAC_REFRESH_SCRIPT = "_refresh_hwpx_mac.applescript"
_COM_REGISTRY_KEYS = (
    r"HWPFrame.HwpObject\CLSID",
    r"SOFTWARE\Classes\HWPFrame.HwpObject\CLSID",
    r"SOFTWARE\Classes\Wow6432Node\HWPFrame.HwpObject\CLSID",
)
_MAC_BUNDLE_ID = "com.hancom.office.hwp12.mac.general"
_MAC_APP_CANDIDATES = (
    "/Applications/Hancom Office HWP.app",
    "/Applications/Hancom Office HWP 2024.app",
    "/Applications/Hancom Office HWP 2022.app",
)


class RenderBackend:
    """Common render-oracle interface.

    ``visual_check`` only requires :meth:`available` and :meth:`render_many`.
    The default :meth:`render_many` serializes :meth:`render_pdf` — correct for
    the GUI backend (single session, one doc at a time); the COM backend
    overrides it to reuse one Hancom session across the batch.
    """

    def available(self) -> bool:  # pragma: no cover - overridden
        return False

    def render_pdf(self, hwpx_path: str, out_pdf: str | None = None) -> str | None:
        raise NotImplementedError

    def render_many(self, pairs: list[tuple[str, str]]) -> dict[str, str | None]:
        result: dict[str, str | None] = {src: None for src, _ in pairs}
        if not pairs or not self.available():
            return result
        for src, pdf in pairs:
            try:
                result[src] = self.render_pdf(src, pdf)
            except Exception:
                result[src] = None
        return result


class WindowsComOracle(RenderBackend):
    """Adapter that renders ``.hwpx`` → PDF through Hancom (한글) COM.

    Isolated and swappable: off-Windows (or where Hancom is not registered)
    :meth:`available` returns ``False`` and the engine degrades to structural
    checks instead of crashing. A fake oracle with ``available() -> False`` is
    the supported way to exercise the degrade path in tests.
    """

    def __init__(
        self,
        *,
        powershell: str | None = None,
        timeout: float = 300.0,
        dpi: int = 150,
    ) -> None:
        self._powershell = powershell or "powershell"
        self.timeout = timeout
        self.dpi = dpi

    def available(self) -> bool:
        """True only on Windows with the ``HWPFrame.HwpObject`` COM class registered."""

        if sys.platform != "win32":
            return False
        try:
            import winreg
        except Exception:
            return False
        roots = (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_LOCAL_MACHINE)
        for root in roots:
            for sub in _COM_REGISTRY_KEYS:
                try:
                    with winreg.OpenKey(root, sub):
                        return True
                except OSError:
                    continue
        return False

    def render_many(self, pairs: list[tuple[str, str]]) -> dict[str, str | None]:
        """Render ``(src_hwpx, out_pdf)`` pairs in one Hancom session.

        Returns ``{src: pdf_path or None}``. A single COM session is reused for
        the whole batch (Hancom startup dominates), and dialogs are auto-dismissed.
        """

        result: dict[str, str | None] = {src: None for src, _ in pairs}
        if not pairs or not self.available():
            return result

        tmp = tempfile.mkdtemp(prefix="hwpx-render-")
        try:
            jobs = [{"src": os.path.abspath(src), "pdf": os.path.abspath(pdf)} for src, pdf in pairs]
            jobs_path = os.path.join(tmp, "jobs.json")
            res_path = os.path.join(tmp, "result.json")
            with open(jobs_path, "w", encoding="utf-8") as handle:
                json.dump(jobs, handle, ensure_ascii=False)

            with resources.as_file(resources.files("hwpx.visual").joinpath(_BACKEND_SCRIPT)) as ps1:
                cmd = [
                    self._powershell, "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                    "-Jobs", jobs_path, "-ResultPath", res_path,
                ]
                try:
                    subprocess.run(
                        cmd, capture_output=True, timeout=self.timeout + 60.0 * len(pairs),
                        check=False,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    return result

            if not os.path.exists(res_path):
                return result
            try:
                # PowerShell Set-Content -Encoding UTF8 prepends a BOM; utf-8-sig
                # strips it (and reads BOM-less output fine too).
                with open(res_path, encoding="utf-8-sig") as handle:
                    entries = json.load(handle)
            except (json.JSONDecodeError, ValueError, OSError):
                # PowerShell/COM failure left no parseable result -> all unrendered.
                return result
            if isinstance(entries, dict):  # single job -> ConvertTo-Json emits an object
                entries = [entries]
            if not isinstance(entries, list):
                return result
            for (src, _pdf), entry in zip(pairs, entries):
                pdf = entry.get("pdf")
                if entry.get("saved") and pdf and os.path.exists(pdf):
                    result[src] = pdf
            return result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def render_pdf(self, hwpx_path: str, out_pdf: str | None = None) -> str | None:
        """Render a single ``.hwpx`` to PDF; returns the PDF path or ``None``."""

        if out_pdf is None:
            handle, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(handle)
        return self.render_many([(hwpx_path, out_pdf)]).get(hwpx_path)

    def open_check_many(self, paths: list[str]) -> list[dict[str, object]]:
        """OPEN-check ``paths`` through Hancom COM and return per-file verdicts.

        This is the M9 open-rate primitive (specs/007-open-rate FR-001). It is
        deliberately DISTINCT from :meth:`render_many`: it surfaces the real
        Hancom ``opened`` boolean as its own signal — never conflated with the
        ``saved``/render verdict that :meth:`render_many` (and ``visual_check``
        at oracle.py:402) report. ``opened`` answers "did real Hancom load this
        generated file without a corruption modal", which is the published
        open-rate; ``saved`` answers a different question (did it render to PDF).

        Each entry is::

            {
                "path": str,            # the input path as requested
                "opened": bool | None,  # True/False from Hancom; None = unverified
                "parsed": bool | None,  # opened and GetPageText(1..) textLength>0
                "text_length": int | None,
                "error": str | None,
                "retried": bool,        # opened only on the single retry pass
                "status": str,          # "ok" | "open_failed" | "unverified"
            }

        Honest degrade (constitution V/VI): off-Windows or where Hancom is not
        reachable, EVERY entry is returned with ``opened=None`` and
        ``status="unverified"`` — NEVER ``False`` (that would slander a file we
        never tested) and NEVER a silent ``True``. The aggregator maps
        ``unverified`` to the unverified bucket, not the numerator or denominator
        success count.
        """

        if not paths:
            return []
        if not self.available():
            return [self._unverified_entry(p) for p in paths]

        abs_paths = [os.path.abspath(p) for p in paths]
        # path -> requested (original) string, for surfacing the caller's path.
        requested = {os.path.abspath(p): p for p in paths}

        tmp = tempfile.mkdtemp(prefix="hwpx-open-rate-")
        try:
            jsonl_path = os.path.join(tmp, "checkpoint.jsonl")
            res_path = os.path.join(tmp, "result.json")
            with resources.as_file(
                resources.files("hwpx.visual").joinpath(_OPEN_RATE_SCRIPT)
            ) as ps1:
                cmd = [
                    self._powershell, "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                    "-OutJsonl", jsonl_path, "-OutJson", res_path,
                    "-Path", *abs_paths,
                ]
                try:
                    subprocess.run(
                        cmd, capture_output=True,
                        timeout=self.timeout + 60.0 * len(paths), check=False,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    # Subprocess never finished: prefer the crash-safe checkpoint
                    # (records written per-file) before degrading the rest.
                    return self._merge_checkpoint(abs_paths, requested, jsonl_path)

            entries = self._read_open_result(res_path)
            if entries is None:
                # No parseable consolidated result: fall back to the checkpoint.
                return self._merge_checkpoint(abs_paths, requested, jsonl_path)
            return self._entries_from_records(abs_paths, requested, entries)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _unverified_entry(path: str) -> dict[str, object]:
        return {
            "path": path,
            "opened": None,
            "parsed": None,
            "text_length": None,
            "error": "OPEN_ORACLE_UNAVAILABLE: no Hancom reachable on this platform",
            "retried": False,
            "status": "unverified",
        }

    @staticmethod
    def _normalise_record(record: dict[str, object]) -> dict[str, object]:
        """Map one PS1 ``{sourcePath,opened,textLength,error,retried}`` record to
        the ``open_check_many`` entry shape (open/render distinction preserved)."""

        opened_raw = record.get("opened")
        opened = bool(opened_raw) if opened_raw is not None else None
        text_length = record.get("textLength")
        try:
            text_length = int(text_length) if text_length is not None else None
        except (TypeError, ValueError):
            text_length = None
        error = record.get("error")
        parsed: bool | None
        if opened is None:
            parsed = None
        else:
            parsed = bool(opened and (text_length or 0) > 0)
        status = "ok" if opened else ("unverified" if opened is None else "open_failed")
        return {
            "path": record.get("sourcePath"),
            "opened": opened,
            "parsed": parsed,
            "text_length": text_length,
            "error": error,
            "retried": bool(record.get("retried", False)),
            "status": status,
        }

    @staticmethod
    def _read_open_result(res_path: str) -> list[dict[str, object]] | None:
        if not os.path.exists(res_path):
            return None
        try:
            # PowerShell Set-Content -Encoding UTF8 prepends a BOM; utf-8-sig
            # strips it (and reads BOM-less output fine too).
            with open(res_path, encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, ValueError, OSError):
            return None
        if isinstance(data, dict):  # single file -> ConvertTo-Json emits an object
            data = [data]
        if not isinstance(data, list):
            return None
        return data

    def _entries_from_records(
        self,
        abs_paths: list[str],
        requested: dict[str, str],
        records: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Align PS1 records back to the requested order, degrading any missing
        file to ``unverified`` (never silently dropped)."""

        by_path: dict[str, dict[str, object]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            if record.get("_meta"):  # repair-mode-probe meta line, not a verdict
                continue
            norm = self._normalise_record(record)
            src = norm.get("path")
            if isinstance(src, str):
                by_path[os.path.abspath(src)] = norm
        out: list[dict[str, object]] = []
        for abs_path in abs_paths:
            norm = by_path.get(abs_path)
            if norm is None:
                out.append(self._unverified_entry(requested.get(abs_path, abs_path)))
            else:
                # Surface the caller's original path string.
                norm["path"] = requested.get(abs_path, norm.get("path"))
                out.append(norm)
        return out

    def _merge_checkpoint(
        self,
        abs_paths: list[str],
        requested: dict[str, str],
        jsonl_path: str,
    ) -> list[dict[str, object]]:
        """Recover verdicts from the per-file JSONL checkpoint after a crash or
        timeout; files with no checkpoint record degrade to ``unverified``."""

        records: list[dict[str, object]] = []
        if os.path.exists(jsonl_path):
            try:
                with open(jsonl_path, encoding="utf-8-sig") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            records.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            continue
            except OSError:
                records = []
        return self._entries_from_records(abs_paths, requested, records)


class MacHancomOracle(RenderBackend):
    """Adapter that renders ``.hwpx`` → PDF through ``Hancom Office HWP.app``.

    *Dev / spot-check grade.* The render is as faithful as COM (same Hancom
    engine), but the transport is GUI automation: this build ships no AppleScript
    dictionary and no headless convert CLI, so a packaged AppleScript
    (``_render_hwpx_mac.applescript``) drives the menus through System Events:

        open <input> → 파일 (File) > "PDF로 저장하기..." → NSSavePanel (Return = 저장)
        → 파일 > "문서 닫기"

    The save panel is *document-relative* (it pre-fills 위치 = the input's
    directory and the name field = the input's stem), so :meth:`render_pdf`
    stages the input as ``<out_dir>/<out_stem>.hwpx`` and the panel writes exactly
    ``<out_dir>/<out_stem>.pdf`` with no path typing. The target is pre-deleted so
    no overwrite sheet appears.

    Operational notes: the GUI is a single shared session, so renders MUST be
    serialized (the default serial :meth:`render_many` does this). Requires a
    logged-in GUI session and Automation + Accessibility permission for the
    process that runs ``osascript``. Windows COM stays canonical for CI/scale.
    """

    def __init__(
        self,
        *,
        timeout: float = 300.0,
        dpi: int = 150,
        osascript: str = "osascript",
    ) -> None:
        self.timeout = timeout
        self.dpi = dpi
        self._osascript = osascript

    def _app_path(self) -> str | None:
        for candidate in _MAC_APP_CANDIDATES:
            if os.path.isdir(candidate):
                return candidate
        # Fall back to a Spotlight lookup by bundle id (handles non-default
        # install locations / localized app names).
        try:
            proc = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{_MAC_BUNDLE_ID}'"],
                capture_output=True, text=True, timeout=10.0, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.endswith(".app") and os.path.isdir(line):
                return line
        return None

    def available(self) -> bool:
        """True only on macOS with ``Hancom Office HWP.app`` installed."""

        if sys.platform != "darwin":
            return False
        return self._app_path() is not None

    def render_pdf(self, hwpx_path: str, out_pdf: str | None = None) -> str | None:
        """Render a single ``.hwpx`` to PDF via the GUI; returns the path or ``None``."""

        if not self.available():
            return None
        if out_pdf is None:
            handle, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(handle)

        src = os.path.abspath(hwpx_path)
        out_pdf = os.path.abspath(out_pdf)
        out_dir = os.path.dirname(out_pdf)
        out_stem = os.path.splitext(os.path.basename(out_pdf))[0]
        os.makedirs(out_dir, exist_ok=True)

        # Stage the input next to the target, named as the target stem, so the
        # document-relative save panel needs no typing (see class docstring).
        staged = os.path.join(out_dir, out_stem + ".hwpx")
        staged_is_source = os.path.abspath(staged) == src

        try:  # pre-delete target -> the overwrite ("대치?") sheet never appears
            if os.path.exists(out_pdf):
                os.remove(out_pdf)
        except OSError:
            pass

        cleanup_staged = False
        try:
            if not staged_is_source:
                shutil.copyfile(src, staged)
                cleanup_staged = True
            with resources.as_file(
                resources.files("hwpx.visual").joinpath(_MAC_BACKEND_SCRIPT)
            ) as script:
                cmd = [
                    self._osascript, str(script), staged, out_pdf, str(int(self.timeout)),
                ]
                try:
                    subprocess.run(
                        cmd, capture_output=True, text=True,
                        timeout=self.timeout + 60.0, check=False,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    return None
            if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0:
                return out_pdf
            return None
        finally:
            if cleanup_staged:
                try:
                    os.remove(staged)
                except OSError:
                    pass

    def refresh_document(self, hwpx_path: str) -> bool:
        """Open ``hwpx_path``, let dirty fields regenerate, save in place, close.

        The measured native-TOC re-number trigger (M7): a ``dirty="1"``
        TABLEOFCONTENTS is rebuilt on open — Hancom itself computes entries and
        page numbers — and CROSSREF caches recompute automatically. Exporting a
        PDF from the same regenerating session crashes this Hancom build
        (deterministic truncated PDFs, then the process dies), so refresh and
        render are intentionally two separate sessions. Returns True when the
        file was re-saved.
        """
        if not self.available():
            return False
        src = os.path.abspath(hwpx_path)
        try:
            before = os.stat(src).st_mtime_ns
        except OSError:
            return False
        with resources.as_file(
            resources.files("hwpx.visual").joinpath(_MAC_REFRESH_SCRIPT)
        ) as script:
            cmd = [self._osascript, str(script), src, str(int(self.timeout))]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=self.timeout + 60.0, check=False,
                )
            except (subprocess.TimeoutExpired, OSError):
                return False
        if "OK" not in (proc.stdout or ""):
            return False
        try:
            return os.stat(src).st_mtime_ns != before
        except OSError:
            return False


class NullOracle(RenderBackend):
    """Sentinel backend for environments with no reachable Hancom.

    ``available()`` is always ``False`` so ``visual_check`` degrades to a
    labelled structural pass rather than crashing.
    """

    def available(self) -> bool:
        return False

    def render_pdf(self, hwpx_path: str, out_pdf: str | None = None) -> str | None:
        return None


def resolve_oracle(
    *,
    powershell: str | None = None,
    timeout: float = 300.0,
    dpi: int = 150,
    osascript: str = "osascript",
) -> RenderBackend:
    """Return the best reachable render backend (Windows COM → Mac GUI → Null).

    Windows COM is canonical (CI/scale); Mac GUI is the dev/spot-check fallback;
    :class:`NullOracle` is the degrade sentinel when no Hancom is reachable.
    """

    windows = WindowsComOracle(powershell=powershell, timeout=timeout, dpi=dpi)
    if windows.available():
        return windows
    mac = MacHancomOracle(timeout=timeout, dpi=dpi, osascript=osascript)
    if mac.available():
        return mac
    return NullOracle()


# Backward-compatible alias: ``RenderOracle`` was the Windows COM oracle.
RenderOracle = WindowsComOracle


def _degraded(message: str) -> VisualReport:
    return VisualReport(ok=True, render_checked=False, warnings=[message])


def visual_check(
    before_hwpx: str | None,
    after_hwpx: str,
    *,
    oracle: RenderBackend,
    edit_mask: EditMask | None = None,
    diff_eps: float = 0.005,
    dpi: int = 150,
    work_dir: str | None = None,
    keep_artifacts: bool = False,
) -> VisualReport:
    """Render ``before``/``after`` through ``oracle`` and judge the change.

    ``before_hwpx=None`` requests a single new-doc structural-visual pass.
    Off-oracle or without imaging deps the report degrades
    (``render_checked=False``, ``ok=True``, warning) and never raises.
    """

    if oracle is None or not oracle.available():
        return _degraded(
            "RENDER_ORACLE_UNAVAILABLE: no Hancom reachable on this platform; "
            "structural degrade -- visual_complete is unverified, not confirmed."
        )
    if not (detectors.imaging_available() and diff.pymupdf_available()):
        return _degraded(
            "visual scoring dependencies (pymupdf/Pillow/numpy) unavailable; "
            "structural degrade -- visual_complete is unverified, not confirmed."
        )

    retain = keep_artifacts or work_dir is not None
    created_tmp = work_dir is None
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="hwpx-visual-"))
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    errors: list[str] = []

    try:
        after_abs = os.path.abspath(after_hwpx)
        pairs: list[tuple[str, str]] = [(after_abs, str(work / "after.pdf"))]
        before_abs: str | None = None
        if before_hwpx is not None:
            before_abs = os.path.abspath(before_hwpx)
            pairs.append((before_abs, str(work / "before.pdf")))

        rendered = oracle.render_many(pairs)
        after_render = rendered.get(after_abs)
        if after_render is None:
            errors.append("RENDER_ORACLE_UNAVAILABLE: Hancom failed to render the output document.")
            return VisualReport(ok=False, render_checked=False, warnings=warnings, errors=errors)

        if before_abs is not None:
            before_render = rendered.get(before_abs)
            if before_render is None:
                errors.append("RENDER_ORACLE_UNAVAILABLE: Hancom failed to render the original document.")
                return VisualReport(
                    ok=False, render_checked=False, output_render=after_render,
                    warnings=warnings, errors=errors,
                )
            signals = diff.compare_renders(
                before_render, after_render, edit_mask=edit_mask, diff_eps=diff_eps,
                dpi=dpi, diff_image_path=str(work / "diff.png"),
            )
            original_render: str | None = before_render
        else:
            signals = diff.analyze_single(after_render, dpi=dpi)
            original_render = None
            warnings.append(
                "no before document: single-render structural-visual only "
                "(overlap baseline unavailable)."
            )

        problem = (
            bool(signals.get("unexpected_diff_outside_mask"))
            or bool(signals.get("overlap_detected"))
            or bool(signals.get("overflow_detected"))
            or bool(signals.get("page_count_changed"))
        )
        report = VisualReport(
            ok=not problem,
            render_checked=True,
            original_render=original_render,
            output_render=after_render,
            diff_image=signals.get("diff_image"),
            unexpected_diff_outside_mask=bool(signals.get("unexpected_diff_outside_mask")),
            overlap_detected=bool(signals.get("overlap_detected")),
            overflow_detected=bool(signals.get("overflow_detected")),
            table_break_detected=False,
            page_count_changed=signals.get("page_count_changed"),
            warnings=warnings,
            errors=errors,
            max_diff_ratio=signals.get("max_diff_ratio"),
            before_page_count=signals.get("before_page_count"),
            after_page_count=signals.get("after_page_count"),
        )
        if not retain:
            # Verdict-only: artifacts are not kept, so don't return dangling paths.
            report.original_render = None
            report.output_render = None
            report.diff_image = None
        return report
    finally:
        if created_tmp and not retain:
            shutil.rmtree(work, ignore_errors=True)


@dataclass
class Block:
    """One logical 문항/answer unit identified by its glyphs."""

    id: str
    glyphs: list  # list[WordBox]


@dataclass
class BlockSplit:
    """A block that was found to straddle a column or page boundary."""

    block_id: str
    kind: str  # "column" | "page"


def _column_index(x_center: float, column_x_bounds: list) -> int:
    """Return the index of the column containing *x_center*, or -1 if none."""
    for i, (x0, x1) in enumerate(column_x_bounds):
        if x0 <= x_center <= x1:
            return i
    return -1  # outside any column (overflow handled elsewhere)


def detect_block_splits(
    blocks: list,
    column_x_bounds: list,
    page_height: float,
) -> list:
    """Return a :class:`BlockSplit` for every block whose glyphs span more than
    one page *or* more than one column.

    The detector is pure: it operates on explicit column boundaries and the
    :class:`WordBox` page field only — no Hancom oracle or fitz needed.

    Args:
        blocks: List of :class:`Block` objects to inspect.
        column_x_bounds: Ordered sequence of ``(x0, x1)`` tuples defining each
            column's horizontal extent (PDF points).  Typically two entries for
            a two-column exam sheet.
        page_height: Page height in PDF points.  Accepted but not used by this
            implementation (reserved for future y-position-based page detection).

    Returns:
        A list of :class:`BlockSplit`; empty when every block is wholly within
        one column on one page.
    """
    splits = []
    for block in blocks:
        if not block.glyphs:
            continue
        pages = {g.page for g in block.glyphs}
        if len(pages) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="page"))
            continue
        cols = {
            _column_index((g.x0 + g.x1) / 2.0, column_x_bounds)
            for g in block.glyphs
        }
        cols.discard(-1)  # glyphs outside all columns are not counted
        if len(cols) > 1:
            splits.append(BlockSplit(block_id=block.id, kind="column"))
    return splits


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m hwpx.visual.oracle",
        description="Render before/after .hwpx through Hancom and emit a VisualReport.",
    )
    parser.add_argument("--before", default=None, help="original .hwpx (omit for new-doc check)")
    parser.add_argument("--after", required=True, help="output .hwpx to verify")
    parser.add_argument("--out", default=None, help="dir for report.json + render artifacts")
    parser.add_argument("--diff-eps", type=float, default=0.005)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args(argv)

    try:  # keep Korean paths/warnings printable on cp949 Windows consoles
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    oracle = resolve_oracle(dpi=args.dpi)
    work = None
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        work = args.out
    report = visual_check(
        args.before, args.after, oracle=oracle, diff_eps=args.diff_eps,
        dpi=args.dpi, work_dir=work, keep_artifacts=bool(args.out),
    )
    text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out, "report.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "RenderBackend",
    "WindowsComOracle",
    "MacHancomOracle",
    "NullOracle",
    "RenderOracle",
    "resolve_oracle",
    "visual_check",
    "WordBox",
    "Block",
    "BlockSplit",
    "detect_block_splits",
]
