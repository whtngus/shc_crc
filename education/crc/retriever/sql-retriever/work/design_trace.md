# SQL 검색기 설계 대조표

- 설계 근거: `design/sql-retriever/sql_retriever_워크플로우설계서.pptx` (35장, 작성일 2026-10-15)
- 사용자 승인으로 함께 읽은 자료(2026-10-15)
  - 설계서 스크립트의 「부록 B. 정형쿼리 SQL 전문」 한 구간만 (PPT 30장이 가리키는 곳)
  - `design/sql-retriever/work/db_catalog.json` (PPT 31장 "컬럼: db_catalog.json의 컬럼 전체")
  - `rdb/init/04 ~ 06` 뷰 정의 (PPT 12장 "기간 판정 기준은 뷰 정의(04 ~ 06 SQL)에서 가져옴")
- DB에서 직접 확인(sql_retriever_user, 읽기 전용 트랜잭션, 2026-10-15)
  - `public.lab_metadata` 키: `base_date`(값 2026-08-31), `txn_period`(값 "2025-08 ~ 2026-08") 등 7개
  - `current_user` = sql_retriever_user, `transaction_read_only` = on
- 장 그림: `work/design_png/slide-*.png` (흐름 도식 6장을 눈으로 확인함)
- 표 읽는 법: "구현 위치"는 소스 경로, "확인 시험"은 `tests/` 안의 시험 파일 이름(확장자 생략)  
  개발을 마친 뒤 실제 파일 기준으로 맞춤(2026-10-15). 시험 결과는 `work/test_report.md`

## 1. 단계(S-R1 ~ S-R6)

### 1.1 S-R1 검색 요청 접수와 검증 (8, 9장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-101 | 입력: request_id, question(1 ~ 500자), member_id, base_date(선택) | `app/application/models.py` SearchRequest | `test_presentation`, `test_steps_r1` |
| D-102 | 출력: request_id, masked_question, masked_count, member_id, base_date, coverage_start, started_at, attempt(0) | `app/application/steps.py` step_r1 | `test_steps_r1` |
| D-103 | 작업 1: started_at 기록, 남은 시간 예산 측정(차감 5초) | step_r1 + `app/domain/time_budget.py` | `test_time_budget`, `test_steps_r1` |
| D-104 | 작업 2: member_id 형식 `M-` + 숫자 4자리(설계 가정), base_date 형식 YYYY-MM-DD | `app/domain/request_rules.py` | `test_request_rules` |
| D-105 | 작업 3: 전화번호, 카드번호(15 ~ 16자리), 주민등록번호, 이메일, 회원ID를 `[가림]`으로 바꾸고 개수를 셈(D-07) | `app/domain/masking.py` | `test_masking` |
| D-106 | 작업 4: 읽기 전용 트랜잭션, statement_timeout ≤ 남은 시간 예산, lab_metadata에서 데이터 기준일과 거래 제공 시작일 읽기 | `app/infrastructure/postgres_repository.py` load_member_context | `test_integration_db` |
| D-107 | 작업 5: 세션 변수 3개 set_config(이름, 값, true), member_basic에서 회원 존재와 가입일 확인 후 트랜잭션 종료 | postgres_repository.py | `test_integration_db` |
| D-108 | 오류: 필드 누락, 형식 오류, 500자 초과, 기준일이 데이터 기준일보다 뒤 → INVALID_REQUEST(400) | step_r1, `app/presentation/api.py` | `test_steps_r1`, `test_presentation` |
| D-109 | 오류: 회원 없음 또는 기준일에 가입 전 → MEMBER_NOT_FOUND(404) | step_r1 | `test_steps_r1`, `test_integration_db` |
| D-110 | 오류: DB 접속 또는 조회 실패 → DB_ERROR(500) | postgres_repository.py | `test_steps_r1` |
| D-111 | 오류: 시작 전 남은 시간 예산 부족 → TIME_BUDGET_EXCEEDED(504) | step_r1 | `test_steps_r1` |

