# SPDX-License-Identifier: Apache-2.0
"""The reusable VisualComplete render gate.

``RenderOracle`` is the swappable Hancom-render adapter (Windows + COM via a
packaged PowerShell backend). ``visual_check`` renders a before/after ``.hwpx``
pair through it, scores the result with :mod:`hwpx.visual.diff`, and returns a
:class:`hwpx.visual.report.VisualReport`.

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

from . import detectors, diff
from .masks import EditMask
from .report import VisualReport

_BACKEND_SCRIPT = "_render_hwpx.ps1"
_COM_REGISTRY_KEYS = (
    r"HWPFrame.HwpObject\CLSID",
    r"SOFTWARE\Classes\HWPFrame.HwpObject\CLSID",
    r"SOFTWARE\Classes\Wow6432Node\HWPFrame.HwpObject\CLSID",
)


class RenderOracle:
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


def _degraded(message: str) -> VisualReport:
    return VisualReport(ok=True, render_checked=False, warnings=[message])


def visual_check(
    before_hwpx: str | None,
    after_hwpx: str,
    *,
    oracle: RenderOracle,
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
            "RENDER_ORACLE_UNAVAILABLE: Hancom COM not available on this platform; "
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

    oracle = RenderOracle(dpi=args.dpi)
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


__all__ = ["RenderOracle", "visual_check"]
