# SQL 검색기 개발 계획

- 근거: `work/design_trace.md`(설계 대조표), `references/layered-architecture-guide.md`, `references/dev-comment-guide.md`
- 작성: 지식니(주), 플로니(흐름과 시간 예산), 커넥니(LLM 커넥터와 키), 스택니(CLI와 API) 관점 점검
- 상태: 사용자 승인(2026-10-15, 「모두 승인」). 개발 결과는 `work/test_report.md`

## 1. 계층 배치
레이어드 아키텍처(Layered Architecture): 업무 규칙과 기술 코드를 층으로 나누고, 업무 규칙이 정한 약속(포트)을
기술 코드가 따르게 하는 구조임. 그래서 DB나 LLM 없이도 가짜 객체로 업무 규칙을 시험할 수 있음

| 계층 | 파일 | 담는 설계 항목 |
|------|------|----------------|
| domain | `app/domain/time_budget.py` | 시간 예산 상수(15초, 1초, 5%), 남은 시간과 남은 시간 예산 계산, 단계별 차감값 |
| domain | `app/domain/request_rules.py` | member_id 형식, 질문 길이, 날짜 형식 검사 |
| domain | `app/domain/masking.py` | 개인 식별자 정규식 가림(D-07) |
| domain | `app/domain/catalog.py` | 허용 뷰 12개(기본 7개 + 3조 추가 5개)와 컬럼, 허용 함수, 금지 함수, 금지 스키마, 행 상한 200 |
| domain | `app/domain/fixed_queries.py` | 정형쿼리 FQ-01 ~ FQ-14 SQL과 키워드 규칙(FQ-10 ~ FQ-14는 3조 추가) |
| domain | `app/domain/periods.py` | 뷰별 데이터 제공 기간 계산과 requested_period 판정 |
| domain | `app/domain/messages.py` | S-R6 안내 문장 틀 |
| application | `app/application/models.py` | 요청과 응답 구조, 계획(plan) 구조, 오류 코드 8개 표, 공통 오류 클래스 |
| application | `app/application/ports.py` | 포트 5개(아래 표) |
| application | `app/application/steps.py` | S-R1 ~ S-R6 단계 함수(업무 흐름), 다음 단계 판정 함수 |
| application | `app/application/services.py` | SqlRetrieverService: 요청 1건 실행, 오류를 오류 응답으로 바꿈 |
| infrastructure | `app/infrastructure/settings.py` | `secrets/.env`와 환경변수 읽기 |
| infrastructure | `app/infrastructure/groq_planner.py` | C-01 LLM 커넥터(LangChain ChatOpenAI, Groq OpenAI 호환 주소) |
| infrastructure | `app/infrastructure/prompts/` | C-01 시스템 프롬프트 전문, 유저 프롬프트 틀 |
| infrastructure | `app/infrastructure/sql_validator.py` | S-R4 문법 트리 검사(sqlglot) |
| infrastructure | `app/infrastructure/postgres_repository.py` | S-R1 회원 확인, S-R5 SQL 실행(psycopg 3, 커넥션 풀) |
| infrastructure | `app/infrastructure/graph.py` | 단계 흐름(LangGraph StateGraph) |
| infrastructure | `app/infrastructure/audit_log.py` | 감사 로그(JSON 한 줄씩 파일에 씀) |
| presentation | `app/presentation/api.py` | FastAPI `POST /v1/sql-retriever/search` |
| presentation | `app/presentation/cli.py` | CLI 질문 1건 실행 |
| bootstrap | `app/bootstrap.py` | 설정 읽기 → 구현체 생성 → 서비스 조립. 제공자 groq일 때 GroqPlanner 선택 |
| 실행 스크립트 | `run_cli.py`, `serve_api.py` | presentation만 호출 |