### 1.2 S-R2 정형쿼리 또는 NL2SQL 판단 (10, 11장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-201 | 입력: masked_question, base_date, coverage_start, attempt, retry_reason(선택), previous_sql(선택) | `app/application/steps.py` step_r2 | `test_steps_r2` |
| D-202 | 출력: plan(6개 필드), plan_source(LLM 또는 KEYWORD_RULE), attempt(+1) | step_r2 | `test_steps_r2` |
| D-203 | 작업 1: 남은 시간 예산 측정(차감 5초). 미달이면 키워드 규칙 대체 경로 | step_r2 | `test_steps_r2` |
| D-204 | 작업 3: 유저 프롬프트 조립. member_id는 넣지 않음 | `app/infrastructure/groq_planner.py` | `test_groq_planner` |
| D-205 | 작업 4: C-01 호출 timeout 5초, SDK max_retries 0, response_format json_schema strict | groq_planner.py | `test_groq_planner`, `test_integration_llm` |
| D-206 | 작업 5: 응답 JSON을 plan으로, plan_source LLM | step_r2 | `test_steps_r2` |
| D-207 | 예외: 타임아웃, 연결 오류, 429, 5xx, 400 → 재시도 없이 키워드 규칙으로 정형쿼리 1개, route FIXED, plan_source KEYWORD_RULE | step_r2 + `app/domain/fixed_queries.py` | `test_steps_r2`, `test_domain_rules` |
| D-208 | 예외: 키워드 규칙에도 없음 → LLM_UNAVAILABLE(503) | step_r2 | `test_steps_r2` |
| D-209 | 예외: LLM 거절(refusal) → route UNANSWERABLE 계획으로 S-R3에 넘김 | groq_planner.py, step_r2 | `test_groq_planner`, `test_steps_r2` |
| D-210 | 예외: 429 retry-after는 기록만 하고 기다리지 않음 | groq_planner.py | `test_groq_planner` |

### 1.3 S-R3 계획 적합성 판정 (12, 13장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-301 | 입력: plan, plan_source, attempt, base_date, coverage_start | `app/application/steps.py` step_r3 | `test_steps_r3` |
| D-302 | 출력: verdict(FIT, UNFIT, UNANSWERABLE), candidate_sql, sql_source, query_id, retry_reason, unanswerable_reason | step_r3 | `test_steps_r3` |
| D-303 | 작업 2: route UNANSWERABLE → verdict UNANSWERABLE(사유 plan.reason) | step_r3 | `test_steps_r3` |
| D-304 | 작업 3: route FIXED → query_id가 FQ-01 ~ FQ-08인지, 등록 SQL을 candidate_sql로 | step_r3 + fixed_queries.py | `test_steps_r3` |
| D-305 | 작업 4: route NL2SQL → sql 비어 있지 않음, target_views가 허용 뷰 7개 안 | step_r3 + `app/domain/catalog.py` | `test_steps_r3` |
| D-306 | 작업 5: requested_period가 대상 뷰 제공 기간(월 집계 6개월, 일별 90일, 연체 이력 12개월) 안이고 기준일 이전인지. 밖이면 UNANSWERABLE(데이터 제공 기간 밖) | `app/domain/periods.py` | `test_domain_rules`, `test_steps_r3` |
| D-307 | 작업 6: FIT → S-R4 / UNFIT + attempt 1 → S-R2 / UNFIT + attempt 2 → UNANSWERABLE로 바꿔 S-R6 / UNANSWERABLE → S-R6 | step_r3, `app/infrastructure/graph.py` | `test_steps_r3`, `test_graph_flow` |
| D-308 | 예외: plan 필드 누락 → UNFIT | step_r3 | `test_steps_r3` |
| D-309 | 예외: 3, 4번 확인 실패 → UNFIT, 사유 코드 UNKNOWN_QUERY_ID, VIEW_NOT_ALLOWED 등 | step_r3 | `test_steps_r3` |
| D-310 | 오류 종료 없음(D-08) | step_r3 | `test_graph_flow` |

