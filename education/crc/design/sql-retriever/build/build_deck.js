// SQL 검색기 워크플로우 설계서 PPT 빌드 — references/pptx-guide.md 6절 규칙을 코드로 강제함
// 실행: node design/sql-retriever/build/build_deck.js  (pptxgenjs는 전역 설치본을 NODE_PATH로 찾음)
// 표 내용은 스크립트(md)에서 읽어 와 스크립트와 슬라이드가 어긋나지 않게 함
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const BASE_DIR = path.resolve(__dirname, "..");
const SCRIPT = fs.readFileSync(path.join(BASE_DIR, "sql_retriever_워크플로우설계서.md"), "utf8").split("\r\n").join("\n");
const OUT = path.join(BASE_DIR, "sql_retriever_워크플로우설계서.pptx");

// 6-1 팔레트 상수
const C = {
  title: "2C2926", lead: "000000",
  navy: "1E2A5C", blue: "2E74C6", ink: "2B3242",
  slate: "4A5364", sub: "7C8598", body: "3B4557",
  tint: "EEF3FA", altRow: "F5F8FC", tableHead: "E2EEF9",
  dark: "404155", border: "D9E0EC", line: "EDF0F6", pill: "C3CEE0",
  titleLine: "E2E8F0", footLine: "E9ECF3", pageNum: "6B6B7B", white: "FFFFFF",
};
const FONT = "Pretendard";
const LAYOUT = "내용_단쪽";
const X0 = 0.557, CW = 14.9;
const BODY_TOP = 1.90, BODY_BOTTOM = 7.95;

// 6-2 최소 글자 크기 14pt 강제
const MIN_FONT = 14;
const fsMin = (size) => {
  if (size < MIN_FONT) throw new Error(`fontSize ${size} < ${MIN_FONT}pt 금지! 슬라이드를 분리할 것`);
  return size;
};

let pptx;

// ---------------------------------------------------------------------------
// 스크립트(md) 읽기 도우미
// ---------------------------------------------------------------------------
const clean = (s) => s.replace(/`/g, "").trim();

// 제목 줄 다음에 처음 나오는 마크다운 표를 [헤더, ...행]으로 돌려줌
function mdTable(heading, nth = 0) {
  const start = SCRIPT.indexOf(heading);
  if (start < 0) throw new Error(`스크립트에서 제목을 못 찾음: ${heading}`);
  const lines = SCRIPT.slice(start).split("\n").slice(1);
  const tables = [];
  let cur = null;
  for (const line of lines) {
    if (line.startsWith("## ")) break;
    if (line.startsWith("|")) {
      const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (cells.every((c) => /^[-: ]*$/.test(c))) continue;
      if (!cur) { cur = []; tables.push(cur); }
      cur.push(cells.map(clean));
    } else if (cur) {
      cur = null;
    }
  }
  if (!tables[nth]) throw new Error(`표를 못 찾음: ${heading} #${nth}`);
  return tables[nth];
}

// ---------------------------------------------------------------------------
// 6-3 ~ 6-5 공통 헬퍼
// ---------------------------------------------------------------------------
function defineContentLayout() {
  pptx.defineSlideMaster({
    title: LAYOUT,
    background: { color: C.white },
    objects: [
      { line: { x: 0.556, y: 0.95, w: 14.888, h: 0, line: { color: C.titleLine, width: 1.5 } } },
      { text: { text: "무단전재 및 배포 금지",
          options: { x: 0.4875, y: 8.517, w: 1.675, h: 0.27, fontFace: FONT, fontSize: 12, color: "A6A6A6", margin: 0 } } },
      { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.109, w: 15.025, h: 0.906,
          fontFace: FONT, fontSize: 32, bold: true, color: C.title, margin: 0, align: "left", valign: "middle" },
          text: "" } },
    ],
    slideNumber: { x: 11.913, y: 8.517, w: 3.6, h: 0.25, fontFace: FONT, fontSize: 16, color: C.pageNum, align: "right" },
  });
}

function pageHeader(slide, { title, lead }) {
  slide.addText(title, { placeholder: "title" });
  if (lead) {
    slide.addText(lead, { x: X0, y: 1.259, w: CW, h: 0.42, margin: 0, isTextBox: true,
      fontFace: "Pretendard SemiBold", fontSize: fsMin(18), color: C.lead });
  }
}

function sourceLine(slide, text) {
  slide.addShape(pptx.shapes.LINE, { x: X0, y: 8.08, w: CW, h: 0, line: { color: C.footLine, width: 1 } });
  slide.addText(text, { x: X0, y: 8.14, w: CW, h: 0.32, margin: 0, valign: "top", isTextBox: true,
    fontFace: FONT, fontSize: text.length > 140 ? 12 : 14, color: C.sub });
}

function headerBar(slide, { x, y, w, text, accent = false, h = 0.5 }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06,
    fill: { color: accent ? C.blue : C.navy }, line: { type: "none" } });
  slide.addText(text, { x, y, w, h, align: "center", valign: "middle", color: C.white, bold: true,
    fontSize: fsMin(20), fontFace: FONT, margin: 0 });
}

function numBadge(slide, { x, y, n, color = C.blue, size = 0.42, fontSize = 18 }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y, w: size, h: size, rectRadius: 0.05,
    fill: { color }, line: { type: "none" } });
  slide.addText(String(n), { x, y, w: size, h: size, align: "center", valign: "middle", color: C.white,
    bold: true, fontSize: fsMin(fontSize), fontFace: FONT, margin: 0 });
}

function darkBadge(slide, { x, y, w, text, h = 0.38 }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.05,
    fill: { color: C.dark }, line: { type: "none" } });
  slide.addText(text, { x, y, w, h, align: "center", valign: "middle", color: C.white, bold: true,
    fontSize: fsMin(15), fontFace: FONT, margin: 0 });
}

function pill(slide, { x, y, w, text, h = 0.4 }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: h / 2,
    fill: { color: C.tint }, line: { color: C.pill, width: 1 } });
  slide.addText(text, { x, y, w, h, align: "center", valign: "middle", color: C.navy, bold: true,
    fontSize: fsMin(15), fontFace: FONT, margin: 0 });
}

function tintBox(slide, { x, y, w, h, fill = C.tint }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1,
    fill: { color: fill }, line: { color: C.border, width: 1 } });
}

// 글머리 목록. items는 문자열 또는 {text, bold}
function bullets(slide, items, { x, y, w, h, fontSize = 16, color = C.body, numbered = false, bulletChar }) {
  const runs = items.map((it, i) => {
    const t = typeof it === "string" ? { text: it } : it;
    // 번호 글머리(type: number)는 테마 글꼴(+mj-lt)을 써서 붙여넣기 호환 규칙 7에 걸리므로 번호를 글자로 붙임
    return { text: numbered ? `${i + 1}. ${t.text}` : t.text, options: { bullet: numbered || bulletChar === null ? false : { code: "25AA" },
      bold: !!t.bold, color: t.color || color, breakLine: i < items.length - 1, paraSpaceAfter: 6 } };
  });
  slide.addText(runs, { x, y, w, h, fontFace: FONT, fontSize: fsMin(fontSize), valign: "top", margin: 0.08 });
}

