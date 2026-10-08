---
name: explain-exam
description: 예제 코드를 그 언어를 모르는 사람에게 쉽게 설명하는 웹 페이지를 생성함. 예제 디렉터리를 입력받아 공용 셸로 여는 data.js 하나를 작성하고, 셸이 없으면 스킬에 든 셸을 프로젝트에 설치함. Python·JavaScript·Java·Go 등 주요 언어 지원. "예제 설명 페이지", explain-exam, 코드 해설/설명 페이지 제작 요청 시 사용.
metadata:
  claude:
    argument-hint: "<예제 디렉터리 경로> [셸 디렉터리 경로]"
---

# explain-exam — 예제 설명 페이지 생성

입력: $ARGUMENTS

- **1번째 인자 (필수)** = 설명할 예제 디렉터리 경로
- **2번째 인자 (선택)** = 공용 셸 디렉터리 경로. 생략하면 3단계 규칙으로 찾거나 설치함

그 언어를 전혀 모르는 사람이 예제 코드를 이해하도록 3분할 웹 페이지로 설명함.
좌측(처리 흐름 + 파일별 함수) · 중앙(소스 코드) · 우측(요약→동작원리→줄별 풀이→용어) 구조.

## 핵심 원칙

- 화면(셸)은 **모든 예제가 공유하는 1벌**임. 예제마다 복사하거나 고치지 않음
- 예제마다 **`data.js` 하나만** 새로 작성해 페이지를 구성함
- 읽는 사람은 코드를 "읽기만" 함. 설치·서버·코드 실행 없이 브라우저로 봄
- **특정 폴더 이름에 기대지 않음.** 셸과 예제의 상대 위치만 맞으면 어떤 구조에서도 동작함

## 산출물

| 산출물 | 경로 | 비고 |
|--------|------|------|
| `data.js` | `<예제 디렉터리>/explain/data.js` | **핵심 생성물.** 예제마다 새로 작성 |
| launcher | `<예제 디렉터리>/explain/index.html` | 더블클릭용. `templates/launcher.html`을 복사하고 경로 2개를 채움 |
| 공용 셸 | `<셸 디렉터리>/` | **이미 있으면 건드리지 않음.** 없을 때만 1회 설치 |

## 담당 · 위임

`AGENTS.md` design-agentic-ai 팀의 오케스트레이터 클로니가 진행하며, 설명 콘텐츠를 만드는 구간은
기술 교육·문서 엔지니어 **에듀니(`eduni`)**에게 `Agent` 도구로 **실제 위임**함(인격만 바꿔 직접 쓰지 않음).

| 단계 | 담당 | 호출 방식 | 이유 |
|------|------|----------|------|
| 1 입력 확인 · 2 셸 게이트 | 클로니 | 직접 | 메인 파일 선택·셸 설치 위치를 **사용자에게 되묻는** 자리라 서브에이전트가 못 함 |
| 3 예제 분석 · 4 data.js 작성 · 5 launcher · 6 검증 | 에듀니 | `Agent(subagent_type="eduni")` 1회 | "그 언어를 모르는 사람에게 쉽게 설명"은 에듀니의 전문 영역임 |
| 7 렌더 확인 · 8 목록 등록 · 9 사용자 안내 | 클로니 | 직접 | 산출물 존재·PASS 로그를 검수하고 사용자에게 보고하는 자리 |

- 사용 가능 에이전트 목록에 `eduni`가 없으면(이 스킬만 다른 프로젝트에 배포된 경우)
  `subagent_type="general-purpose"`로 대체 호출하고, 위임 프롬프트 `[역할]`에 에듀니 프로파일
  (에듀/에듀니/남성/34세 · 개발자 5년 + 개발자 교육·테크니컬 라이팅 6년 · "설명이 코드보다 어려우면 실패")을
  직접 적음. 대체 호출한 사실은 9단계 사용자 안내에 함께 적음
- 서브에이전트 기능이 없는 도구(예: Antigravity)에서 실행되면 오케스트레이터가 에듀니의 `[역할]`을 취해
  3 ~ 6단계를 직접 수행하고, 9단계 안내에 `직접 수행(서브에이전트 없음)`으로 적음
- 위임 프롬프트는 `references/prompt-guide.md`의 8섹션 표준을 따르고, 경로 등 입력값은 XML 태그로 감쌈
- 에듀니는 3 ~ 6단계 규칙(이 파일의 「data.js 스키마」·「MUST」·「MUST NOT」·「시행착오」 포함)을
  **이 SKILL.md를 직접 Read해서** 따름. 클로니가 규칙을 요약해 옮겨 적지 않음(축약 손실 방지)

