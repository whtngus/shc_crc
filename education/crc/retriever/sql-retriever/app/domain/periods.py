"""뷰별 데이터 제공 기간과 질문 기간(requested_period) 판정 규칙(S-R3 작업 5).

기간 계산식 출처: rdb/init/04 ~ 06 뷰 정의(설계서 12장이 가리키는 근거, 사용자 승인으로 읽음).
"""

from __future__ import annotations

from datetime import date, timedelta


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    """월 첫날 기준으로 months만큼 더한 월 첫날을 반환함. value는 월 첫날이어야 함."""
    index = value.year * 12 + (value.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def _month_end(value: date) -> date:
    return _add_months(_month_start(value), 1) - timedelta(days=1)


def provision_window(view: str, base_date: date, coverage_start: date) -> tuple[date, date] | None:
    """뷰가 데이터를 내어 주는 기간(시작일, 종료일)을 반환함.

    반환값: 기간 제한이 없는 뷰(프로필, 카드, 최근 연체 1건)는 None을 반환함.
    예시: 기준일 2026-08-31, 거래 제공 시작일 2025-08-01이면
          월 집계 2026-03-01 ~ 2026-08-31, 일별 2026-06-03 ~ 2026-08-31, 연체 이력 2025-09-01 ~ 2026-08-31
    """
    if view == "app.monthly_usage":
        # 뷰 정의: greatest(기준월 - 5개월, 거래 제공 시작월) ~ 기준일
        start = max(_add_months(_month_start(base_date), -5), _month_start(coverage_start))
        return start, base_date
    if view == "app.merchant_usage":
        # 뷰 정의: greatest(기준월 - 5개월, 거래 제공 시작일, 카드 발급일) ~ 기준일. 발급일은 카드마다 달라 뺌
        start = max(_add_months(_month_start(base_date), -5), coverage_start)
        return start, base_date
    if view == "app.customer_daily_usage":
        # 뷰 정의: greatest(기준일 - 89일, 거래 제공 시작일, 가입일) ~ 기준일. 가입일은 S-R1에서 이미 확인함
        start = max(base_date - timedelta(days=89), coverage_start)
        return start, base_date
    if view == "app.customer_delinquency_history":
        # 뷰 정의: 최근 완료월(기준일이 월말이면 그 달, 아니면 전달) - 11개월 ~ 최근 완료월
        if base_date == _month_end(base_date):
            latest_completed = _month_start(base_date)
        else:
            latest_completed = _add_months(_month_start(base_date), -1)
        return _add_months(latest_completed, -11), _month_end(latest_completed)
    # ---- 3조 추가 뷰(rdb/init/07_vip_churn_views.sql). 아래 기간은 SQL을 읽어 정한 값이며 DB 실행으로 확인하지 못함 ----
    if view in ("app.vip_monthly_trend", "app.vip_annual_fee_burden", "app.vip_churn_signal_summary"):
        # 모두 app.monthly_usage를 합치거나 나눈 뷰라 월 집계와 같은 기간임
        return provision_window("app.monthly_usage", base_date, coverage_start)
    if view == "app.vip_category_share":
        # app.merchant_usage를 업종으로 합친 뷰라 가맹점 집계와 같은 기간임
        return provision_window("app.merchant_usage", base_date, coverage_start)
    if view == "app.vip_activity_signal":
        # 마지막 승인일은 거래 제공 시작일부터 기준일까지의 거래 전체에서 구함. 30일 비교 구간은 이 안에 듦
        return coverage_start, base_date
    return None


def is_period_answerable(
    views: list[str],
    period_from: date | None,
    period_to: date | None,
    base_date: date,
    coverage_start: date,
) -> bool:
    """질문 기간이 모든 대상 뷰의 제공 기간 안이고 기준일 이전인지 판정함.

    인자: period_from, period_to가 None이면 그쪽 끝은 제한이 없는 것으로 봄.
    반환값: 기간이 맞으면 True. 하나라도 벗어나면 False(데이터 제공 기간 밖).
    """
    bounds = [value for value in (period_from, period_to) if value is not None]
    if any(value > base_date for value in bounds):
        return False
    for view in views:
        window = provision_window(view, base_date, coverage_start)
        if window is None:
            continue
        start, end = window
        if any(value < start or value > end for value in bounds):
            return False
    return True