### 1.4 S-R4 SQL 검증 (14, 15장, 31장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-401 | 입력: candidate_sql, sql_source, query_id, attempt / 출력: validated_sql, row_limit(200), retry_reason, previous_sql | `app/application/steps.py` step_r4 | `test_steps_r4`, `test_integration_db`(금지 SQL이 DB에 가지 않음) |
| D-402 | 작업 2: PostgreSQL 문법 파서로 문법 트리 생성(sqlglot) | `app/infrastructure/sql_validator.py` | `test_sql_validator` |
| D-403 | 작업 3: 한 문장이고 SELECT(WITH 포함) | sql_validator.py | `test_sql_validator` |
| D-404 | 작업 4: 참조 표가 모두 허용 뷰 7개(app. 스키마, 스키마 이름 붙임) | sql_validator.py + catalog.py | `test_sql_validator` |
| D-405 | 작업 5: 컬럼이 뷰 컬럼 목록 안, 함수가 허용 함수 목록 안 | sql_validator.py | `test_sql_validator` |
| D-406 | 작업 6: 금지 구문(쓰기와 구조 변경 11종, 여러 문장, 주석, FOR UPDATE/SHARE, SELECT INTO, 금지 함수, 금지 스키마) | sql_validator.py | `test_sql_validator` |
| D-407 | 작업 7: LIMIT 없으면 200을 붙이고, 200보다 크면 200으로 낮춤 | sql_validator.py | `test_sql_validator` |
| D-408 | 예외: 실패 + NL2SQL + attempt 1 → 사유와 직전 SQL을 담아 S-R2(L-1) | step_r4, graph.py | `test_steps_r4`, `test_graph_flow` |
| D-409 | 예외: 실패 + attempt 2 → SQL_VALIDATION_FAILED(422) | step_r4 | `test_steps_r4` |
| D-410 | 예외: 실패 + FIXED → SQL_VALIDATION_FAILED(422) + 운영 알림 | step_r4 | `test_steps_r4` |
| D-411 | 오류 메시지에 SQL, 뷰 이름, 컬럼 이름을 넣지 않음(사유 코드는 로그에만) | `app/application/models.py` 오류 문구 | `test_steps_r4`, `test_presentation` |
| D-412 | 정형쿼리도 같은 검사를 거침(이중 안전장치) | step_r4 | `test_sql_validator`(FQ 8개 통과) |

### 1.5 S-R5 SQL 실행 (16, 17장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-501 | 입력: validated_sql, member_id, base_date, coverage_start, started_at / 출력: columns, rows(최대 200), row_count, truncated, db_elapsed_ms | `app/application/steps.py` step_r5 | `test_steps_r5_r6` |
| D-502 | 작업 1: 남은 시간 예산 측정(차감 0초). 미달이면 TIME_BUDGET_EXCEEDED | step_r5 | `test_steps_r5_r6` |
| D-503 | 작업 2 ~ 7: 커넥션 풀, BEGIN READ ONLY, SET LOCAL statement_timeout(남은 시간 예산 이하, 밀리초 내림), set_config 3개, 실행 최대 200행, ROLLBACK | `app/infrastructure/postgres_repository.py` execute | `test_integration_db` |
| D-504 | 예외: 실행 제한 시간 초과 → DB_TIMEOUT(504) | postgres_repository.py | `test_steps_r5_r6`, `test_integration_db` |
| D-505 | 예외: 그 밖의 DB 오류 → DB_ERROR(500) | postgres_repository.py | `test_steps_r5_r6` |
| D-506 | 예외: 결과 0행은 오류 아님 → S-R6 | step_r5 | `test_steps_r5_r6` |

