# SPDX-License-Identifier: Apache-2.0
"""Template/Profile builder — new docs from verified Hancom saves (plan §2 E).

New documents are composed from **verified Hancom-saved templates + harvested
fragments**, never imagined XML. A :class:`~hwpx.design.profile.Profile` bundles a
body-stripped skeleton ``template.hwpx`` (real styles + page setup) with real
``<hp:p>``/``<hp:tbl>`` fragments; :func:`~hwpx.design.composer.compose` lowers a
:class:`~hwpx.design.plan.DocumentPlan` onto it and saves through the one
SavePipeline. Production mode forbids the minimal from-scratch builder.
"""
from __future__ import annotations

from .composer import ComposeResult, ProfileRequiredError, compose, compose_bytes
from .plan import Block, DocumentPlan
from .profile import Profile, available_profiles, load_profile
from .validator import StyleCoverage, style_coverage

__all__ = [
    "DocumentPlan",
    "Block",
    "compose",
    "compose_bytes",
    "ComposeResult",
    "ProfileRequiredError",
    "Profile",
    "load_profile",
    "available_profiles",
    "StyleCoverage",
    "style_coverage",
]
