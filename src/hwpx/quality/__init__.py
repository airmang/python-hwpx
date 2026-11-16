# SPDX-License-Identifier: Apache-2.0
"""The single save gate: ``SavePipeline`` + ``QualityPolicy`` + reports (Phase B).

Every write/save funnels through :class:`SavePipeline`, which runs validation and
(when a policy renders) the Phase-A Hancom visual oracle, then composes one
:class:`VisualCompleteReport` and performs the atomic save or rolls back. See the
implementation plan §2 Phase B and §0.0 (the assurance-tier contract).

``HwpxDocument.save`` routes through the pipeline with
:meth:`QualityPolicy.transparent` by default; pass ``doc.save(target,
quality=QualityPolicy.strict())`` (or another policy) to run that gate and receive
its full report as ``MutationReport.quality``.
"""
from __future__ import annotations

from .ledger import DirtyLayoutLedger, DirtyLayoutRange
from .policy import QualityPolicy
from .report import (
    ERROR_CODES,
    AestheticReport,
    FormReport,
    LayoutReport,
    OpenSafetyReport,
    QualityError,
    SemanticReport,
    VisualCompleteReport,
)
from .save_pipeline import SavePipeline, write_bytes_atomically, write_stream_or_rollback

__all__ = [
    "SavePipeline",
    "QualityPolicy",
    "VisualCompleteReport",
    "QualityError",
    "OpenSafetyReport",
    "SemanticReport",
    "FormReport",
    "LayoutReport",
    "AestheticReport",
    "DirtyLayoutLedger",
    "DirtyLayoutRange",
    "ERROR_CODES",
    "write_bytes_atomically",
    "write_stream_or_rollback",
]
