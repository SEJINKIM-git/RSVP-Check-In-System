#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
APP_URL="http://127.0.0.1:8000/checkin/"

cd "$SCRIPT_DIR"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Missing virtual environment Python at:"
  echo "  $VENV_PYTHON"
  echo
  echo "Create the virtual environment and install dependencies first."
  read -k 1 "?Press any key to close this window..."
  echo
  exit 1
fi

echo "Starting RSVP Check-In System..."
echo "Project: $SCRIPT_DIR"
echo "Website: $APP_URL"
echo

open "$APP_URL"
exec "$VENV_PYTHON" manage.py runserver 127.0.0.1:8000
