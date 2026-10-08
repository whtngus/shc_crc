# crc

Agentic AI 아키텍처 설계 팀 폴더.  
팀 구성·행동원칙·위임 규칙은 [AGENTS.md](AGENTS.md) 참조.  
(원본 참고: [unicorn-campus/design-agentic-ai](https://github.com/unicorn-campus/design-agentic-ai/blob/main/AGENTS.md))

## 폴더 구조

| 경로 | 내용 |
|------|------|
| `AGENTS.md` / `CLAUDE.md` | 팀 규칙 원본 / Claude Code용 진입점(`@AGENTS.md`) |
| `.agents/agents/` | 팀원 7명 정의 원본 + 도구별 매핑표(`_mapping.toml`) |
| `.agents/skills/` | 스킬 원본(design-architecture, develop-agentic-ai, explain-exam) |
| `.claude/` , `.codex/` | 도구별 생성물 — 직접 고치지 않음 |
| `references/` | 프롬프트·PPT·엑셀·계층형 아키텍처·주석 가이드 |
| `scripts/` | `sync-agents.py`(생성물 동기화), `render-pptx.py`(PPT 미리보기) |

## 생성물 동기화

원본(`.agents/`) 수정 후 아래 명령 실행 (Python 3.11 이상 필요).  

```bash
python scripts/sync-agents.py          # 생성물 갱신
python scripts/sync-agents.py --check  # 최신 여부만 검사
```