function callout(slide, { x, y, w, h, text, fontSize = 16 }) {
  slide.addShape(pptx.shapes.RECTANGLE, { x, y, w: 0.07, h, fill: { color: C.blue }, line: { type: "none" } });
  slide.addText(text, { x: x + 0.15, y, w: w - 0.15, h, fontFace: FONT, fontSize: fsMin(fontSize),
    color: C.navy, bold: true, italic: true, valign: "middle", margin: 0.05 });
}

// 6-9 표: 첫 행은 헤더. multiline=true면 " / " 기준으로 줄을 나눔
function table(slide, rows, { x = X0, y = BODY_TOP, w = CW, colW, fontSize = 14, rowH = 0.42, bold0 = false,
  splitCols = [] } = {}) {
  const head = rows[0].map((t) => ({ text: t, options: { fill: { color: C.tableHead }, color: C.navy, bold: true } }));
  const body = rows.slice(1).map((r, ri) => r.map((t, ci) => {
    const text = splitCols.includes(ci) ? t.split(" / ").join("\n") : t;
    return { text, options: { fill: { color: ri % 2 ? C.altRow : C.white }, color: C.body,
      bold: bold0 && ci === 0 } };
  }));
  slide.addTable([head, ...body], { x, y, w, colW, fontFace: FONT, fontSize: fsMin(fontSize), rowH,
    valign: "middle", margin: [0.04, 0.08, 0.04, 0.08], border: { type: "solid", color: C.line, pt: 1 },
    autoPage: false });
}

// ---------------------------------------------------------------------------
// 슬라이드
// ---------------------------------------------------------------------------
async function createSlide01() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "SQL 검색기 워크플로우 설계서" });
  numBadge(s, { x: 7.4, y: 2.2, n: "W-1", color: C.navy, size: 1.2, fontSize: 28 });
  s.addText("SQL 검색기", { x: X0, y: 3.55, w: CW, h: 0.7, align: "center", fontFace: FONT, fontSize: fsMin(36),
    bold: true, color: C.navy, margin: 0 });
  tintBox(s, { x: 2.2, y: 4.5, w: 11.6, h: 1.3 });
  s.addText("상담사 질문을 정형쿼리 또는 NL2SQL로 바꿔 카드 회원 DB에서 안전하게 답을 찾는 동기 요청 워크플로우",
    { x: 2.4, y: 4.5, w: 11.2, h: 1.3, align: "center", valign: "middle", fontFace: FONT, fontSize: fsMin(22),
      color: C.ink, margin: 0 });
  pill(s, { x: 5.0, y: 6.3, w: 2.9, text: "팀 3조", h: 0.5 });
  pill(s, { x: 8.1, y: 6.3, w: 2.9, text: "작성일 2026-10-19", h: 0.5 });
}

async function createSlide02() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "설계 개요",
    lead: "상담사가 기다리는 30초 안에, 허용된 뷰만 읽기 전용으로 조회하는 검색기를 설계함" });
  const lw = 7.6, rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  headerBar(s, { x: X0, y: 1.9, w: lw, text: "설계 대상과 범위" });
  tintBox(s, { x: X0, y: 2.5, w: lw, h: 5.4 });
  const rows = [
    ["설계 대상", "W-1 SQL 검색기(질문 → 정형쿼리 또는 NL2SQL → 결과 행 반환)"],
    ["유저스토리", "없음"],
    ["시작 트리거", "동기 요청(호출자가 검색을 요청하고 응답을 기다림) → 단계ID 접두어 S-R"],
    ["설계 범위", "요청 검증, 경로 판단, 계획 판정, SQL 검증, SQL 실행, 응답 반환, Groq LLM 커넥터"],
    ["제외 범위", "답변 문장 작성(호출자 몫), 뷰와 RLS 변경, 화면, 배포"],
    ["DB 취급", "시스템 내부 구성요소(사용자 결정). 외부시스템 연동과 커넥터 목록에서 제외"],
  ];
  s.addText(rows.flatMap(([k, v], i) => [
    { text: k + "  ", options: { bold: true, color: C.navy } },
    { text: v, options: { color: C.body, breakLine: i < rows.length - 1 } },
  ]), { x: X0 + 0.15, y: 2.6, w: lw - 0.3, h: 5.2, fontFace: FONT, fontSize: fsMin(16), valign: "top",
    paraSpaceAfter: 10, margin: 0.05 });
  headerBar(s, { x: rx, y: 1.9, w: rw, text: "핵심 결정값", accent: true });
  const items = [
    "전체 시간 예산 30초, 종료 처리 시간 1초",
    "LLM: Groq openai/gpt-oss-120b, 타임아웃 12초, 재시도 0회",
    "SQL 검증 실패 시 다시 만들기 1회(반복 구간 L-1)",
    "실행 계정 sql_retriever_user, 허용 뷰 12개, 결과 행 상한 200",
    "필드 표기: 이름(타입, 필수 여부, 설명). 타입은 str, int, bool, date, list, obj",
  ];
  items.forEach((t, i) => {
    const y = 2.6 + i * 1.06;
    numBadge(s, { x: rx + 0.05, y: y + 0.05, n: i + 1 });
    s.addText(t, { x: rx + 0.6, y, w: rw - 0.65, h: 0.95, fontFace: FONT, fontSize: fsMin(16), color: C.ink,
      valign: "top", margin: 0.05 });
  });
}

async function createSlide03() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "설계 개요: 처음 보는 분을 위한 용어 풀이",
    lead: "NL2SQL을 처음 접하는 검토자도 이 설계서를 읽을 수 있도록 용어를 한 줄씩 풀이함" });
  const rows = [["용어", "한 줄 풀이"],
    ["NL2SQL", "사람의 말(자연어) 질문을 LLM이 SQL로 바꾸는 방식"],
    ["정형쿼리", "자주 묻는 조회를 미리 만들어 검증해 둔 고정 SQL. LLM은 ID만 고름"],
    ["뷰(View)", "원본 테이블에서 필요한 컬럼과 기간만 골라 보여 주는 가상 테이블"],
    ["행 수준 보안(RLS)", "같은 테이블이라도 세션에 지정한 회원의 행만 보이게 하는 DB 규칙"],
    ["세션 변수", "한 트랜잭션 동안만 DB에 알려 주는 값. 여기서는 회원ID, 기준일, 거래 제공 시작일"],
    ["최악값", "한 연동이 가장 오래 걸릴 때의 시간. 타임아웃 × (1 + 재시도 횟수)"],
    ["남은 시간 예산", "단계를 시작하기 전에 앞으로 쓸 수 있는 시간을 다시 재는 값"],
    ["착지 단계", "시간이나 재시도를 다 썼을 때 이어서 가는 안전한 단계"]];
  table(s, rows, { w: 10.6, colW: [2.6, 8.0], rowH: 0.62, fontSize: 16, bold0: true });
  const bx = X0 + 10.9, bw = CW - 10.9;
  tintBox(s, { x: bx, y: 1.9, w: bw, h: 5.6 });
  s.addText("읽는 순서", { x: bx + 0.2, y: 2.0, w: bw - 0.4, h: 0.5, fontFace: FONT, fontSize: fsMin(20),
    bold: true, color: C.navy, margin: 0 });
  const order = ["① 흐름", "② 단계", "③ 연동", "④ 반복", "⑤ 합계", "커넥터", "⑥ 실행 중 시간 관리"];
  s.addText(order.map((t, i) => ({ text: t, options: { bullet: { code: "2192" }, breakLine: i < order.length - 1 } })),
    { x: bx + 0.3, y: 2.6, w: bw - 0.5, h: 4.7, fontFace: FONT, fontSize: fsMin(18), color: C.ink, valign: "top",
      paraSpaceAfter: 10 });
}

