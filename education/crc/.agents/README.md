# `.agents/` — 스킬·에이전트 단일 원본

여러 바이브코딩 도구(Claude Code · Codex · Cursor · Antigravity)에서 같은 스킬과 에이전트를 쓰기 위한 원본 폴더임.  
**여기 있는 파일만 손으로 고치고**, 도구별 파일은 `scripts/sync-agents.py`가 만듦.

## 구조

```
.agents/
├── README.md                      이 문서
├── skills/<스킬명>/
│   ├── SKILL.md                   스킬 원본 (Agent Skills 표준 6키 + metadata.claude)
│   └── prompts/ guides/ shell/ …  스킬 부속 파일
└── agents/
    ├── _mapping.toml              범주(tier·permissions) → 도구별 값 매핑표
    └── <에이전트명>.md             에이전트 원본 (8섹션 본문 + name/description/tier/permissions) — 본문은 여기 1곳에만 있음

.claude/skills/<스킬명>/SKILL.md   [생성물] Claude Code 래퍼 (확장 프론트매터 + 원본 본문 동적 주입)
.claude/agents/<에이전트명>.md      [생성물] Claude Code 서브에이전트 — 원본을 읽고 따르라는 포인터 (Cursor도 이 파일을 읽음)
.codex/agents/<에이전트명>.toml     [생성물] Codex 커스텀 에이전트 — developer_instructions 가 원본 포인터
.codex/config.toml                 [생성물 구간] [agents.<이름>] 등록 (마커 사이만 스크립트가 관리)
```

에이전트 본문(8섹션)은 `.agents/agents/<에이전트명>.md`에만 있음. 도구별 생성물은 프론트매터·모델·권한과
"원본을 먼저 읽고 그대로 따름"이라는 포인터만 담으므로, 지침을 고칠 때 한 파일만 고치면 됨.  
대신 서브에이전트가 시작할 때 원본을 한 번 읽는 비용(Read 1회)이 듦. Claude Code·Codex 모두 에이전트 파일이
다른 파일을 포함하는 구문을 제공하지 않아(공식 문서 확인) 이 방식이 유일한 단일화 수단임.

## 어느 도구가 무엇을 읽나

| 도구 | 스킬 | 에이전트 | 비고 |
|------|------|---------|------|
| Claude Code | `.claude/skills/*` 래퍼 → 원본 주입 | `.claude/agents/*.md` 포인터 → 원본 Read | 래퍼가 `disallowed-tools`·`argument-hint` 등 확장 키를 맡음 |
| Codex | `.agents/skills/*` 직접 | `.codex/agents/*.toml` 포인터 (config.toml 등록 필수) | 드롭인·인라인 정의는 인식되지 않음(실측). 프로젝트를 신뢰(trust)해야 `.codex/config.toml`이 읽힘 |
| Cursor | `.agents/skills/*` 직접 | `.claude/agents/*.md` 호환 읽기 | 이름 충돌 시 `.cursor/` 우선 |
| Antigravity | `.agents/skills/*` 직접 | 없음(서브에이전트 기능 없음) | 스킬 본문의 담당 표를 오케스트레이터가 직접 수행 |

## 작성 규칙

- 스킬 원본 프론트매터는 표준 6키(`name` `description` `license` `compatibility` `metadata` `allowed-tools`)만 씀.  
  Claude Code 전용 키(`disallowed-tools` `argument-hint` `model` `context` 등)는 `metadata.claude:` 아래에 둠.  
  표준 외 키가 최상위에 있으면 스크립트가 오류로 멈춤
- 에이전트 원본 프론트매터는 `name` `description` `tier`(top|standard) `permissions`(write|readonly)만 씀.  
  모델 ID·sandbox 값은 `_mapping.toml`에서만 정함. 본문은 `[목표]` ~ `[예시]` 8섹션(`references/prompt-guide.md`)
- 스킬 본문에서 `{스킬 디렉토리}`·`<스킬 디렉터리>`는 이 폴더의 `skills/<스킬명>/`을 뜻함.  
  Claude Code 래퍼가 그 경로를 명시해 주입하므로 원본 본문은 도구 무관하게 씀
- 서브에이전트 호출 예시는 Claude Code `Agent` 도구 기준으로 적고, 담당 표는 도구 중립으로 유지함

## 갱신 절차

```bash
python scripts/sync-agents.py          # 생성물 갱신
python scripts/sync-agents.py --check  # 최신 여부만 검사 (CI·커밋 전 확인용)
```

## 심볼릭 링크를 쓰지 않는 이유

- Windows에서 링크 생성은 개발자 모드 또는 관리자 권한이 필요하고, git은 `core.symlinks=true`가 아니면 링크를
  경로 문자열 파일로 체크아웃함. 정션은 git이 저장하지 못함
- 래퍼 방식은 권한·git 설정과 무관하게 동작하고, Claude 확장 프론트매터를 원본과 분리해 표준 준수를 지킴
