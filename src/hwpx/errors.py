# SPDX-License-Identifier: Apache-2.0
"""Structured exception base for python-hwpx.

The structured contract covers the safe-write and preservation path, the
moved-surface guidance, and the failures documented on an individual API: those
raise a :class:`HwpxError` (or a subclass). It is not a blanket wrapper around
every call. Operating-system and container-level failures keep the exception
Python already raises — ``FileNotFoundError`` for a missing path,
:class:`zipfile.BadZipFile` for a payload that is not an HWPX package — and the
support matrix documents them in that form.

The base carries three machine-readable fields on top of the human-readable
message, so a caller can branch on a stable ``code``, read the measured
``context``, and surface an actionable ``suggestion`` without parsing prose:

- ``code`` — a stable, kebab-case identifier for the failure class. Callers may
  switch on it; it is part of the contract and changes only on a major boundary.
- ``context`` — a JSON-serialisable dict of the measured values that triggered
  the failure (offending parts, indices, counts…). Empty when there is nothing
  to measure.
- ``suggestion`` — one actionable next step, or ``None`` when there is nothing
  specific to advise.

``str(exc)`` stays the human sentence (the ``message``), so existing ``except``
handlers and log lines are unchanged. Subclasses set :attr:`default_code`, which
lets a historical ``raise Subclass("message")`` site keep working while gaining
the structured fields with no raise-site churn (§11 — no bulk raise rewrites).
"""

from __future__ import annotations

from typing import Any, Mapping


class HwpxError(Exception):
    """Base for structured, fail-closed python-hwpx errors."""

    #: Stable ``code`` used when a raise site does not pass an explicit ``code``.
    default_code: str = "hwpx-error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.default_code
        self.context: dict[str, Any] = dict(context) if context else {}
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, Any]:
        """The structured envelope: ``code`` / ``message`` / ``context`` / ``suggestion``."""

        return {
            "code": self.code,
            "message": self.message,
            "context": dict(self.context),
            "suggestion": self.suggestion,
        }


class SaveError(HwpxError, ValueError):
    """A representative save path (``save_to_path`` / ``save_to_stream`` /
    ``to_bytes``) failed closed before writing any output.

    Subclasses :class:`ValueError` for backward compatibility: pre-4.0 callers
    caught ``ValueError`` from these paths and must keep working.
    """

    default_code = "save-failed"


class HwpxValueError(HwpxError, ValueError):
    """An argument's *value* is not usable for the requested operation.

    Dual inheritance follows the :class:`SaveError` precedent: a 5.x caller
    that wrote ``except ValueError`` around a facade call keeps working, and
    gains ``code`` / ``context`` / ``suggestion`` for free.
    """

    default_code = "hwpx-value-error"


class HwpxTypeError(HwpxError, TypeError):
    """An argument's *type* is not one the operation accepts."""

    default_code = "hwpx-type-error"


class HwpxLookupError(HwpxError, KeyError):
    """A named or indexed thing (style, section, paragraph, field…) is absent.

    ``KeyError.__str__`` would wrap the message in the repr quotes it uses for
    missing keys, which contradicts the base contract stated above — ``str(exc)``
    stays the human sentence. :meth:`__str__` restores it.
    """

    default_code = "hwpx-lookup-error"

    def __str__(self) -> str:
        return self.message


class HwpxStateError(HwpxError, RuntimeError):
    """The document is not in a state where the operation is meaningful."""

    default_code = "hwpx-state-error"


#: The kebab-case ``HwpxError.code`` vocabulary. Codes are ``<domain>-<condition>``
#: where the domain names a surface area (the 6.0 namespaces plus the package-level
#: concerns). This is deliberately **not** unified with the SCREAMING_SNAKE codes in
#: :mod:`hwpx.quality.report`: those are values in a released receipt schema
#: (``hwpx.mutation-report/v1``, ``VisualCompleteReport``), and renaming them would
#: break receipt consumers. The two vocabularies meet in exactly one place —
#: :mod:`hwpx._document.persistence` wraps a quality failure as ``quality-gate-failed``.
ERROR_CODE_DOMAINS = frozenset(
    {
        "capability",
        "contract",
        "document",
        "field",
        "heading",
        "hwpx",
        "media",
        "note",
        "open",
        "package",
        "page",
        "paragraph",
        "plan",
        "preservation",
        "quality",
        "ref",
        "save",
        "section",
        "shape",
        "style",
        "table",
        "text",
        "track",
    }
)


