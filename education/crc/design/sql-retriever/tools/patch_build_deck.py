# -*- coding: utf-8 -*-
"""build_deck.js 에 3조 변경(뷰 5개, FQ-10 ~ FQ-14)을 반영하는 1회용 스크립트임.

반영 표식("createSlide22b")이 이미 있으면 멈춤.
사용법: python design/sql-retriever/tools/patch_build_deck.py
"""

from __future__ import annotations

from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "build" / "build_deck.js"
text = JS.read_text(encoding="utf-8")

if "createSlide22b" in text:
    raise SystemExit("이미 반영된 파일임. 중단함")


def rep(old: str, new: str) -> None:
    global text
    assert old in text, "찾지 못함: " + old[:70]
    assert text.count(old) == 1, f"{text.count(old)}곳에 있음: " + old[:70]
    text = text.replace(old, new)


# 제목 장표
rep('text: "팀 design-agentic-ai"', 'text: "팀 3조"')
rep('text: "작성일 2026-10-15"', 'text: "작성일 2026-10-19"')

# 개수 문구
rep("실행 계정 sql_retriever_user, 허용 뷰 7개, 결과 행 상한 200",
    "실행 계정 sql_retriever_user, 허용 뷰 12개, 결과 행 상한 200")
rep("정형쿼리 9개의 키워드 표로 규칙 매칭하면", "정형쿼리 14개의 키워드 표로 규칙 매칭하면")

# 부록 A, B, C 문구
rep('lead: "NL2SQL 실행 계정이 읽을 수 있는 뷰는 9개이며, LLM에는 app 스키마 7개만 보여 줌" });',
    'lead: "NL2SQL 실행 계정이 읽을 수 있는 뷰는 14개이며, LLM에는 app 스키마 12개만 보여 줌(기본 7개와 3조 추가 5개)" });')
rep('sourceLine(s, "출처: rdb/init/04 ~ 06 SQL, work/db_catalog.json(2026-10-15 실측)");',
    'sourceLine(s, "출처: rdb/init/04 ~ 06 SQL, work/db_catalog.json(2026-10-15 실측). 3조 추가 뷰 5개는 다음 장");')
rep('lead: "정형쿼리 9개는 모두 실행 계정 권한으로 EXPLAIN을 통과함(실행하지 않고 계획만 확인)" });',
    'lead: "정형쿼리 14개 중 FQ-01 ~ FQ-09는 EXPLAIN을 통과함. FQ-10 ~ FQ-14(3조 추가)는 DB 미실행으로 확인 전임" });')
rep('sourceLine(s, "출처: work/explain_fixed_queries.log (sql_retriever_user, 9/9 통과)");',
    'sourceLine(s, "출처: work/explain_fixed_queries.log (sql_retriever_user, FQ-01 ~ FQ-09 9/9 통과). FQ-10 ~ FQ-14는 다음 장");')
rep('"허용 뷰: app 스키마 뷰 7개와 그 컬럼 전부"', '"허용 뷰: app 스키마 뷰 12개와 그 컬럼 전부"')

# 부록 G 보강
rep('"Groq 요청 한도(문서끼리 값이 달라 조직 한도 페이지 확인 필요)"],',
    '"Groq 요청 한도(문서끼리 값이 달라 조직 한도 페이지 확인 필요)",\n'
    '    "3조 이탈 신호 기준(전월 대비, 연 환산 배수, 최근 30일 비교)은 상담 현장 기준으로 확인"],')
rep('"customer_daily_usage의 EXPLAIN 예상 비용이 큼 → 실행 시간 실측 필요"],',
    '"customer_daily_usage의 EXPLAIN 예상 비용이 큼 → 실행 시간 실측 필요",\n'
    '    "3조 추가 뷰 5개와 FQ-10 ~ FQ-14는 DB 미실행 → 팀원 PC에서 EXPLAIN과 접근 권한 확인"],')

# 이어지는 장 2개
new_funcs = '''
async function createSlide22b() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 A(계속): 3조 추가 논리 뷰",
    lead: "VIP 이탈 신호(사용 감소, 연회비 부담, 최근 활동, 주 사용 업종)를 보는 뷰 5개를 더함. 기존 뷰와 RLS는 고치지 않음" });
  const lw = 11.0;
  table(s, mdTable("## 슬라이드 22-2."), { w: lw, colW: [3.5, 3.1, 2.6, 1.8], rowH: 0.78, fontSize: 14 });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  tintBox(s, { x: rx, y: 1.9, w: rw, h: 5.95 });
  s.addText("적용 방식", { x: rx + 0.15, y: 2.0, w: rw - 0.3, h: 0.45, fontFace: FONT, fontSize: fsMin(18), bold: true, color: C.navy, margin: 0 });
  bullets(s, ["회원 조건 없이 RLS와 세션 변수 3개로 회원과 기간을 가름(기존 뷰와 같은 방식)",
    "뷰 소유자 app_reader, 서비스 계정 sql_retriever_user는 뷰 조회 권한만 받음",
    "이탈 신호 기준(전월 대비, 연 환산 배수, 최근 30일 비교)은 설계 가정이며 상담 현장 기준으로 확인할 값임"],
  { x: rx + 0.1, y: 2.5, w: rw - 0.2, h: 5.2, fontSize: 15 });
  sourceLine(s, "출처: rdb/init/07_vip_churn_views.sql (DB 미실행, SQL을 읽어 검토함)");
}

async function createSlide23b() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 B(계속): 3조 추가 정형쿼리",
    lead: "VIP 이탈 신호를 묻는 질문에 쓰는 정형쿼리 5개를 더함. EXPLAIN은 DB 미실행으로 확인 전임" });
  table(s, mdTable("## 슬라이드 23-2."), { colW: [1.6, 3.8, 3.2, 6.3], rowH: 0.7, fontSize: 15, bold0: true });
  s.addText("전체 SQL은 work/fixed_queries.json. 이 5개의 explain 값은 미실행으로 적어 둠",
    { x: X0, y: 7.1, w: CW, h: 0.38, fontFace: FONT, fontSize: fsMin(15), color: C.slate, margin: 0 });
  sourceLine(s, "출처: work/fixed_queries.json (3조 추가, 2026-10-19)");
}
'''
rep("async function createSlide24() {", new_funcs + "\nasync function createSlide24() {")
rep("createSlide22, createSlide23, createSlide24,", "createSlide22, createSlide22b, createSlide23, createSlide23b, createSlide24,")

JS.write_text(text, encoding="utf-8")
print("build_deck.js 반영 완료")
