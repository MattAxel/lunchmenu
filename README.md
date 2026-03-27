# Lunch Menu — Torslanda & Amhult

Weekly lunch menu aggregator for restaurants in Torslanda and Amhult, Gothenburg.

Fetches menus every Monday, extracts structured data using the Claude Code CLI, and publishes a clean web page via GitHub Pages.

## Restaurants

| Name | Area | Method |
|------|------|--------|
| Golfkrogen | Torslanda | Text scraping |
| Bryggan (ICA Maxi) | Amhult | Image → Claude Vision |

Add new restaurants by editing `restaurants.json` — no code changes needed.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Make sure `claude` (Claude Code CLI) is on your `$PATH` and authenticated.

## Usage

Fetch all restaurants:
```bash
python -m scraper.run
```

Fetch a single restaurant:
```bash
python -m scraper.run Golfkrogen
```

Output goes to `data/menus-YYYY-WNN.json` and `web/latest.json`.

Open `web/index.html` in a browser to view the result.

## GitHub Actions

The workflow runs every Monday at 07:00 Stockholm time. To use it:

1. Push to GitHub
2. Add `ANTHROPIC_API_KEY` as a repository secret (used by the Claude Code CLI in CI)
3. Enable GitHub Pages (Settings → Pages → Source: GitHub Actions)
4. The workflow can also be triggered manually from the Actions tab

## Adding a restaurant

Add an entry to `restaurants.json`:

```json
{
  "name": "Restaurant Name",
  "url": "https://example.com/lunch",
  "type": "text",
  "area": "Torslanda"
}
```

Supported types:
- `"text"` — fetches HTML and extracts text
- `"image"` — uses Playwright to capture menu image, then Claude Code CLI to read it
