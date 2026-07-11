#!/usr/bin/env python3
"""Resumable 24-hour queue/worker soak runner with metadata-only checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def now() -> datetime:
    return datetime.now(timezone.utc)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--secret-env", default="HWPX_RENDER_QUEUE_SECRET")
    parser.add_argument("--max-samples", type=int)
    args = parser.parse_args()
    secret = os.environ.get(args.secret_env)
    if not secret:
        parser.error(f"secret environment variable {args.secret_env} is required")

    # Lazy import keeps python-hwpx independent; a 3-stack soak requires the MCP package.
    from hwpx_mcp_server.workflow.render_queue import DurableRenderQueue, sign_submission
    from hwpx_mcp_server.workflow.render_security import RenderSecurityPolicy
    from hwpx_mcp_server.workflow.rendering import RenderJobV2

    fixture = args.fixture.resolve()
    data = fixture.read_bytes()
    content_hash = "sha256:" + hashlib.sha256(data).hexdigest()
    policy = RenderSecurityPolicy(sandbox_root=args.queue_root.resolve() / "sandboxes")
    queue = DurableRenderQueue(args.queue_root, secret=secret.encode(), policy=policy)
    if args.checkpoint.exists():
        state = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    else:
        state = {
            "schemaVersion": "hwpx.render-soak-checkpoint.v1",
            "startedAt": now().isoformat(), "samples": [], "jobs": [],
            "fixtureHash": content_hash,
        }
    started = datetime.fromisoformat(state["startedAt"])
    target_seconds = args.duration_hours * 3600

    while (now() - started).total_seconds() < target_seconds:
        if args.max_samples is not None and len(state["samples"]) >= args.max_samples:
            break
        observed = now()
        sequence = len(state["jobs"]) + 1
        stable = hashlib.sha256(f"{state['startedAt']}:{sequence}".encode()).hexdigest()[:24]
        job = RenderJobV2(
            job_id=f"soak-{stable}", workflow_id="workflow-s068-soak",
            idempotency_key=f"soak-key-{stable}", source_content_hash=content_hash,
            source_size_bytes=len(data), submitted_at=observed,
        )
        receipt = queue.submit(
            job, data, signature=sign_submission(secret.encode(), job),
            principal_id="s068-soak", filename=fixture.name,
        )
        state["jobs"].append({"jobId": job.job_id, "submittedAt": observed.isoformat(), "status": receipt.status.value})
        health = queue.health(now=observed)
        state["samples"].append({
            "observedAt": observed.isoformat(), "available": health["available"],
            "degradedReason": health["degradedReason"], "queueDepth": health["queueDepth"],
            "runningJobs": health["runningJobs"], "oldestQueuedAgeSeconds": health["oldestQueuedAgeSeconds"],
        })
        queue.purge(now=observed)
        atomic_json(args.checkpoint, state)
        time.sleep(args.interval_seconds)

    finished = now()
    terminal = []
    for item in state["jobs"]:
        receipt = queue.get(item["jobId"])
        if receipt.status.value in {"succeeded", "failed", "unavailable", "cancelled"}:
            terminal.append(receipt)
    samples = state["samples"]
    elapsed = (finished - started).total_seconds()
    report = {
        "schemaVersion": "hwpx.render-soak.v1",
        "startedAt": started.isoformat(), "finishedAt": finished.isoformat(),
        "elapsedSeconds": elapsed, "requiredSeconds": 86400,
        "qualified24h": elapsed >= 86400,
        "samples": len(samples), "submittedJobs": len(state["jobs"]),
        "terminalJobs": len(terminal),
        "availability": (sum(bool(item["available"]) for item in samples) / len(samples)) if samples else None,
        "queueDepth": {
            "max": max((item["queueDepth"] for item in samples), default=0),
            "p95": percentile([float(item["queueDepth"]) for item in samples], 0.95),
        },
        "oldestQueuedAgeSecondsP95": percentile(
            [float(item["oldestQueuedAgeSeconds"]) for item in samples], 0.95
        ),
        "cleanupInvokedEverySample": True,
        "fixtureHash": content_hash,
        "containsDocumentText": False,
        "containsSecret": False,
    }
    atomic_json(args.out, report)
    return 0 if report["qualified24h"] and report["terminalJobs"] == report["submittedJobs"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