#: 5.x 에 이미 나간 코드 중 ``<도메인>-<조건>`` 문법에 맞지 않는 것들.
#:
#: 이름이 "무엇이"가 아니라 "무슨 일이"로 시작해서 도메인이 성립하지 않는다
#: (``unknown-contract-document`` 의 도메인은 ``unknown`` 이 아니라
#: ``contract`` 이어야 했다). 그런데 이 코드들은 5.6.0 에 발행됐고, 계약상
#: 코드는 호출자가 분기하는 값이다. 문법을 지키자고 **이미 나간 값을 바꾸는
#: 것**보다 유예 목록을 명시하는 쪽이 정직하다. 7.0 에서 정리한다.
GRANDFATHERED_CODES = frozenset(
    {
        "unknown-contract-document",
        "unknown-contract-schema",
    }
)

#: The public-path code vocabulary: ``code`` → one-line meaning.
#:
#: This registry is the **single source** for ``docs/error-codes.md`` — the doc is
#: rendered from it, so the two cannot drift apart. (A guard that compared two
#: documents to each other is exactly what let a shipped capability go unrecorded
#: in 5.7.0; comparing a document against code is the direction that catches it.)
#:
#: Codes are contract. A caller may ``switch`` on them, so they change only on a
#: major boundary.
ERROR_CODES: dict[str, str] = {
    # -- 계약 위반 일반 --------------------------------------------------
    "hwpx-error": "분류되지 않은 구조화 오류(베이스 기본값).",
    "hwpx-value-error": "인자 값이 이 연산에 쓸 수 없다(분류되지 않음).",
    "hwpx-type-error": "인자 타입이 이 연산이 받는 것이 아니다(분류되지 않음).",
    "hwpx-lookup-error": "이름·인덱스로 지목한 것이 없다(분류되지 않음).",
    "hwpx-state-error": "문서 상태가 이 연산을 할 수 있는 상태가 아니다(분류되지 않음).",
    # -- 계약 문서·스키마 ------------------------------------------------
    "contract-document-missing": "동봉돼야 할 계약 문서가 휠에 없다.",
    "unknown-contract-document": "그런 이름의 계약 문서가 없다.",
    "unknown-contract-schema": "그런 이름의 계약 스키마가 없다.",
    # -- 문서·섹션·문단 --------------------------------------------------
    "document-header-missing": "문서에 header.xml 파트가 없다.",
    "document-validation-failed": "저장 전 문서 검증이 실패했다.",
    "section-missing": "문서에 섹션이 하나도 없다.",
    "section-not-found": "섹션 인덱스가 범위를 벗어났다.",
    "section-invalid-type": "section 인자가 정수도 섹션 객체도 아니다.",
    "section-argument-conflict": "section 과 section_index 를 동시에 지정했다.",
    "paragraph-missing": "문서(또는 지정 범위)에 문단이 하나도 없다.",
    "paragraph-not-found": "문단 인덱스가 범위를 벗어났다.",
    "paragraph-invalid-type": "paragraph 인자가 정수도 문단 객체도 아니다.",
    "paragraph-argument-conflict": "paragraph_index 와 paragraph_indexes 를 동시에 지정했다.",
    "paragraph-indexes-empty": "paragraph_indexes 가 비어 있다.",
    "paragraph-format-empty": "적용할 문단 서식 항목이 하나도 없다.",
    "paragraph-line-spacing-invalid": "줄 간격은 양수여야 한다.",
    "paragraph-outline-level-out-of-range": "문단 개요 수준이 0~10 밖이다.",
    # -- 스타일·제목 -----------------------------------------------------
    "style-not-found": "그 id·이름의 스타일이 없다(가용 목록·가장 가까운 이름 동봉).",
    "style-ambiguous": "같은 이름을 쓰는 스타일이 둘 이상이다(후보 동봉).",
    "style-argument-conflict": "style 과 style_id_ref 를 동시에 지정했다.",
    "style-list-level-invalid": "글머리표/번호 수준은 1 이상이어야 한다.",
    "style-list-property-failed": "번호 문단모양을 만들지 못했다.",
    "heading-level-invalid": "개요 수준이 정수가 아니다.",
    "heading-level-out-of-range": "개요 수준이 1~10 밖이다.",
    "heading-style-missing": "이 문서에 해당 수준의 개요 스타일이 없다.",
    # -- 쪽 기하 ---------------------------------------------------------
    "page-argument-conflict": "text 와 content 를 동시에 지정했다.",
    "page-argument-missing": "text 또는 content 중 하나는 있어야 한다.",
    "page-kind-invalid": "kind 는 'header' 또는 'footer' 여야 한다.",
    "page-columns-invalid": "단 수는 1 이상이어야 한다.",
    "page-orientation-unsupported": "지원하지 않는 용지 방향이다.",
    "page-paper-size-unsupported": "지원하지 않는 용지 규격이다.",
    # -- 양식개체 --------------------------------------------------------
    "field-name-empty": "누름틀 이름이 비어 있다.",
    "field-not-found": "그 선택자로 누름틀을 찾지 못했다.",
    "field-ambiguous": "선택자가 누름틀 여럿에 걸린다.",
    "field-not-created": "만든 누름틀을 표준 매처가 다시 찾지 못했다.",
    "field-selector-conflict": "선택자를 둘 이상 동시에 지정했다.",
    "field-checkbox-caption-empty": "체크박스 캡션이 비어 있다.",
    "field-checkbox-not-found": "그 선택자로 체크박스를 찾지 못했다.",
    "field-checkbox-ambiguous": "선택자가 체크박스 여럿에 걸린다.",
    "field-checkbox-not-created": "만든 체크박스를 표준 리더가 다시 찾지 못했다.",
    # -- 인라인 개체 -----------------------------------------------------
    "shape-equation-script-empty": "수식 스크립트가 비어 있다.",
    "shape-equation-script-too-large": "수식 스크립트가 크기 한도를 넘었다.",
    "shape-equation-not-verbatim": "만든 수식이 스크립트를 그대로 담지 않았다.",
    "shape-equation-not-created": "만든 수식을 표준 스캔이 다시 찾지 못했다.",
    "shape-chart-xml-empty": "차트 XML 이 비어 있다.",
    "shape-chart-xml-malformed": "차트 XML 이 올바른 XML 이 아니다.",
    "shape-chart-root-invalid": "차트 XML 루트가 c:chartSpace 가 아니다.",
    "shape-chart-anchor-detached": "만든 차트 앵커가 자기 파트를 가리키지 않는다.",
    "shape-chart-not-created": "만든 차트를 표준 스캔이 다시 찾지 못했다.",
    # -- 미디어 ----------------------------------------------------------
    "media-item-id-taken": "그 이진 항목 id 가 이미 쓰이고 있다.",
    # -- 주석 ------------------------------------------------------------
    "note-anchor-detached": "앵커를 걸 문단이 섹션에 속해 있지 않다.",
    "note-memo-detached": "메모가 섹션에 속해 있지 않다.",
    "note-argument-conflict": "앵커 없는 메모에 앵커 전용 인자를 줬다.",
    # -- 변경추적 --------------------------------------------------------
    "track-text-empty": "변경추적 삽입 텍스트가 비어 있다.",
    "track-match-empty": "찾을 문자열이 비어 있다.",
    "track-match-not-found": "문단에서 찾을 문자열을 찾지 못했다.",
    "track-match-crosses-markup": "찾은 구간이 인라인 마크업을 가로질러 안전하게 감쌀 수 없다.",
    "track-paragraph-empty": "지울 텍스트가 문단에 없다.",
    # -- 텍스트 ----------------------------------------------------------
    "text-search-empty": "바꿀 대상 문자열이 비어 있다.",
    # -- 저장·패키지 -----------------------------------------------------
    "save-failed": "저장 경로가 아무것도 쓰기 전에 fail-closed 했다.",
    "save-package-contract-violated": "package.save(None) 이 bytes 를 돌려주지 않았다.",
    "open-safety-failed": "산출 패키지가 편집기 열기 안전성 검사를 통과하지 못했다.",
    "quality-gate-failed": "품질 게이트가 저장을 막았다(quality 코드는 context 에).",
    "preservation-downgrade": "요청한 보존 등급을 저장이 달성하지 못했다.",
    # -- 계획 실행기 -----------------------------------------------------
    "plan-invalid": "편집 계획이 v1 계약을 위반한다.",
}


__all__ = [
    "ERROR_CODES",
    "GRANDFATHERED_CODES",
    "ERROR_CODE_DOMAINS",
    "HwpxError",
    "HwpxLookupError",
    "HwpxStateError",
    "HwpxTypeError",
    "HwpxValueError",
    "SaveError",
]
