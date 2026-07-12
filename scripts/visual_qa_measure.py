#!/usr/bin/env python3
"""Measure the frozen S-069 fixture corpus without claiming real-Hancom assurance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwpx.visual.fixture_corpus import load_fixture_manifest
from hwpx.visual.qa_metrics import measure_fixture_corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = measure_fixture_corpus(load_fixture_manifest(args.manifest))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["gatePassed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
