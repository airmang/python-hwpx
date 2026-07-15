from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_mac_spike_membership_requires_real_sources(tmp_path: Path) -> None:
    mod = _load_script("m9_p0_mac_spike.py")
    source = tmp_path / "one.hwpx"
    source.write_bytes(b"hwpx")
    receipt = tmp_path / "membership.jsonl"
    receipt.write_text(json.dumps({"src": str(source)}) + "\n", encoding="utf-8")

    assert mod._load_sources(receipt) == [source.resolve()]

    source.unlink()
    try:
        mod._load_sources(receipt)
    except FileNotFoundError:
        pass
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError("missing source must fail")


def test_prepare_box_freezes_five_buckets_and_hashes(tmp_path: Path) -> None:
    mod = _load_script("m9_p0_prepare_box.py")
    records = []
    for index, bucket in enumerate(mod.BUCKET_ORDER):
        data = f"{bucket}-{index}".encode()
        source = tmp_path / f"{bucket}.hwpx"
        source.write_bytes(data)
        records.append(
            {
                "id": f"{bucket}-id",
                "bucket": bucket,
                "produced": True,
                "output_path": str(source),
                "output_sha256": _sha(data),
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"records": records}), encoding="utf-8")

    negative_rows = []
    for index in range(4):
        data = f"negative-{index}".encode()
        source = tmp_path / f"negative-{index}.hwpx"
        source.write_bytes(data)
        negative_rows.append(
            {
                "path": str(source),
                "name": source.name,
                "kind": f"kind-{index}",
                "tier": "must_refuse",
                "sha256": _sha(data),
            }
        )
    negatives = tmp_path / "negatives.json"
    negatives.write_text(json.dumps({"negatives": negative_rows}), encoding="utf-8")

    out = tmp_path / "payload"
    args = type(
        "Args",
        (),
        {"manifest": str(manifest), "negatives_manifest": str(negatives), "out_dir": str(out)},
    )()
    mod.run(args)

    jobs = json.loads((out / "render_jobs.json").read_text(encoding="utf-8"))
    receipt = json.loads((out / "payload_receipt.json").read_text(encoding="utf-8"))
    assert len(jobs) == 5
    assert [row["bucket"] for row in receipt["renderInputs"]] == list(mod.BUCKET_ORDER)
    assert len(receipt["mustRefuseInputs"]) == 4
    assert (out / "redline_paths.txt").read_text(encoding="utf-8").count("\n") == 1


def test_windows_spike_scripts_preserve_privacy_and_fail_closed() -> None:
    render = (ROOT / "scripts" / "m9_p0_box_render_probe.ps1").read_text(encoding="utf-8")
    redline = (ROOT / "scripts" / "m9_p0_redline_text_probe.ps1").read_text(encoding="utf-8")

    assert "Count -ne 5" in render
    assert "sourceSha256" in render
    assert "renderMs" in render
    assert "exit 2" in render

    assert 'GetTextFile($Format, $Option)' in redline
    assert "InitScan($Option, 0x0007, 0, 0, -1, -1)" in redline
    assert '"normal" "byref"' in redline
    assert '"all-masks" "noarg"' in redline
    assert "textSha256" in redline
    assert "textPreview" not in redline
