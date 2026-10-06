# SPDX-License-Identifier: Apache-2.0
"""Genre and policy logic may not hide inside core-owned functions.

The ownership ledger classifies whole files; ``scripts/layer_leak_guard.py``
looks inside them for Hangul regexes and the automation layer's
document-plan keys. Every existing hit is listed with a reason in
``tests/data/layer_leak_allowlist.json``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import layer_leak_guard as guard  # scripts/ is on the pytest pythonpath

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "tests" / "data" / "layer_leak_allowlist.json"


def _scan(source: str, relative: str = "tools/new_genre.py") -> list[guard.Hit]:
    return guard.scan_source(relative, textwrap.dedent(source))


def test_the_committed_tree_matches_the_allowlist() -> None:
    found = guard.problems(guard.scan(), guard.load_allowlist()) + guard.undetected_problems()

    assert found == [], "\n".join(found) + "\n\n" + guard.GUIDANCE


def test_cli_passes_on_the_committed_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "layer_leak_guard.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_new_hangul_regex_fails_and_points_to_the_guardrails() -> None:
    new = _scan(
        """
        import re

        def classify_notice(text):
            return re.search(r"^\\s*공고\\s*제\\d+호", text)
        """
    )

    found = guard.problems(guard.scan() + new, guard.load_allowlist())

    assert len(found) == 1
    assert "new hangul-regex in src/hwpx/tools/new_genre.py classify_notice" in found[0]
    assert "section 4" in guard.GUIDANCE
    assert "docs/architecture/product-boundary.md" in guard.GUIDANCE


def test_a_second_hit_in_an_allowlisted_function_fails() -> None:
    extra = _scan(
        """
        def _paragraphs_from_document_plan(plan):
            return plan["blocks"]
        """,
        relative="tools/doc_diff.py",
    )

    found = guard.problems(guard.scan() + extra, guard.load_allowlist())

    assert len(found) == 1
    assert "3 found, 2 allowed" in found[0]


def test_a_fixed_leak_must_leave_the_allowlist() -> None:
    hits = [h for h in guard.scan() if h.qualname != "ARABIC_HEAD"]

    found = guard.problems(hits, guard.load_allowlist())

    assert found == [
        "stale allowlist entry src/hwpx/tools/markdown_export.py ARABIC_HEAD hangul-regex: "
        "1 allowed, 0 found — lower or remove it in tests/data/layer_leak_allowlist.json"
    ]


@pytest.mark.parametrize(
    "source,qualname",
    [
        # module-level constant passed by name
        ('import re\nPAT = "^붙임"\ndef f(t):\n    return re.match(PAT, t)\n', "f"),
        # aliased module, keyword argument, method of a class
        (
            "import re as _re\nclass C:\n    def m(self, t):\n"
            "        return _re.fullmatch(pattern='개요', string=t)\n",
            "C.m",
        ),
        # from-import, implicit concatenation
        ('from re import sub\ndef g(t):\n    return sub("[가-힣]" "+", "", t)\n', "g"),
        # module-level compile is reported under its name
        ('import re\nHEAD = re.compile(r"^제\\d+장")\n', "HEAD"),
    ],
)
def test_hangul_regex_forms(source: str, qualname: str) -> None:
    hits = _scan(source)

    assert [(h.kind, h.qualname) for h in hits] == [("hangul-regex", qualname)]


def test_plan_schema_keys() -> None:
    hits = _scan(
        """
        def adapt(plan):
            for section in plan.get("sections", []):
                yield section["blocks"]
            plan["title"]
            plan.get("paragraphs")
        """
    )

    assert [(h.kind, h.detail) for h in hits] == [
        ("plan-schema-key", ".get('sections')"),
        ("plan-schema-key", "['blocks']"),
    ]


def test_ascii_regexes_and_non_regex_hangul_are_not_hits() -> None:
    hits = _scan(
        """
        import re
        LABEL = "표"
        def f(t):
            re.compile(r"section\\d+\\.xml$")
            return LABEL in t
        """
    )

    assert hits == []


def test_excluded_paths_are_not_scanned() -> None:
    scanned = {path.relative_to(guard.SRC).as_posix() for path in guard.product_modules()}

    assert "_moved_modules.py" not in scanned
    assert not any(path.startswith("data/") for path in scanned)
    assert "table_patch.py" in scanned


def test_allowlist_entries_are_classified_and_explained() -> None:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))

    for entry in data["entries"]:
        assert set(entry) == {"file", "qualname", "kind", "count", "classification", "reason"}
        assert entry["kind"] in {"hangul-regex", "plan-schema-key"}
        assert entry["classification"] in {"known-leak", "format-vocabulary"}
        assert entry["count"] >= 1 and entry["reason"]
        if entry["classification"] == "known-leak":
            assert "a candidate to move in a later major release" in entry["reason"]
    for entry in data["undetected"]:
        assert set(entry) == {"file", "qualname", "reason"}
        assert "a candidate to move in a later major release" in entry["reason"]


def test_undetected_known_leaks_must_still_exist(tmp_path: Path) -> None:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    data["undetected"].append(
        {"file": "table_patch.py", "qualname": "moved_away", "reason": "x"}
    )
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    found = guard.undetected_problems(allowlist)

    assert found == [
        "undetected known leak src/hwpx/table_patch.py moved_away no longer exists — "
        "remove it from tests/data/layer_leak_allowlist.json"
    ]