### 1.6 S-R6 응답 구성과 반환 (18, 19장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-601 | 출력(호출자 응답) 13개 필드: request_id, status, route, query_id, plan_source, columns, rows, row_count, truncated, base_date, coverage_start, message, elapsed_ms | `app/application/models.py` SearchResponse, step_r6 | `test_steps_r5_r6`, `test_presentation` |
| D-602 | 작업 1: 남은 시간 측정, 미달이어도 실행 | step_r6 | `test_steps_r5_r6` |
| D-603 | 작업 2: verdict UNANSWERABLE → status UNANSWERABLE, 아니면 OK | step_r6 | `test_steps_r5_r6` |
| D-604 | 작업 3: message 문장 틀(기준일 건수, 200건 도달, 0건, 답할 수 없음 사유) | `app/domain/messages.py` | `test_domain_rules` |
| D-605 | 작업 4: SQL 문장, 회원ID, 내부 뷰 이름을 응답에 넣지 않음 | step_r6 | `test_steps_r5_r6` |
| D-606 | 작업 5: 감사 로그(request_id, route, query_id, plan_source, attempt, elapsed_ms, row_count, 가린 질문, 회원ID 해시) | step_r6 + `app/infrastructure/audit_log.py` | `test_steps_r5_r6` |
| D-607 | 작업 6: HTTP 200 반환 | api.py | `test_presentation` |
| D-608 | 예외: 응답 구성 실패 → INTERNAL_ERROR(500) / 감사 로그 실패 → 응답은 반환하고 로그 실패만 알림 | step_r6 | `test_steps_r5_r6` |

## 2. 흐름 유형과 반복 구간 (5, 6, 7, 21장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-701 | 순차 S-R1 → S-R2 → S-R3, 분기 S-R3(FIT, UNFIT, UNANSWERABLE), 분기 S-R4(통과, 재생성, 오류), 합류 S-R6 | `app/infrastructure/graph.py` | `test_graph_flow` |
| D-702 | 반복 구간 L-1: S-R2 ~ S-R4, 재시도 1회, 최악값 10초 | graph.py, steps.py | `test_graph_flow` |
| D-703 | 병렬 없음 | graph.py(간선이 모두 한 갈래) | `test_graph_flow`(그래프 모양) |
| D-704 | 착지: S-R3 부적합 → S-R6(답할 수 없음), S-R4 실패 → SQL_VALIDATION_FAILED | steps.py | `test_graph_flow` |

## 3. LLM 커넥터 C-01 (20, 23 ~ 26장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-801 | 제공자 SQL_RETRIEVER_LLM_PROVIDER = groq, 모델 SQL_RETRIEVER_LLM_MODEL = openai/gpt-oss-120b, 키 GROQ_API_KEY | `app/infrastructure/settings.py`, `app/bootstrap.py` | `test_settings_and_layers` |
| D-802 | 베이스 URL `https://api.groq.com/openai/v1`, POST /chat/completions, Bearer 인증 | groq_planner.py | `test_groq_planner` |
| D-803 | temperature 0.2, top_p 1, reasoning_effort low, include_reasoning false, max_completion_tokens 4096, seed 42 | groq_planner.py | `test_groq_planner` |
| D-804 | response_format json_schema strict: route, query_id(string 또는 null), sql(string 또는 null), target_views(array), requested_period(from, to), reason | groq_planner.py | `test_groq_planner`, `test_integration_llm` |
| D-805 | timeout 5초, SDK max_retries 0 | groq_planner.py | `test_groq_planner` |
| D-806 | logprobs, logit_bias, messages[].name은 넣지 않음(400 오류) | groq_planner.py | `test_groq_planner` |
| D-807 | 시스템 프롬프트 8섹션(요약 근거로 전문 작성, 사용자 승인) | `app/infrastructure/prompts/c01_system_prompt.md` | `test_groq_planner` |
| D-808 | 유저 프롬프트 변수 6개를 XML 태그로 감쌈, 첫 회 retry_reason과 previous_sql은 "없음" | `app/infrastructure/prompts/c01_user_prompt.md` | `test_groq_planner` |
| D-809 | 제공자를 더하면 같은 응답 구조를 지키는 어댑터를 하나 더 만듦 | `app/application/ports.py` PlannerPort, `app/bootstrap.py` create_planner | `test_settings_and_layers`(포트 추상 메서드) |

