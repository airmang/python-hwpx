# SPDX-License-Identifier: Apache-2.0
"""Regenerate docs/python-example-ledger.json after editing a current manual.

The documentation gate (tests/test_documentation_code_fences.py) freezes the
Python-fence census, per-file hashes, and mechanical classifications. This
script recomputes all of that with the gate's own logic — imported, not
copied, so the two can never drift — while preserving the human-written
``requiredContext`` prose per classification.

It intentionally does NOT edit the gate's ``EXPECTED_FENCE_COUNT`` /
``EXPECTED_FENCE_SHA256`` constants: updating those is the reviewed act that
makes a fence change deliberate. The script prints the values to paste.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tests" / "test_documentation_code_fences.py"
LEDGER = ROOT / "docs" / "python-example-ledger.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("documentation_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    gate = _load_gate()
    previous = json.loads(LEDGER.read_text(encoding="utf-8"))
    previous_context = {
        name: record["requiredContext"]
        for name, record in previous["classifications"].items()
    }

    fences = gate._python_fences()
    classifications: dict[str, dict[str, object]] = {
        name: {"ids": [], "requiredContext": previous_context[name]}
        for name in (
            "standalone",
            "context-fragment/external-input",
            "context-fragment/prior-state",
            "context-fragment/illustrative-signature",
        )
    }
    required_symbols: dict[str, list[str]] = {}
    for document, ordinal, code in fences:
        example_id = f"{document}#{ordinal}"
        classification = gate._mechanical_classification(code, example_id)
        classifications[classification]["ids"].append(example_id)
        if classification == "context-fragment/prior-state":
            required_symbols[example_id] = gate._external_names(code, example_id)
    classifications["context-fragment/prior-state"]["requiredSymbols"] = (
        required_symbols
    )

    ledger = {
        "schemaVersion": previous["schemaVersion"],
        "manuals": [path.as_posix() for path in gate.CURRENT_CORE_MANUALS],
        "fenceCount": len(fences),
        "sourceSha256": gate._fence_digest(fences),
        "manualSha256": {
            relative.as_posix(): hashlib.sha256(
                (ROOT / relative).read_bytes()
            ).hexdigest()
            for relative in gate.CURRENT_CORE_MANUALS
        },
        "classifications": classifications,
    }
    LEDGER.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[OK] {LEDGER.relative_to(ROOT)} regenerated")
    print(f"fenceCount   = {ledger['fenceCount']}")
    print(f"sourceSha256 = {ledger['sourceSha256']}")
    print(
        "Update EXPECTED_FENCE_COUNT / EXPECTED_FENCE_SHA256 in "
        "tests/test_documentation_code_fences.py to match."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
