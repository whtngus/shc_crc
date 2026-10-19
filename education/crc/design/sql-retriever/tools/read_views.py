"""DB 구조 읽기 스크립트 — SQL 검색기 설계서의 근거가 되는 뷰 목록과 권한을 읽어 JSON으로 저장함.

다시 돌려도 같은 결과가 나오도록 데이터 행은 읽지 않고 시스템 카탈로그와 `LIMIT 0`만 사용함.
세션은 접속 직후 읽기 전용으로 두므로 이 스크립트로는 DB에 아무것도 쓸 수 없음.

사용법:
    python design/sql-retriever/tools/read_views.py --allow-admin-account
비밀번호는 `secrets/.env`의 `RDB_PASSWORD`에서 읽고 화면이나 파일에 남기지 않음.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_DIR = Path(__file__).resolve().parents[1]
ADMIN_FLAGS = ("rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls")
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


def read_password(env_path: Path) -> str:
    """`.env`에서 `RDB_PASSWORD` 값만 꺼냄. 값이 없으면 사용자가 직접 등록하도록 안내 후 종료함."""
    if not env_path.is_file():
        sys.exit(f"[중단] {env_path} 파일이 없음. RDB_PASSWORD={{비밀번호}} 한 줄을 직접 등록해 주세요.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "RDB_PASSWORD":
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    sys.exit(f"[중단] {env_path}에 RDB_PASSWORD 값이 없음. 직접 등록해 주세요.")


def fetch_all(cur, query: str, params: tuple = ()) -> list[dict]:
    cur.execute(query, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="SQL 검색기 설계용 DB 구조 읽기")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="cardlab")
    parser.add_argument("--user", default="cardlab")
    parser.add_argument("--env", default=str(REPO_ROOT / "secrets" / ".env"))
    parser.add_argument("--view-sql", nargs="+", default=[str(REPO_ROOT / "rdb" / "init" / "04_views_rls.sql")])
    # NL2SQL이 실제로 쓸 서비스 역할. 접속 계정이 관리자일 때 이 역할 기준 권한을 따로 셈
    parser.add_argument("--nl2sql-role", default="sql_retriever_user")
    # 관리자 계정 접속은 사용자 결정(2026-10-15)으로만 허용함. 이 플래그가 없으면 관리자 계정에서 멈춤
    parser.add_argument("--allow-admin-account", action="store_true")
    parser.add_argument("--out", default=str(BASE_DIR / "work" / "db_catalog.json"))
    args = parser.parse_args()

    password = read_password(Path(args.env))
    conninfo = dict(host=args.host, port=args.port, dbname=args.dbname, user=args.user,
                    password=password, connect_timeout=5)
    try:
        conn = psycopg.connect(**conninfo, autocommit=True)
    except psycopg.OperationalError as exc:
        # 오류 문장에 비밀번호는 들어가지 않지만 접속 문자열 전체를 찍지 않도록 종류만 알림
        sys.exit(f"[접속 실패] {type(exc).__name__}: {str(exc).splitlines()[0]}")

    with conn, conn.cursor() as cur:
        # 접속 직후 읽기 전용으로 둠. 이후 모든 트랜잭션은 쓰기 구문을 거부함
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SHOW default_transaction_read_only")
        read_only = cur.fetchone()[0]
        print(f"[세션] default_transaction_read_only = {read_only}")

        role = fetch_all(cur, f"SELECT rolname, {', '.join(ADMIN_FLAGS)} FROM pg_roles WHERE rolname = current_user")[0]
        admin_flags = [f for f in ADMIN_FLAGS if role[f]]
        print(f"[계정] {role['rolname']} 관리자 권한: {admin_flags or '없음'}")
        if admin_flags and not args.allow_admin_account:
            sys.exit("[중단] 관리자 권한이 있는 계정임. NL2SQL 실행 계정으로 다시 접속해 주세요.")

        target = fetch_all(cur, f"SELECT rolname, {', '.join(ADMIN_FLAGS)} FROM pg_roles WHERE rolname = %s",
                           (args.nl2sql_role,))
        target_role = target[0] if target else None

        views = fetch_all(cur, """
            SELECT n.nspname AS schema, c.relname AS name,
                   obj_description(c.oid, 'pg_class') AS comment,
                   pg_get_userbyid(c.relowner) AS owner,
                   coalesce(array_to_string(c.reloptions, ','), '') AS options,
                   has_table_privilege(current_user, c.oid, 'SELECT') AS select_by_connect_user,
                   CASE WHEN %(role)s::text IS NULL THEN NULL
                        ELSE has_table_privilege(%(role)s::text, c.oid, 'SELECT') END AS select_by_nl2sql_role
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('v', 'm') AND n.nspname <> ALL(%(sys)s)
            ORDER BY n.nspname, c.relname
        """, {"role": target_role and args.nl2sql_role, "sys": list(SYSTEM_SCHEMAS)})

        for v in views:
            v["columns"] = fetch_all(cur, """
                SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type,
                       col_description(a.attrelid, a.attnum) AS comment
                FROM pg_attribute a
                WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (f'"{v["schema"]}"."{v["name"]}"',))
            ident = sql.Identifier(v["schema"], v["name"])
            # 접근 가능 여부만 확인함. LIMIT 0이므로 데이터 행은 한 건도 오지 않음
            for who, set_role in (("connect_user", None), ("nl2sql_role", target_role and args.nl2sql_role)):
                if who == "nl2sql_role" and not set_role:
                    v[f"limit0_{who}"] = None
                    continue
                try:
                    with conn.transaction():
                        if set_role:
                            cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(set_role)))
                        cur.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(ident))
                        assert cur.fetchall() == []
                    v[f"limit0_{who}"] = "ok"
                except psycopg.Error as exc:
                    v[f"limit0_{who}"] = f"error: {exc.sqlstate} {str(exc).splitlines()[0]}"

        tables = fetch_all(cur, """
            SELECT n.nspname AS schema, c.relname AS name,
                   c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
                   pg_get_userbyid(c.relowner) AS owner,
                   has_table_privilege(current_user, c.oid, 'SELECT') AS select_by_connect_user,
                   CASE WHEN %(role)s::text IS NULL THEN NULL
                        ELSE has_table_privilege(%(role)s::text, c.oid, 'SELECT') END AS select_by_nl2sql_role
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p') AND n.nspname <> ALL(%(sys)s)
            ORDER BY n.nspname, c.relname
        """, {"role": target_role and args.nl2sql_role, "sys": list(SYSTEM_SCHEMAS)})
        for t in tables:
            t["columns"] = fetch_all(cur, """
                SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type
                FROM pg_attribute a
                WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (f'"{t["schema"]}"."{t["name"]}"',))

        policies = fetch_all(cur, """
            SELECT schemaname AS schema, tablename AS "table", policyname AS policy,
                   cmd, roles::text AS roles, qual
            FROM pg_policies ORDER BY schemaname, tablename, policyname
        """)
        schema_grants = fetch_all(cur, """
            SELECT n.nspname AS schema, obj_description(n.oid, 'pg_namespace') AS comment,
                   has_schema_privilege(current_user, n.oid, 'USAGE') AS usage_by_connect_user,
                   CASE WHEN %(role)s::text IS NULL THEN NULL
                        ELSE has_schema_privilege(%(role)s::text, n.oid, 'USAGE') END AS usage_by_nl2sql_role,
                   CASE WHEN %(role)s::text IS NULL THEN NULL
                        ELSE has_schema_privilege(%(role)s::text, n.oid, 'CREATE') END AS create_by_nl2sql_role
            FROM pg_namespace n
            WHERE n.nspname <> ALL(%(sys)s) AND n.nspname NOT LIKE 'pg_temp%%' AND n.nspname NOT LIKE 'pg_toast%%'
            ORDER BY n.nspname
        """, {"role": target_role and args.nl2sql_role, "sys": list(SYSTEM_SCHEMAS)})
        cur.execute("SHOW server_version")
        server_version = cur.fetchone()[0]

    # View 생성 SQL 파일에 적힌 뷰와 DB에 있는 뷰를 비교함
    import re
    sql_views: dict[str, str] = {}
    for path in args.view_sql:
        text = Path(path).read_text(encoding="utf-8")
        for m in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w.]+)", text, re.IGNORECASE):
            sql_views[m.group(1)] = Path(path).name
    db_views = {f'{v["schema"]}.{v["name"]}' for v in views}

    accessible_connect = [f'{v["schema"]}.{v["name"]}' for v in views if v["limit0_connect_user"] == "ok"]
    accessible_role = [f'{v["schema"]}.{v["name"]}' for v in views if v["limit0_nl2sql_role"] == "ok"]
    catalog = {
        "generated_on": date.today().isoformat(),
        "connection": {"db_type": "PostgreSQL", "server_version": server_version, "host": args.host,
                       "port": args.port, "dbname": args.dbname, "user": args.user,
                       "password_source": "secrets/.env RDB_PASSWORD (값은 기록하지 않음)",
                       "session_read_only": read_only},
        "connect_user_role": role, "connect_user_admin_flags": admin_flags,
        "admin_account_allowed_by_user": bool(admin_flags and args.allow_admin_account),
        "nl2sql_role": target_role,
        "schemas": schema_grants,
        "views": views,
        "tables": tables,
        "rls_policies": policies,
        "view_sql_files": [Path(p).resolve().relative_to(REPO_ROOT).as_posix() for p in args.view_sql],
        "compare": {
            "only_in_view_sql": sorted(set(sql_views) - db_views),
            "only_in_db": sorted(db_views - set(sql_views)),
        },
        "summary": {
            "views_total": len(views),
            "views_accessible_by_connect_user": len(accessible_connect),
            "views_accessible_by_nl2sql_role": len(accessible_role),
            "nl2sql_role_accessible_views": accessible_role,
            "base_tables_readable_by_nl2sql_role": [f'{t["schema"]}.{t["name"]}' for t in tables
                                                     if t["select_by_nl2sql_role"]],
            "base_tables_readable_by_connect_user": [f'{t["schema"]}.{t["name"]}' for t in tables
                                                      if t["select_by_connect_user"]],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    s = catalog["summary"]
    print(f"[뷰] DB 전체 {s['views_total']}개 / 접속 계정 접근 가능 {s['views_accessible_by_connect_user']}개"
          f" / {args.nl2sql_role} 접근 가능 {s['views_accessible_by_nl2sql_role']}개")
    print(f"[원본 테이블] {args.nl2sql_role} 읽기 가능: {s['base_tables_readable_by_nl2sql_role'] or '없음'}")
    print(f"[원본 테이블] 접속 계정 읽기 가능: {len(s['base_tables_readable_by_connect_user'])}개")
    print(f"[비교] View SQL에만 있음: {catalog['compare']['only_in_view_sql'] or '없음'}")
    print(f"[비교] DB에만 있음: {catalog['compare']['only_in_db'] or '없음'}")
    print(f"[저장] {out.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
