from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from hwpx.practice.registry import (
    build_source_integrity_receipt,
    snapshot_source_tree,
    validate_storage_roots,
)


def test_snapshot_is_read_only_and_unchanged_receipt_exposes_no_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    work = tmp_path / "work"
    source.mkdir()
    (source / "a.hwpx").write_bytes(b"first")
    (source / "metadata.bin").write_bytes(b"second")
    before_stats = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in source.iterdir()
    }

    validate_storage_roots(source, work)
    before = snapshot_source_tree(source)
    after = snapshot_source_tree(source)
    receipt = build_source_integrity_receipt(before, after)

    assert receipt["unchanged"] is True
    assert receipt["sourceFileCountBefore"] == 2
    assert receipt["changedCount"] == 0
    assert receipt["addedCount"] == 0
    assert receipt["removedCount"] == 0
    assert before_stats == {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in source.iterdir()
    }
    encoded = json.dumps(receipt)
    assert "a.hwpx" not in encoded
    assert str(source) not in encoded


def test_integrity_receipt_detects_change_add_remove_and_write_event(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first = source / "first.hwpx"
    removed = source / "removed.bin"
    first.write_bytes(b"before")
    removed.write_bytes(b"remove-me")
    before = snapshot_source_tree(source)

    first.write_bytes(b"after")
    removed.unlink()
    (source / "added.sidecar").write_bytes(b"added")
    after = snapshot_source_tree(source)
    receipt = build_source_integrity_receipt(before, after, write_events=1)

    assert receipt["unchanged"] is False
    assert receipt["changedCount"] == 1
    assert receipt["addedCount"] == 1
    assert receipt["removedCount"] == 1
    assert receipt["writeEventCount"] == 1


def test_write_monitor_fails_even_when_bytes_return_to_original(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.hwpx").write_bytes(b"same")
    snapshot = snapshot_source_tree(source)
    receipt = build_source_integrity_receipt(snapshot, snapshot, write_events=1)
    assert receipt["beforeManifestSha256"] == receipt["afterManifestSha256"]
    assert receipt["unchanged"] is False


def test_integrity_paths_use_unicode_nfc_for_mac_and_smb_equivalence() -> None:
    digest = "a" * 64
    nfc = "한글양식.hwpx"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    receipt = build_source_integrity_receipt(
        {nfc: {"sha256": digest, "sizeBytes": 10}},
        {nfd: {"sha256": digest, "sizeBytes": 10}},
    )
    assert receipt["unchanged"] is True


def test_integrity_rejects_unicode_normalization_collision() -> None:
    digest = "a" * 64
    nfc = "한글.hwpx"
    nfd = unicodedata.normalize("NFD", nfc)
    with pytest.raises(ValueError, match="normalization path collision"):
        build_source_integrity_receipt(
            {
                nfc: {"sha256": digest, "sizeBytes": 10},
                nfd: {"sha256": digest, "sizeBytes": 10},
            },
            {},
        )


@pytest.mark.parametrize(
    ("source_parts", "work_parts"),
    [
        (("root",), ("root",)),
        (("root",), ("root", "work")),
        (("root", "source"), ("root",)),
    ],
)
def test_source_and_work_roots_must_be_disjoint(
    tmp_path: Path,
    source_parts: tuple[str, ...],
    work_parts: tuple[str, ...],
) -> None:
    source = tmp_path.joinpath(*source_parts)
    work = tmp_path.joinpath(*work_parts)
    with pytest.raises(ValueError, match="disjoint"):
        validate_storage_roots(source, work)


def test_source_snapshot_rejects_symlink_escape(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside.hwpx"
    source.mkdir()
    outside.write_bytes(b"outside")
    (source / "linked.hwpx").symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        snapshot_source_tree(source)
