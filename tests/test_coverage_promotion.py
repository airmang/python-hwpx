# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

from hwpx.tools import generic_inventory


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
SAMPLES = [
    sample["file"]
    for sample in json.loads((CORPUS / "manifest.json").read_text("utf-8"))["samples"]
]


def test_generic_inventory_scans_engine_generic_body_elements() -> None:
    inventory = generic_inventory.scan_corpus(CORPUS)

    assert inventory
    assert "sec" not in inventory

    top = generic_inventory.top_entries(inventory, limit=10)
    assert top
    assert top[0]["tag"]
    assert top[0]["count"] >= top[0]["documents"] >= 1
    assert set(top[0]) == {"tag", "count", "documents", "samples"}


def test_generic_inventory_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "generic_inventory.json"

    written = generic_inventory.write_inventory(CORPUS, output, limit=10)

    payload = json.loads(output.read_text("utf-8"))
    assert written == payload
    assert payload["sample_count"] == len(SAMPLES)
    assert len(payload["top"]) == 10
    assert payload["inventory"]
