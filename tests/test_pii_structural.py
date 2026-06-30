# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import logging
import re

from hwpx.tools.pii import (
    PiiLogFilter,
    Pseudonymizer,
    __all__ as pii_all,
    deidentify,
    minimize_fields,
    scrub_exception_message,
)


RRN = "900101-2123456"
PHONE = "010-1234-5678"
EMAIL = "alpha.seed@example.com"
CARD = "4111-1111-1111-1111"


class _CapturingHandler(logging.StreamHandler):
    def __init__(self, stream: io.StringIO) -> None:
        super().__init__(stream)
        self.formatted: list[str] = []
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        self.formatted.append(self.format(record))
        super().emit(record)


def test_structural_helpers_are_exported() -> None:
    assert {
        "PiiLogFilter",
        "Pseudonymizer",
        "deidentify",
        "minimize_fields",
        "scrub_exception_message",
    }.issubset(set(pii_all))


def test_minimize_fields_keeps_allowed_drops_others_and_empty_values() -> None:
    record = {
        "name": "홍길동",
        "phone": PHONE,
        "email": "",
        "note": None,
        "score": 0,
        "active": False,
        "tags": [],
        "extra": "drop-me",
    }
    allowed = ["score", "email", "name", "active", "note", "tags", "missing"]

    minimized = minimize_fields(record, allowed)

    assert minimized == {
        "score": 0,
        "email": "",
        "name": "홍길동",
        "active": False,
        "note": None,
        "tags": [],
    }
    assert list(minimized) == ["score", "email", "name", "active", "note", "tags"]
    assert "phone" not in minimized
    assert "extra" not in minimized
    assert minimize_fields(record, allowed, drop_empty=True) == {
        "score": 0,
        "name": "홍길동",
        "active": False,
    }
    assert "phone" in record


def test_pseudonymizer_is_deterministic_by_instance_with_per_kind_counters() -> None:
    pseudonymizer = Pseudonymizer()

    assert pseudonymizer.token("홍길동") == "이름_001"
    assert pseudonymizer.token("홍길동") == "이름_001"
    assert pseudonymizer.token("김철수") == "이름_002"
    assert pseudonymizer.token("서울특별시", kind="주소") == "주소_001"
    assert pseudonymizer.token("부산광역시", kind="주소") == "주소_002"

    assert pseudonymizer.mapping() == {
        "홍길동": "이름_001",
        "김철수": "이름_002",
        "서울특별시": "주소_001",
        "부산광역시": "주소_002",
    }

    exposed = pseudonymizer.mapping()
    exposed["홍길동"] = "changed"
    assert pseudonymizer.token("홍길동") == "이름_001"


def test_deidentify_is_deterministic_salted_and_length_limited() -> None:
    first = deidentify("홍길동", salt="salt-a", length=16)
    second = deidentify("홍길동", salt="salt-a", length=16)

    assert first == second
    assert first != deidentify("홍길동", salt="salt-b", length=16)
    assert re.fullmatch(r"di_[0-9a-f]{16}", first)
    assert len(deidentify("홍길동", salt="salt-a", length=8)) == len("di_") + 8
    assert "홍길동" not in first


def test_pii_log_filter_masks_formatted_messages_and_args() -> None:
    stream = io.StringIO()
    handler = _CapturingHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logger = logging.getLogger("tests.pii.structural")
    logger.handlers.clear()
    logger.filters.clear()
    logger.addHandler(handler)
    logger.addFilter(PiiLogFilter())
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        logger.info("rrn=%s phone=%s email: %s card=%s count=%d", RRN, PHONE, EMAIL, CARD, 7)
        logger.info("dict email: %(email)s phone=%(phone)s", {"email": EMAIL, "phone": PHONE})
    finally:
        logger.handlers.clear()
        logger.filters.clear()
        logger.propagate = True

    emitted = stream.getvalue()
    assert "900101-2******" in emitted
    assert "010-****-****" in emitted
    assert "a****@example.com" in emitted
    assert "4111-****-****-1111" in emitted
    for raw in (RRN, PHONE, EMAIL, CARD):
        assert raw not in emitted
        assert raw not in "\n".join(handler.formatted)
    assert all(record.args == () for record in handler.records)


def test_scrub_exception_message_masks_pii() -> None:
    scrubbed = scrub_exception_message(f"failed for {EMAIL} / {PHONE}")

    assert EMAIL not in scrubbed
    assert PHONE not in scrubbed
    assert "a****@example.com" in scrubbed
    assert "010-****-****" in scrubbed