### 1.1 포트
| 포트 | 메서드 | 구현체 | 시험용 가짜 |
|------|--------|--------|-------------|
| PlannerPort | plan(입력) → 계획 또는 LLM 실패 신호 | GroqPlanner | FakePlanner |
| MemberRepositoryPort | load_member_context(member_id, base_date, 제한 시간) | PostgresRepository | FakeRepository |
| SqlExecutorPort | execute(validated_sql, 세션 변수, 제한 시간) | PostgresRepository | FakeRepository |
| SqlValidatorPort | validate(sql) → 통과 SQL 또는 사유 코드 | SqlglotValidator | 실제 구현 그대로 사용(외부 연동 없음) |
| AuditLogPort | write(기록) | JsonlAuditLog | FakeAuditLog |
| WorkflowRunnerPort | run(시작 상태) → 최종 상태 | LangGraphRunner | 서비스 시험에서 가짜 사용 |

- 시계는 `Callable[[], float]`(초 단위 단조 시계)로 주입해 시간 예산 시험에서 흐른 시간을 마음대로 정함

## 2. 단계 흐름 구현 방식: LangGraph 제안
- 제안: 단계 흐름은 LangGraph `StateGraph`, LLM 호출은 LangChain(`ChatOpenAI`, `ChatPromptTemplate`)으로 구현함
- 이유
  - 설계 흐름에 되돌림 반복(L-1: S-R3 또는 S-R4 → S-R2)과 3갈래 분기(S-R3), 합류(S-R6)가 있음
  - LangChain 체인(LCEL)은 앞으로만 흐르는 구조라 되돌림 반복을 코드 바깥 반복문으로 따로 짜야 함
  - LangGraph는 LangChain 팀이 만든 흐름 도구라 조건 간선(`add_conditional_edges`)으로 반복과 분기를 설계서 도식과
    같은 모양으로 적을 수 있음(출처: context7 `/websites/langchain_oss_python_langgraph`)
- 노드 6개(S-R1 ~ S-R6)와 조건 간선 2개(S-R3 뒤, S-R4 뒤)만 둠. 오류 종료는 단계 함수가 공통 오류를 던져
  그래프를 멈추고, 서비스가 오류 응답으로 바꿈
- 루프 상한(플로니 점검): 반복 횟수는 attempt로 막고, 혹시 모를 무한 반복은 `recursion_limit` 12로 한 번 더 막음
  (정상 최대 방문 수는 S-R1, S-R2, S-R3, S-R4, S-R2, S-R3, S-R4, S-R5, S-R6의 9회)
- 체크포인트는 두지 않음(설계서 재개 방안 "해당없음")

