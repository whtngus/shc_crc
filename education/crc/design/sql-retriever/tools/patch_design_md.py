# -*- coding: utf-8 -*-
"""설계서 스크립트(md)에 3조 변경(VIP 이탈 방지 뷰 5개, 정형쿼리 FQ-10 ~ FQ-14)을 반영하는 1회용 스크립트임.

이미 반영된 파일에 다시 실행해도 같은 줄을 두 번 더하지 않도록, 반영 표식(3조 반영 줄)이 있으면 멈춤.
사용법: python design/sql-retriever/tools/patch_design_md.py
"""

from __future__ import annotations

from pathlib import Path

MD = Path(__file__).resolve().parent.parent / "sql_retriever_워크플로우설계서.md"
text = MD.read_text(encoding="utf-8")

if "3조 반영(2026-10-19)" in text:
    raise SystemExit("이미 반영된 파일임. 중단함")


def rep(old: str, new: str) -> None:
    global text
    assert old in text, "찾지 못함: " + old[:60]
    assert text.count(old) == 1, f"{text.count(old)}곳에 있음: " + old[:60]
    text = text.replace(old, new)


# 1. 문서 머리말
rep("- 작성일: 2026-10-15\n",
    "- 작성일: 2026-10-15\n"
    "- 3조 반영(2026-10-19): VIP 이탈 방지용 논리 뷰 5개(`rdb/init/07_vip_churn_views.sql`)와 정형쿼리 `FQ-10` ~ `FQ-14`를 더함.  \n"
    "  DB를 실행하지 못해 새 뷰와 정형쿼리의 EXPLAIN, 접근 권한 실측은 하지 않았음(팀원 PC에서 확인 필요)\n")

# 2. 슬라이드 1
rep("  - 팀명: design-agentic-ai / 작성일: 2026-10-15\n",
    "  - 팀명: 3조(기반 설계: design-agentic-ai 예제) / 작성일: 2026-10-19\n")

# 3. 설계 개요
rep("실행 계정 `sql_retriever_user`, 허용 뷰 7개, 결과 행 상한 200",
    "실행 계정 `sql_retriever_user`, 허용 뷰 12개(기본 7개 + 3조 추가 5개), 결과 행 상한 200")
rep("  - 제외 범위: 답변 문장 작성(호출자 몫), 뷰와 RLS 변경, 화면, 배포",
    "  - 제외 범위: 답변 문장 작성(호출자 몫), 기존 뷰와 RLS의 변경(3조는 이탈 신호용 뷰 5개를 추가만 함), 화면, 배포")

# 4. 정형쿼리 번호 범위, 개수
rep("fixed: `fixed_query_id`가 `FQ-01` ~ `FQ-09`에 있으면", "fixed: `fixed_query_id`가 `FQ-01` ~ `FQ-14`에 있으면")
rep("정형쿼리 9개의 키워드 표로 규칙 매칭하면", "정형쿼리 14개의 키워드 표로 규칙 매칭하면")
rep("fixed일 때 `FQ-01` ~ `FQ-09`, 그 밖에는 null", "fixed일 때 `FQ-01` ~ `FQ-14`, 그 밖에는 null")

# 5. 부록 A
rep("- 리드문: NL2SQL 실행 계정이 읽을 수 있는 뷰는 9개이며, LLM에는 app 스키마 7개만 보여 줌",
    "- 리드문: NL2SQL 실행 계정이 읽을 수 있는 뷰는 14개이며, LLM에는 app 스키마 12개만 보여 줌(기본 7개 + 3조 추가 5개)")
rep("- 출처 줄: rdb/init/04 ~ 06 SQL, work/db_catalog.json(2026-10-15 실측)",
    "- 출처 줄: rdb/init/04 ~ 06 SQL, work/db_catalog.json(2026-10-15 실측). 3조 추가 뷰 5개는 다음 장 참조")

appendix_a2 = """## 슬라이드 22-2. 부록 A(계속): 3조 추가 논리 뷰

- 패턴: D (뷰 표)
- 리드문: VIP 이탈 신호(사용 감소, 연회비 부담, 최근 활동, 주 사용 업종)를 보는 뷰 5개를 더함. 기존 뷰와 RLS는 고치지 않음

| 뷰 | 담는 내용 | 주요 컬럼 | LLM 노출 |
|----|----------|----------|----------|
| `app.vip_monthly_trend` | 최근 6개월 월 사용액과 전월 대비 증감, 부분 월 표시 | month, approved_amount, change_rate_pct | 예 |
| `app.vip_annual_fee_burden` | 카드별 연회비와 연 환산 사용액 대비 연회비 배수 | card_ref, annual_fee, yearly_usage_to_fee_ratio | 예 |
| `app.vip_activity_signal` | 마지막 승인일과 최근 30일, 이전 30일 비교 | last_approved_date, days_since_last_approved | 예 |
| `app.vip_category_share` | 업종별 사용액 비중과 순위(1위가 주 사용 업종) | category, share_pct, amount_rank | 예 |
| `app.vip_churn_signal_summary` | 최근 3개월 사용액 변화율과 최근 활동을 1행으로 요약 | change_rate_pct, days_since_last_approved | 예 |

- 우측 틴트 박스(적용 방식)
  - 회원 조건 없이 RLS와 세션 변수 3개로 회원과 기간을 가름(기존 뷰와 같은 방식)
  - 뷰 소유자 `app_reader`, 서비스 계정 `sql_retriever_user`는 뷰 조회 권한만 받음
  - 이탈 신호 기준(전월 대비, 연 환산 배수, 최근 30일 비교)은 설계 가정이며 상담 현장 기준으로 확인할 값임
- 출처 줄: rdb/init/07_vip_churn_views.sql (DB 미실행, SQL을 읽어 검토함)

"""
rep("## 슬라이드 23. 부록 B: 정형쿼리 목록", appendix_a2 + "## 슬라이드 23. 부록 B: 정형쿼리 목록")

