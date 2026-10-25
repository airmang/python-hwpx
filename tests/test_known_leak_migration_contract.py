# SPDX-License-Identifier: Apache-2.0
"""The known-leak migration contract covers exactly the allowlisted leaks.

docs/architecture/known-leak-migration.json says, for each group of genre or
policy logic still in core, who owns it after the move, what core keeps and
what replaces it. These checks keep it in step with the layer leak allowlist:
every known leak belongs to exactly one group, every group names only real
leaks, and the contract promises no version or date while the compatibility
decision is open.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "docs" / "architecture" / "known-leak-migration.json").read_text(encoding="utf-8")
)
CONTRACT_DOC = (ROOT / "docs" / "architecture" / "known-leak-migration.md").read_text(encoding="utf-8")
ALLOWLIST = json.loads((ROOT / "tests" / "data" / "layer_leak_allowlist.json").read_text(encoding="utf-8"))

_REQUIRED = {
    "id",
    "title",
    "allowlist",
    "undetected",
    "canonicalOwner",
    "coreKeeps",
    "publicReplacement",
    "coreSurfaceAffected",
    "automationConsumers",
}


def _names(groups: list[dict], key: str) -> list[tuple[str, str]]:
    return [(item["file"], item["qualname"]) for group in groups for item in group[key]]


def test_every_known_leak_belongs_to_exactly_one_group() -> None:
    groups = CONTRACT["groups"]
    known = sorted(
        (entry["file"], entry["qualname"])
        for entry in ALLOWLIST["entries"]
        if entry["classification"] == "known-leak"
    )
    undetected = sorted((entry["file"], entry["qualname"]) for entry in ALLOWLIST["undetected"])

    assert sorted(_names(groups, "allowlist")) == known
    assert sorted(_names(groups, "undetected")) == undetected
    assert len(known) + len(undetected) == 8


def test_format_vocabulary_is_not_scheduled_to_move() -> None:
    vocabulary = {
        (entry["file"], entry["qualname"])
        for entry in ALLOWLIST["entries"]
        if entry["classification"] == "format-vocabulary"
    }
    assert vocabulary == {("tools/mail_merge.py", "_SAFE_FILENAME_RE"), ("tools/toc_author.py", "_OUTLINE_NAME_RE")}
    assert not vocabulary & set(_names(CONTRACT["groups"], "allowlist"))


def test_each_group_names_an_automation_owner_core_primitive_and_replacement() -> None:
    ids = [group["id"] for group in CONTRACT["groups"]]
    assert ids == [
        "official-reference-policy",
        "document-plan-input",
        "report-heading-guess",
        "evalplan-caption-cleanup",
    ]
    for group in CONTRACT["groups"]:
        assert _REQUIRED <= set(group), group["id"]
        assert group["canonicalOwner"].startswith("hwpx_automation."), group["id"]
        for key in ("coreKeeps", "publicReplacement", "coreSurfaceAffected", "automationConsumers"):
            assert group[key] and all(str(item).strip() for item in group[key]), (group["id"], key)
        assert f"### {group['id']}" in CONTRACT_DOC, group["id"]


def test_no_schedule_is_promised_while_the_decision_is_open() -> None:
    compatibility = CONTRACT["compatibility"]
    assert compatibility["decision"] == "pending-owner"
    assert [option["id"] for option in compatibility["options"]] == ["A", "B", "C"]
    text = json.dumps(CONTRACT, ensure_ascii=False)
    # No release number or date: 6.x / "next major" wording only.
    assert not re.search(r"\b\d+\.\d+(\.\d+)?\b", text.replace("6.x", ""))
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text)