async function createSlide04() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "목차",
    lead: "설계 가이드의 작성 순서 ① ~ ⑥에 커넥터 설계와 부록을 더해 구성함" });
  const cols = [
    ["흐름", ["① 단계 도출 및 순서 정의", "단계 목록, 흐름 도식, Mermaid", "② 단계별 명세", "S-R1 ~ S-R6"]],
    ["시간", ["③ 외부시스템 연동 명세", "④ 반복 구간 명세", "⑤ 워크플로우 명세", "⑥ 남은 시간 예산 정책"]],
    ["연결과 부록", ["커넥터 설계", "목록, LLM 명세, 프롬프트, 응답 구조", "부록", "뷰와 정형쿼리, SQL 검증 규칙, 필드 영문명, 오류 응답, 설계 점검표, 설계 가정과 위험 항목"]],
  ];
  const w = (CW - 0.6) / 3;
  cols.forEach(([head, lines], i) => {
    const x = X0 + i * (w + 0.3);
    tintBox(s, { x, y: 1.9, w, h: 5.8 });
    numBadge(s, { x: x + 0.25, y: 2.1, n: i + 1, size: 0.55, fontSize: 22 });
    s.addText(head, { x: x + 0.95, y: 2.1, w: w - 1.1, h: 0.55, fontFace: FONT, fontSize: fsMin(24), bold: true,
      color: C.navy, valign: "middle", margin: 0 });
    s.addText(lines.map((t, j) => ({ text: t, options: { bold: !(i !== 1 && j % 2 === 1), color: i !== 1 && j % 2 === 1 ? C.slate : C.ink,
      breakLine: j < lines.length - 1 } })),
      { x: x + 0.25, y: 2.9, w: w - 0.5, h: 4.6, fontFace: FONT, fontSize: fsMin(18), valign: "top", paraSpaceAfter: 12, margin: 0.05 });
  });
}

async function createSlide05() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "① 단계 도출 및 순서 정의: 단계 목록과 흐름 유형",
    lead: "입력 워크플로우의 6단계를 그대로 쓰고, 분기 2곳과 반복 1곳을 둠" });
  darkBadge(s, { x: X0, y: 1.9, w: 2.2, text: "단계 목록" });
  table(s, [["단계ID", "단계명", "담당자 유형"],
    ["S-R1", "검색 요청 접수와 검증", "규칙기반 코드"],
    ["S-R2", "정형쿼리 또는 NL2SQL 판단", "생성형AI + 규칙기반 코드"],
    ["S-R3", "계획 적합성 판정", "규칙기반 코드"],
    ["S-R4", "SQL 검증", "규칙기반 코드"],
    ["S-R5", "SQL 실행", "규칙기반 코드"],
    ["S-R6", "응답 구성과 반환", "규칙기반 코드"]],
  { y: 2.4, w: 6.4, colW: [1.0, 2.9, 2.5], rowH: 0.78, fontSize: 16, bold0: true });
  const rx = X0 + 6.7, rw = CW - 6.7;
  darkBadge(s, { x: rx, y: 1.9, w: 2.2, text: "흐름 유형" });
  table(s, [["흐름 유형", "위치", "판단 이유"],
    ["순차", "S-R1 → S-R2 → S-R3 → S-R4 → S-R5 → S-R6", "앞 단계 출력이 뒤 단계 입력임"],
    ["분기", "S-R3", "계획이 \"답할 수 없음\"이면 SQL 없이 S-R6로 감"],
    ["분기", "S-R4", "통과는 S-R5, 실패는 다시 만들기 또는 오류 종료"],
    ["반복", "L-1(S-R2 ~ S-R4)", "검증 실패 사유를 주고 SQL을 1회 다시 만듦"],
    ["병렬", "없음", "모든 단계가 바로 앞 단계 출력을 써서 동시에 돌릴 단계가 없음"]],
  { x: rx, y: 2.4, w: rw, colW: [1.2, 3.0, rw - 4.2], rowH: 0.92, fontSize: 16, bold0: true });
}

// 흐름 도식 — 그림 파일이 아니라 PowerPoint에서 바로 고칠 수 있는 도형으로 그림
const FLOW_EDGES = [];
function arrow(s, x1, y1, x2, y2, { dash = false, head = true, color = C.navy } = {}) {
  const line = { color, width: 1.75, dashType: dash ? "dash" : "solid" };
  if (head) line.endArrowType = "triangle";
  s.addShape(pptx.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1, line });
}
function edgeLabel(s, text, cx, y, w = 1.3) {
  s.addText(text, { x: cx - w / 2, y, w, h: 0.32, align: "center", valign: "middle", fontFace: FONT,
    fontSize: fsMin(14), color: C.slate, margin: 0 });
}

