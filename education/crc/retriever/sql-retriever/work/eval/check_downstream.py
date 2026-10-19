"""평가 로그의 계획을 S-R3 기간 판정과 S-R4 SQL 검사에 오프라인으로 넣어 봄(1회성 평가 스크립트, DB·LLM 호출 없음).

route를 잘못 골라도 결과가 같으면 괜찮은지, 아니면 사용자 답이 달라지는지 보려는 것.
실행: retriever/sql-retriever 폴더에서 `.venv/Scripts/python work/eval/check_downstream.py [--pass-label p1]`
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.domain.fixed_queries import FIXED_QUERIES  # noqa: E402
from app.domain.periods import is_period_answerable  # noqa: E402
from app.domain.request_rules import parse_date  # noqa: E402
from app.infrastructure.sql_validator import SqlglotValidator  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RUN_LOG = EVAL_DIR / "routing_run_log.jsonl"


def simulate(row: dict, base_date: date, coverage_start: date, validator: SqlglotValidator) -> str:
    """S-R3(기간) → S-R4(검사) 결과를 한 단어로 돌려줌. 실행 결과(행 값)는 DB가 필요해 보지 않음."""
    route = row["route"]
    if route == "UNANSWERABLE":
        return "UNANSWERABLE"
    if route == "FIXED":
        fixed = FIXED_QUERIES.get(row["query_id"] or "")
        if fixed is None:
            return "UNFIT(UNKNOWN_QUERY_ID)"
        views = [fixed.view]
    else:
        views = row["target_views"] or []
    period = row["requested_period"] or {}
    period_from = parse_date(period.get("from")) if period.get("from") else None
    period_to = parse_date(period.get("to")) if period.get("to") else None
    if not is_period_answerable(views, period_from, period_to, base_date, coverage_start):
        return "OUT_OF_PERIOD→UNANSWERABLE"
    if route == "FIXED":
        return "FIXED 실행"
    result = validator.validate(row["sql"] or "")
    return "NL2SQL 실행" if result.ok else f"검사 실패({result.reason})→재계획"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pass-label", default="p1")
    args = parser.parse_args()
    spec = json.loads((EVAL_DIR / "routing_questions.json").read_text(encoding="utf-8"))
    base_date = date.fromisoformat(spec["base_date"])
    coverage_start = date.fromisoformat(spec["coverage_start"])
    validator = SqlglotValidator()

    latest: dict[str, dict] = {}
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["pass"] == args.pass_label and row["result"] == "plan":
            latest[row["id"]] = row

    print("| ID | 정답 | LLM 선택 | requested_period | 다음 단계 시뮬레이션 |")
    print("|----|------|----------|------------------|---------------------|")
    summary: dict[str, int] = {}
    for row in sorted(latest.values(), key=lambda r: r["id"]):
        outcome = simulate(row, base_date, coverage_start, validator)
        key = f"{row['expected_route']}→{row['route']}: {outcome}"
        summary[key] = summary.get(key, 0) + 1
        if row["strict_ok"] and outcome in ("FIXED 실행", "NL2SQL 실행", "UNANSWERABLE"):
            continue  # 정답이고 그대로 실행되는 문항은 표에서 뺌
        period = row["requested_period"] or {}
        expected = row["expected_route"] + (f"/{row['expected_query_id']}" if row["expected_query_id"] else "")
        chosen = row["route"] + (f"/{row['query_id']}" if row["query_id"] else "")
        print(f"| {row['id']} | {expected} | {chosen} | {period.get('from')} ~ {period.get('to')} | {outcome} |")
    print("\n| 정답→선택: 다음 단계 결과 | 문항 수 |")
    print("|---------------------------|--------|")
    for key, count in sorted(summary.items()):
        print(f"| {key} | {count} |")


if __name__ == "__main__":
    main()
