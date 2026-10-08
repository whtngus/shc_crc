---
name: design-architecture
description: 기획 산출물(비즈니스모델·유저스토리·이벤트스토밍)을 입력으로 AI 앱 아키텍처 설계서 7종(목표/품질 카드·논리아키텍처·워크플로우·역할계약서·지식/도구·관측/가드레일·배포)과 반영대조표 1종을 순서대로 생성. "아키텍처 설계", "설계서 작성", "논리아키텍처", "워크플로우 설계", "역할계약서" 등 키워드 감지 시 사용
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent
disallowed-tools: Bash, PowerShell, WebFetch, WebSearch, NotebookEdit, Artifact, mcp__*
---
<!-- scripts/sync-agents.py 가 만든 Claude Code 래퍼임. 원본: .agents/skills/design-architecture/SKILL.md
     이 파일을 직접 고치지 않음. 원본을 고친 뒤 `python scripts/sync-agents.py` 를 다시 실행함 -->

> **이 스킬의 원본은 `.agents/skills/design-architecture/SKILL.md`이며 아래에 그대로 주입됨.**
> 본문에서 `{스킬 디렉토리}` · `<스킬 디렉터리>` · "이 SKILL.md가 위치한 디렉토리"는 모두
> `${CLAUDE_PROJECT_DIR}/.agents/skills/design-architecture` 를 뜻함(`prompts/` · `guides/` · `shell/` · `templates/`가 그 아래에 있음).
> 인자: $ARGUMENTS

!`cat "${CLAUDE_PROJECT_DIR}/.agents/skills/design-architecture/SKILL.md"`
