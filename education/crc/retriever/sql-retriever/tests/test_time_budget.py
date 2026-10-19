"""남은 시간 예산 계산이 설계서 28장 계산 예와 같은 값을 내는지 확인함."""

import pytest

from app.domain import time_budget as tb


def test_constants_match_design():
    assert tb.TOTAL_BUDGET_SECONDS == 15.0
    assert tb.FINALIZE_SECONDS == 1.0
    assert tb.START_THRESHOLD_SECONDS == pytest.approx(0.75)
    assert tb.LLM_WORST_SECONDS == 5.0


@pytest.mark.parametrize(
    ("label", "elapsed", "deduction", "remaining_time", "remaining_budget", "can_start"),
    [
        ("예 1: S-R2 1차, 기존 사용 0.4초", 0.4, 5.0, 13.6, 8.6, True),
        ("예 2: S-R2 재시도, 기존 사용 6.2초", 6.2, 5.0, 7.8, 2.8, True),
        ("예 3: S-R2 재시도, 기존 사용 9.6초", 9.6, 5.0, 4.4, -0.6, False),
        ("예 4: S-R5, 기존 사용 11.3초", 11.3, 0.0, 2.7, 2.7, True),
    ],
)
def test_design_examples(label, elapsed, deduction, remaining_time, remaining_budget, can_start):
    check = tb.check_budget(elapsed, deduction)
    assert check.remaining_time == pytest.approx(remaining_time), label
    assert check.remaining_budget == pytest.approx(remaining_budget), label
    assert check.can_start is can_start, label


def test_example4_statement_timeout_is_2700ms():
    """28장 예 4: statement_timeout = 2,700ms 이하."""
    assert tb.check_budget(11.3, 0.0).remaining_budget_ms <= 2700
    assert tb.check_budget(11.3, 0.0).remaining_budget_ms >= 2699  # 부동소수 내림 오차만 허용


def test_threshold_boundary():
    """시작 조건은 남은 시간 예산 ≥ 0.75초(같으면 시작)."""
    assert tb.check_budget(15 - 1 - 5 - 0.75, 5.0).can_start is True
    assert tb.check_budget(15 - 1 - 5 - 0.75 + 0.001, 5.0).can_start is False


@pytest.mark.parametrize(
    ("stage", "attempt", "retry_disabled", "expected"),
    [
        ("S-R1", 0, False, 5.0),
        ("S-R2", 0, False, 5.0),
        ("S-R2", 1, False, 5.0),
        ("S-R3", 1, False, 5.0),
        ("S-R4", 1, False, 5.0),
        ("S-R3", 2, False, 0.0),
        ("S-R4", 2, False, 0.0),
        ("S-R3", 1, True, 0.0),
        ("S-R5", 2, False, 0.0),
        ("S-R6", 2, False, 0.0),
    ],
)
def test_deduction_table(stage, attempt, retry_disabled, expected):
    """27장 측정 시점별 차감값 표."""
    assert tb.deduction_for(stage, attempt, retry_disabled=retry_disabled) == expected


def test_negative_budget_ms_is_zero():
    assert tb.check_budget(20, 0).remaining_budget_ms == 0
