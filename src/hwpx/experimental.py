# SPDX-License-Identifier: Apache-2.0
"""실험적(experimental) 공개 표면.

여기 노출되는 이름들은 **계약이 유동적**입니다 — minor 릴리스에서 시그니처,
동작, 반환 스키마가 예고 없이 바뀔 수 있습니다. 안정 계약이 필요하면 stable 표면
(:mod:`hwpx` 최상위 ``__all__`` / ``docs/stable-api.md``)만 사용하세요.

이 모듈은 실제 구현 모듈에서 이름을 **재내보내기(re-export)** 만 합니다(모듈을
옮기지 않음). 4.0~6.x의 최상위 ``from hwpx import ...`` 재내보내기는 7.0에서
없어졌습니다 — ``from hwpx.experimental import ...``를 쓰세요.

문서 ingest(``DocumentIngestor`` 등 7개)와 미리보기(``render_layout_preview`` 등 5개)는
7.0에서 python-hwpx-automation(``hwpx_automation.ingest`` / ``hwpx_automation.preview``)으로
옮겼습니다. 그 이름을 가져오면 새 자리를 알려 주는 ``ImportError``가 납니다.

수식 변환(``latex_to_eqedit``·``estimate_equation_size``·``UnsupportedLatexError``)은 7.0에서
:mod:`hwpx.equation` 의 stable 이름이 되어 여기서 빠졌습니다. 여기서 가져오면 그 자리를 알려 주는
``hwpx.MovedToSubmodule``(ImportError)이 납니다.
"""

from __future__ import annotations

from .capabilities import (
    contract_document,
    contract_json_schema,
    describe_capabilities,
)
from .plan import (
    EditPlan,
    PlanReport,
    PlanValidationError,
    apply_edit_plan,
    validate_edit_plan,
)
from .layout.pages import (
    EstimatedLine,
    PageEstimate,
    estimate_pages,
)

__all__ = [
    "estimate_pages",
    "PageEstimate",
    "EstimatedLine",
    "EditPlan",
    "PlanReport",
    "PlanValidationError",
    "apply_edit_plan",
    "validate_edit_plan",
    "describe_capabilities",
    "contract_document",
    "contract_json_schema",
]

#: 4.0~6.x가 여기서 실험 기능으로 내보내던 수식 변환. 7.0에서 ``hwpx.equation`` 의 stable 이름이다.
_MOVED_TO_EQUATION = frozenset({"UnsupportedLatexError", "estimate_equation_size", "latex_to_eqedit"})


def __getattr__(name: str) -> object:
    """7.0에서 ``hwpx.equation`` 으로 간 수식 변환이나 python-hwpx-automation으로 옮긴 실험 이름이면
    새 자리를 알려 준다."""

    if name in _MOVED_TO_EQUATION:
        from . import MovedToSubmodule

        raise MovedToSubmodule(
            f"'hwpx.experimental.{name}'는 python-hwpx 7.0에서 hwpx.equation의 stable 이름이 되었고 "
            f"hwpx.experimental에서는 빠졌습니다. 이렇게 가져오세요:\n"
            f"    from hwpx.equation import {name}"
        )
    from ._moved_modules import moved_name_error

    moved = moved_name_error(__name__, name)
    if moved is not None:
        raise moved
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
