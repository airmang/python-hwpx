# SPDX-License-Identifier: Apache-2.0
"""PII detection, masking, and structural privacy helpers.

The machine-checkable set is intentionally always enabled by default. Contextual
patterns are label-gated and reported as low-confidence to avoid broad free-text
over-masking.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable, Mapping, Sized
from dataclasses import dataclass
from typing import Any, Literal, TypedDict


Confidence = Literal["high", "low"]


class PIISpan(TypedDict):
    type: str
    start: int
    end: int
    value: str
    confidence: Confidence


@dataclass(frozen=True)
class PIIPolicy:
    """Controls PII detection and masking behavior."""

    mask_char: str = "*"
    machine_enabled: bool = True
    contextual_enabled: bool = True
    prefix_len: int = 1
    suffix_len: int = 0

    def __post_init__(self) -> None:
        if len(self.mask_char) != 1:
            raise ValueError("mask_char must be exactly one character")
        if self.prefix_len < 0 or self.suffix_len < 0:
            raise ValueError("prefix_len and suffix_len must be non-negative")


DEFAULT_POLICY = PIIPolicy()

__all__ = [
    "Confidence",
    "DEFAULT_POLICY",
    "PIIPolicy",
    "PIISpan",
    "PiiLogFilter",
    "Pseudonymizer",
    "deidentify",
    "detect_pii",
    "mask_pii",
    "mask_value",
    "minimize_fields",
    "scrub_exception_message",
]

_RRN_RE = re.compile(r"(?<!\d)(?P<front>\d{6})-?(?P<gender>[1-4])(?P<rear>\d{6})(?!\d)")
_PHONE_RE = re.compile(
    r"(?<!\d)(?P<prefix>010|011|016|017|018|019)-?(?P<middle>\d{3,4})-?(?P<last>\d{4})(?!\d)"
)
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"(?P<local>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)"
    r"@"
    r"(?P<domain>[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)"
    r"(?![A-Za-z0-9-])"
)
_CARD_RE = re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)")

_ACCOUNT_RE = re.compile(
    r"(?:계좌(?:번호)?|통장(?:번호)?)[^\d\n]{0,12}(?P<value>\d[\d-]{8,20}\d)"
)
_REGIONS = (
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원도",
    "충청북도",
    "충청남도",
    "전라북도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
)
_REGION_RE = "|".join(re.escape(region) for region in _REGIONS)
_ADDRESS_RE = re.compile(
    rf"(?:주소|도로명주소|소재지|거주지)\s*[:：]?\s*(?P<value>(?:{_REGION_RE})[^\n,;]{{2,80}})"
)
_NAME_RE = re.compile(r"(?:성명|수신자|이름)\s*[:：]\s*(?P<value>[가-힣]{2,4})")

_TYPE_ALIASES = {
    "resident_registration_number": "rrn",
    "registration_number": "rrn",
    "jumin": "rrn",
    "주민등록번호": "rrn",
    "휴대폰": "phone",
    "전화번호": "phone",
    "mobile": "phone",
    "email_address": "email",
    "이메일": "email",
    "card_number": "card",
    "credit_card": "card",
    "카드": "card",
    "account_number": "account",
    "계좌번호": "account",
    "계좌": "account",
    "주소": "address",
    "이름": "name",
    "성명": "name",
    "수신자": "name",
}


def detect_pii(text: str, policy: PIIPolicy = DEFAULT_POLICY) -> list[PIISpan]:
    """Detect PII spans in ``text`` according to ``policy``."""

    spans: list[PIISpan] = []
    if not text:
        return spans

    if policy.machine_enabled:
        for match in _RRN_RE.finditer(text):
            spans.append(_span("rrn", match.start(), match.end(), match.group(0), "high"))
        for match in _PHONE_RE.finditer(text):
            spans.append(_span("phone", match.start(), match.end(), match.group(0), "high"))
        for match in _EMAIL_RE.finditer(text):
            spans.append(_span("email", match.start(), match.end(), match.group(0), "high"))
        for match in _CARD_RE.finditer(text):
            value = match.group(0)
            if _luhn_valid(_digits(value)):
                spans.append(_span("card", match.start(), match.end(), value, "high"))

    if policy.contextual_enabled:
        for match in _ACCOUNT_RE.finditer(text):
            value = match.group("value")
            digits = _digits(value)
            if 10 <= len(digits) <= 14:
                spans.append(_span("account", match.start("value"), match.end("value"), value, "low"))
        for match in _ADDRESS_RE.finditer(text):
            value = match.group("value").rstrip()
            start = match.start("value")
            spans.append(_span("address", start, start + len(value), value, "low"))
        for match in _NAME_RE.finditer(text):
            value = match.group("value")
            spans.append(_span("name", match.start("value"), match.end("value"), value, "low"))

    return _without_overlaps(spans)


def mask_pii(text: str, policy: PIIPolicy = DEFAULT_POLICY) -> str:
    """Return ``text`` with detected PII spans masked."""

    masked = text
    for span in sorted(detect_pii(text, policy), key=lambda item: item["start"], reverse=True):
        start = span["start"]
        end = span["end"]
        masked = masked[:start] + mask_value(span["value"], span["type"], policy) + masked[end:]
    return masked


def mask_value(value: str, pii_type: str, policy: PIIPolicy = DEFAULT_POLICY) -> str:
    """Mask a single known PII value."""

    normalized_type = _normalize_type(pii_type)
    if normalized_type == "rrn":
        match = _RRN_RE.fullmatch(value)
        if match:
            return f"{match.group('front')}-{match.group('gender')}{policy.mask_char * 6}"
        digits = _digits(value)
        if len(digits) == 13 and digits[6] in "1234":
            return f"{digits[:6]}-{digits[6]}{policy.mask_char * 6}"
    if normalized_type == "phone":
        match = _PHONE_RE.fullmatch(value)
        if match:
            return f"{match.group('prefix')}-{policy.mask_char * 4}-{policy.mask_char * 4}"
    if normalized_type == "email":
        match = _EMAIL_RE.fullmatch(value)
        if match:
            return f"{match.group('local')[:1]}{policy.mask_char * 4}@{match.group('domain')}"
    if normalized_type == "card":
        digits = _digits(value)
        if len(digits) == 16:
            return f"{digits[:4]}-{policy.mask_char * 4}-{policy.mask_char * 4}-{digits[-4:]}"
    if normalized_type == "account":
        digits = _digits(value)
        suffix_len = policy.suffix_len if policy.suffix_len > 0 else 4
        if len(digits) > suffix_len:
            return f"{policy.mask_char * 3}-{policy.mask_char * 4}-{digits[-suffix_len:]}"
    if normalized_type == "name":
        return _mask_generic(value, policy, suffix_len=0)
    if normalized_type == "address":
        return _mask_generic(value, policy, prefix_len=max(policy.prefix_len, 2), suffix_len=0)
    return _mask_generic(value, policy)


def minimize_fields(
    record: Mapping[str, Any],
    allowed: Iterable[str],
    *,
    drop_empty: bool = False,
) -> dict[str, Any]:
    """Return a minimized copy containing only allowed fields.

    Output order follows the order of ``allowed``. Missing fields are skipped.
    When ``drop_empty`` is true, ``None`` and empty sized values are omitted
    while falsey scalars such as ``0`` and ``False`` are retained.
    """

    minimized: dict[str, Any] = {}
    for key in allowed:
        if key not in record:
            continue
        value = record[key]
        if drop_empty and _is_empty_value(value):
            continue
        minimized[key] = value
    return minimized


class Pseudonymizer:
    """Deterministic in-memory reversible pseudonym token map.

    ``mapping()`` exposes the value-to-token map. Persisting that map outside
    this instance makes the pseudonymization reversible; v1 keeps it in memory
    only.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def token(self, value: str, *, kind: str = "이름") -> str:
        """Return a stable token for ``value`` within this instance."""

        if value in self._tokens:
            return self._tokens[value]
        count = self._counts.get(kind, 0) + 1
        self._counts[kind] = count
        token = f"{kind}_{count:03d}"
        self._tokens[value] = token
        return token

    def mapping(self) -> dict[str, str]:
        """Return a copy of the in-memory value-to-token map."""

        return dict(self._tokens)


