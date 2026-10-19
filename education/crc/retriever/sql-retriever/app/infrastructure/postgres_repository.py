"""PostgreSQL 조회 구현체(S-R1 회원 확인, S-R5 SQL 실행). psycopg 3과 커넥션 풀을 씀."""

from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool, PoolTimeout

from ..application.models import DatabaseFailure, DatabaseTimeout, ExecutionResult, MemberContext
from ..application.ports import MemberRepositoryPort, SqlExecutorPort
from ..domain.request_rules import parse_coverage_start, parse_date, resolve_base_date

CONNECT_TIMEOUT_SECONDS = 3  # 새 접속을 여는 데 기다리는 상한. 시간 예산 15초를 지키려고 짧게 둠
POOL_MIN_SIZE = 1  # 사용자 승인 P-14
POOL_MAX_SIZE = 4

# 세션 변수 3개(29장). set_config(이름, 값, true)의 true는 "이 트랜잭션 안에서만 유효"라는 뜻임
_SET_SCOPE_SQL = (
    "SELECT set_config('app.member_id', %s, true),"
    " set_config('app.base_date', %s, true),"
    " set_config('app.coverage_start', %s, true)"
)
# SET LOCAL statement_timeout과 같은 효과. SET 문은 값 자리표시자를 못 쓰므로 set_config로 지정함
_SET_TIMEOUT_SQL = "SELECT set_config('statement_timeout', %s, true)"
_METADATA_SQL = "SELECT key, value FROM public.lab_metadata WHERE key IN ('base_date', 'txn_period')"
# 회원 조건은 RLS(행 수준 보안)가 이미 걸지만, 서비스 코드 전용 조회라 회원ID 조건을 한 번 더 붙임
_MEMBER_SQL = "SELECT join_date FROM app_internal.member_basic WHERE member_id = %s"


class PostgresRepository(MemberRepositoryPort, SqlExecutorPort):
    """NL2SQL 계정(sql_retriever_user)으로 읽기 전용 조회만 함.

    모든 조회는 BEGIN READ ONLY로 시작하고 ROLLBACK으로 끝냄. 그래서 세션 변수도 트랜잭션과 함께 지워짐.
    """

    def __init__(self, *, host: str, port: int, dbname: str, user: str, password: str):
        conninfo = make_conninfo(
            host=host, port=port, dbname=dbname, user=user, connect_timeout=CONNECT_TIMEOUT_SECONDS
        )
        # autocommit=True로 두고 BEGIN READ ONLY와 ROLLBACK을 직접 보냄. 설계서 17장 순서를 코드에 그대로 드러냄
        self._pool = ConnectionPool(
            conninfo,
            kwargs={"password": password, "autocommit": True},
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            open=False,
            name="sql-retriever",
        )
        self._opened = False

    def close(self) -> None:
        """커넥션 풀을 닫음. 서버 종료 시 부름."""
        if self._opened:
            self._pool.close()
            self._opened = False

    def _ensure_open(self) -> None:
        if not self._opened:
            # 서버가 DB 없이도 뜰 수 있게 첫 요청 때 풀을 염. 접속은 뒤에서 채움
            self._pool.open(wait=False)
            self._opened = True

    def load_member_context(
        self, member_id: str, requested_base_date: date | None, timeout_ms: int
    ) -> MemberContext:
        """S-R1 작업 4 ~ 5. 메타데이터, 세션 변수 지정, 회원 가입일 조회를 트랜잭션 하나에서 함."""
        try:
            with self._read_only(timeout_ms) as cursor:
                cursor.execute(_METADATA_SQL)
                metadata = {key: value for key, value in cursor.fetchall()}
                data_base_date = parse_date(metadata.get("base_date"))
                if data_base_date is None or "txn_period" not in metadata:
                    raise DatabaseFailure("lab_metadata 키 없음")
                coverage_start = parse_coverage_start(metadata["txn_period"])
                base_date = resolve_base_date(requested_base_date, data_base_date)
                cursor.execute(_SET_SCOPE_SQL, (member_id, base_date.isoformat(), coverage_start.isoformat()))
                cursor.execute(_MEMBER_SQL, (member_id,))
                row = cursor.fetchone()
        except ValueError as error:
            raise DatabaseFailure("lab_metadata 값 형식 오류") from error
        return MemberContext(
            data_base_date=data_base_date,
            base_date=base_date,
            coverage_start=coverage_start,
            join_date=row[0] if row else None,
        )

    def execute(
        self,
        validated_sql: str,
        *,
        member_id: str,
        base_date: date,
        coverage_start: date,
        timeout_ms: int,
        row_limit: int,
    ) -> ExecutionResult:
        """S-R5 작업 2 ~ 7. 세션 변수를 걸고 검증된 SQL을 실행해 최대 row_limit행을 받음."""
        with self._read_only(timeout_ms) as cursor:
            cursor.execute(_SET_SCOPE_SQL, (member_id, base_date.isoformat(), coverage_start.isoformat()))
            started = time.perf_counter()
            # 값 인자 없이 실행하면 psycopg가 SQL 속 %를 자리표시자로 해석하지 않음(LIKE '%..%' 보호)
            cursor.execute(validated_sql)
            fetched = cursor.fetchmany(row_limit)
            db_elapsed_ms = int((time.perf_counter() - started) * 1000)
            description = cursor.description or []
        columns = [{"name": column.name, "type": column.type_display} for column in description]
        names = [column["name"] for column in columns]
        rows = [{name: _to_json_value(value) for name, value in zip(names, row)} for row in fetched]
        return ExecutionResult(columns=columns, rows=rows, db_elapsed_ms=db_elapsed_ms)

    def _read_only(self, timeout_ms: int) -> _ReadOnlyTransaction:
        self._ensure_open()
        return _ReadOnlyTransaction(self._pool, timeout_ms)