async function createSlide06() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "① 단계 도출 및 순서 정의: 흐름 도식",
    lead: "LLM은 경로 판단 한 곳에서만 쓰고, SQL은 검증을 통과해야만 DB로 감" });

  // 범례
  const lg = [
    ["LLM 단계", { fill: C.blue, line: C.blue }, pptx.shapes.RECTANGLE],
    ["규칙기반 단계", { fill: C.white, line: C.navy }, pptx.shapes.RECTANGLE],
    ["판정", { fill: C.white, line: C.navy }, pptx.shapes.DIAMOND],
    ["DB 조회", { fill: C.tint, line: C.navy, width: 3 }, pptx.shapes.RECTANGLE],
    ["오류 종료", { fill: C.dark, line: C.dark }, pptx.shapes.RECTANGLE],
  ];
  let lx = X0;
  lg.forEach(([t, st, shp]) => {
    s.addShape(shp, { x: lx, y: 1.93, w: 0.45, h: 0.32, fill: { color: st.fill }, line: { color: st.line, width: st.width || 1.25 } });
    s.addText(t, { x: lx + 0.52, y: 1.9, w: 1.9, h: 0.38, fontFace: FONT, fontSize: fsMin(14), color: C.ink, margin: 0, valign: "middle" });
    lx += 2.45;
  });
  arrow(s, lx, 2.09, lx + 0.6, 2.09, { dash: true });
  s.addText("반복(L-1)", { x: lx + 0.7, y: 1.9, w: 1.6, h: 0.38, fontFace: FONT, fontSize: fsMin(14), color: C.ink, margin: 0, valign: "middle" });

  // 노드 배치
  const cy = 4.25;
  const spec = [
    { id: "T", w: 0.95, h: 0.95, kind: "start", text: "동기\n요청" },
    { id: "S-R1", w: 1.75, h: 1.3, kind: "rule", text: "S-R1\n요청 접수와\n검증" },
    { id: "S-R2", w: 1.75, h: 1.3, kind: "llm", text: "S-R2\n정형쿼리 또는\nNL2SQL 판단" },
    { id: "S-R3", w: 2.1, h: 1.7, kind: "judge", text: "S-R3\n계획 적합성\n판정" },
    { id: "S-R4", w: 2.1, h: 1.7, kind: "judge", text: "S-R4\nSQL 검증" },
    { id: "S-R5", w: 1.75, h: 1.3, kind: "db", text: "S-R5\nSQL 실행" },
    { id: "S-R6", w: 1.75, h: 1.3, kind: "rule", text: "S-R6\n응답 구성과\n반환" },
  ];
  const gap = (CW - spec.reduce((a, n) => a + n.w, 0)) / (spec.length - 1);
  let x = X0;
  const N = {};
  const STYLE = {
    start: { shape: pptx.shapes.OVAL, fill: C.navy, line: C.navy, color: C.white, width: 1.25 },
    rule: { shape: pptx.shapes.RECTANGLE, fill: C.white, line: C.navy, color: C.ink, width: 1.5 },
    llm: { shape: pptx.shapes.RECTANGLE, fill: C.blue, line: C.blue, color: C.white, width: 1.5 },
    judge: { shape: pptx.shapes.DIAMOND, fill: C.white, line: C.navy, color: C.ink, width: 1.5 },
    db: { shape: pptx.shapes.RECTANGLE, fill: C.tint, line: C.navy, color: C.ink, width: 3 },
  };
  for (const n of spec) {
    n.x = x; n.cx = x + n.w / 2; n.top = cy - n.h / 2; n.bot = cy + n.h / 2; n.right = x + n.w;
    N[n.id] = n; x += n.w + gap;
    const st = STYLE[n.kind];
    s.addShape(st.shape, { x: n.x, y: n.top, w: n.w, h: n.h, fill: { color: st.fill }, line: { color: st.line, width: st.width } });
    s.addText(n.text, { x: n.x, y: n.top, w: n.w, h: n.h, align: "center", valign: "middle", fontFace: FONT,
      fontSize: fsMin(14), bold: n.kind === "start", color: st.color, margin: 0 });
  }
  const link = (a, b) => { if (a.startsWith("S-R") && b.startsWith("S-R")) FLOW_EDGES.push([a, b]); };

  // 가로 연결
  const main = [["T", "S-R1", ""], ["S-R1", "S-R2", ""], ["S-R2", "S-R3", ""], ["S-R3", "S-R4", "검증 대상"],
    ["S-R4", "S-R5", "통과"], ["S-R5", "S-R6", "성공"]];
  for (const [a, b, label] of main) {
    arrow(s, N[a].right, cy, N[b].x, cy);
    if (label) edgeLabel(s, label, (N[a].right + N[b].x) / 2, cy - 0.5, 1.1);
    link(a, b);
  }
  // S-R3 → S-R6 (답할 수 없음): 위로 돌아감
  const topY = 2.85;
  arrow(s, N["S-R3"].cx, N["S-R3"].top, N["S-R3"].cx, topY, { head: false });
  arrow(s, N["S-R3"].cx, topY, N["S-R6"].cx, topY, { head: false });
  arrow(s, N["S-R6"].cx, topY, N["S-R6"].cx, N["S-R6"].top);
  edgeLabel(s, "답할 수 없음(SQL 없이 응답)", (N["S-R3"].cx + N["S-R6"].cx) / 2, topY - 0.36, 3.6);
  link("S-R3", "S-R6");
  // S-R4 → S-R2 (L-1 다시 만들기): 아래로 돌아감, 점선
  const loopY = 5.6, r2in = N["S-R2"].cx + 0.35;
  arrow(s, N["S-R4"].cx, N["S-R4"].bot, N["S-R4"].cx, loopY, { dash: true, head: false });
  arrow(s, N["S-R4"].cx, loopY, r2in, loopY, { dash: true, head: false });
  arrow(s, r2in, loopY, r2in, N["S-R2"].bot, { dash: true });
  edgeLabel(s, "실패 1회차: 실패 사유를 주고 다시 만듦(L-1)", (r2in + N["S-R4"].cx) / 2, loopY + 0.05, 5.0);
  link("S-R4", "S-R2");

  // 오류 종료 막대와 연결
  const barY = 6.75, barX = N["S-R1"].x, barW = N["S-R5"].right - N["S-R1"].x;
  s.addShape(pptx.shapes.RECTANGLE, { x: barX, y: barY, w: barW, h: 0.5, fill: { color: C.dark }, line: { color: C.dark, width: 1 } });
  s.addText("오류 종료(오류 코드와 안내 문구로 응답)", { x: barX, y: barY, w: barW, h: 0.5, align: "center", valign: "middle",
    fontFace: FONT, fontSize: fsMin(15), bold: true, color: C.white, margin: 0 });
  // S-R4 마름모 오른쪽 아래 변 위의 점에서 내려감(아래 꼭짓점은 반복 화살표가 씀)
  const r4dx = 0.55, r4y = cy + (N["S-R4"].h / 2) * (1 - r4dx / (N["S-R4"].w / 2));
  const errs = [
    [N["S-R1"].cx, N["S-R1"].bot, "요청 오류"],
    [N["S-R2"].cx - 0.35, N["S-R2"].bot, "LLM 실패, 대체 불가"],
    [N["S-R4"].cx + r4dx, r4y, "실패 2회차"],
    [N["S-R5"].cx, N["S-R5"].bot, "실행 실패"],
  ];
  for (const [ex, ey, label] of errs) {
    arrow(s, ex, ey, ex, barY, { color: C.dark });
    s.addText(label, { x: ex + 0.06, y: barY - 0.42, w: 2.3, h: 0.34, fontFace: FONT, fontSize: fsMin(14),
      color: C.slate, margin: 0, valign: "middle" });
  }
  s.addText("모든 단계는 시작 전에 ⑥ 남은 시간 예산을 확인하고, 기준에 못 미치면 착지 단계로 감",
    { x: X0, y: 7.45, w: CW, h: 0.4, fontFace: FONT, fontSize: fsMin(15), color: C.slate, margin: 0, valign: "middle" });
  fs.writeFileSync(path.join(__dirname, "flow_edges.json"), JSON.stringify(FLOW_EDGES));
}