## 4. 정형쿼리와 SQL 검증 규칙 (29 ~ 31장, 부록 B, db_catalog.json)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-901 | 정형쿼리 FQ-01 ~ FQ-08 SQL 전문(부록 B) | `app/domain/fixed_queries.py` | `test_sql_validator`, `test_integration_db`(8개 모두 실행) |
| D-902 | 대체 경로 키워드(설계 가정), 위에서부터 처음 맞는 1개 | fixed_queries.py | `test_domain_rules` |
| D-903 | 허용 뷰 7개(app 스키마)와 뷰별 컬럼(db_catalog.json) | `app/domain/catalog.py` | `test_sql_validator` |
| D-904 | 허용 구문: SELECT 한 문장, WITH, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT, 허용 뷰끼리 JOIN, 서브쿼리 | sql_validator.py | `test_sql_validator` |
| D-905 | 허용 함수: count, sum, avg, min, max, date_trunc, to_char, extract, coalesce, round, greatest, least, abs, 형변환 | catalog.py, sql_validator.py | `test_sql_validator` |
| D-906 | 금지: INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, TRUNCATE, GRANT, REVOKE, COPY | sql_validator.py | `test_sql_validator` |
| D-907 | 금지: 여러 문장(;), 주석(--, /* */), FOR UPDATE, FOR SHARE, SELECT INTO | sql_validator.py | `test_sql_validator` |
| D-908 | 금지 함수: set_config, current_setting, pg_로 시작, generate_series, pg_sleep | sql_validator.py | `test_sql_validator` |
| D-909 | 금지 스키마: app_internal, public, pg_catalog, information_schema | sql_validator.py | `test_sql_validator` |
| D-910 | 결과 행 상한 LIMIT 200 | sql_validator.py | `test_sql_validator` |
| D-911 | 뷰 제공 기간(뷰 정의 04 ~ 06): 월 집계와 가맹점은 max(기준월 - 5개월, 거래 제공 시작일) ~ 기준일, 일별은 max(기준일 - 89일, 거래 제공 시작일) ~ 기준일, 연체 이력은 최근 완료월 - 11개월 ~ 최근 완료월 말일 | `app/domain/periods.py` | `test_domain_rules` |

## 5. 시간 예산 정책 (2, 20, 22, 27, 28장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-1001 | 전체 시간 예산 15초, 종료 처리 1초, 시작 기준 15 × 5% = 0.75초 | `app/domain/time_budget.py` | `test_time_budget` |
| D-1002 | 남은 시간 = 15 - 기존 사용 - 1, 남은 시간 예산 = 남은 시간 - 차감값, 시작 조건 ≥ 0.75초 | time_budget.py | `test_time_budget`(28장 예 1 ~ 4) |
| D-1003 | 차감값: S-R1 5초, S-R2 5초, S-R3/S-R4 attempt 1은 5초 attempt 2는 0초, S-R5/S-R6 0초 | time_budget.py | `test_time_budget` |
| D-1004 | 착지: S-R1 안전 종료, S-R2 키워드 규칙(없으면 안전 종료), S-R3/S-R4 재시도 끄고 차감 0초로 재계산 후 미달이면 안전 종료, S-R5 안전 종료, S-R6 항상 실행 | steps.py | `test_steps_r1` ~ `test_steps_r4`, `test_steps_r5_r6`, `test_graph_flow` |
| D-1005 | S-R5 statement_timeout = 그 시점 남은 시간 예산 이하(28장 예 4: 2,700ms) | steps.py, postgres_repository.py | `test_steps_r5_r6`, `test_time_budget` |
| D-1006 | 최악값 합계 10초 ≤ 15초, 여유 4초는 DB 조회와 규칙 처리 몫(실측 확인) | `tests/integration_support.py` 실측 기록 | `test_integration_db`, `test_integration_llm`(`work/measurements.jsonl`) |

## 6. 오류 응답 (33장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-1101 | 오류 코드 8개와 HTTP 상태, 다시 시도 여부 | `app/application/models.py` ERROR_CATALOG | `test_settings_and_layers`, `test_presentation` |
| D-1102 | 오류 응답 구조: request_id, status("ERROR"), error_code, message(한국어), retryable | models.py ErrorResponse | `test_presentation` |
| D-1103 | 오류 응답에 SQL, DB 식별자, 접속 정보, 키를 넣지 않음 | models.py, api.py | `test_presentation` |

