"""routing_run_log.jsonl을 읽어 보고서용 마크다운 표를 출력함(1회성 평가 스크립트).

실행: retriever/sql-retriever 폴더에서 `.venv/Scripts/python work/eval/summarize_routing.py [--pass-label p1]`
같은 pass에 같은 질문 결과가 여럿이면(429 재시도) 마지막 결과 1개만 셈.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

RUN_LOG = Path(__file__).resolve().parent / "routing_run_log.jsonl"
GROUP_ORDER = ["FIXED_DIRECT", "FIXED_DERIVABLE", "NL2SQL", "UNANSWERABLE"]
ROUTES = ["FIXED", "NL2SQL", "UNANSWERABLE", "(실패)"]


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f}%)" if d else "-"


def p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, round(0.95 * len(ordered)) - 1)]


def stats_row(label: str, values: list[int]) -> str:
    if not values:
        return f"| {label} | 0 | - | - | - | - | - |"
    return (f"| {label} | {len(values)} | {statistics.mean(values):.0f} | {statistics.median(values):.0f} | "
            f"{p95(values)} | {min(values)} | {max(values)} |")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pass-label", default="p1")
    args = parser.parse_args()

    latest: dict[str, dict] = {}
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["pass"] == args.pass_label:
            latest[row["id"]] = row
    rows = list(latest.values())
    print(f"## pass={args.pass_label} 문항 {len(rows)}개\n")

    print("### 그룹별 정답률\n")
    print("| 그룹 | 문항 | route 정답 | route+query_id 정답(엄격) | 허용 대안 포함 |")
    print("|------|------|-----------|--------------------------|---------------|")
    by_group = defaultdict(list)
    for row in rows:
        by_group[row["group"]].append(row)
    for group in GROUP_ORDER:
        items = by_group.get(group, [])
        n = len(items)
        print(f"| {group} | {n} | {pct(sum(r['route_ok'] for r in items), n)} | "
              f"{pct(sum(r['strict_ok'] for r in items), n)} | {pct(sum(r['lenient_ok'] for r in items), n)} |")
    n = len(rows)
    print(f"| 전체 | {n} | {pct(sum(r['route_ok'] for r in rows), n)} | {pct(sum(r['strict_ok'] for r in rows), n)} | "
          f"{pct(sum(r['lenient_ok'] for r in rows), n)} |\n")

    print("### 정형쿼리별 FIXED 선택률(DIRECT 5 + DERIVABLE 1)\n")
    print("| 정형쿼리 | 문항 | FIXED 선택 | query_id까지 정답 | 다른 route로 간 문항 |")
    print("|----------|------|-----------|------------------|---------------------|")
    by_fq = defaultdict(list)
    for row in rows:
        if row["expected_route"] == "FIXED":
            by_fq[row["expected_query_id"]].append(row)
    for fq in sorted(by_fq):
        items = by_fq[fq]
        misses = [f"{r['id']}→{r['route'] or r['result']}{'/' + r['query_id'] if r['query_id'] else ''}"
                  for r in items if not r["strict_ok"]]
        print(f"| {fq} | {len(items)} | {pct(sum(r['route'] == 'FIXED' for r in items), len(items))} | "
              f"{pct(sum(r['strict_ok'] for r in items), len(items))} | {', '.join(misses) or '-'} |")
    print()

    print("### 혼동 행렬(행: 정답 route, 열: LLM이 고른 route)\n")
    print("| 정답 \\ 선택 | " + " | ".join(ROUTES) + " |")
    print("|" + "---|" * (len(ROUTES) + 1))
    for expected in ["FIXED", "NL2SQL", "UNANSWERABLE"]:
        counts = Counter((r["route"] or "(실패)") for r in rows if r["expected_route"] == expected)
        print(f"| {expected} | " + " | ".join(str(counts.get(route, 0)) for route in ROUTES) + " |")
    print()

    planned = [r for r in rows if r["result"] == "plan"]
    print("### 출력 토큰 수(성공 응답만)\n")
    print("| 구분 | 건수 | 평균 | 중앙값 | p95 | 최소 | 최대 |")
    print("|------|------|------|--------|-----|------|------|")
    for route in ["FIXED", "NL2SQL", "UNANSWERABLE"]:
        print(stats_row(f"LLM이 고른 route={route}", [r["output_tokens"] for r in planned
                                                       if r["route"] == route and r.get("output_tokens") is not None]))
    print(stats_row("전체", [r["output_tokens"] for r in planned if r.get("output_tokens") is not None]))
    print()
    inputs = [r["input_tokens"] for r in planned if r.get("input_tokens") is not None]
    if inputs:
        print(f"입력 토큰: 평균 {statistics.mean(inputs):.0f}, 최소 {min(inputs)}, 최대 {max(inputs)}\n")

    print("### 응답 시간(ms, 호출 1회 기준. 호출 사이 대기 시간 제외)\n")
    print("| 구분 | 건수 | 평균 | 중앙값 | p95 | 최소 | 최대 |")
    print("|------|------|------|--------|-----|------|------|")
    for route in ["FIXED", "NL2SQL", "UNANSWERABLE"]:
        print(stats_row(f"LLM이 고른 route={route}", [r["elapsed_ms"] for r in planned if r["route"] == route]))
    print(stats_row("전체(실패 포함)", [r["elapsed_ms"] for r in rows]))
    print()
    results = Counter(r["result"] for r in rows)
    over = sum(r["over_timeout"] for r in rows)
    print(f"호출 결과: {dict(results)} / 5초 초과: {over}건\n")

    print("### 오답 목록\n")
    print("| ID | 질문 | 정답 | LLM 선택 | 출력 토큰 | 판단 이유(LLM reason) |")
    print("|----|------|------|----------|-----------|----------------------|")
    for row in sorted(rows, key=lambda r: r["id"]):
        if row["strict_ok"]:
            continue
        expected = row["expected_route"] + (f"/{row['expected_query_id']}" if row["expected_query_id"] else "")
        chosen = (row["route"] or row["result"]) + (f"/{row['query_id']}" if row["query_id"] else "")
        tag = " (허용 대안)" if row["lenient_ok"] else ""
        print(f"| {row['id']} | {row['question']} | {expected} | {chosen}{tag} | {row.get('output_tokens')} | "
              f"{(row['reason'] or '').replace('|', '/')} |")


if __name__ == "__main__":
    main()
