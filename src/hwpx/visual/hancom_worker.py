# SPDX-License-Identifier: Apache-2.0
"""Serialized, supervised real-Hancom render worker primitives."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable, Protocol


WORKER_SCHEMA_VERSION = "hwpx.hancom-worker.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True)
class WorkerJob:
    job_id: str
    input_path: Path
    input_content_hash: str
    dpi: int = 144


@dataclass(frozen=True)
class WorkerArtifact:
    kind: str
    content_hash: str
    size_bytes: int
    relative_path: str
    page_number: int | None = None


@dataclass(frozen=True)
class WorkerResult:
    schema_version: str
    job_id: str
    status: str
    real_hancom: bool
    render_checked: bool
    worker_version: str
    hancom_build: str | None
    session_generation: int
    retryable: bool
    terminal_reason: str
    artifacts: tuple[WorkerArtifact, ...] = field(default_factory=tuple)
    page_count: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class RenderSession(Protocol):
    real_hancom: bool
    hancom_build: str | None

    def render_pdf(self, source: Path, target: Path) -> Path | None: ...
    def abort(self) -> None: ...
    def close(self) -> None: ...


class PowerShellHancomSession:
    """One-at-a-time Windows COM adapter with a killable PowerShell boundary."""

    real_hancom = True

    def __init__(self, *, hancom_build: str, powershell: str = "powershell") -> None:
        if not hancom_build:
            raise ValueError("hancom_build is required for real-Hancom provenance")
        self.hancom_build = hancom_build
        self.powershell = powershell
        self._process: subprocess.Popen[bytes] | None = None
        self._guard = threading.Lock()

    def render_pdf(self, source: Path, target: Path) -> Path | None:
        target.parent.mkdir(parents=True, exist_ok=True)
        work = target.parent
        jobs = work / "jobs.json"
        result = work / "result.json"
        jobs.write_text(json.dumps([{"src": str(source.resolve()), "pdf": str(target.resolve())}]), encoding="utf-8")
        script = resources.files("hwpx.visual").joinpath("_render_hwpx.ps1")
        with resources.as_file(script) as ps1:
            command = [
                self.powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(ps1), "-Jobs", str(jobs), "-ResultPath", str(result),
            ]
            with self._guard:
                self._process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                return_code = self._process.wait()
            finally:
                with self._guard:
                    self._process = None
        if return_code != 0 or not target.is_file():
            return None
        return target

    def abort(self) -> None:
        with self._guard:
            process = self._process
        if process and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()

    def close(self) -> None:
        self.abort()


class DeterministicFakeSession:
    """Contract-faithful CI renderer that can never claim real Hancom."""

    real_hancom = False
    hancom_build = None

    def __init__(self) -> None:
        self.aborted = False

    def render_pdf(self, source: Path, target: Path) -> Path | None:
        target.write_bytes(b"%PDF-FAKE\n" + source.read_bytes()[:64])
        return target

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        return None


class SerializedHancomWorker:
    """Single-flight worker; a timeout poisons and replaces the render session."""

    def __init__(
        self,
        root: Path,
        *,
        session_factory: Callable[[], RenderSession],
        worker_version: str,
        timeout_seconds: float = 300,
        abort_grace_seconds: float = 10,
    ) -> None:
        self.root = root.resolve()
        self.sandboxes = self.root / "sandboxes"
        self.artifacts = self.root / "artifacts"
        self.sandboxes.mkdir(parents=True, exist_ok=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.session_factory = session_factory
        self.worker_version = worker_version
        self.timeout_seconds = timeout_seconds
        self.abort_grace_seconds = abort_grace_seconds
        self._lock = threading.Lock()
        self._session: RenderSession | None = None
        self._generation = 0

    def _new_session(self) -> RenderSession:
        self._generation += 1
        self._session = self.session_factory()
        return self._session

    def _restart_session(self) -> None:
        if self._session:
            self._session.close()
        self._session = None

    def render(self, job: WorkerJob) -> WorkerResult:
        if not self._lock.acquire(blocking=False):
            return self._failure(job, "WORKER_BUSY", retryable=True)
        try:
            return self._render_locked(job)
        finally:
            self._lock.release()

    def _render_locked(self, job: WorkerJob) -> WorkerResult:
        actual = sha256_file(job.input_path)
        if actual != job.input_content_hash:
            return self._failure(job, "INPUT_HASH_MISMATCH", retryable=False)
        sandbox = Path(tempfile.mkdtemp(prefix=f"{job.job_id}-", dir=self.sandboxes))
        try:
            source = sandbox / "input.hwpx"
            shutil.copyfile(job.input_path, source)
            pdf = sandbox / "output.pdf"
            session = self._session or self._new_session()
            outcome: dict[str, object] = {}

            def invoke() -> None:
                try:
                    outcome["pdf"] = session.render_pdf(source, pdf)
                except BaseException as exc:  # contained at the worker boundary
                    outcome["error"] = type(exc).__name__

            thread = threading.Thread(target=invoke, name=f"hancom-{job.job_id}", daemon=True)
            thread.start()
            thread.join(self.timeout_seconds)
            if thread.is_alive():
                session.abort()
                thread.join(self.abort_grace_seconds)
                self._restart_session()
                return self._failure(job, "COM_WATCHDOG_TIMEOUT", retryable=True)
            if "error" in outcome or not outcome.get("pdf") or not pdf.is_file():
                self._restart_session()
                return self._failure(job, "HANCOM_RENDER_FAILED", retryable=True)

            destination = self.artifacts / job.job_id
            if destination.exists():
                shutil.rmtree(destination)
            destination.mkdir(parents=True)
            final_pdf = destination / "document.pdf"
            shutil.copyfile(pdf, final_pdf)
            try:
                pages = self._rasterize(final_pdf, destination, job.dpi)
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                return self._failure(job, "PAGE_RASTERIZE_FAILED", retryable=True)
            artifacts = [
                WorkerArtifact("pdf", sha256_file(final_pdf), final_pdf.stat().st_size, f"{job.job_id}/document.pdf")
            ]
            artifacts.extend(
                WorkerArtifact("page_png", sha256_file(page), page.stat().st_size, f"{job.job_id}/{page.name}", index)
                for index, page in enumerate(pages, 1)
            )
            real = bool(session.real_hancom and session.hancom_build)
            return WorkerResult(
                WORKER_SCHEMA_VERSION, job.job_id, "succeeded", real, real,
                self.worker_version, session.hancom_build, self._generation, False,
                "SUCCEEDED" if real else "FAKE_RENDER_ONLY", tuple(artifacts), len(pages),
            )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    @staticmethod
    def _rasterize(pdf: Path, destination: Path, dpi: int) -> list[Path]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for page PNG output") from exc
        document = fitz.open(pdf)
        pages: list[Path] = []
        try:
            scale = dpi / 72
            for index, page in enumerate(document, 1):
                target = destination / f"page-{index:04d}.png"
                page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(target)
                pages.append(target)
        finally:
            document.close()
        return pages

    def _failure(self, job: WorkerJob, reason: str, *, retryable: bool) -> WorkerResult:
        session = self._session
        return WorkerResult(
            WORKER_SCHEMA_VERSION, job.job_id, "unverified", False, False,
            self.worker_version, session.hancom_build if session else None,
            self._generation, retryable, reason,
        )

    def close(self) -> None:
        with self._lock:
            self._restart_session()


__all__ = [
    "DeterministicFakeSession", "PowerShellHancomSession", "SerializedHancomWorker",
    "WorkerArtifact", "WorkerJob", "WorkerResult", "WORKER_SCHEMA_VERSION", "sha256_file",
]
