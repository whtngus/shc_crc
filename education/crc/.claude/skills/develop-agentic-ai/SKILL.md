---
name: develop-agentic-ai
description: 아키텍처 설계서 7종을 입력으로 개발 프롬프트 9종(런타임·데이터셋·지식경로·커넥터·가드레일·워크플로우·API/UI·배포·평가)을 정해진 순서로 호출해 실행 가능한 코드·시험·README를 생성. "개발 시작", "코드 생성", "개발 프롬프트 실행", "설계서를 코드로" 등 키워드 감지 시 사용
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent
disallowed-tools: Bash, PowerShell, WebFetch, WebSearch, NotebookEdit, Artifact, mcp__*
---
<!-- scripts/sync-agents.py 가 만든 Claude Code 래퍼임. 원본: .agents/skills/develop-agentic-ai/SKILL.md
     이 파일을 직접 고치지 않음. 원본을 고친 뒤 `python scripts/sync-agents.py` 를 다시 실행함 -->

> **이 스킬의 원본은 `.agents/skills/develop-agentic-ai/SKILL.md`이며 아래에 그대로 주입됨.**
> 본문에서 `{스킬 디렉토리}` · `<스킬 디렉터리>` · "이 SKILL.md가 위치한 디렉토리"는 모두
> `${CLAUDE_PROJECT_DIR}/.agents/skills/develop-agentic-ai` 를 뜻함(`prompts/` · `guides/` · `shell/` · `templates/`가 그 아래에 있음).
> 인자: $ARGUMENTS

!`cat "${CLAUDE_PROJECT_DIR}/.agents/skills/develop-agentic-ai/SKILL.md"`
