#!/usr/bin/env python3
"""Prepare a hash-bound, bounded Windows payload for S-063 P0."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


BUCKET_ORDER = ("authored", "form-fit", "mail-merge", "exam", "redline")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_bound(source: Path, target: Path, expected: str | None) -> dict[str, Any]:
    source = source.expanduser().resolve()
    actual = sha256(source)
    if expected and actual != expected:
        raise ValueError(f"sha256 mismatch for {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    copied = sha256(target)
    if copied != actual:
        raise RuntimeError(f"copy hash mismatch for {source.name}")
    return {"name": target.name, "sha256": actual, "bytes": target.stat().st_size}


def run(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    negatives_path = Path(args.negatives_manifest).resolve()
    out = Path(args.out_dir).resolve()
    inputs = out / "inputs"
    negatives_dir = out / "negatives"
    out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [r for r in manifest["records"] if r.get("produced")]
    selected: list[dict[str, Any]] = []
    for bucket in BUCKET_ORDER:
        row = next((r for r in rows if r.get("bucket") == bucket), None)
        if row is None:
            raise ValueError(f"missing produced bucket {bucket}")
        selected.append(row)

    render_jobs: list[dict[str, str]] = []
    copied_inputs: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        source = Path(row["output_path"])
        target_name = f"{index:02d}_{row['id']}.hwpx"
        copied = copy_bound(source, inputs / target_name, row.get("output_sha256"))
        copied.update({"id": row["id"], "bucket": row["bucket"]})
        copied_inputs.append(copied)
        render_jobs.append(
            {
                "sourceId": row["id"],
                "sourceSha256": copied["sha256"],
                "src": rf"C:\openrate\m9-p0\inputs\{target_name}",
                "pdf": rf"C:\openrate\m9-p0\pdf\{index:02d}_{row['id']}.pdf",
            }
        )

    negatives = json.loads(negatives_path.read_text(encoding="utf-8"))["negatives"]
    must_refuse = [row for row in negatives if row.get("tier") == "must_refuse"]
    copied_negatives: list[dict[str, Any]] = []
    for index, row in enumerate(must_refuse):
        source = Path(row["path"])
        target_name = f"{index:02d}_{row['name']}"
        copied = copy_bound(source, negatives_dir / target_name, row.get("sha256"))
        copied.update({"kind": row.get("kind"), "tier": "must_refuse"})
        copied_negatives.append(copied)

    redline_paths = [
        rf"C:\openrate\m9-p0\inputs\{index:02d}_{row['id']}.hwpx"
        for index, row in enumerate(selected)
        if row["bucket"] == "redline"
    ]
    if len(redline_paths) != 1:
        raise ValueError("bounded render set must contain exactly one redline document")

    (out / "render_jobs.json").write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "redline_paths.txt").write_text("\n".join(redline_paths) + "\n", encoding="utf-8")
    (out / "negative_paths.txt").write_text(
        "\n".join(rf"C:\openrate\m9-p0\negatives\{r['name']}" for r in copied_negatives) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schemaVersion": 1,
        "purpose": "S-063 P0 bounded Windows render/redline spike",
        "sourceManifestSha256": sha256(manifest_path),
        "negativeManifestSha256": sha256(negatives_path),
        "renderInputs": copied_inputs,
        "mustRefuseInputs": copied_negatives,
        "renderJobsSha256": sha256(out / "render_jobs.json"),
        "redlinePathsSha256": sha256(out / "redline_paths.txt"),
        "negativePathsSha256": sha256(out / "negative_paths.txt"),
    }
    (out / "payload_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--negatives-manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
