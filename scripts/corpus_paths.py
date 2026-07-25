# SPDX-License-Identifier: Apache-2.0
"""Shared path handling for the corpus QA scripts.

This lived in corpus_pii_leak_sweep, whose PII rules moved to the MCP owner in
5.0. Re-rooting a recorded output path against a corpus directory has nothing to
do with personal information, and two scripts already depended on it, so it moves
here instead of leaving with the part that did.
"""

from __future__ import annotations

from pathlib import Path


def resolve_output_path(raw: str | None, corpus_root: Path) -> Path | None:
    """Resolve a manifest output_path against a possibly-relocated corpus root.

    Tries, in order: the recorded path as-is (absolute), the path joined to
    ``corpus_root`` (relative form), and — when the recorded path contains the
    corpus root's directory name — the tail re-rooted under ``corpus_root``
    (absolute paths from the generating machine). Returns None when no
    candidate exists on disk.
    """
    if not raw:
        return None
    recorded = Path(raw)
    candidates: list[Path] = []
    if recorded.is_absolute():
        candidates.append(recorded)
    else:
        candidates.append(corpus_root / recorded)
    parts = recorded.parts
    root_name = corpus_root.name
    if root_name in parts:
        idx = len(parts) - 1 - parts[::-1].index(root_name)
        tail = parts[idx + 1 :]
        if tail:
            candidates.append(corpus_root.joinpath(*tail))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
