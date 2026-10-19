"""개인 식별자 5종(전화번호, 카드번호, 주민등록번호, 이메일, 회원ID) 가림을 확인함. 값은 모두 가짜임."""

import pytest

from app.domain.masking import MASK_TOKEN, mask_identifiers


@pytest.mark.parametrize(
    ("question", "expected_count"),
    [
        ("010-1234-5678 번호로 연락 온 고객", 1),
        ("01012345678", 1),
        ("02-123-4567 지점", 1),
        ("카드 1234-5678-9012-3456 결제", 1),
        ("카드 1234 5678 9012 3456", 1),
        ("카드 123456789012345", 1),  # 15자리
        ("주민번호 900101-1234567", 1),
        ("메일 test.user@example.com 으로", 1),
        ("회원 M-1002 의 연체", 1),
        ("M-1002 회원, 010-1111-2222, a@b.co", 3),
    ],
)
def test_masks_identifiers(question, expected_count):
    masked, count = mask_identifiers(question)
    assert count == expected_count
    assert MASK_TOKEN in masked


@pytest.mark.parametrize(
    "question",
    ["7월에 50000원 이상 쓴 내역", "2026-08-31 기준 연체", "최근 90일 일별 사용액", "보유 카드 목록"],
)
def test_keeps_ordinary_text(question):
    masked, count = mask_identifiers(question)
    assert (masked, count) == (question, 0)


def test_card_number_is_not_split_into_phone():
    masked, count = mask_identifiers("0101234567890123 카드")
    assert count == 1
    assert masked == f"{MASK_TOKEN} 카드"
