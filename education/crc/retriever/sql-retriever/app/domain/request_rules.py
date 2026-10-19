"""S-R1 요청 형식 검사 규칙과 조회 범위(기준일, 거래 제공 시작일) 계산 규칙."""

from __future__ import annotations

import re
from datetime import date

QUESTION_MIN_LENGTH = 1
QUESTION_MAX_LENGTH = 500  # 설계 가정 A-4
# 회원ID 형식: "M-" + 숫자 4자리(설계 가정 A-4). 합성 DB의 회원ID(M-1001 등)와 같은 모양임
MEMBER_ID_PATTERN = re.compile(r"^M-[0-9]{4}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
# lab_metadata.txn_period 값 모양. 예: "2025-08 ~ 2026-08"
TXN_PERIOD_PATTERN = re.compile(r"^\s*([0-9]{4})-([0-9]{2})\s*~\s*([0-9]{4})-([0-9]{2})\s*$")


def is_valid_request_id(value: object) -> bool:
    """request_id가 비어 있지 않은 문자열인지 확인함."""
    return isinstance(value, str) and value.strip() != ""


def is_valid_question(value: object) -> bool:
    """질문이 공백만이 아닌 1 ~ 500자 문자열인지 확인함."""
    if not isinstance(value, str) or value.strip() == "":
        return False
    return QUESTION_MIN_LENGTH <= len(value) <= QUESTION_MAX_LENGTH


def is_valid_member_id(value: object) -> bool:
    """회원ID가 "M-" + 숫자 4자리 형식인지 확인함."""
    return isinstance(value, str) and MEMBER_ID_PATTERN.fullmatch(value) is not None


def parse_date(value: object) -> date | None:
    """YYYY-MM-DD 문자열을 날짜로 바꿈. 형식이 틀리거나 없는 날짜면 None을 반환함."""
    if not isinstance(value, str) or DATE_PATTERN.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_coverage_start(txn_period: str) -> date:
    """거래 제공 기간 문자열의 앞쪽 월 첫날을 거래 제공 시작일로 반환함.

    근거: 사용자 승인 결정 P-02(2026-10-15). 설계서는 키 이름을 "개발 시 확인"으로 남겨 둠.
    예시: "2025-08 ~ 2026-08" → 2025-08-01
    예외: 형식이 다르면 ValueError를 발생시킴.
    """
    matched = TXN_PERIOD_PATTERN.fullmatch(txn_period)
    if matched is None:
        raise ValueError("txn_period 형식이 올바르지 않음")
    return date(int(matched.group(1)), int(matched.group(2)), 1)


def resolve_base_date(requested: date | None, data_base_date: date) -> date:
    """요청 기준일이 없으면 데이터 기준일을 조회 기준일로 씀(8장 입력 데이터 설명)."""
    return requested if requested is not None else data_base_date
