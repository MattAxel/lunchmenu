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

echo "Fetching menus..."
python3 -m scraper.run

git add data/ web/latest.json
if git diff --cached --quiet; then
  echo "No changes, nothing to push."
else
  git commit -m "Update lunch menus $(date +%Y-W%V)"
  git push
  echo "Pushed to GitHub."
fi
