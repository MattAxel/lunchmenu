# Lunch Menu

Weekly lunch menu aggregator for restaurants in Gothenburg. Scrapes restaurant websites, extracts structured menu data using the Claude Code CLI, and publishes a clean web page via GitHub Pages with day filtering and mobile support.

Supports multiple regions — each region gets its own page and URL.

## Regions

### Torslanda & Amhult

| Name | Area | Method |
|------|------|--------|
| Golfkrogen | Torslanda | Text scraping |
| Restaurang Hörnet | Torslanda | Text scraping |
| Masala Zone | Torslanda | Text scraping |
| Bryggan (ICA Maxi) | Amhult | Image → Claude Vision |
| Masala Corner | Amhult | Text scraping |
| Tsuki Hana | Amhult | Text scraping |
| Tilda & Josper | Amhult | Text scraping |
| Kalimera | Amhult | Text scraping |

### Platinan

Coming soon.

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

Output goes to `data/menus-YYYY-WNN.json` and `web/{region}/latest.json`.

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
  "area": "Platinan",
  "region": "platinan"
}
```

- `area` — displayed as a badge on the web page
- `region` — determines which subdirectory the restaurant appears in (`web/{region}/`)

Supported types:
- `"text"` — fetches HTML and extracts text
- `"image"` — uses Playwright to capture menu image, then Claude Code CLI to read it

## Adding a new region

1. Add restaurants to `restaurants.json` with the new `region` value
2. Create `web/{region}/index.html` (copy from an existing region page and adjust the title)
3. Add a link to the new region on `web/index.html`