# 6. 부록 B
rep("- 리드문: 정형쿼리 9개는 모두 실행 계정 권한으로 EXPLAIN을 통과함(실행하지 않고 계획만 확인)",
    "- 리드문: 정형쿼리는 14개이며, FQ-01 ~ FQ-09는 실행 계정 권한으로 EXPLAIN을 통과함. FQ-10 ~ FQ-14(3조 추가)는 DB 미실행으로 확인 전임")
rep("- 출처 줄: work/explain_fixed_queries.log (sql_retriever_user, 9/9 통과)",
    "- 출처 줄: work/explain_fixed_queries.log (sql_retriever_user, FQ-01 ~ FQ-09 9/9 통과). FQ-10 ~ FQ-14는 다음 장 참조")

appendix_b2 = """## 슬라이드 23-2. 부록 B(계속): 3조 추가 정형쿼리

- 패턴: D (정형쿼리 표)
- 리드문: VIP 이탈 신호를 묻는 질문에 쓰는 정형쿼리 5개를 더함. EXPLAIN은 DB 미실행으로 확인 전이라 팀원 PC에서 확인해야 함

| 고정 조회ID | 설명 | 결과 단위 | SQL 요지 |
|-------------|------|----------|----------|
| `FQ-10` | 월 사용액 추이와 전월 대비 | 월 1개당 1행 | vip_monthly_trend, 월 순 |
| `FQ-11` | 연회비 대비 사용액 | 카드 1장당 1행 | vip_annual_fee_burden, card_ref 순 |
| `FQ-12` | 최근 활동 신호 | 고객 1행 | vip_activity_signal 전체 |
| `FQ-13` | 업종별 사용액 비중과 순위 | 업종 1개당 1행 | vip_category_share, 순위 순 |
| `FQ-14` | 이탈 신호 종합 | 고객 1행 | vip_churn_signal_summary 전체 |

- 전체 SQL은 `work/fixed_queries.json`. 이 5개의 `explain` 값은 "미실행"으로 적어 둠
- 출처 줄: work/fixed_queries.json (3조 추가, 2026-10-19)

"""
rep("## 슬라이드 24. 부록 C: SQL 검증 규칙", appendix_b2 + "## 슬라이드 24. 부록 C: SQL 검증 규칙")

# 7. 부록 C
rep("  - 허용 뷰: `app` 스키마 뷰 7개와 그 컬럼 전부", "  - 허용 뷰: `app` 스키마 뷰 12개와 그 컬럼 전부")

# 8. 부록 G (설계 가정과 위험 항목)
rep("  6. Groq 요청 한도(문서끼리 값이 달라 조직 한도 페이지 확인 필요)\n",
    "  6. Groq 요청 한도(문서끼리 값이 달라 조직 한도 페이지 확인 필요)\n"
    "  7. 3조 이탈 신호 기준(전월 대비, 연 환산 사용액 대비 연회비 배수, 최근 30일 비교)은 상담 현장 기준으로 확인\n")
rep("  5. `customer_daily_usage`의 EXPLAIN 예상 비용이 큼 → 실행 시간 실측 필요\n",
    "  5. `customer_daily_usage`의 EXPLAIN 예상 비용이 큼 → 실행 시간 실측 필요\n"
    "  6. 3조 추가 뷰 5개와 FQ-10 ~ FQ-14는 DB 미실행(EXPLAIN, 접근 권한, 뷰 수 대조 미확인) → 팀원 PC에서 확인\n")

# 9. C-01 응답 JSON 스키마, 키워드 표
rep('"enum": ["FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06", "FQ-07", "FQ-08", "FQ-09", null]},',
    '"enum": ["FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06", "FQ-07", "FQ-08", "FQ-09",\n'
    '                                  "FQ-10", "FQ-11", "FQ-12", "FQ-13", "FQ-14", null]},')
rep('"app.customer_delinquency_history", "app.customer_daily_usage", "app.merchant_usage"]}},',
    '"app.customer_delinquency_history", "app.customer_daily_usage", "app.merchant_usage",\n'
    '        "app.vip_monthly_trend", "app.vip_annual_fee_burden", "app.vip_activity_signal",\n'
    '        "app.vip_category_share", "app.vip_churn_signal_summary"]}},')
rep("| `FQ-08` | 업종 |\n| `FQ-09` | 가맹점 |\n",
    "| `FQ-08` | 업종(비중, 비율, 순위, 주로가 없을 때) |\n| `FQ-09` | 가맹점 |\n"
    "| `FQ-10` | 추이 또는 증감 또는 전월 |\n"
    "| `FQ-11` | 연회비 + (대비 또는 부담 또는 본전) |\n"
    "| `FQ-12` | 마지막 또는 경과 또는 활동 또는 휴면 |\n"
    "| `FQ-13` | 업종 + (비중 또는 비율 또는 순위 또는 주로) |\n"
    "| `FQ-14` | 이탈 + (신호 또는 위험 또는 징후) |\n")

MD.write_text(text, encoding="utf-8")
print("설계서 스크립트 반영 완료")