**위임 호출 형태(Claude Code `Agent` 도구 기준)**

```
Agent(
  subagent_type="eduni",
  description="explain-exam data.js 작성",
  prompt="[목표] <예제디렉터리>의 예제를 그 언어를 모르는 사람이 이해하도록 설명하는 data.js와
          launcher를 만들고 verify PASS까지 확인함
          [역할] 에듀니 — 기술 교육·문서 엔지니어(`.agents/agents/eduni.md`)
          [맥락] 공용 셸은 이미 확정됨. 셸·스키마·검증 도구는 고치지 않고 내용만 채움
          [입력] <예제디렉터리>{절대경로}</예제디렉터리> <메인파일>{파일명}</메인파일>
                 <언어>{meta.lang 값}</언어> <셸디렉터리>{절대경로}</셸디렉터리>
                 <스킬디렉터리>{이 SKILL.md가 있는 절대경로}</스킬디렉터리>
          [처리] <스킬디렉터리>/SKILL.md를 Read로 읽고 「3. 예제 분석」 ~ 「6. 검증」 ·
                 「data.js 스키마」 · 「MUST」 · 「MUST NOT」 · 「시행착오」 절을 요약 없이 그대로 수행.
                 예제 코드는 실행하지 않음. 라이브러리 함수 의미가 불확실하면 context7 MCP로 확인
          [출력] <예제디렉터리>/explain/data.js · <예제디렉터리>/explain/index.html
          [제약조건] `node <셸디렉터리>/verify-data.js <예제디렉터리>/explain/data.js` 결과
                 `VERIFY: PASS` 로그를 첨부한 뒤에만 완료 보고. 미통과면 고치고 재실행",
  run_in_background=false
)
```

- 호출 완료 후 클로니가 `<예제 디렉터리>/explain/data.js`·`index.html`이 실제로 있는지와 보고에 담긴
  PASS 로그를 확인한 뒤에만 7단계로 넘어감(정직한 보고 규칙)
- PASS가 아니거나 파일이 없으면 미통과 내용을 `<미통과항목>` 태그로 넘겨 같은 형태로 재호출함
  (**재작성 카운터 최대 2회**). 2회째도 미통과면 멈추고 사유를 사용자에게 보고함

## 처리 절차

### 1. 입력 확인

- **1번째 인자**(예제 디렉터리)가 비면 사용자에게 물음
- 예제의 **메인 파일**을 식별함. 언어별로 단서가 다름
  - Python: `if __name__ == "__main__"` · `streamlit run` 대상 · `main.py` · `app.py`
  - JS/TS: `package.json`의 `main`·`scripts.start` · `index.js` · `main.ts`
  - Java/Kotlin: `public static void main` · `fun main`
  - Go: `package main`의 `func main`
  - 그 밖: 진입점처럼 보이는 파일이 여럿이면 **사용자에게 물음.** 임의로 고르지 않음
- 메인 파일 확장자로 **언어**를 정함(`data.js`의 `meta.lang`에 적음).
  아는 언어 목록은 아래 "언어(lang)" 절 참고

### 2. 공용 셸 찾기 또는 설치 (게이트)

아래 순서로 `<셸 디렉터리>`를 정함. **셸이 확정되기 전에는 `data.js`를 쓰지 않음.**

1. **2번째 인자가 있으면** 그 경로를 씀
2. 없으면 저장소 안에서 **이미 있는 셸**을 찾음.
   `index.html` · `assets/app.js` · `assets/style.css` · `verify-data.js`가 **모두 있는** 디렉터리가 셸임
   (이름이 `explain-exam`이 아니어도 됨). 여러 개 나오면 예제 디렉터리에서 **가장 가까운 것**을 고름
3. 하나도 없으면 **설치함**
   - 설치 위치 기본값: `<저장소 루트>/explain-exam/`(저장소 루트는 `.git`이 있는 디렉터리.
     없으면 예제들을 모두 담는 가장 가까운 상위 디렉터리)
   - **설치 전에 사용자에게 위치를 확인받음.** 예제 폴더 밖에 파일을 만드는 일이므로 조용히 하지 않음
   - `<스킬 디렉터리>/shell/`의 4개 파일 + `README.md`를 그 위치에 **그대로 복사**함
     (`<스킬 디렉터리>` = 이 `SKILL.md`가 있는 디렉터리)
4. 정해진 셸에 4개 파일이 실제로 있는지 확인함. 하나라도 없으면 중단하고 사용자에게 알림

