"""남은 시간 예산 정책(설계서 ⑥, 27 ~ 28장)의 계산 규칙."""

from __future__ import annotations

import math
from dataclasses import dataclass

TOTAL_BUDGET_SECONDS = 15.0  # 전체 시간 예산(설계 개요 2장)
FINALIZE_SECONDS = 1.0  # 종료 처리 시간. S-R6 몫으로 미리 떼어 둠
START_RATIO = 0.05  # 시작 기준 비율(설계 가정 A-3, 설계 가이드 기본값)
START_THRESHOLD_SECONDS = TOTAL_BUDGET_SECONDS * START_RATIO  # 15 × 0.05 = 0.75초
LLM_WORST_SECONDS = 5.0  # C-01 최악값 = 타임아웃 5초 × (1 + 재시도 0)

STAGE_R1 = "S-R1"
STAGE_R2 = "S-R2"
STAGE_R3 = "S-R3"
STAGE_R4 = "S-R4"
STAGE_R5 = "S-R5"
STAGE_R6 = "S-R6"


@dataclass(frozen=True)
class BudgetCheck:
    """단계 시작 전 측정 결과. 값은 모두 초 단위임."""

    elapsed: float  # started_at부터 실제로 흐른 시간
    remaining_time: float  # 전체 예산 - 기존 사용 - 종료 처리
    deduction: float  # 앞으로 남은 단계의 외부 연동 최악값 합
    remaining_budget: float  # 남은 시간 - 차감값
    can_start: bool  # 남은 시간 예산 ≥ 시작 기준 시간

    @property
    def remaining_budget_ms(self) -> int:
        """남은 시간 예산을 밀리초로 내림한 값. 음수면 0을 반환함."""
        return max(0, math.floor(self.remaining_budget * 1000))


def deduction_for(stage: str, attempt: int = 0, *, retry_disabled: bool = False) -> float:
    """측정 시점별 차감값(27장 표)을 반환함.

    인자: attempt는 S-R2가 1 늘린 뒤의 계획 시도 횟수임. S-R3, S-R4에서만 의미가 있음.
    반환값: S-R1, S-R2는 5초. S-R3, S-R4는 되돌아갈 수 있는 attempt 1에서만 5초, 그 밖에는 0초.
    """
    if stage in (STAGE_R1, STAGE_R2):
        return LLM_WORST_SECONDS
    if stage in (STAGE_R3, STAGE_R4):
        # 되돌아갈 경로(S-R2 재호출)가 남아 있을 때만 그 최악값을 미리 떼어 둠
        return LLM_WORST_SECONDS if attempt == 1 and not retry_disabled else 0.0
    return 0.0


def check_budget(elapsed: float, deduction: float) -> BudgetCheck:
    """남은 시간 예산을 계산하고 시작 조건을 판정함.

    예시: 기존 사용 9.6초, 차감 5초 → 남은 시간 4.4초, 남은 시간 예산 -0.6초 → 시작 불가(28장 예 3).
    """
    remaining_time = TOTAL_BUDGET_SECONDS - elapsed - FINALIZE_SECONDS
    remaining_budget = remaining_time - deduction
    return BudgetCheck(
        elapsed=elapsed,
        remaining_time=remaining_time,
        deduction=deduction,
        remaining_budget=remaining_budget,
        can_start=remaining_budget >= START_THRESHOLD_SECONDS,
    )