async function createSlide07() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "① 단계 도출 및 순서 정의: Mermaid 도식 스크립트",
    lead: "같은 흐름을 Mermaid 스크립트로도 남겨 누구나 다시 그릴 수 있게 함" });
  const code = SCRIPT.match(/```mermaid\n([\s\S]*?)```/)[1].trimEnd();
  tintBox(s, { x: X0, y: 1.9, w: 10.4, h: 5.95, fill: C.altRow });
  s.addText(code, { x: X0 + 0.2, y: 2.0, w: 10.0, h: 5.75, fontFace: FONT, fontSize: fsMin(15), color: C.ink,
    valign: "top", margin: 0.05, paraSpaceAfter: 2 });
  const rx = X0 + 10.7, rw = CW - 10.7;
  headerBar(s, { x: rx, y: 1.9, w: rw, text: "보는 방법", accent: true });
  const steps = ["mermaid.live/edit 접속", "왼쪽 편집 창에 스크립트 붙여 넣기", "오른쪽 위 전체보기 아이콘을 눌러 봄"];
  steps.forEach((t, i) => {
    numBadge(s, { x: rx + 0.1, y: 2.7 + i * 1.0, n: i + 1 });
    s.addText(t, { x: rx + 0.65, y: 2.62 + i * 1.0, w: rw - 0.7, h: 0.8, fontFace: FONT, fontSize: fsMin(16),
      color: C.ink, valign: "top", margin: 0.03 });
  });
  callout(s, { x: rx, y: 6.0, w: rw, h: 1.5, text: "노드 R1 ~ R6은 단계 S-R1 ~ S-R6, 점선은 반복 구간 L-1임", fontSize: 15 });
}

// ② 단계별 명세 — 스크립트의 11개 항목 표를 한 장의 표(칸 합치기)로 옮김
function stepSpecSlide(sid) {
  const heading = SCRIPT.match(new RegExp(`## 슬라이드 \\d+\\. ② 단계별 명세: ${sid}[^\\n]*`))[0];
  const rows = mdTable(heading).slice(1);
  const v = Object.fromEntries(rows.map(([k, val]) => [k, val]));
  const lead = SCRIPT.slice(SCRIPT.indexOf(heading)).match(/- 리드문: (.*)/)[1];
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: `② 단계별 명세: ${sid} ${v["단계명"]}`, lead });
  const L = (t, colspan = 1) => ({ text: t, options: { colspan, fill: { color: C.navy }, color: C.white, bold: true,
    fontSize: fsMin(15), align: "center" } });
  const V = (t, colspan = 1, fill = C.white) => ({ text: t, options: { colspan, fill: { color: fill }, color: C.body,
    fontSize: fsMin(14), valign: "top" } });
  const lines = (t, sep) => t.split(sep).map((x) => x.trim()).filter(Boolean).join("\n");
  const tasks = v["수행 작업"].split(/\s(?=\d+\.\s)/).join("\n");
  const grid = [
    [L("단계ID"), L("단계명"), L("이전 단계", 2), L("담당자 유형"), L("외부시스템")],
    [V(v["단계ID"]), V(v["단계명"]), V(v["이전 단계"], 2), V(v["담당자 유형"]), V(v["외부시스템"])],
    [L("비즈니스 목표"), V(v["비즈니스 목표"], 5, C.tint)],
    [L("입력 데이터", 2), L("수행 작업", 2), L("출력 데이터", 2)],
    [V(lines(v["입력 데이터"], " / "), 2), V(tasks, 2), V(lines(v["출력 데이터"], " / "), 2)],
    [L("예외 처리", 3), L("비고", 3)],
    [V(lines(v["예외 처리"], " / "), 3, C.altRow), V(v["비고"], 3, C.altRow)],
  ];
  s.addTable(grid, { x: X0, y: 1.9, w: CW, colW: Array(6).fill(CW / 6), fontFace: FONT, fontSize: fsMin(14),
    rowH: [0.36, 0.62, 0.5, 0.36, 3.05, 0.36, 0.72], valign: "middle", margin: [0.04, 0.08, 0.04, 0.08],
    border: { type: "solid", color: C.border, pt: 1 }, autoPage: false });
}
async function createSlide08() { stepSpecSlide("S-R1"); }
async function createSlide09() { stepSpecSlide("S-R2"); }
async function createSlide10() { stepSpecSlide("S-R3"); }
async function createSlide11() { stepSpecSlide("S-R4"); }
async function createSlide12() { stepSpecSlide("S-R5"); }
async function createSlide13() { stepSpecSlide("S-R6"); }

async function createSlide14() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "③ 외부시스템 연동 명세", lead: "바깥으로 나가는 연동은 Groq LLM 하나뿐이며, 최악값은 12초임" });
  table(s, mdTable("## 슬라이드 14."), { colW: [1.0, 1.4, 1.1, 1.1, 1.1, 0.9, 2.4, 5.9], rowH: 0.5, fontSize: 15 });
  const cards = [
    ["1 부분결과로 계속", "해당 안 됨", "경로와 SQL이 없으면 낼 결과가 없음", C.dark],
    ["2 대체 경로로 계속", "채택", "정형쿼리 14개의 키워드 표로 규칙 매칭하면 LLM 없이도 자주 묻는 질문은 답함", C.blue],
    ["3 안전 종료", "키워드가 맞지 않을 때만", "LLM_UNAVAILABLE(503) \"잠시 후 다시 시도해 주세요\"", C.navy],
  ];
  const w = (CW - 0.6) / 3;
  cards.forEach(([h, verdict, why, color], i) => {
    const x = X0 + i * (w + 0.3);
    s.addShape(pptx.shapes.ROUNDED_RECTANGLE, { x, y: 3.15, w, h: 0.5, rectRadius: 0.06, fill: { color }, line: { type: "none" } });
    s.addText(h, { x, y: 3.15, w, h: 0.5, align: "center", valign: "middle", fontFace: FONT, fontSize: fsMin(18), bold: true, color: C.white, margin: 0 });
    tintBox(s, { x, y: 3.7, w, h: 2.0 });
    s.addText([{ text: verdict, options: { bold: true, color: C.navy, breakLine: true } }, { text: why, options: { color: C.body } }],
      { x: x + 0.15, y: 3.8, w: w - 0.3, h: 1.8, fontFace: FONT, fontSize: fsMin(16), valign: "top", paraSpaceAfter: 6, margin: 0.03 });
  });
  callout(s, { x: X0, y: 5.95, w: CW, h: 1.2, fontSize: 15,
    text: "판단 이유: 타임아웃 12초는 최대 출력 5000토큰 ÷ 약 500토큰/초 ≈ 10초에 여유 2초를 더한 설계 가정. 재시도 0회는 다시 만들기(L-1)와 합쳐 30초를 넘지 않게 하려는 사용자 결정" });
  s.addText("DB는 시스템 내부 구성요소라 이 표에 넣지 않음", { x: X0, y: 7.35, w: CW, h: 0.4, fontFace: FONT, fontSize: fsMin(15), color: C.slate, margin: 0 });
  sourceLine(s, "출처: Groq Models, Reasoning 문서(2026-10-15 조사), work/decisions.json D-05");
}