`<셸 디렉터리>`와 예제는 **같은 저장소 안**에 있어야 함. 서로 상대경로가 나오지 않으면
(다른 드라이브 등) 중단하고 사용자에게 알림.

### 3. 예제 분석 (다중 파일 필수)

> 3 ~ 6단계는 **에듀니(`eduni`) 위임 구간**임 — 위 「담당 · 위임」의 호출 형태로 1회 호출함.
> 아래 규칙은 에듀니가 이 파일을 직접 읽고 따르는 내용임.

- 메인 파일의 가져오기 문(`import` · `require` · `use` · `#include` 등)을 따라
  **프로젝트 안의 로컬 모듈을 모두 수집**함. 외부 라이브러리는 제외
  - 예: `from tools import TRAVEL_TOOLS` → 같은/상위 경로의 `tools.py`를 찾아 포함
  - 검색 경로를 바꾸는 코드(`sys.path.insert(...)` 등)가 있으면 그 경로도 추적함
- 메인 + 의존 모듈의 **함수·주요 상수·장식자/애너테이션**을 파일별로 목록화함
- 전체 처리 흐름(실행 진입 → 입력 → 처리 → 응답 생성 → 표시)을 단계로 정리함

### 4. data.js 작성

- 아래 "data.js 스키마"를 따름. `window.EXPLAIN_DATA = { ... }` 전역 할당
- 코드(`code`)는 **실제 소스 그대로** 넣음(발췌·재구성 금지). 구문 강조는 셸이 처리
- 줄별 풀이(`lines`)는 줄 번호가 아니라 **앵커(`at`: 코드 안의 부분 문자열)**로 작성함
- 파일마다 언어가 다르면 `files[].lang`을 각각 적음. 전부 같으면 `meta.lang` 하나로 충분함

### 5. launcher 만들기

`<스킬 디렉터리>/templates/launcher.html`을 `<예제 디렉터리>/explain/index.html`로 복사하고
자리표시자 2개를 **실제 상대경로**로 채움.

| 자리표시자 | 무엇으로 채우나 | 예 |
|-----------|---------------|-----|
| `__SHELL_REL__` | launcher 파일 기준, `<셸 디렉터리>`까지의 상대경로 | `../../explain-exam` |
| `__DATA_REL__` | `<셸 디렉터리>` 기준, 이 폴더 `data.js`까지의 상대경로 | `../my-example/explain/data.js` |

