# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Weekly lunch menu aggregator for restaurants in Torslanda/Amhult, Gothenburg. Scrapes restaurant websites, extracts structured menu data via the Claude Code CLI (`claude -p`), and publishes a static web page via GitHub Pages.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run scraper (all restaurants)
python -m scraper.run

# Run scraper (single restaurant)
python -m scraper.run Golfkrogen

# Serve web page locally
python -m http.server -d web 8000
```

## Architecture

- **`restaurants.json`** — single config file for all restaurants. Adding a restaurant = adding one JSON entry, no code changes.
- **`scraper/fetch.py`** — two strategies: `fetch_text` (requests + BeautifulSoup) for HTML menus, `fetch_image` (Playwright) for image-based menus.
- **`scraper/extract.py`** — calls the Claude Code CLI (`claude -p --model sonnet`) with a structured prompt, returns JSON with days/dishes/prices. For images, saves to a temp file and uses `--allowedTools Read`.
- **`scraper/run.py`** — orchestrator. Loads config, iterates restaurants, calls fetch→extract, writes `data/menus-YYYY-WNN.json` and `web/latest.json`.
- **`web/index.html`** — standalone HTML/CSS/JS page that fetches `latest.json` and renders restaurant cards. Highlights today's menu.
- **`.github/workflows/weekly.yml`** — runs Monday 07:00 Stockholm time, commits new data, deploys `web/` to GitHub Pages.

## Key conventions

- Week format: `YYYY-WNN` (ISO week numbers)
- Menu JSON schema: `{ week, generated, restaurants: [{ name, area, url, days: [{ day, dishes: [{ name, price }] }] }] }`
- Swedish day names: Måndag, Tisdag, Onsdag, Torsdag, Fredag
- The `claude` CLI must be on `$PATH`. This project uses Claude Code for extraction (no direct API key needed locally).
