"""C-01 route 판정 평가 실행기(1회성 평가 스크립트). 실제 Groq로 평가셋 질문을 1개씩 보내고 결과를 JSONL로 남김.

실행: retriever/sql-retriever 폴더에서 `.venv/Scripts/python work/eval/run_routing_eval.py [--resume] [--only F05-1,N-01] [--pass-label p2]`
- 시스템 프롬프트와 C-01 코드는 그대로 씀(bootstrap.create_planner). 평가용으로 고친 곳 없음
- 호출 사이를 21초 이상 띄움. 대기는 시간 측정 밖에서 함(Groq 분당 토큰 한도, 위험 R-03)
- 비밀값은 load_settings로만 읽고 출력하지 않음
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # retriever/sql-retriever 폴더
sys.path.insert(0, str(ROOT))

from app.application.models import PlannerFailure, PlanRequest  # noqa: E402
from app.bootstrap import create_planner  # noqa: E402
from app.infrastructure.groq_planner import TIMEOUT_SECONDS  # noqa: E402
from app.infrastructure.settings import load_settings  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = EVAL_DIR / "routing_questions.json"
RUN_LOG = EVAL_DIR / "routing_run_log.jsonl"
MIN_INTERVAL_SECONDS = 21.0  # 통합 시험의 20초보다 1초 여유를 둠
RATE_LIMIT_WAIT_SECONDS = 60.0  # 429가 나면 평가 쪽에서만 기다렸다 다시 보냄(서비스는 기다리지 않음)
MAX_RATE_LIMIT_RETRIES = 2


class _TokenCapture(logging.Handler):
    """GroqPlanner의 "planner ok" 로그에서 입력과 출력 토큰 수를 받아 둠(코드를 고치지 않고 재려는 것)."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.last: dict[str, int | None] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("planner ok") and isinstance(record.args, tuple):
            _, input_tokens, output_tokens = record.args
            self.last = {"input_tokens": input_tokens, "output_tokens": output_tokens}


def judge(question: dict, plan: dict | None) -> dict:
    """정답 판정. strict는 정답 route(+FIXED면 query_id) 일치, lenient는 허용 대안까지 인정."""
    if plan is None:
        return {"route_ok": False, "query_id_ok": False, "strict_ok": False, "lenient_ok": False}
    route = plan.get("route")
    qid = plan.get("query_id")
    route_ok = route == question["expected_route"]
    if question["expected_route"] == "FIXED":
        allowed_ids = question.get("acceptable_query_ids") or [question["expected_query_id"]]
        query_id_ok = route_ok and qid in allowed_ids
    else:
        query_id_ok = route_ok
    lenient_ok = query_id_ok or route in question.get("acceptable_alt", [])
    return {"route_ok": route_ok, "query_id_ok": query_id_ok, "strict_ok": query_id_ok, "lenient_ok": lenient_ok}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="같은 pass에서 이미 결과가 있는 질문은 건너뜀")
    parser.add_argument("--only", default="", help="쉼표로 나눈 질문 ID만 실행")
    parser.add_argument("--pass-label", default="p1", help="반복 실행 구분 이름")
    args = parser.parse_args()

    spec = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    base_date = date.fromisoformat(spec["base_date"])
    coverage_start = date.fromisoformat(spec["coverage_start"])
    questions = spec["questions"]
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]

    done: set[str] = set()
    if args.resume and RUN_LOG.exists():
        for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("pass") == args.pass_label and row.get("result") != "RATE_LIMIT":
                done.add(row["id"])

    settings = load_settings()
    planner = create_planner(settings)
    capture = _TokenCapture()
    llm_logger = logging.getLogger("sql_retriever.llm")
    llm_logger.setLevel(logging.INFO)
    llm_logger.addHandler(capture)

    print(f"model={settings.llm_model} questions={len(questions)} skip={len(done)} pass={args.pass_label}", flush=True)
    last_call_end = 0.0
    for index, question in enumerate(questions, 1):
        if question["id"] in done:
            continue
        for attempt_no in range(MAX_RATE_LIMIT_RETRIES + 1):
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - last_call_end)
            if wait > 0:
                time.sleep(wait)  # 측정 시간 밖에서 기다림
            capture.last = {}
            request = PlanRequest(question=question["question"], base_date=base_date,
                                  coverage_start=coverage_start, attempt=1)
            started = time.perf_counter()
            plan = None
            refusal = None
            failure: PlannerFailure | None = None
            try:
                outcome = planner.plan(request)
                plan, refusal = outcome.plan, outcome.refusal
            except PlannerFailure as error:
                failure = error
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            last_call_end = time.monotonic()

            result = "plan" if plan is not None else ("refusal" if refusal else failure.kind)
            row = {
                "measured_at": datetime.now(timezone.utc).isoformat(),
                "pass": args.pass_label,
                "id": question["id"],
                "group": question["group"],
                "question": question["question"],
                "expected_route": question["expected_route"],
                "expected_query_id": question["expected_query_id"],
                "result": result,
                "elapsed_ms": elapsed_ms,
                "over_timeout": elapsed_ms > TIMEOUT_SECONDS * 1000,
                **capture.last,
                "route": plan.get("route") if plan else None,
                "query_id": plan.get("query_id") if plan else None,
                "target_views": plan.get("target_views") if plan else None,
                "requested_period": plan.get("requested_period") if plan else None,
                "reason": plan.get("reason") if plan else None,
                # LLM이 만든 SQL. 회원 조건은 프롬프트로 금지되어 회원 정보가 없음. 오분류 분석용
                "sql": plan.get("sql") if plan else None,
                "status_code": getattr(failure, "status_code", None),
                "retry_after": getattr(failure, "retry_after", None),
                **judge(question, plan),
            }
            with RUN_LOG.open("a", encoding="utf-8") as file:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
            mark = "OK " if row["strict_ok"] else ("ALT" if row["lenient_ok"] else "NG ")
            print(f"[{index:02d}/{len(questions)}] {mark} {question['id']:6s} {result:10s} "
                  f"route={row['route']} qid={row['query_id']} {elapsed_ms}ms "
                  f"out={row.get('output_tokens')}", flush=True)
            if result != "RATE_LIMIT":
                break
            try:
                retry_after = float(row["retry_after"] or 0)
            except ValueError:
                retry_after = 0.0
            if retry_after > 120:  # 일일 한도로 보임. 남은 질문은 --resume으로 나중에 이어 감
                print(f"stop: retry-after={retry_after}s", flush=True)
                return
            time.sleep(max(RATE_LIMIT_WAIT_SECONDS, retry_after))  # 평가 전용 대기. 다음 시도도 다시 21초 간격을 지킴


if __name__ == "__main__":
    main()
