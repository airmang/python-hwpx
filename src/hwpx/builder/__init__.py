# SPDX-License-Identifier: Apache-2.0
"""Public builder nodes for declarative HWPX document generation."""

from .core import (
    Bullet,
    Document,
    Footer,
    Header,
    Heading,
    Image,
    Margins,
    Metadata,
    NumberedList,
    PageBreak,
    PageNumber,
    PageSize,
    Paragraph,
    Run,
    Section,
    Table,
    approval_box,
)
from .report import (
    FIDELITY_CONTRACT,
    BuilderSaveReport,
    BuilderVerifyReport,
    ReopenReport,
)

__all__ = [
    "FIDELITY_CONTRACT",
    "BuilderSaveReport",
    "BuilderVerifyReport",
    "Bullet",
    "Document",
    "Footer",
    "Header",
    "Heading",
    "Image",
    "Margins",
    "Metadata",
    "NumberedList",
    "PageBreak",
    "PageNumber",
    "PageSize",
    "Paragraph",
    "ReopenReport",
    "Run",
    "Section",
    "Table",
    "approval_box",
]