async function createSlide15() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "④ 반복 구간 명세", lead: "SQL 검증에 실패하면 실패 사유를 LLM에 주고 한 번만 다시 만듦" });
  table(s, mdTable("## 슬라이드 15."), { colW: [1.4, 3.0, 1.5, 0.9, 3.3, 4.8], rowH: 0.6, fontSize: 15 });
  const half = (CW - 0.3) / 2;
  headerBar(s, { x: X0, y: 3.45, w: half, text: "최악값 계산" });
  tintBox(s, { x: X0, y: 4.05, w: half, h: 3.3 });
  bullets(s, ["S-R2 단계 최악값 12초(C-01 타임아웃 12초 × (1 + 0))", "S-R3, S-R4는 외부 연동 없음 → 0초",
    { text: "구간 최악값 = (12 + 0 + 0) × (1 + 1) = 24초", bold: true }],
  { x: X0 + 0.15, y: 4.2, w: half - 0.3, h: 3.0, fontSize: 17 });
  const rx = X0 + half + 0.3;
  headerBar(s, { x: rx, y: 3.45, w: half, text: "착지 단계 판단 이유", accent: true });
  tintBox(s, { x: rx, y: 4.05, w: half, h: 3.3 });
  bullets(s, ["부분결과: 없음(실행할 SQL이 없음)",
    "대체 경로(키워드 매칭): LLM이 이미 nl2sql로 판단한 질문이라 맞지 않는 정형쿼리를 고를 위험이 있어 쓰지 않음",
    { text: "결론: 안전 종료(SQL_VALIDATION_FAILED 422)", bold: true }],
  { x: rx + 0.15, y: 4.2, w: half - 0.3, h: 3.0, fontSize: 17 });
  sourceLine(s, "출처: 설계 가이드 1-4, work/decisions.json D-08");
}

async function createSlide16() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "⑤ 워크플로우 명세", lead: "최악값 합계 24초로 전체 시간 예산 30초 안에 들고, 남는 5초는 DB와 규칙 처리 몫임" });
  const lw = 8.2;
  table(s, mdTable("## 슬라이드 16."), { w: lw, colW: [2.0, lw - 2.0], rowH: 0.74, fontSize: 15, bold0: true });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  headerBar(s, { x: rx, y: 1.9, w: rw, text: "최악값 합계 계산과 예산 대조", accent: true });
  tintBox(s, { x: rx, y: 2.5, w: rw, h: 5.35 });
  bullets(s, [
    "분기 비교: SQL 실행 경로(S-R3 → S-R4 → S-R5 → S-R6)가 답할 수 없음 경로(S-R3 → S-R6)보다 길어 이 경로를 더함",
    "반복 구간 단계(S-R2 ~ S-R4)는 따로 더하지 않고 L-1 24초로 한 번만 더함",
    { text: "예산 대조: 24초 ≤ 30초 → 통과. 조정 없음", bold: true },
    "여유: 30 - 24 - 1(종료 처리) = 5초 → DB 조회(S-R1 회원 확인, S-R4 EXPLAIN, S-R5 실행)와 규칙 처리 몫. 개발 후 실측으로 확인할 항목",
  ], { x: rx + 0.15, y: 2.6, w: rw - 0.3, h: 5.15, fontSize: 16 });
  sourceLine(s, "출처: 설계 가이드 1-5, work/decisions.json D-02");
}

async function createSlide17() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "커넥터 설계: 커넥터 목록과 LLM 명세",
    lead: "커넥터는 Groq LLM 하나이며, 접속 주소와 설정값은 모두 Groq 공식 문서 조사값임" });
  table(s, mdTable("## 슬라이드 17.", 0), { colW: [1.5, 6.0, 3.0, 4.4], rowH: 0.42, fontSize: 15 });
  s.addText("DB(PostgreSQL cardlab)는 시스템 내부 구성요소로 취급해 커넥터 목록에서 제외함(사용자 결정)",
    { x: X0, y: 2.78, w: CW, h: 0.36, fontFace: FONT, fontSize: fsMin(15), color: C.slate, margin: 0 });
  table(s, mdTable("## 슬라이드 17.", 1), { y: 3.25, colW: [2.2, CW - 2.2], rowH: 0.56, fontSize: 15, bold0: true });
  sourceLine(s, "출처: console.groq.com/docs (openai, models, api-reference, reasoning, structured-outputs), context7 groq-python, 2026-10-15");
}

async function createSlide18() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "커넥터 설계: 시스템 프롬프트와 유저 프롬프트",
    lead: "시스템 프롬프트는 프롬프트 가이드 8섹션으로 쓰고, 전문은 스크립트 부록에 둠" });
  const lw = 8.0;
  headerBar(s, { x: X0, y: 1.9, w: lw, text: "시스템 프롬프트(섹션별 요약)" });
  table(s, [["섹션", "요약"],
    ["[목표]", "질문에 맞는 조회 경로를 고르고, 필요할 때만 허용 뷰로 읽기 SQL 1개를 만듦"],
    ["[역할]", "카드사 상담 데이터에 익숙한 PostgreSQL NL2SQL 전문가"],
    ["[맥락]", "회원 범위와 기간은 DB가 세션 변수로 이미 걸러 둠. SQL에 회원 조건을 쓰지 않음"],
    ["[입력]", "가린 질문, 기준일, 거래 제공 시작일, 정형쿼리 목록, 허용 뷰와 컬럼, 검증 실패 사유"],
    ["[처리]", "정형쿼리 우선 → 없으면 SQL 생성 → 데이터로 답할 수 없으면 unanswerable"],
    ["[출력]", "JSON 5개 필드(route, fixed_query_id, sql, used_views, reason)"],
    ["[제약조건]", "SELECT 1문장, 허용 뷰와 함수만, LIMIT 200 이하, 개인정보 추측 금지"],
    ["[예시]", "질문 3개에 대한 fixed, nl2sql, unanswerable 응답 예"]],
  { y: 2.5, w: lw, colW: [1.5, lw - 1.5], rowH: 0.6, fontSize: 14, bold0: true });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  headerBar(s, { x: rx, y: 1.9, w: rw, text: "유저 프롬프트 변수", accent: true });
  table(s, [["변수", "타입", "필수", "설명"],
    ["masked_question", "str", "필수", "개인 식별자를 가린 질문"],
    ["base_date", "date", "필수", "조회 기준일"],
    ["coverage_start", "date", "필수", "거래 제공 시작일"],
    ["fixed_query_catalog", "list", "필수", "정형쿼리 ID, 이름, 설명"],
    ["view_catalog", "list", "필수", "허용 뷰, 컬럼, 타입, 설명"],
    ["row_limit", "int", "필수", "결과 행 상한 200"],
    ["validation_feedback", "obj", "선택", "다시 만들 때 실패 사유와 이전 SQL"]],
  { x: rx, y: 2.5, w: rw, colW: [2.35, 0.75, 0.75, rw - 3.85], rowH: 0.68, fontSize: 14 });
}