def deidentify(value: str, *, salt: str, length: int = 12) -> str:
    """Return an irreversible deterministic salted hash token."""

    digest = hashlib.sha256((salt + "\x00" + value).encode()).hexdigest()
    return "di_" + digest[:length]


class PiiLogFilter(logging.Filter):
    """Logging filter that masks PII in formatted log messages."""

    def __init__(self, name: str = "", policy: PIIPolicy = DEFAULT_POLICY) -> None:
        super().__init__(name)
        self.policy = policy

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _scrub_log_value(record.msg, self.policy)
        record.args = _scrub_log_value(record.args, self.policy)
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        masked_message = mask_pii(message, self.policy)
        record.msg = masked_message
        record.args = ()
        return True


def scrub_exception_message(msg: str, policy: PIIPolicy = DEFAULT_POLICY) -> str:
    """Mask PII in an exception message before exposing or logging it."""

    return mask_pii(msg, policy)


def _span(kind: str, start: int, end: int, value: str, confidence: Confidence) -> PIISpan:
    return {"type": kind, "start": start, "end": end, "value": value, "confidence": confidence}


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, Sized) and len(value) == 0


def _scrub_log_value(value: Any, policy: PIIPolicy) -> Any:
    if isinstance(value, str):
        return mask_pii(value, policy)
    if isinstance(value, tuple):
        return tuple(_scrub_log_value(item, policy) for item in value)
    if isinstance(value, Mapping):
        return {key: _scrub_log_value(item, policy) for key, item in value.items()}
    return value


