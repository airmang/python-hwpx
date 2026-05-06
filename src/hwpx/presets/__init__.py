# SPDX-License-Identifier: Apache-2.0
"""Opinionated document presets built on public ``python-hwpx`` APIs."""

from .proposal import (
    DEFAULT_PROPOSAL_SECTIONS,
    ProposalSection,
    ProposalSpec,
    ProposalStylePreset,
    create_proposal_document,
    inspect_proposal_quality,
    normalize_proposal_spec,
)

__all__ = [
    "DEFAULT_PROPOSAL_SECTIONS",
    "ProposalSection",
    "ProposalSpec",
    "ProposalStylePreset",
    "create_proposal_document",
    "inspect_proposal_quality",
    "normalize_proposal_spec",
]
