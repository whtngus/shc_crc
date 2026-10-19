# -*- coding: utf-8 -*-
"""3조 VIP 이탈 방지 자산을 설계 파일에 더하는 1회용 스크립트임.

하는 일
  1. work/fixed_queries.json 에 FQ-10 ~ FQ-14 를 더함
  2. work/db_catalog.json 에 app 뷰 5개를 더함(DB 미접속이므로 SQL에서 정적으로 옮긴 값임)
  3. work/decisions.json 에 3조 결정 기록을 더함(제안 상태, 사용자 승인 대기)

DB에 접속하지 않으며 같은 값을 두 번 더하지 않도록 이미 있으면 건너뜀.
사용법: python design/sql-retriever/tools/add_vip_assets.py
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WORK = BASE / "work"
TODAY = "2026-10-19"
NOT_RUN = "미실행(DB 미접속, 팀원 PC에서 explain_fixed_queries.py로 확인 필요)"

NEW_QUERIES = [
    {
        "id": "FQ-10",
        "name": "월 사용액 추이와 전월 대비",
        "description": "최근 6개월 월별 사용액과 전월 대비 증감액, 증감률, 부분 월 여부",
        "result_unit": "월 1개당 1행",
        "sql": "SELECT month, approved_amount, transaction_count, change_amount, change_rate_pct, is_partial_month "
               "FROM app.vip_monthly_trend ORDER BY month",
    },
    {
        "id": "FQ-11",
        "name": "연회비 대비 사용액",
        "description": "카드별 연회비, 최근 사용액, 월평균 사용액, 연 환산 사용액 대비 연회비 배수",
        "result_unit": "카드 1장당 1행",
        "sql": "SELECT card_ref, product_name, annual_fee, recent_period_amount, avg_monthly_amount, "
               "yearly_usage_to_fee_ratio FROM app.vip_annual_fee_burden ORDER BY card_ref",
    },
    {
        "id": "FQ-12",
        "name": "최근 활동 신호",
        "description": "마지막 승인일과 경과일, 최근 30일과 그 이전 30일의 승인 건수와 금액",
        "result_unit": "고객 1행",
        "sql": "SELECT last_approved_date, days_since_last_approved, approved_count_last_30d, "
               "approved_count_prev_30d, approved_amount_last_30d, approved_amount_prev_30d "
               "FROM app.vip_activity_signal",
    },
    {
        "id": "FQ-13",
        "name": "업종별 사용액 비중과 순위",
        "description": "최근 6개월 업종별 사용액, 비중(%), 순위. 순위 1이 주 사용 업종",
        "result_unit": "업종 1개당 1행",
        "sql": "SELECT category, approved_amount, transaction_count, share_pct, amount_rank "
               "FROM app.vip_category_share ORDER BY amount_rank, category",
    },
    {
        "id": "FQ-14",
        "name": "이탈 신호 종합",
        "description": "최근 3개월 월평균 사용액 변화율과 최근 활동을 한 줄로 요약",
        "result_unit": "고객 1행",
        "sql": "SELECT recent_3m_avg_amount, prev_avg_amount, recent_month_count, prev_month_count, "
               "change_rate_pct, days_since_last_approved, approved_count_last_30d, approved_count_prev_30d "
               "FROM app.vip_churn_signal_summary",
    },
]

# 컬럼 타입은 07_vip_churn_views.sql의 식에서 읽은 값임(정적 추출)
NEW_VIEWS = {
    "vip_monthly_trend": (
        "최근 6개월 월별 승인 사용액(모든 카드 합계)과 전월 대비 증감. 기준일이 속한 달이 월말 전이면 is_partial_month가 true임.",
        [("month", "text"), ("approved_amount", "bigint"), ("transaction_count", "integer"),
         ("prev_month_amount", "bigint"), ("change_amount", "bigint"), ("change_rate_pct", "numeric"),
         ("is_partial_month", "boolean")],
    ),
    "vip_annual_fee_burden": (
        "카드별 연회비와 최근 6개월 사용액. yearly_usage_to_fee_ratio는 월평균 사용액을 12배 한 값을 연회비로 나눈 배수이며 연회비가 0이면 NULL임.",
        [("card_ref", "text"), ("product_name", "text"), ("annual_fee", "integer"),
         ("recent_period_amount", "bigint"), ("usage_month_count", "integer"),
         ("avg_monthly_amount", "bigint"), ("yearly_usage_to_fee_ratio", "numeric")],
    ),
    "vip_activity_signal": (
        "마지막 승인일과 경과일, 최근 30일과 그 이전 30일의 승인 건수와 금액(고객 1행). 거래가 없으면 건수와 금액은 0이고 마지막 승인일은 NULL임.",
        [("last_approved_date", "date"), ("days_since_last_approved", "integer"),
         ("approved_count_last_30d", "integer"), ("approved_count_prev_30d", "integer"),
         ("approved_amount_last_30d", "bigint"), ("approved_amount_prev_30d", "bigint")],
    ),
    "vip_category_share": (
        "최근 6개월 업종별 승인 사용액과 건수, 전체 대비 비중(%)과 사용액 순위. 순위 1이 주 사용 업종임.",
        [("category", "text"), ("approved_amount", "bigint"), ("transaction_count", "integer"),
         ("share_pct", "numeric"), ("amount_rank", "integer")],
    ),
    "vip_churn_signal_summary": (
        "이탈 신호 종합(고객 1행). 최근 3개월 월평균 사용액과 그 이전 달들의 월평균 비교(부분 월 제외), 마지막 승인 경과일, 최근 30일과 이전 30일 승인 건수.",
        [("recent_3m_avg_amount", "bigint"), ("prev_avg_amount", "bigint"), ("recent_month_count", "integer"),
         ("prev_month_count", "integer"), ("change_rate_pct", "numeric"), ("days_since_last_approved", "integer"),
         ("approved_count_last_30d", "integer"), ("approved_count_prev_30d", "integer")],
    ),
}


def load(name: str) -> dict:
    return json.loads((WORK / name).read_text(encoding="utf-8"))


def save(name: str, data: dict) -> None:
    (WORK / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_fixed_queries() -> None:
    data = load("fixed_queries.json")
    have = {q["id"] for q in data["queries"]}
    for q in NEW_QUERIES:
        if q["id"] not in have:
            data["queries"].append({**q, "explain": NOT_RUN})
    if "3조" not in data["note"]:
        data["note"] += (" FQ-10 ~ FQ-14는 3조(VIP 이탈 방지)가 " + TODAY + "에 더한 후보이며 DB를 실행하지 못해 EXPLAIN은 미실행임.")
    save("fixed_queries.json", data)


def add_views() -> None:
    data = load("db_catalog.json")
    have = {(v["schema"], v["name"]) for v in data["views"]}
    for name, (comment, columns) in NEW_VIEWS.items():
        if ("app", name) in have:
            continue
        data["views"].append({
            "schema": "app", "name": name, "comment": comment, "owner": "app_reader",
            "options": "security_barrier=true",
            "select_by_connect_user": None, "select_by_nl2sql_role": True,
            "columns": [{"name": c, "type": t, "comment": None} for c, t in columns],
            "limit0_ok": None,
            "verified_by_db": False,
            "source": f"rdb/init/07_vip_churn_views.sql 에서 정적으로 옮김({TODAY}, DB 미접속). 권한은 GRANT 문 기준이며 실제 확인 전임.",
        })
    files = data.get("view_sql_files", [])
    if "rdb/init/07_vip_churn_views.sql" not in files:
        files.append("rdb/init/07_vip_churn_views.sql")
    data["view_sql_files"] = files
    nl2sql = data["summary"].get("nl2sql_role_accessible_views", [])
    for name in NEW_VIEWS:
        full = f"app.{name}"
        if full not in nl2sql:
            nl2sql.append(full)
    data["summary"]["nl2sql_role_accessible_views"] = sorted(nl2sql)
    data["summary"]["views_total"] = len(data["views"])
    data["summary"]["views_accessible_by_nl2sql_role"] = len(nl2sql)
    data["summary"]["note_3jo"] = (
        f"{TODAY} 3조가 app 뷰 5개를 더함. 이 5개는 DB를 실행하지 못해 SQL에서 옮긴 값이며 "
        "views_accessible_by_connect_user(11)에는 포함하지 않음. 팀원 PC에서 read_views.py로 다시 읽어 맞춰야 함."
    )
    save("db_catalog.json", data)


def add_decisions() -> None:
    data = load("decisions.json")
    ids = {d["id"] for d in data["decisions"]}
    records = [
        {
            "id": "D-3J-01",
            "item": "3조 논리 뷰 추가(VIP 이탈 방지)",
            "value": "app.vip_monthly_trend, vip_annual_fee_burden, vip_activity_signal, vip_category_share, vip_churn_signal_summary 5개",
            "user_answer": "설계 범위: 단계는 예제 그대로 두고, 논리뷰와 정형쿼리만 우리 고객군용으로 바꿈",
            "decided_by": "사용자(범위 결정), 뷰 목록은 AI 제안으로 승인 대기",
            "date": TODAY,
            "evidence": "rdb/init/07_vip_churn_views.sql. 근거: 대화에서 정한 이탈 신호(연회비 부담, 사용 감소, 주 사용 업종)",
            "status": "제안(승인 대기)",
        },
        {
            "id": "D-3J-02",
            "item": "3조 정형쿼리 추가",
            "value": "FQ-10 월 사용액 추이, FQ-11 연회비 대비 사용액, FQ-12 최근 활동 신호, FQ-13 업종 비중과 순위, FQ-14 이탈 신호 종합",
            "user_answer": "위와 같음",
            "decided_by": "사용자(범위 결정), 쿼리 목록은 AI 제안으로 승인 대기",
            "date": TODAY,
            "evidence": "work/fixed_queries.json. EXPLAIN은 DB 미접속으로 미실행",
            "status": "제안(승인 대기)",
        },
        {
            "id": "D-3J-03",
            "item": "정형쿼리 키워드 규칙 조정(S-R2 대체 경로)",
            "value": "FQ-08은 '업종'에서 비중, 비율, 순위, 주로가 없을 때로 좁히고, 같은 표현은 FQ-13이 받음",
            "user_answer": "위와 같음",
            "decided_by": "AI 제안(승인 대기)",
            "date": TODAY,
            "evidence": "두 개 이상 일치하면 안전 종료하는 규칙에서 FQ-08과 FQ-13이 겹치지 않게 하려는 것임",
            "status": "제안(승인 대기)",
        },
        {
            "id": "D-3J-04",
            "item": "DB 실행 검증 방식",
            "value": "DB를 설치하지 않고 SQL을 사람이 읽어 검토함. 실행이 필요한 검증은 팀원 PC에서 함",
            "user_answer": "최대한 뭐 설치하지말고 시뮬레이션으로만부탁해. 설치했다고 가정하고",
            "decided_by": "사용자",
            "date": TODAY,
            "evidence": "EXPLAIN, 통합 시험, db_catalog 뷰 수 대조는 미실행으로 남김",
            "status": "확정",
        },
        {
            "id": "D-3J-05",
            "item": "LLM 통합 시험",
            "value": "Groq 키 없이 단위 시험까지만 하고, LLM 통합 시험은 하지 않음",
            "user_answer": "키 없이 단위 시험까지만",
            "decided_by": "사용자",
            "date": TODAY,
            "evidence": "secrets/.env에 GROQ 키 없음",
            "status": "확정",
        },
    ]
    for r in records:
        if r["id"] not in ids:
            data["decisions"].append(r)
    save("decisions.json", data)


if __name__ == "__main__":
    add_fixed_queries()
    add_views()
    add_decisions()
    print("3조 자산 추가 완료")
