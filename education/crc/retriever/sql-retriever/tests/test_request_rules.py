"""S-R1 형식 검사 규칙과 조회 범위 계산 규칙을 확인함."""

from datetime import date

import pytest

from app.domain import request_rules as rr


@pytest.mark.parametrize("value", ["M-1001", "M-0000", "M-9999"])
def test_member_id_valid(value):
    assert rr.is_valid_member_id(value)


@pytest.mark.parametrize("value", ["M-100", "M-10010", "m-1001", "1001", "M1001", "", None, 1001])
def test_member_id_invalid(value):
    assert not rr.is_valid_member_id(value)


def test_question_length_bounds():
    assert rr.is_valid_question("가")
    assert rr.is_valid_question("가" * 500)
    assert not rr.is_valid_question("가" * 501)
    assert not rr.is_valid_question("")
    assert not rr.is_valid_question("   ")
    assert not rr.is_valid_question(None)


@pytest.mark.parametrize("value", ["2026-08-31", "2025-02-28"])
def test_parse_date_valid(value):
    assert rr.parse_date(value) == date.fromisoformat(value)


@pytest.mark.parametrize("value", ["2026-8-31", "2026/08/31", "2026-02-30", "20260831", "", 20260831])
def test_parse_date_invalid(value):
    assert rr.parse_date(value) is None


def test_coverage_start_from_txn_period():
    """사용자 승인 P-02: txn_period 앞쪽 월 첫날."""
    assert rr.parse_coverage_start("2025-08 ~ 2026-08") == date(2025, 8, 1)
    with pytest.raises(ValueError):
        rr.parse_coverage_start("2025-08")


def test_resolve_base_date_defaults_to_data_date():
    assert rr.resolve_base_date(None, date(2026, 8, 31)) == date(2026, 8, 31)
    assert rr.resolve_base_date(date(2026, 7, 31), date(2026, 8, 31)) == date(2026, 7, 31)
