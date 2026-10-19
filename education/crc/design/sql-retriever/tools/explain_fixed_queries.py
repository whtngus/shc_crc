"""정형쿼리 후보 EXPLAIN 확인 — 문법과 권한만 보고 데이터 행은 읽지 않음.

접속 계정이 관리자(사용자 결정으로 허용)이므로, 트랜잭션 안에서 NL2SQL 실행 역할로 바꾼 뒤
EXPLAIN을 실행해 그 역할의 권한으로 통과하는지 확인함.

사용법:
    python design/sql-retriever/tools/explain_fixed_queries.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_views import BASE_DIR, REPO_ROOT, read_password  # noqa: E402


def main() -> int:
    queries = json.loads((BASE_DIR / "work" / "fixed_queries.json").read_text(encoding="utf-8"))["queries"]
    password = read_password(REPO_ROOT / "secrets" / ".env")
    failed = 0
    with psycopg.connect(host="localhost", port=5432, dbname="cardlab", user="cardlab",
                         password=password, connect_timeout=5, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
        for q in queries:
            try:
                with conn.transaction():
                    cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier("sql_retriever_user")))
                    # EXPLAIN은 실행 계획만 만들고 쿼리를 실행하지 않음
                    cur.execute("EXPLAIN " + q["sql"])
                    plan = cur.fetchone()[0]
                q["explain"] = "ok"
                print(f"[통과] {q['id']} {q['name']} | {plan[:70]}")
            except psycopg.Error as exc:
                failed += 1
                q["explain"] = f"error: {exc.sqlstate} {str(exc).splitlines()[0]}"
                print(f"[실패] {q['id']} {q['name']} | {q['explain']}")
    out = BASE_DIR / "work" / "fixed_queries.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    data["queries"] = queries
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[결과] {len(queries) - failed}/{len(queries)} 통과 (역할: sql_retriever_user)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
