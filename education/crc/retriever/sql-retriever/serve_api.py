"""API 서버 실행 스크립트. 예: python serve_api.py → http://127.0.0.1:8000/v1/sql-retriever/search."""

import argparse

import uvicorn

from app.bootstrap import configure_logging
from app.presentation.api import create_app


def main() -> None:
    """uvicorn으로 API 서버를 띄움. 기본 주소는 127.0.0.1:8000(사용자 답)."""
    parser = argparse.ArgumentParser(description="SQL 검색기 API 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    configure_logging()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
