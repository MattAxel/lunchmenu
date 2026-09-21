# GROK.md

Guidance for working with this repository when using xAI Grok for menu extraction.

## Project

Weekly lunch menu aggregator for restaurants in Gothenburg, supporting multiple regions. Scrapes restaurant websites, extracts structured menu data via the xAI Grok API (`https://api.x.ai/v1/chat/completions`), and publishes static web pages via GitHub Pages.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
export XAI_API_KEY=your_xai_api_key_here

# Run scraper (all restaurants)
python -m scraper.run

# Run scraper (single restaurant)
python -m scraper.run Golfkrogen

# Serve web page locally
python -m http.server -d web 8000
```

## Architecture

- **`restaurants.json`** — single config file for all restaurants. Each entry has a `region` field that determines which subdirectory it appears in.
- **`scraper/fetch.py`** — two strategies: `fetch_text` (requests + BeautifulSoup) for HTML menus, `fetch_image` (Playwright) for image-based menus.
- **`scraper/extract.py`** — calls the xAI Grok chat completions API (OpenAI-compatible) with a structured system prompt, returns JSON with days/dishes/prices. Text uses system+user messages; images are sent as base64 data URLs (multimodal); PDFs use `pypdf` text extraction first.
- **`scraper/run.py`** — orchestrator. Loads config, iterates restaurants, calls fetch→extract, writes `data/menus-YYYY-WNN.json` and splits output to `web/{region}/latest.json`.
- **`web/index.html`** — landing page linking to each region.
- **`web/{region}/index.html`** — standalone HTML/CSS/JS page that fetches `latest.json` and renders restaurant cards. Highlights today's menu.
- **`.github/workflows/weekly.yml`** — deploys `web/` to GitHub Pages on push to `main` (and manual dispatch).

## Key conventions

- Week format: `YYYY-WNN` (ISO week numbers)
- Menu JSON schema: `{ week, generated, restaurants: [{ name, area, region, url, days: [{ day, dishes: [{ name, price }] }] }] }`
- Regions: each restaurant belongs to a `region` (e.g. `torslanda`, `platinan`) which maps to `web/{region}/`
- Swedish day names: Måndag, Tisdag, Onsdag, Torsdag, Fredag
- Auth: set `XAI_API_KEY` in the environment (required). Optional `XAI_MODEL` defaults to `grok-4.6`.
