# SPDX-License-Identifier: Apache-2.0
"""공개 예외가 기존 부모를 지키면서 ``HwpxError`` 로도 잡히는지 본다(ARC-14)."""

from __future__ import annotations

import pytest

from hwpx.equation.authoring import UnsupportedLatexError, latex_to_eqedit
from hwpx.equation.eqedit import EquationConversionError
from hwpx.equation.mathml import MathMLUnavailableError
from hwpx.errors import ERROR_CODES, HwpxError
from hwpx.ingest.base import DocumentIngestError, UnsupportedDocumentFormat
from hwpx.tools.recover import RecoverError
from hwpx.tools.toc_fidelity import WordBoxExtractorRequired

CASES = [
    (EquationConversionError, ValueError),
    (UnsupportedLatexError, ValueError),
    (MathMLUnavailableError, RuntimeError),
    (DocumentIngestError, RuntimeError),
    (UnsupportedDocumentFormat, RuntimeError),
    (RecoverError, ValueError),
    (WordBoxExtractorRequired, RuntimeError),
]


@pytest.mark.parametrize(("error", "builtin_parent"), CASES)
def test_public_exception_keeps_its_parent_and_joins_hwpx_error(error, builtin_parent) -> None:
    assert issubclass(error, HwpxError)
    assert issubclass(error, builtin_parent)
    raised = error("메시지")
    assert str(raised) == "메시지"
    assert raised.code == error.default_code
    assert raised.code in ERROR_CODES
    assert raised.to_dict()["message"] == "메시지"


def test_ingest_error_keeps_attempts() -> None:
    raised = UnsupportedDocumentFormat("없음", attempts=())
    assert raised.attempts == []
    assert raised.as_dict()["error"] == "UnsupportedDocumentFormat"


def test_unsupported_latex_is_caught_as_hwpx_error() -> None:
    with pytest.raises(HwpxError) as caught:
        latex_to_eqedit(r"\thiscommanddoesnotexist{x}")
    assert isinstance(caught.value, ValueError)
    assert caught.value.code == "equation-latex-unsupported"
