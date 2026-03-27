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

echo "=== $(date '+%Y-%m-%d %H:%M') ==="

echo "Fetching menus..."
if ! python3 -m scraper.run; then
  echo "FAILED: scraper exited with error"
  exit 1
fi

git add data/ web/latest.json
if git diff --cached --quiet; then
  echo "OK: No changes, nothing to push."
else
  if git commit -m "Update lunch menus $(date +%Y-W%V)" && git push; then
    echo "OK: Pushed to GitHub."
  else
    echo "FAILED: git commit/push failed"
    exit 1
  fi
fi
