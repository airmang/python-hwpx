#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute every core 5.0 migration import against an installed companion."""

from __future__ import annotations

import importlib.util

import hwpx


def main() -> int:
    if importlib.util.find_spec("hwpx_automation") is None:
        raise SystemExit(
            "python-hwpx-automation is not installed; install the candidate "
            "wheel before running this cross-stack verification"
        )

    failures: list[str] = []
    for legacy_name, surface in sorted(hwpx._MOVED_TO_COMPANION.items()):
        statement = surface.import_statement(legacy_name)
        if statement is None:
            failures.append(f"{legacy_name}: moved surface has no import statement")
            continue
        namespace: dict[str, object] = {}
        try:
            exec(statement, namespace)
        except Exception as exc:
            failures.append(
                f"{legacy_name}: {statement}: {type(exc).__name__}: {exc}"
            )
            continue
        if legacy_name not in namespace:
            failures.append(f"{legacy_name}: statement did not bind the legacy name")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print(f"[OK] executed {len(hwpx._MOVED_TO_COMPANION)} moved-surface hints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