def _normalize_type(pii_type: str) -> str:
    lowered = pii_type.strip().lower()
    return _TYPE_ALIASES.get(lowered, lowered)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _luhn_valid(digits: str) -> bool:
    if len(digits) != 16 or not digits.isdigit():
        return False
    total = 0
    double = False
    for char in reversed(digits):
        value = int(char)
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return total % 10 == 0


def _without_overlaps(spans: list[PIISpan]) -> list[PIISpan]:
    selected: list[PIISpan] = []
    for span in sorted(spans, key=lambda item: (item["start"], -(item["end"] - item["start"]))):
        if any(_overlaps(span, existing) for existing in selected):
            continue
        selected.append(span)
    return sorted(selected, key=lambda item: (item["start"], item["end"]))


def _overlaps(left: PIISpan, right: PIISpan) -> bool:
    return left["start"] < right["end"] and right["start"] < left["end"]


def _mask_generic(
    value: str,
    policy: PIIPolicy,
    *,
    prefix_len: int | None = None,
    suffix_len: int | None = None,
) -> str:
    if not value:
        return value
    requested_prefix = policy.prefix_len if prefix_len is None else prefix_len
    requested_suffix = policy.suffix_len if suffix_len is None else suffix_len
    if len(value) <= requested_prefix + requested_suffix:
        visible_prefix = min(requested_prefix, max(len(value) - 1, 0))
        return f"{value[:visible_prefix]}{policy.mask_char * (len(value) - visible_prefix)}"
    prefix = min(len(value), requested_prefix)
    suffix = min(len(value) - prefix, requested_suffix)
    mask_count = len(value) - prefix - suffix
    suffix_text = value[-suffix:] if suffix else ""
    return f"{value[:prefix]}{policy.mask_char * mask_count}{suffix_text}"
