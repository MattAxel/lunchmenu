# Lunch Menu — Torslanda & Amhult

Weekly lunch menu aggregator for restaurants in Torslanda and Amhult, Gothenburg.

Scrapes restaurant websites every Monday, extracts structured menu data using the Claude Code CLI, and publishes a clean web page via GitHub Pages with day filtering and mobile support.

## Restaurants

| Name | Area | Method |
|------|------|--------|
| Golfkrogen | Torslanda | Text scraping |
| Restaurang Hörnet | Torslanda | Text scraping |
| Masala Zone | Torslanda | Text scraping |
| Bryggan (ICA Maxi) | Amhult | Image → Claude Vision |
| Masala Corner | Amhult | Text scraping |
| Tsuki Hana | Amhult | Text scraping |
| Tilda & Josper | Amhult | Text scraping |

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

Start the web server:
```bash
./serve.sh
# Open http://localhost:8000
```

Output goes to `data/menus-YYYY-WNN.json` and `web/latest.json`.

## GitHub Actions

The workflow runs every Monday at 07:00 Stockholm time. To use it:

1. Add `ANTHROPIC_API_KEY` as a repository secret (Settings → Secrets and variables → Actions)
2. Enable GitHub Pages (Settings → Pages → Source: GitHub Actions)
3. The workflow can also be triggered manually from the Actions tab

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
