#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="/usr/bin/python3"

cd "$PROJECT_DIR"

# Load local environment variables if present (Telegram token/chat_id, etc.)
if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

NOW_HM="$(TZ=Asia/Seoul date +%H%M)"
FORCE_DAILY_SUMMARY="${FORCE_DAILY_SUMMARY:-0}"

if [[ "$NOW_HM" == "0900" || "$FORCE_DAILY_SUMMARY" == "1" ]]; then
  "$PYTHON_BIN" "$PROJECT_DIR/src/auto_run.py" --daily-summary
else
  "$PYTHON_BIN" "$PROJECT_DIR/src/auto_run.py"
fi
