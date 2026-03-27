#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Setting up virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  playwright install chromium
else
  source .venv/bin/activate
fi

PORT=8000
lsof -ti:$PORT | xargs kill 2>/dev/null

echo "Serving at http://localhost:$PORT"
python3 -m http.server -d web $PORT
