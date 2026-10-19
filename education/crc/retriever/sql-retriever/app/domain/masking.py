"""외부 LLM으로 보내기 전 질문 속 개인 식별자를 가리는 규칙(S-R1 작업 3, 사용자 결정 D-07)."""

from __future__ import annotations

import re

MASK_TOKEN = "[가림]"

# 가리는 순서가 중요함. 숫자가 긴 카드번호를 먼저 가려야 그 일부가 전화번호로 잘못 잡히지 않음.
# 숫자 앞뒤에 다른 숫자가 붙어 있으면 더 긴 숫자의 일부이므로 잡지 않음((?<!\d), (?!\d)).
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 카드번호: 숫자 15 ~ 16자리. 4자리마다 하이픈이나 띄어쓰기가 들어간 형태도 잡음
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){14,15}\d(?!\d)")),
    # 주민등록번호: 생년월일 6자리 + 성별 숫자로 시작하는 7자리
    ("resident", re.compile(r"(?<!\d)\d{6}[ -]?[1-8]\d{6}(?!\d)")),
    # 전화번호: 휴대폰(010 등), 인터넷 전화(070), 지역번호(02, 031 등)
    ("phone", re.compile(r"(?<!\d)(?:01[016789]|070|0[2-6][0-9]?)[ -]?\d{3,4}[ -]?\d{4}(?!\d)")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # 회원ID: "M-" + 숫자 4자리(설계 가정 A-4)
    ("member_id", re.compile(r"(?<![A-Za-z0-9])M-\d{4}(?!\d)")),
)


def mask_identifiers(question: str) -> tuple[str, int]:
    """질문 속 전화번호, 카드번호, 주민등록번호, 이메일, 회원ID를 [가림]으로 바꿈.

    반환값: (가린 질문, 가린 개수). 가릴 것이 없으면 원문과 0을 반환함.
    주의: 이름처럼 정규식으로 못 잡는 식별자는 남을 수 있음(위험 항목 R-04).
    """
    masked = question
    total = 0
    for _, pattern in _PATTERNS:
        masked, count = pattern.subn(MASK_TOKEN, masked)
        total += count
    return masked, total