async function createSlide19() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "커넥터 설계: 응답 데이터 구조",
    lead: "응답은 JSON 스키마 엄격 모드로 받아, 형식이 틀린 답이 다음 단계로 가지 않게 함" });
  const lw = 9.2;
  darkBadge(s, { x: X0, y: 1.9, w: 2.6, text: "C-01 응답 필드" });
  table(s, mdTable("## 슬라이드 19."), { y: 2.4, w: lw, colW: [2.0, 2.3, lw - 4.3], rowH: 0.78, fontSize: 15, bold0: true });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  tintBox(s, { x: rx, y: 1.9, w: rw, h: 5.6 });
  const rules = ["모든 필드 required, additionalProperties: false(strict 모드 요구 사항)",
    "선택 값은 [\"string\", \"null\"] 합 타입으로 표현", "스키마가 맞아도 내용 판정은 S-R3, S-R4가 다시 함",
    "응답 메타데이터의 토큰 사용량은 감사 로그에 남김"];
  rules.forEach((t, i) => {
    numBadge(s, { x: rx + 0.2, y: 2.15 + i * 1.3, n: i + 1 });
    s.addText(t, { x: rx + 0.75, y: 2.08 + i * 1.3, w: rw - 0.9, h: 1.15, fontFace: FONT, fontSize: fsMin(16), color: C.ink, valign: "top", margin: 0.03 });
  });
  sourceLine(s, "출처: console.groq.com/docs/structured-outputs (2026-10-15 조사)");
}

async function createSlide20() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "⑥ 남은 시간 예산 정책: 측정과 계산",
    lead: "각 단계 시작 직전에 실제로 흐른 시간을 재고, 남은 시간 예산이 1.5초 이상일 때만 시작함" });
  const lw = 8.4;
  table(s, mdTable("## 슬라이드 20."), { w: lw, colW: [2.4, lw - 2.4], rowH: 0.78, fontSize: 15, bold0: true });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  headerBar(s, { x: rx, y: 1.9, w: rw, text: "계산 예", accent: true });
  const ex = [
    ["예 1  S-R2 2회차 시작", "사용 13초 → 남은 시간 30 - 13 - 1 = 16초\n남은 시간 예산 16 - 12 = 4초 ≥ 1.5초 → 시작"],
    ["예 2  S-R2 2회차 시작", "사용 16초 → 남은 시간 30 - 16 - 1 = 13초\n남은 시간 예산 13 - 12 = 1초 < 1.5초 → 착지(안전 종료)"],
    ["예 3  S-R5 시작", "사용 26초 → 남은 시간 30 - 26 - 1 = 3초\n남은 시간 예산 3 - 0 = 3초 ≥ 1.5초 → 시작\nstatement_timeout = min(3초, 5초) = 3초"],
  ];
  let y = 2.5;
  ex.forEach(([h, body], i) => {
    const hh = i === 2 ? 1.95 : 1.6;
    tintBox(s, { x: rx, y, w: rw, h: hh });
    s.addText([{ text: h, options: { bold: true, color: C.navy, breakLine: true } }, { text: body, options: { color: C.body } }],
      { x: rx + 0.15, y: y + 0.05, w: rw - 0.3, h: hh - 0.1, fontFace: FONT, fontSize: fsMin(15), valign: "top", margin: 0.03, paraSpaceAfter: 4 });
    y += hh + 0.12;
  });
  sourceLine(s, "출처: 설계 가이드 2-1 ~ 2-3");
}

async function createSlide21() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "⑥ 남은 시간 예산 정책: 기준 미달 시 착지 단계",
    lead: "기준에 못 미치면 부분결과 → 대체 경로 → 안전 종료 순서로 검토해 단계마다 착지 단계를 정함" });
  table(s, mdTable("## 슬라이드 21."), { colW: [1.8, 6.0, 7.1], rowH: 0.74, fontSize: 15, bold0: true });
}

async function createSlide22() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 A: 논리 뷰 목록",
    lead: "NL2SQL 실행 계정이 읽을 수 있는 뷰는 14개이며, LLM에는 app 스키마 12개만 보여 줌(기본 7개와 3조 추가 5개)" });
  const lw = 11.0;
  table(s, mdTable("## 슬라이드 22."), { w: lw, colW: [3.5, 3.1, 2.6, 1.8], rowH: 0.56, fontSize: 14 });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  tintBox(s, { x: rx, y: 1.9, w: rw, h: 5.95 });
  s.addText("권한 요약", { x: rx + 0.15, y: 2.0, w: rw - 0.3, h: 0.45, fontFace: FONT, fontSize: fsMin(18), bold: true, color: C.navy, margin: 0 });
  bullets(s, ["RLS: member, card, card_txn, delinquency 테이블에 회원 격리 정책(app.member_id)",
    "세션 변수 3개(app.member_id, app.base_date, app.coverage_start)를 지정하지 않으면 0행(기본 거부)",
    "원본 테이블 중 sql_retriever_user가 읽는 것은 public.lab_metadata 하나"],
  { x: rx + 0.1, y: 2.5, w: rw - 0.2, h: 5.2, fontSize: 15 });
  sourceLine(s, "출처: rdb/init/04 ~ 06 SQL, work/db_catalog.json(2026-10-15 실측). 3조 추가 뷰 5개는 다음 장");
}

async function createSlide23() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 B: 정형쿼리 목록",
    lead: "정형쿼리 14개 중 FQ-01 ~ FQ-09는 EXPLAIN을 통과함. FQ-10 ~ FQ-14(3조 추가)는 DB 미실행으로 확인 전임" });
  table(s, mdTable("## 슬라이드 23."), { colW: [1.6, 3.8, 3.2, 6.3], rowH: 0.56, fontSize: 15, bold0: true });
  s.addText("전체 SQL은 work/fixed_queries.json, 확인 로그는 work/explain_fixed_queries.log",
    { x: X0, y: 7.55, w: CW, h: 0.38, fontFace: FONT, fontSize: fsMin(15), color: C.slate, margin: 0 });
  sourceLine(s, "출처: work/explain_fixed_queries.log (sql_retriever_user, FQ-01 ~ FQ-09 9/9 통과). FQ-10 ~ FQ-14는 다음 장");
}


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

async function createSlide24() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 C: SQL 검증 규칙", lead: "허용 목록에 있는 것만 통과시키는 방식(기본 거부)으로 SQL을 검사함" });
  const half = (CW - 0.3) / 2;
  headerBar(s, { x: X0, y: 1.9, w: half, text: "허용" });
  tintBox(s, { x: X0, y: 2.5, w: half, h: 4.4 });
  bullets(s, ["허용 뷰: app 스키마 뷰 12개와 그 컬럼 전부",
    "허용 구문: SELECT 1문장, WITH, WHERE, JOIN(허용 뷰끼리), GROUP BY, HAVING, ORDER BY, LIMIT, CASE",
    "허용 함수: sum, count, avg, min, max, date_trunc, to_char, extract, coalesce, round, greatest, least, abs, nullif",
    "결과 행 상한: 200(검증 단계에서 LIMIT 201로 강제, 201행째는 잘림 표시에만 씀)"],
  { x: X0 + 0.1, y: 2.6, w: half - 0.2, h: 4.2, fontSize: 16 });
  const rx = X0 + half + 0.3;
  headerBar(s, { x: rx, y: 1.9, w: half, text: "금지", accent: true });
  tintBox(s, { x: rx, y: 2.5, w: half, h: 4.4 });
  bullets(s, ["쓰기와 정의 구문: INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, TRUNCATE, GRANT, REVOKE, COPY, SET, CALL, DO",
    "여러 문장(세미콜론), 주석(--, /* */), SELECT INTO, FOR UPDATE",
    "스키마: app_internal, public, private, pg_catalog, information_schema",
    "함수: set_config, current_setting, pg_sleep, generate_series, 허용 목록 밖의 모든 함수"],
  { x: rx + 0.1, y: 2.6, w: half - 0.2, h: 4.2, fontSize: 16 });
  callout(s, { x: X0, y: 7.1, w: CW, h: 0.7, text: "검증을 통과해도 실행은 읽기 전용 트랜잭션과 RLS 안에서만 함(이중 방어)", fontSize: 17 });
}

