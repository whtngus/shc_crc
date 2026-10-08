---
name: explain-exam
description: 예제 코드를 그 언어를 모르는 사람에게 쉽게 설명하는 웹 페이지를 생성함. 예제 디렉터리를 입력받아 공용 셸로 여는 data.js 하나를 작성하고, 셸이 없으면 스킬에 든 셸을 프로젝트에 설치함. Python·JavaScript·Java·Go 등 주요 언어 지원. "예제 설명 페이지", explain-exam, 코드 해설/설명 페이지 제작 요청 시 사용.
argument-hint: "<예제 디렉터리 경로> [셸 디렉터리 경로]"
---
<!-- scripts/sync-agents.py 가 만든 Claude Code 래퍼임. 원본: .agents/skills/explain-exam/SKILL.md
     이 파일을 직접 고치지 않음. 원본을 고친 뒤 `python scripts/sync-agents.py` 를 다시 실행함 -->

> **이 스킬의 원본은 `.agents/skills/explain-exam/SKILL.md`이며 아래에 그대로 주입됨.**
> 본문에서 `{스킬 디렉토리}` · `<스킬 디렉터리>` · "이 SKILL.md가 위치한 디렉토리"는 모두
> `${CLAUDE_PROJECT_DIR}/.agents/skills/explain-exam` 를 뜻함(`prompts/` · `guides/` · `shell/` · `templates/`가 그 아래에 있음).
> 인자: $ARGUMENTS

!`cat "${CLAUDE_PROJECT_DIR}/.agents/skills/explain-exam/SKILL.md"`
