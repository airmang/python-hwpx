# SPDX-License-Identifier: Apache-2.0
"""Profile loader + registry (plan §2 Phase E, task 1).

A :class:`Profile` bundles a verified Hancom-saved skeleton ``template.hwpx`` with
the harvested ``<hp:p>``/``<hp:tbl>`` fragments keyed by role. The default registry
loads the profiles committed under ``hwpx/design/profiles/``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

PROFILES_DIRNAME = "profiles"


@dataclass(slots=True)
class Profile:
    """A verified template skeleton + its harvested fragments."""

    id: str
    root: Path
    manifest: dict[str, Any]
    template_bytes: bytes
    _fragments: dict[str, bytes] = field(default_factory=dict)

    @property
    def style_coverage_threshold(self) -> float:
        return float(self.manifest.get("style_coverage_threshold", 0.98))

    @property
    def roles(self) -> list[str]:
        return list(self._fragments)

    def has_role(self, role: str) -> bool:
        return role in self._fragments

    def fragment(self, role: str) -> etree._Element:
        """Return a fresh (deep, detached) clone of the *role* fragment element."""

        if role not in self._fragments:
            raise KeyError(f"profile {self.id!r} has no fragment for role {role!r}")
        return etree.fromstring(self._fragments[role])

    @classmethod
    def load(cls, root: str | Path) -> "Profile":
        root = Path(root)
        manifest = json.loads((root / "profile.json").read_text(encoding="utf-8"))
        template_bytes = (root / manifest["template"]).read_bytes()
        fragments: dict[str, bytes] = {}
        for role, rel in manifest.get("fragments", {}).items():
            fragments[role] = (root / rel).read_bytes()
        return cls(
            id=manifest["id"],
            root=root,
            manifest=manifest,
            template_bytes=template_bytes,
            _fragments=fragments,
        )


@lru_cache(maxsize=1)
def _registry_root() -> Path:
    return Path(__file__).resolve().parent / PROFILES_DIRNAME


def available_profiles() -> list[str]:
    root = _registry_root()
    return sorted(p.name for p in root.iterdir() if (p / "profile.json").exists())


@lru_cache(maxsize=None)
def load_profile(profile_id: str) -> Profile:
    """Load a committed profile by id (cached)."""

    root = _registry_root() / profile_id
    if not (root / "profile.json").exists():
        raise KeyError(
            f"unknown profile {profile_id!r}; available: {available_profiles()}"
        )
    return Profile.load(root)


__all__ = ["Profile", "load_profile", "available_profiles", "PROFILES_DIRNAME"]