## 7. DB 접속과 실행 환경 (2, 23, 29장)
| ID | 설계 항목 | 구현 위치 | 확인 시험 |
|----|-----------|-----------|-----------|
| D-1201 | PostgreSQL cardlab, 계정 sql_retriever_user(관리자 권한 없음, 읽기 전용 세션). 호스트 localhost, 포트 5432(사용자 답) | settings.py | `test_integration_db` |
| D-1202 | 비밀번호 RDB_PASSWORD는 `secrets/.env`에서만 읽음 | settings.py | `test_settings_and_layers` |
| D-1203 | 시작 트리거 동기 요청, API `POST /v1/sql-retriever/search`(사용자 답) | `app/presentation/api.py`, `serve_api.py` | `test_presentation`, `work/logs/api_run.txt` |
| D-1204 | 재개 방안 해당없음(처음부터 다시 해도 됨) | `app/infrastructure/graph.py`(체크포인트 없이 compile) | `test_graph_flow` |

## 8. 설계 가정(실측으로 확인할 값, 35장)
| ID | 설계 가정 | 확인 방법 |
|----|-----------|-----------|
| A-1 | LLM 타임아웃 5초, temperature 0.2, reasoning_effort low | 통합 시험에서 C-01 응답 시간 측정 |
| A-2 | DB 조회와 규칙 처리가 여유 4초 안(특히 FQ-08) | FQ 8개와 회원 확인 실행 시간 측정 |
| A-3 | 시작 기준 비율 5% | 단계별 남은 시간 예산 기록 |
| A-4 | member_id 형식, 질문 500자 상한, 키워드 규칙표, lab_metadata 키 이름 | 실제 DB 회원ID와 메타데이터 키로 확인 |
| A-5 | 출력 4096 토큰 상한에서도 5초 안 응답 | 통합 시험 응답 시간과 토큰 수 기록 |

## 9. 사용자에게 물어 정한 값 (2026-10-15)
| 질문 | 사용자 답 |
|------|-----------|
| 설계서 폴더 | `design/sql-retriever` |
| 출력 기준 폴더 | `sql-retriever` (2026-10-15 `retriever/sql-retriever`로 이동) |
| 비밀값 위치 | `secrets/.env` (사용자가 직접 만듦) |
| 정형쿼리 SQL 전문 | 설계서 스크립트의 부록 B만 읽기 |
| 허용 컬럼 출처 | `db_catalog.json` 읽기 |
| 기간 판정 기준 | `rdb/init/04 ~ 06` 읽기 |
| DB 호스트와 포트 | localhost:5432 |
| API 경로 | `POST /v1/sql-retriever/search` (포트 8000) |
| S-R2 예산 미달 + 키워드 규칙 없음 | TIME_BUDGET_EXCEEDED(504) |
| SQL_RETRIEVER_LLM_MODEL | 사용자가 `secrets/.env`에 직접 추가 |

## 10. 설계서에서 확인한 불일치와 빈 곳
| 구분 | 내용 | 처리 |
|------|------|------|
| 도식 표현 차이 | 6장 그림은 S-R3 상자 + "적합?" 마름모, 7장 Mermaid는 S-R3 자체를 마름모로 그림 | 연결 방향과 분기는 같음. 구현 차이 없음 |
| 도식에 없는 경로 | S-R4 실패 + sql_source FIXED → 오류 종료(15장)는 도식에 따로 없음 | 15장 명세대로 구현 |
| 빈 곳 | 정형쿼리 SQL, 허용 컬럼, 기간 계산식, DB 호스트, API 경로 | 9절의 사용자 답으로 정함 |
| 개발 계획에서 정한 값 | coverage_start 계산(txn_period 해석), 내부 상태 필드, 401 등 그 밖의 LLM 오류 처리 등 | `work/dev_plan.md` 5절 P-01 ~ P-17(사용자 승인 2026-10-15) |