async function createSlide25() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 D: 필드 영문명",
    lead: "호출자와 주고받는 필드 이름을 하나로 고정해 구현과 시험이 같은 이름을 쓰게 함" });
  const lw = 6.0;
  darkBadge(s, { x: X0, y: 1.9, w: 2.2, text: "요청 필드" });
  table(s, [["영문명", "한글명", "타입"], ["request_id", "요청 추적 ID", "str"], ["member_id", "회원ID", "str"],
    ["question", "상담사 질문", "str"], ["base_date", "조회 기준일", "date"]],
  { y: 2.4, w: lw, colW: [2.2, 2.6, 1.2], rowH: 0.56, fontSize: 15, bold0: true });
  const rx = X0 + lw + 0.3, rw = CW - lw - 0.3;
  darkBadge(s, { x: rx, y: 1.9, w: 2.2, text: "응답 필드" });
  table(s, [["영문명", "한글명", "타입"], ["request_id", "요청 추적 ID", "str"],
    ["status", "처리 결과(ok, unanswerable, error)", "str"], ["route", "조회 경로(fixed, nl2sql, none)", "str"],
    ["fixed_query_id", "고정 조회ID", "str"], ["period", "조회 기간(base_date, coverage_start)", "obj"],
    ["columns / rows", "컬럼 목록 / 결과 행", "list"], ["row_count / truncated", "행 수 / 잘림 여부", "int / bool"],
    ["message", "안내 문구", "str"], ["error", "오류(code, message)", "obj"], ["elapsed_ms", "처리 시간(밀리초)", "int"]],
  { x: rx, y: 2.4, w: rw, colW: [2.9, 4.2, rw - 7.1], rowH: 0.5, fontSize: 15, bold0: true });
}

async function createSlide26() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 E: 오류 응답",
    lead: "오류 메시지에는 SQL, DB 식별자, 접속 정보, 키를 넣지 않고 다음 행동만 안내함" });
  table(s, mdTable("## 슬라이드 26."), { colW: [3.0, 1.3, 2.4, 4.0, 4.2], rowH: 0.56, fontSize: 16, bold0: true });
  s.addText("오류 응답 형식: request_id, status(error), error(code, message), elapsed_ms",
    { x: X0, y: 7.5, w: CW, h: 0.4, fontFace: FONT, fontSize: fsMin(16), color: C.slate, margin: 0 });
}

async function createSlide27() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 F: 설계 점검표", lead: "설계 가이드 5절 점검표와 이 설계서의 완료 기준을 모두 확인함" });
  table(s, mdTable("## 슬라이드 27."), { colW: [11.4, 3.5], rowH: 0.46, fontSize: 15 });
}

async function createSlide28() {
  const s = pptx.addSlide({ masterName: LAYOUT });
  pageHeader(s, { title: "부록 G: 설계 가정과 위험 항목", lead: "근거 없는 수치는 설계 가정으로 두고, 개발 후 실측으로 확인함" });
  const half = (CW - 0.3) / 2;
  headerBar(s, { x: X0, y: 1.9, w: half, text: "설계 가정(실측 항목)" });
  tintBox(s, { x: X0, y: 2.5, w: half, h: 5.4 });
  bullets(s, ["LLM 타임아웃 12초(최대 출력 5000토큰을 약 500토큰/초로 나눈 값 + 여유)",
    "DB 문장 상한 5초, DB와 규칙 처리 몫 5초(30 - 24 - 1)", "시작 기준 비율 5%(1.5초)",
    "회원ID 형식 M- + 숫자 4자리, txn_period 값에서 시작일을 꺼내는 방식",
    "temperature 0.1에서 반복 출력이 없는지(Groq 권장 0.5 ~ 0.7)",
    "Groq 요청 한도(문서끼리 값이 달라 조직 한도 페이지 확인 필요)",
    "3조 이탈 신호 기준(전월 대비, 연 환산 배수, 최근 30일 비교)은 상담 현장 기준으로 확인"],
  { x: X0 + 0.1, y: 2.6, w: half - 0.2, h: 5.2, fontSize: 15, numbered: true });
  const rx = X0 + half + 0.3;
  headerBar(s, { x: rx, y: 1.9, w: half, text: "위험 항목", accent: true });
  tintBox(s, { x: rx, y: 2.5, w: half, h: 5.4 });
  bullets(s, ["DB 구조 읽기를 관리자 계정 cardlab으로 함(사용자 결정). 읽기 전용 세션, LIMIT 0과 EXPLAIN만 사용",
    "원본 테이블 읽기: sql_retriever_user는 public.lab_metadata만 읽음(위험 낮음). cardlab은 전부 읽음",
    "app_internal 뷰 2개도 실행 계정이 읽을 수 있음 → SQL 검증에서 스키마 금지로 막음",
    "이름 같은 개인 식별자는 정규식으로 못 가림 → 외부 LLM 전송 위험",
    "customer_daily_usage의 EXPLAIN 예상 비용이 큼 → 실행 시간 실측 필요",
    "3조 추가 뷰 5개와 FQ-10 ~ FQ-14는 DB 미실행 → 팀원 PC에서 EXPLAIN과 접근 권한 확인"],
  { x: rx + 0.1, y: 2.6, w: half - 0.2, h: 5.2, fontSize: 15, numbered: true });
}

// 6-11 진입점
async function main() {
  pptx = new pptxgen();
  pptx.defineLayout({ name: "CUSTOM", width: 16, height: 9 });
  pptx.layout = "CUSTOM";
  pptx.title = "SQL 검색기 워크플로우 설계서";
  defineContentLayout();
  const fns = [createSlide01, createSlide02, createSlide03, createSlide04, createSlide05, createSlide06, createSlide07,
    createSlide08, createSlide09, createSlide10, createSlide11, createSlide12, createSlide13, createSlide14,
    createSlide15, createSlide16, createSlide17, createSlide18, createSlide19, createSlide20, createSlide21,
    createSlide22, createSlide22b, createSlide23, createSlide23b, createSlide24, createSlide25, createSlide26, createSlide27, createSlide28];
  for (const fn of fns) await fn();
  await pptx.writeFile({ fileName: OUT });
  console.log("✅ PPT 생성 완료:", path.relative(process.cwd(), OUT), `(${fns.length}장)`);
}

main().catch((e) => { console.error("❌ PPT 생성 실패:", e); process.exit(1); });