class _ReadOnlyTransaction:
    """BEGIN READ ONLY → statement_timeout 지정 → (본문) → ROLLBACK 순서를 지키는 문맥 관리자.

    psycopg 예외를 응용 계층 예외(DatabaseTimeout, DatabaseFailure)로 바꿈. 메시지에 SQL과 접속 정보는 넣지 않음.
    """

    def __init__(self, pool: ConnectionPool, timeout_ms: int):
        self._pool = pool
        self._timeout_ms = max(1, timeout_ms)  # 0은 PostgreSQL에서 "제한 없음"이라 최소 1ms로 둠
        self._connection_cm: Any = None
        self._cursor: psycopg.Cursor | None = None

    def __enter__(self) -> psycopg.Cursor:
        try:
            # 풀에서 접속을 기다리는 시간도 남은 시간 예산을 넘지 않게 함
            self._connection_cm = self._pool.connection(timeout=self._timeout_ms / 1000)
            connection = self._connection_cm.__enter__()
            self._cursor = connection.cursor()
            self._cursor.execute("BEGIN READ ONLY")
            self._cursor.execute(_SET_TIMEOUT_SQL, (str(self._timeout_ms),))
            return self._cursor
        except BaseException as error:
            self._finish(error)
            raise _translate(error) from error

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self._finish(exc)
        if exc is None:
            return False
        if isinstance(exc, (DatabaseFailure, DatabaseTimeout)):
            return False
        translated = _translate(exc)
        if translated is exc:
            return False
        raise translated from exc

    def _finish(self, error: BaseException | None) -> None:
        if self._cursor is not None:
            try:
                # ROLLBACK으로 끝내 세션 변수까지 함께 지움(17장 작업 7)
                self._cursor.execute("ROLLBACK")
            except psycopg.Error:
                pass  # 접속이 끊긴 경우. 풀이 상태를 보고 그 접속을 버림
            finally:
                self._cursor.close()
                self._cursor = None
        if self._connection_cm is not None:
            cm, self._connection_cm = self._connection_cm, None
            try:
                cm.__exit__(None, None, None)
            except psycopg.Error:
                pass


def _translate(error: BaseException) -> BaseException:
    if isinstance(error, pg_errors.QueryCanceled):
        return DatabaseTimeout("statement_timeout 초과")
    if isinstance(error, PoolTimeout):
        return DatabaseFailure("커넥션 풀 대기 시간 초과")
    if isinstance(error, psycopg.Error):
        return DatabaseFailure(type(error).__name__)
    return error


def _to_json_value(value: Any) -> Any:
    """DB 값을 JSON에 바로 담을 수 있는 값으로 바꿈. 날짜는 ISO 문자열, 정수 Decimal은 int로 바꿈."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value
