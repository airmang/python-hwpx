#!/usr/bin/env python3
"""Run one supervised render job. Queue/network credentials stay outside CLI/logs.

Production service wiring must inject authenticated queue jobs and requires owner
approval. This command is deliberately a local worker diagnostic, not a public
document upload endpoint.

Windows operator runbook:
1. Use a dedicated licensed Windows account/desktop with no interactive documents.
2. Keep the queue private; inject its secret through the service manager, never CLI.
3. Set HWPX_HANCOM_BUILD from the installed About/build value and pin worker code.
4. Give the service account write access only to ``--root`` and deny public ingress.
5. Treat COM watchdog failures as a poisoned session; investigate repeated failures
   before restarting the dedicated host. Host/firewall/service changes need owner approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from hwpx.visual.hancom_worker import PowerShellHancomSession, SerializedHancomWorker, WorkerJob


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--hancom-build", default=os.environ.get("HWPX_HANCOM_BUILD"))
    parser.add_argument("--worker-version", default="hancom-worker/1")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    if not args.hancom_build:
        parser.error("--hancom-build or HWPX_HANCOM_BUILD is required")
    digest = "sha256:" + hashlib.sha256(args.input.read_bytes()).hexdigest()
    worker = SerializedHancomWorker(
        args.root,
        session_factory=lambda: PowerShellHancomSession(hancom_build=args.hancom_build),
        worker_version=args.worker_version,
        timeout_seconds=args.timeout,
    )
    try:
        result = worker.render(WorkerJob(args.job_id, args.input, digest))
        print(result.to_json())
        return 0 if result.render_checked else 2
    finally:
        worker.close()


if __name__ == "__main__":
    raise SystemExit(main())