## 3. 패키지 목록과 출처
모두 PyPI(https://pypi.org)에서 받아 `retriever/sql-retriever/.venv`에 설치함. 버전은 2026-10-15 기준 최신 안정판임

| 패키지 | 버전 | 쓰는 곳 | 사용법 확인 |
|--------|------|---------|-------------|
| langchain-core | 1.6.10 | 프롬프트 틀, 메시지 | context7 `/websites/reference_langchain` |
| langchain-openai | 1.7.2 | ChatOpenAI(Groq OpenAI 호환 주소), with_structured_output(json_schema, strict) | context7 `/websites/reference_langchain` |
| langgraph | 1.2.15 | StateGraph 흐름 | context7 `/websites/langchain_oss_python_langgraph` |
| psycopg[binary] | 3.3.6 | PostgreSQL 드라이버 | context7 `/websites/psycopg_psycopg3` |
| psycopg-pool | 3.3.3 | 커넥션 풀 | context7 `/websites/psycopg_psycopg3` |
| sqlglot | 30.22.0 | SQL 문법 트리 검사 | context7 `/tobymao/sqlglot` |
| fastapi | 0.143.1 | API, 오류 처리기 | context7 `/websites/fastapi_tiangolo` |
| uvicorn | 0.54.0 | API 서버 실행 | context7 대상 아님(실제 서버 실행으로 확인) |
| pydantic | 2.14.1 | 요청과 응답 구조 | context7 대상 아님(시험으로 확인) |
| python-dotenv | 1.2.4 | `secrets/.env` 읽기 | context7 대상 아님(시험으로 확인) |
| pytest | 9.1.1 | 시험 | context7 대상 아님 |
| httpx | 0.28.1 | FastAPI TestClient | context7 대상 아님 |

- LLM 연결에 `langchain-groq` 대신 `langchain-openai`를 쓰는 이유: 설계서가 베이스 URL을 OpenAI 호환 주소
  `https://api.groq.com/openai/v1`로 정했고, ChatOpenAI가 base_url, timeout, max_retries, reasoning_effort, seed,
  extra_body(include_reasoning 전달)를 모두 받음

## 4. 시험 계획
| 구분 | 파일 | 확인하는 것 |
|------|------|-------------|
| 단위 | `tests/test_time_budget.py` | 28장 계산 예 1 ~ 4가 같은 값을 냄, 차감값 표 |
| 단위 | `tests/test_request_rules.py`, `tests/test_masking.py` | 형식 검사, 식별자 5종 가림과 개수 |
| 단위 | `tests/test_sql_validator.py` | 31장 허용 예와 금지 예 하나씩, 정형쿼리 14개 통과, 뷰 12개, LIMIT 붙임과 낮춤 |
| 단위 | `tests/test_keyword_rule.py`, `tests/test_periods.py`, `tests/test_messages.py` | 키워드 규칙 순서, 뷰별 제공 기간, 문장 틀 |
| 단위 | `tests/test_steps_r1.py` ~ `tests/test_steps_r6.py` | 단계마다 정상 경로와 오류 종료 경로(가짜 LLM, 가짜 DB) |
| 단위 | `tests/test_graph_flow.py` | L-1 되돌림 1회, 재시도 소진, 답할 수 없음 합류, 예산 착지 |
| 단위 | `tests/test_groq_planner.py` | 하이퍼파라미터 값, 유저 프롬프트 조립(member_id 없음), 실패 분류(가짜 모델 주입) |
| 단위 | `tests/test_api.py`, `tests/test_cli.py` | HTTP 상태 변환, 응답 구조, 오류 응답에 SQL 없음(가짜 서비스) |
| 통합 | `tests/test_integration_db.py` | 실제 DB: 정형쿼리 14개 1회씩, 회원 확인, 회원 없음, 읽기 전용 확인 |
| 통합 | `tests/test_integration_llm.py` | 실제 Groq: NL2SQL 질문 몇 개, 금지 SQL을 유도하는 질문 → 오류 코드 확인 |
| 실행 확인 | `work/test_report.md` | CLI 실제 실행, API 서버에 실제 요청, 설계 가정 실측 |

- 통합 시험은 `pytest -m integration`으로 따로 돌리고, 기본 실행(`pytest`)은 외부 연동 없는 단위 시험만 돌림
- 시험용 회원ID는 `rdb/README.md`의 합성 회원(M-1001, M-5001 등)을 씀

## 5. 승인받을 결정
설계서에 없거나 정해야 하는 값임. 괄호 안이 제안임

| 번호 | 항목 | 제안 |
|------|------|------|
| P-01 | 단계 흐름 도구 | LangGraph StateGraph(2절) |
| P-02 | coverage_start 계산 | `lab_metadata.txn_period` 값 "2025-08 ~ 2026-08"의 앞쪽 월 첫날(2025-08-01). 데이터 기준일은 `lab_metadata.base_date` |
| P-03 | 내부 상태 필드 1개 추가 | `retry_disabled`(boolean): S-R3, S-R4 예산 착지("재시도를 끄고 차감값 0초로 다시 계산") 표시용. 응답에는 안 나감 |
| P-04 | 설계서에 없는 LLM 오류 | 401, 403, 404, 422와 응답 JSON 읽기 실패도 11장 목록(타임아웃 등)과 같은 키워드 규칙 대체 경로로 보냄 |
| P-05 | 키워드 비교 방식 | 질문과 키워드 모두 띄어쓰기를 지우고 비교("보유카드"도 "보유 카드"에 맞음) |
| P-06 | API 입력 형식 오류 | 필드 누락, 타입 오류도 FastAPI 기본 422가 아니라 INVALID_REQUEST(400)로 돌려줌. request_id를 못 읽으면 오류 응답의 request_id는 빈 문자열 |
| P-07 | 답할 수 없음 응답 | columns, rows는 빈 목록, row_count 0, truncated false. route와 query_id는 S-R3가 정한 값이 있을 때만 넣음 |
| P-08 | 안내 문장 | OK: "기준일 {base_date} 기준 {row_count}건" (+ 200건이면 ", 앞 200건만 보여 줌") / 0건: "기준일 {base_date} 기준 해당 데이터 없음" / 답할 수 없음: "답할 수 없음: {사유}" |
| P-09 | 답할 수 없음 사유 | LLM 사유(plan.reason)에 `app.`, `app_internal.` 같은 내부 뷰 이름이 있으면 지우고 씀(D-605 "내부 뷰 이름은 넣지 않음") |
| P-10 | 감사 로그와 운영 알림 | 감사 로그는 `logs/audit.jsonl`에 JSON 한 줄씩, 회원ID는 SHA-256 해시. 운영 알림(FQ 검증 실패, 감사 로그 실패)은 경고 로그 |
| P-11 | 오류 문구 | 오류 코드마다 한국어 안내 1줄(SQL, 뷰 이름, 접속 정보 없음). SQL_VALIDATION_FAILED는 33장 예 문장 그대로 |
| P-12 | 개인 식별자 정규식 | 카드번호(숫자 15 ~ 16자리, 하이픈과 띄어쓰기 허용) → 주민등록번호(6자리-7자리) → 전화번호(01X 휴대폰, 0X 지역번호) → 이메일 → 회원ID(`M-` + 숫자 4자리) 순서로 가림 |
| P-13 | S-R1 DB 시간 초과 | 33장 표대로 DB_ERROR(500). DB_TIMEOUT은 S-R5에서만 씀 |
| P-14 | 커넥션 풀 | 최소 1개, 최대 4개. 풀에서 접속을 기다리는 시간도 그 시점 남은 시간 예산 이하 |
| P-15 | CLI 인자 | `python run_cli.py --member-id M-1001 --question "..." [--base-date YYYY-MM-DD] [--request-id ...]`. 응답 JSON 출력, 오류면 종료 코드 1 |
| P-16 | `.env`의 설계서에 없는 이름 | `SQL_RETRIEVER_LLM_RUNTIME`, `SQL_RETRIEVER_VLLM_API_KEY` 등은 읽지 않음 |
| P-17 | LLM 시스템 프롬프트 전문 | `app/infrastructure/prompts/c01_system_prompt.md`(25장 요약 8섹션 근거) |

## 3조 변경 이력(2026-10-19)
- 범위: 사용자 결정 「단계는 예제 그대로, 논리뷰와 정형쿼리만 우리 고객군용으로」
- 바꾼 파일: `app/domain/catalog.py`, `fixed_queries.py`, `periods.py`, `app/infrastructure/prompts/c01_system_prompt.md`,
  `groq_planner.py`(주석), 시험 6개 파일, `README.md`
- 정형쿼리 번호를 설계서(FQ-01 ~ FQ-09 + 3조 FQ-10 ~ FQ-14)에 맞춤. 예제 코드의 옛 번호는 업종 FQ-05, 최근 연체 FQ-06,
  연체 이력 FQ-07, 일별 FQ-08이었음
- 키워드 규칙은 예제 코드의 「위에서부터 처음 맞는 1개」 방식을 유지함. 설계서 키워드 표는 「모두 포함 시 일치」로 적혀 있어
  표현이 다르지만, 같은 질문은 같은 정형쿼리로 연결됨(시험 29건으로 확인)
- 남은 차이(3조가 건드리지 않음): 전체 시간 예산(코드 15초, 설계서 30초), C-01 타임아웃(코드 5초, 설계서 12초),
  응답 필드 이름(코드 `query_id`, `target_views`, 설계서 `fixed_query_id`, `used_views`). 예제 저장소에서 이미 다른 부분임
