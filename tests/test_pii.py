from __future__ import annotations

import pytest

from hwpx.tools.pii import PIIPolicy, detect_pii, mask_pii, mask_value


def _types(text: str) -> list[str]:
    return [span["type"] for span in detect_pii(text)]


def test_rrn_detects_and_masks_with_gender_digit_preserved() -> None:
    text = "주민등록번호 900101-2123456"

    spans = detect_pii(text)

    assert spans == [
        {
            "type": "rrn",
            "start": 7,
            "end": 21,
            "value": "900101-2123456",
            "confidence": "high",
        }
    ]
    assert mask_pii(text) == "주민등록번호 900101-2******"
    assert mask_value("9001012123456", "rrn") == "900101-2******"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("010-1234-5678", "010-****-****"),
        ("01012345678", "010-****-****"),
        ("011-123-4567", "011-****-****"),
        ("0191234567", "019-****-****"),
    ],
)
def test_phone_variants_detect_and_mask(value: str, expected: str) -> None:
    assert _types(value) == ["phone"]
    assert mask_pii(value) == expected
    assert mask_value(value, "phone") == expected


def test_email_detects_and_masks() -> None:
    text = "이메일 alpha.seed@example.com"

    assert _types(text) == ["email"]
    assert mask_pii(text) == "이메일 a****@example.com"
    assert mask_value("alpha.seed@example.com", "email") == "a****@example.com"


def test_luhn_valid_card_detects_and_masks() -> None:
    text = "카드 4111-1111-1111-1111"

    assert _types(text) == ["card"]
    assert mask_pii(text) == "카드 4111-****-****-1111"
    assert mask_value("4111111111111111", "card") == "4111-****-****-1111"


def test_luhn_rejects_invalid_card() -> None:
    text = "카드 4111-1111-1111-1112"

    assert detect_pii(text) == []
    assert mask_pii(text) == text


def test_false_positive_guards_for_plain_numbers() -> None:
    text = "주문번호 123456, 기준연도 2026, 참조번호 1234567890123456"

    assert detect_pii(text) == []
    assert mask_pii(text) == text


def test_contextual_patterns_are_label_gated_low_confidence() -> None:
    text = (
        "성명: 홍길동\n"
        "계좌번호: 123-456789-01234\n"
        "주소: 서울특별시 중구 세종대로 1"
    )

    spans = detect_pii(text)

    assert [span["type"] for span in spans] == ["name", "account", "address"]
    assert {span["confidence"] for span in spans} == {"low"}
    assert mask_pii("홍길동은 서울에 산다") == "홍길동은 서울에 산다"


def test_policy_can_disable_machine_detection_and_change_mask_character() -> None:
    text = "900101-2123456 alpha@example.com"
    policy = PIIPolicy(mask_char="#", machine_enabled=False)

    assert detect_pii(text, policy) == []
    assert mask_pii(text, policy) == text
    assert mask_value("abcdef", "unknown", PIIPolicy(mask_char="#", prefix_len=2, suffix_len=2)) == "ab##ef"
    assert mask_value("a", "unknown") == "*"