- 두 값은 **깊이마다 다름.** 다른 예제의 launcher를 그대로 복사해 쓰지 않고 매번 계산함
- 경로 구분자는 `/`만 씀(윈도우에서도 `\` 금지)
- 계산이 맞는지 확인: `<셸 디렉터리>` + `/` + `__DATA_REL__`을 정규화하면
  `<예제 디렉터리>/explain/data.js`가 나와야 함

### 6. 검증 (게이트 — 필수)

```bash
node <셸 디렉터리>/verify-data.js <예제 디렉터리>/explain/data.js
```

- 결과가 **`VERIFY: PASS (오류 0건)`**이어야 함. 실패 시 메시지대로 고치고 재실행
- `lang` 경고가 나오면 오타인지 확인함(경고만으로는 실패가 아니지만 대개 오타임)

### 7. (권장) 실제 렌더 확인

> 여기부터 다시 **클로니 직접** 구간임. 먼저 에듀니 보고의 PASS 로그와 산출물 2건의 존재를 확인함.

로컬 HTTP 또는 headless Chrome로 렌더를 확인함(아래 "테스트 방법" 참고).

### 8. 목록에 등록 (있을 때만)

예제 목록 페이지가 있으면 이 예제를 등록해 찾기 쉽게 함. 아래 순서로 판단함.

1. `<셸 디렉터리>/examples.js`(레지스트리, `window.EXAMPLE_INDEX` 배열)가 있으면
   **항목 1개를 append**함: `{chapter, name, file, desc, link, readme}`.
   `link`는 셸 기준 launcher 상대경로임
2. 레지스트리가 없고 예제들을 담는 상위 디렉터리에 목록 `index.html`이 있으면 거기에 항목을 추가함
3. 둘 다 없으면 **이 단계를 건너뜀**(없다고 실패로 보지 않음)

### 9. 사용자 안내

- 가장 간단한 방법: **`<예제 디렉터리>/explain/index.html`을 더블클릭**
- 또는 직접 열기: `<셸 디렉터리>/index.html?data=<예제 data.js 상대경로>`
- 셸을 새로 설치했으면 **어디에 설치했는지 알림**

## data.js 스키마 (고정 계약 — 셸이 이 구조에만 의존)

```js
window.EXPLAIN_DATA = {
  meta:  {
    title: "페이지 제목",
    entry: "메인 파일명",
    lang:  "python"                  // (선택) 구문 강조 언어. 없으면 파일 확장자로 알아냄
  },
  files: [ { id: "main", label: "파일명.py", role: "한 줄 역할", lang: "python" } ],  // lang 선택
  flow:  [ {
    step: 1, title: "단계명", summary: "중앙 한 줄", detail: "우측 상세(비유 포함)",
    label: "좌측용 짧은 제목",         // (선택) 좌측 '처리 흐름' 바로가기 표시명. 없으면 title 사용
    refs: ["get_agent"],             // (선택) 이 단계의 함수 id들 → 좌측 단계 클릭·중앙 '코드:' 칩으로 점프
  } ],
  functions: [
    {
      id: "get_agent",               // 고유 식별자
      name: "get_agent()",           // 좌측 메뉴 표시명
      fileId: "main",                // files[].id 참조 → 파일별 그룹핑
      summary: "한 줄 요약",
      how: "동작 원리(선택, 여러 문장 가능)",
      lang: "python",                // (선택) 이 함수만 다른 언어일 때
      terms: ["create_react_agent"], // glossary 키 참조 → 우측 용어
      lines: [                       // 줄별 풀이: 줄 번호 대신 앵커(at)
        { at: 'require_api_key(', text: "그 줄이 하는 일(쉬운 말)" }
      ],
      code: "def get_agent():\n    ..."  // 실제 소스 전체(줄바꿈 포함)
    }
  ],
  glossary: { "create_react_agent": "쉬운 설명" }
};
```

### 언어(lang)

셸이 강조 언어를 정하는 순서임.

```
functions[].lang → files[].lang → meta.lang → files[].label 확장자 → meta.entry 확장자 → python
```

아는 언어: `python` `javascript` `typescript` `java` `kotlin` `scala` `swift` `csharp` `dart`
`go` `rust` `c` `cpp` `php` `ruby` `sql` `bash` `powershell` `r` `yaml` `json`

- 목록에 없는 언어를 적어도 **동작함**(generic 규칙: 줄 주석 `//`·`#`, 블록 주석 `/* */`, 따옴표).
  다만 `verify-data.js`가 경고를 내므로 오타인지 확인함
- 파일 확장자로 알아내므로 **한 언어 프로젝트면 `lang`을 안 적어도 됨**
- 한 예제에 언어가 섞여 있으면(백엔드 `.py` + 프론트 `.ts`) `files[].lang`을 파일마다 적음

### 작성 팁

- `code`는 JS 템플릿 리터럴(백틱)로 작성하기 쉬움.
  **소스에 백틱이 있으면 이스케이프**함(JS·마크다운 소스에서 자주 나옴)
- `terms`의 각 항목은 `glossary`에 키가 존재해야 함
- `files[].id`와 `functions[].fileId`가 일치해야 좌측 그룹에 표시됨
- (선택) `flow[].label`·`flow[].refs`로 **처리 흐름↔함수**를 연결함.
  깨끗이 대응되는 함수가 없는 단계는 `refs`를 **생략**함(억지 매칭 금지 = graceful degrade)

## MUST

- **줄 번호 매칭**: `lines`는 반드시 `{ at, text }` 앵커로 작성함. `at`은 해당 함수 `code` 안에서
  **정확히 한 줄**과만 매칭되는 부분 문자열이어야 함(0개=오타, 2개+=모호).
  → 생성 후 `verify-data.js`가 **PASS** 해야 함(이 게이트로 줄 번호 어긋남을 원천 차단)
- **초보자 친화**: 모든 설명은 그 언어를 모르는 사람 기준. 필요 시 비유·예시 사용
- **용어 설명**: 기술 용어·약어는 모두 `glossary`에 쉬운 말로 풀이.
  그 언어의 관용구(파이썬 `if __name__`, JS `async/await` 등)도 용어로 넣음
- **다중 파일 그룹핑**: 메인 + 의존 모듈을 `files`로 나눠, 함수를 파일별로 묶음
- **코드 충실성**: `code`는 실제 소스 그대로. 발췌 시 그 사실을 주석으로 명시
- **file:// 안전**: `data.js`는 `window.EXPLAIN_DATA` 전역 할당만 함.
  `fetch`/`import`/ES 모듈 사용 금지(셸이 동적 `<script>`로 불러오고 charset도 셸이 처리함)
- **경로는 상대경로**: launcher의 두 값과 `?data=`는 모두 상대경로여야 함(절대경로는 다른 PC에서 깨짐)

## MUST NOT

- 읽는 사람에게 빌드·서버·코드 실행을 요구하지 않음
- 공용 셸(`index.html`·`assets/`·`verify-data.js`)을 예제마다 복사·수정하지 않음
- 예제 코드를 실행하거나 외부 API를 호출하지 않음(정적 설명 전용)
- 영문 위주 설명 금지(한국어 기준, 기술 용어만 원어 병기)
- 셸이 없다고 `data.js`만 만들고 끝내지 않음(열 화면이 없으면 산출물이 아님)
- 확인 없이 예제 폴더 밖에 셸을 설치하지 않음
- 3 ~ 6단계(분석·data.js·launcher·검증)를 클로니가 에듀니 인격만 빌려 직접 작성하지 않음 — 반드시 `Agent` 호출
- 에듀니 보고의 PASS 로그를 확인하지 않은 채 7단계 이후로 넘어가지 않음

## 시행착오 (반드시 참고 — 과거 실수)

- [HIGH] `data.json` + `fetch`는 `file://`에서 CORS(null origin)로 차단되어 **빈 화면**이 됨 →
  `data.js`의 `window` 전역 + `<script>` 로드만 사용(셸이 동적 주입). fetch 금지
- [HIGH] **줄 번호 수동 입력은 어긋남**. 특히 여러 줄 주석이 있는 함수에서 원본 파일 기준으로
  적으면 화면의 1-기반 줄 번호와 안 맞음 → **앵커(at) 방식 + verify-data.js 게이트**로 해결
- [HIGH] `file://`에선 HTTP charset 헤더가 없어 한글이 깨질(mojibake) 수 있음 → 셸이
  `<script charset="utf-8">`로 로드하므로 `data.js`는 UTF-8로 저장만 하면 됨(BOM 불필요)
- [HIGH] launcher 경로를 다른 예제에서 복사해 오면 **깊이가 달라 셸을 못 찾음** →
  `__SHELL_REL__`·`__DATA_REL__`을 매번 계산하고 정규화로 검산함
- [MED] JS 템플릿 리터럴 `code`에 소스의 백틱이 그대로 들어가면 리터럴이 깨짐 → 백틱은 이스케이프
- [MED] 앵커가 함수 안에서 2곳 이상 매칭되면 verify 실패 → 더 긴/구체적 부분 문자열 사용
- [MED] 예제는 단일 파일이 아님(메인이 로컬 모듈을 가져다 씀) → 가져오기를 따라 전부 포함, 파일별 그룹핑
- [MED] 테스트 도구가 `file://`를 막을 때가 있음 → headless Chrome `--virtual-time-budget`로 검증
  (동적 스크립트 로드가 끝나기 전 캡처되면 false blank가 나므로 budget 필수)

## 완료조건

- `node <셸 디렉터리>/verify-data.js <data.js>` → `VERIFY: PASS`
- 좌측에 처리 흐름 + 함수가 파일별로 표시(메인 + 의존 모듈 전부)
- 함수 클릭 시 중앙 소스 + 우측 요약·동작원리·줄별 풀이·용어가 표시되고, 줄별 풀이의 줄 번호가 코드와 일치
- `<예제 디렉터리>/explain/index.html` 더블클릭으로 빈 화면·한글 깨짐 없이 열림
- 목록 페이지·레지스트리가 있으면 이 예제 항목이 등록되어 있음
- 셸을 새로 설치했으면 그 위치를 사용자에게 알렸음
- 3 ~ 6단계가 에듀니(`eduni`) `Agent` 호출 1회 이상으로 수행됐고, 사용자 안내에 호출 여부
  (`eduni` 호출 / `general-purpose` 대체 / 재호출 횟수)가 적혀 있음

## 테스트 방법 (참고)

로컬 HTTP:

```bash
python -m http.server 8777 --bind 127.0.0.1
# 브라우저: http://127.0.0.1:8777/<셸 디렉터리>/index.html?data=<data.js 상대경로>
```

headless Chrome로 `file://` (Windows 예):

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu `
  --screenshot="$env:TEMP\explain.png" --window-size=1600,1000 --virtual-time-budget=6000 `
  "file:///<절대경로>/<예제 디렉터리>/explain/index.html"
# 생성된 explain.png 를 열어 3분할이 보이고 한글이 정상인지 확인
```
