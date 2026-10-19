"""설계서 스크립트 계산 검증 — 스크립트에 적힌 수치와 연결을 다시 계산해 서로 맞는지 확인함.

확인 항목
  1. 연동 최악값 = 타임아웃 x (1 + 재시도)
  2. 반복 구간 최악값 = (구간 단계 최악값 합계) x (1 + 재시도)
  3. 최악값 합계 <= 전체 시간 예산 (분기는 가장 큰 경로만)
  4. 남은 시간 예산 계산 예의 각 값
  5. 단계별 명세의 이전 단계, Mermaid, (빌드 후) PPT 도식 연결이 같음
  6. 입력 필드의 출처 단계가 그 필드를 실제로 출력함, 11개 항목에 빈칸 없음
  7. 가운뎃점 없음, 표와 코드 밖 줄은 120자 이내

사용법:
    python design/sql-retriever/tools/verify_calc.py [--edges design/sql-retriever/build/flow_edges.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BASE_DIR / "sql_retriever_워크플로우설계서.md"
ITEMS = ["단계ID", "단계명", "이전 단계", "비즈니스 목표", "입력 데이터", "수행 작업", "출력 데이터",
         "담당자 유형", "외부시스템", "예외 처리", "비고"]
STEP_RE = re.compile(r"S-R\d")

errors: list[str] = []


def check(cond: bool, ok_msg: str, ng_msg: str) -> None:
    print(("[통과] " + ok_msg) if cond else ("[실패] " + ng_msg))
    if not cond:
        errors.append(ng_msg)


def table_after(text: str, heading: str) -> list[list[str]]:
    """제목 다음에 처음 나오는 마크다운 표를 행 목록으로 돌려줌(헤더와 구분선 제외)."""
    start = text.index(heading)
    rows, seen = [], False
    for line in text[start:].splitlines()[1:]:
        if line.startswith("|"):
            seen = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                rows.append(cells)
        elif seen:
            break
    return rows[1:]


def nums(s: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges", help="build_deck.js가 내보낸 PPT 도식 연결(JSON)")
    args = parser.parse_args()
    text = SCRIPT.read_text(encoding="utf-8")

    # 계산 입력값
    params = {r[0]: r[1] for r in table_after(text, "## 부록(스크립트 전용). 계산 검증 입력값")}
    total, closing = float(params["total_budget_s"]), float(params["closing_s"])
    ratio = float(params["start_ratio"])
    timeout, retries = float(params["llm_timeout_s"]), int(params["llm_retries"])
    loop_retries = int(params["loop_retries"])
    print(f"[입력] 예산 {total}초, 종료 처리 {closing}초, LLM {timeout}초 x (1+{retries}), 반복 재시도 {loop_retries}")

    # 1. 연동 최악값
    link = table_after(text, "## 슬라이드 14. ③ 외부시스템 연동 명세")[0]
    link_worst = timeout * (1 + retries)
    check(nums(link[4])[0] == timeout and int(link[5]) == retries and nums(link[6])[-1] == link_worst,
          f"③ 연동 최악값 {link_worst:g}초 = {timeout:g} x (1 + {retries})",
          f"③ 연동 최악값 불일치: 표 {link[4]}, {link[5]}, {link[6]} / 계산 {link_worst}")

    # 2. 반복 구간 최악값 (S-R3, S-R4는 외부 연동 없음 → 0초)
    step_worst = {s: 0.0 for s in params["path_steps"].replace(" ", "").split(",")}
    step_worst[link[0].strip("`")] = link_worst
    loop_steps = params["loop_steps"].replace(" ", "").split(",")
    loop_worst = sum(step_worst[s] for s in loop_steps) * (1 + loop_retries)
    loop = table_after(text, "## 슬라이드 15. ④ 반복 구간 명세")[0]
    check(int(loop[3]) == loop_retries and nums(loop[4])[-1] == loop_worst,
          f"④ L-1 최악값 {loop_worst:g}초 = ({' + '.join(f'{step_worst[s]:g}' for s in loop_steps)}) x (1 + {loop_retries})",
          f"④ L-1 최악값 불일치: 표 {loop[4]} / 계산 {loop_worst}")

    # 3. 최악값 합계 (가장 긴 경로: S-R1 → L-1 → S-R5 → S-R6)
    outside = [s for s in step_worst if s not in loop_steps]
    total_worst = sum(step_worst[s] for s in outside) + loop_worst
    wf = {r[0]: r[1] for r in table_after(text, "## 슬라이드 16. ⑤ 워크플로우 명세")}
    check(nums(wf["전체 시간 예산"])[0] == total and nums(wf["종료 처리 시간"])[0] == closing,
          "⑤ 전체 시간 예산과 종료 처리 시간이 결정값과 같음", "⑤ 예산 값 불일치")
    stated = re.search(r"=\s*(\d+)초\s*\(", wf["최악값 합계"])
    check(stated is not None and float(stated.group(1)) == total_worst and total_worst <= total,
          f"⑤ 최악값 합계 {total_worst:g}초 <= 전체 시간 예산 {total:g}초",
          f"⑤ 최악값 합계 불일치 또는 예산 초과: 표 {wf['최악값 합계']} / 계산 {total_worst}")
    margin = total - total_worst - closing
    check(f"30 - 24 - 1(종료 처리) = {margin:g}초" in text,
          f"⑤ 여유 {margin:g}초(DB와 규칙 처리 몫) 계산 일치", "⑤ 여유 계산 불일치")

    # 4. 남은 시간 예산 계산 예
    threshold = total * ratio
    check(f"30 × 5% = {threshold:g}초" in text, f"⑥ 시작 기준 시간 {threshold:g}초", "⑥ 시작 기준 시간 불일치")
    examples = re.findall(r"사용 (\d+)초 → 남은 시간 (\d+) - (\d+) - (\d+) = (\d+)초 → 남은 시간 예산 (\d+) - (\d+) = (\d+)초 ([≥<]) 1\.5초",
                          text)
    check(len(examples) == 3, "⑥ 계산 예 3개를 찾음", f"⑥ 계산 예 개수 {len(examples)}")
    for used, t, u2, c, remain, r2, ext, budget, op in examples:
        used, t, u2, c, remain, r2, ext, budget = map(float, (used, t, u2, c, remain, r2, ext, budget))
        exp_remain = total - used - closing
        exp_budget = exp_remain - ext
        ok = (t == total and u2 == used and c == closing and remain == exp_remain and r2 == exp_remain
              and ext in (link_worst, 0.0) and budget == exp_budget and (op == "≥") == (exp_budget >= threshold))
        check(ok, f"⑥ 사용 {used:g}초: 남은 시간 {exp_remain:g}초, 남은 시간 예산 {exp_budget:g}초 {op} {threshold:g}초",
              f"⑥ 계산 예 불일치(사용 {used:g}초)")
    st = re.search(r"min\((\d+)초, 5초\) = (\d+)초", text)
    check(st is not None and min(float(st.group(1)), 5) == float(st.group(2)),
          "⑥ statement_timeout 계산 예 일치", "⑥ statement_timeout 계산 예 불일치")

    # 5. 연결 일치: 단계별 명세 이전 단계 vs Mermaid
    specs: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"## 슬라이드 \d+\. ② 단계별 명세: (S-R\d)", text):
        rows = table_after(text, m.group(0))
        specs[m.group(1)] = {r[0]: r[1] for r in rows}
    check(sorted(specs) == [f"S-R{i}" for i in range(1, 7)], "② 단계별 명세 6장(S-R1 ~ S-R6)",
          f"② 단계별 명세 누락: {sorted(specs)}")
    for sid, row in specs.items():
        missing = [k for k in ITEMS if not row.get(k, "").strip()]
        check(not missing, f"② {sid} 11개 항목 모두 채움", f"② {sid} 빈 항목: {missing}")

    spec_edges = set()
    for sid, row in specs.items():
        for prev in STEP_RE.findall(row["이전 단계"]):
            spec_edges.add((prev, sid))
    mermaid = re.search(r"```mermaid\n(.*?)```", text, re.S).group(1)
    node = {}
    for nid, label in re.findall(r"(\w+)[\[\(\{]+\(?([^\]\)\}]*)", mermaid):
        found = STEP_RE.search(label)
        if found:
            node[nid] = found.group(0)
    mer_edges = set()
    for line in mermaid.splitlines():
        # 화살표 끝(-->, .->) 바로 뒤 노드가 도착점. 라벨 안의 하이픈(L-1 등)에 속지 않게 마지막 화살표를 씀
        head = re.match(r"\s*(\w+)", line)
        tail = re.findall(r"(?:-->|\.->)\s*(\w+)", line)
        if head and tail and head.group(1) in node and tail[-1] in node:
            mer_edges.add((node[head.group(1)], node[tail[-1]]))
    check(spec_edges == mer_edges, f"① Mermaid 연결 {len(mer_edges)}개 = 단계별 명세 이전 단계",
          f"① 연결 불일치: 명세만 {spec_edges - mer_edges}, Mermaid만 {mer_edges - spec_edges}")
    if args.edges:
        deck = {tuple(e) for e in json.loads(Path(args.edges).read_text(encoding="utf-8"))}
        check(deck == spec_edges, f"① PPT 도식 연결 {len(deck)}개 = 단계별 명세 이전 단계",
              f"① PPT 도식 연결 불일치: 도식만 {deck - spec_edges}, 명세만 {spec_edges - deck}")

    # 6. 입력 필드의 출처 단계가 그 필드를 출력함
    outputs = {sid: set(re.findall(r"`([a-z_]+)`", row["출력 데이터"])) for sid, row in specs.items()}
    for sid, row in specs.items():
        for seg in row["입력 데이터"].split(" / "):
            fields = re.findall(r"`([a-z_]+)`", seg)
            sources = STEP_RE.findall(seg)
            for src in sources:
                lost = [f for f in fields if f not in outputs[src]]
                check(not lost, f"② {sid} 입력 {fields} ← {src} 출력에 있음",
                      f"② {sid} 입력 {lost}가 {src} 출력에 없음")

    # 7. 표기 규칙
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    check("·" not in text, "가운뎃점(·) 0건", "가운뎃점(·)이 남아 있음")
    long_lines = [ln for ln in body.splitlines() if len(ln) > 120 and not ln.startswith("|")]
    check(not long_lines, "표와 코드 밖 줄 120자 이내", f"120자 초과 줄 {len(long_lines)}개: {long_lines[:2]}")

    print(f"[결과] 실패 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
