"""CLI 실행 스크립트. 예: python run_cli.py --member-id M-1001 --question "보유 카드 목록 보여 주세요"."""

import sys

from app.presentation.cli import main

if __name__ == "__main__":
    sys.exit(main())
