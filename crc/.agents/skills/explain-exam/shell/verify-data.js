/*
 * data.js 검증 게이트 (Node 실행)
 *
 * 사용법:  node verify-data.js <예제 data.js 경로>
 * 예)      node verify-data.js ../09.langchain/claude/explain/data.js
 *
 * 검사 항목 (하나라도 실패하면 exit 1):
 *   1) 스키마: meta.title/entry, files[], flow[], functions[], glossary{} 존재
 *   2) functions[].fileId 가 files[].id 중 하나와 일치
 *   3) functions[].terms[] 가 glossary 키와 일치
 *   4) functions[].lines[].at(앵커) 가 code 안에서 "정확히 한 줄"과 매칭
 *        - 0개 매칭(앵커 오타) 또는 2개 이상 매칭(모호함) → 오류
 *        - 이 검사가 "줄 번호 어긋남" 버그를 원천 차단함
 *   5) flow[] 각 항목에 step/title/summary/detail 존재
 *   6) flow[].refs(선택 필드) 가 있으면 각 id 가 functions[].id 에 존재
 *        - 처리 흐름↔함수 바로가기 링크의 무결성 보장(없으면 통과 = 하위호환)
 *   7) lang(선택 필드)이 있으면 셸이 아는 언어인지 확인(모르면 경고 = generic 규칙으로 강조됨)
 */
"use strict";

var path = require("path");

var target = process.argv[2];
if (!target) {
  console.error("사용법: node verify-data.js <data.js 경로>");
  process.exit(2);
}
var abs = path.resolve(process.cwd(), target);

var errors = [];
var warns = [];
function err(msg) { errors.push(msg); }
function warn(msg) { warns.push(msg); }

// data.js 로드 (window 전역 셈)
global.window = {};
try {
  require(abs);
} catch (e) {
  console.error("[로드 실패] " + abs + "\n  " + e.message);
  process.exit(1);
}
var D = global.window.EXPLAIN_DATA;

if (!D || typeof D !== "object") {
  console.error("[치명] window.EXPLAIN_DATA 가 정의되지 않음: " + abs);
  process.exit(1);
}

// 1) 스키마
if (!D.meta || !D.meta.title) err("meta.title 누락");
if (!D.meta || !D.meta.entry) warn("meta.entry 누락(권장)");
if (!Array.isArray(D.files) || !D.files.length) err("files[] 누락 또는 비어 있음");
if (!Array.isArray(D.flow) || !D.flow.length) err("flow[] 누락 또는 비어 있음");
if (!Array.isArray(D.functions) || !D.functions.length) err("functions[] 누락 또는 비어 있음");
if (!D.glossary || typeof D.glossary !== "object") err("glossary{} 누락");

var fileIds = {};
(D.files || []).forEach(function (f, i) {
  if (!f.id) err("files[" + i + "].id 누락");
  if (!f.label) err("files[" + i + "].label 누락");
  if (f.id) fileIds[f.id] = true;
});

var glossKeys = D.glossary || {};

// 7) lang(선택 필드) — 셸 assets/app.js 의 LANG_SYN 과 같은 목록
var KNOWN_LANGS = {};
("python javascript typescript java kotlin scala swift csharp dart go rust c cpp php ruby " +
 "sql bash powershell r yaml json").split(" ").forEach(function (l) { KNOWN_LANGS[l] = true; });

function checkLang(val, where) {
  if (val === undefined || val === null || val === "") return;
  if (typeof val !== "string") { err(where + " 는 문자열이어야 함"); return; }
  if (!KNOWN_LANGS[val.toLowerCase()]) {
    warn(where + " '" + val + "' 는 셸이 모르는 언어(generic 규칙으로 강조됨). 오타인지 확인");
  }
}

checkLang(D.meta && D.meta.lang, "meta.lang");
(D.files || []).forEach(function (f, i) { checkLang(f.lang, "files[" + i + "].lang"); });

// 5) flow
(D.flow || []).forEach(function (s, i) {
  ["step", "title", "summary", "detail"].forEach(function (k) {
    if (s[k] === undefined || s[k] === null || s[k] === "") err("flow[" + i + "]." + k + " 누락");
  });
});

// 2~4) functions
var annTotal = 0, fileUsed = {}, fnIds = {};
(D.functions || []).forEach(function (fn, i) {
  var tag = "functions[" + i + "]" + (fn.id ? "(" + fn.id + ")" : "");
  if (!fn.id) err(tag + ".id 누락");
  else fnIds[fn.id] = true;
  if (!fn.name) err(tag + ".name 누락");
  if (!fn.code) err(tag + ".code 누락");
  if (!fn.summary) warn(tag + ".summary 누락(권장)");
  checkLang(fn.lang, tag + ".lang");

  // 2) fileId
  if (!fn.fileId) err(tag + ".fileId 누락");
  else if (!fileIds[fn.fileId]) err(tag + ".fileId '" + fn.fileId + "' 가 files[].id 에 없음");
  else fileUsed[fn.fileId] = true;

  // 3) terms
  (fn.terms || []).forEach(function (t) {
    if (!(t in glossKeys)) err(tag + ".terms 의 '" + t + "' 가 glossary 에 없음");
  });

  // 4) lines 앵커 매칭
  var rawLines = String(fn.code || "").split("\n");
  (fn.lines || []).forEach(function (a, j) {
    annTotal++;
    var loc = tag + ".lines[" + j + "]";
    if (a.at === undefined || a.at === null || a.at === "") { err(loc + ".at(앵커) 누락"); return; }
    if (!a.text) warn(loc + ".text 누락(권장)");
    var hits = [];
    for (var k = 0; k < rawLines.length; k++) {
      if (rawLines[k].indexOf(a.at) !== -1) hits.push(k + 1);
    }
    if (hits.length === 0) err(loc + " 앵커 '" + a.at + "' 가 code 에서 발견되지 않음(오타 의심)");
    else if (hits.length > 1) err(loc + " 앵커 '" + a.at + "' 가 여러 줄(" + hits.join(",") + ")에 매칭됨(더 구체적으로)");
  });
});

// 6) flow[].refs (선택 필드) — 있으면 각 id 가 functions[].id 에 존재해야 함(없으면 통과 = 하위호환)
(D.flow || []).forEach(function (s, i) {
  if (s.refs === undefined || s.refs === null) return;
  if (!Array.isArray(s.refs)) { err("flow[" + i + "].refs 는 배열이어야 함"); return; }
  s.refs.forEach(function (rid) {
    if (!fnIds[rid]) err("flow[" + i + "].refs 의 '" + rid + "' 가 functions[].id 에 없음");
  });
});

// 미사용 파일 그룹(함수 0개) 경고
(D.files || []).forEach(function (f) {
  if (f.id && !fileUsed[f.id]) warn("files '" + f.id + "' 에 연결된 함수가 없음(좌측에 안 보임)");
});

// 결과 출력
console.log("대상: " + abs);
console.log("구성: files " + (D.files || []).length + " · functions " + (D.functions || []).length +
  " · flow " + (D.flow || []).length + " · glossary " + Object.keys(glossKeys).length +
  " · 줄풀이(앵커) " + annTotal);

if (warns.length) {
  console.log("\n경고 " + warns.length + "건:");
  warns.forEach(function (w) { console.log("  - " + w); });
}

if (errors.length) {
  console.log("\n실패 " + errors.length + "건:");
  errors.forEach(function (e) { console.log("  X " + e); });
  console.log("\nVERIFY: FAIL");
  process.exit(1);
}

console.log("\nVERIFY: PASS (오류 0건)");
process.exit(0);
