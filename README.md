# Lunch Menu

Weekly lunch menu aggregator for restaurants in Gothenburg. Scrapes restaurant websites, extracts structured menu data using the xAI Grok API, and publishes a clean web page via GitHub Pages with day filtering and mobile support.

Supports multiple regions — each region gets its own page and URL.

## Regions

### Torslanda & Amhult

| Name | Area | Method |
|------|------|--------|
| Golfkrogen | Torslanda | Text scraping |
| Restaurang Hörnet | Torslanda | Text scraping |
| Masala Zone | Torslanda | Text scraping |
| Bryggan (ICA Maxi) | Amhult | Image → Grok Vision |
| Masala Corner | Amhult | Text scraping |
| Tsuki Hana | Amhult | Text scraping |
| Tilda & Josper | Amhult | Text scraping |
| Kalimera | Amhult | Text scraping |

### Platinan

| Name | Area | Method |
|------|------|--------|
| Björkmans Skafferi | Platinan | Text scraping (JS) |
| Pagoden | Platinan | Text scraping |
| Poppels Citybryggeriet | Platinan | Manual override |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and set `XAI_API_KEY` (get a key from https://console.x.ai/). Optionally set `XAI_MODEL` (defaults to `grok-4.6`).

```bash
export XAI_API_KEY=your_xai_api_key_here
# optional:
# export XAI_MODEL=grok-4.6
```

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

The workflow deploys `web/` to GitHub Pages on push to `main`. To use it:

1. Add `XAI_API_KEY` as a repository secret if you also run scraping in CI (Settings → Secrets and variables → Actions)
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
- `"text_js"` — uses Playwright for JS-rendered pages, then extracts text
- `"image"` — uses Playwright to capture menu image, then Grok vision to read it
- `"pdf"` — downloads a PDF, extracts text with pypdf, then Grok; scanned PDFs should use `"image"` instead

For restaurants that can't be scraped automatically, place a text file in `data/overrides/{restaurant-slug}.txt` with the menu text. The scraper will use the override instead of fetching.

## Adding a new region

1. Add restaurants to `restaurants.json` with the new `region` value
2. Create `web/{region}/index.html` (copy from an existing region page and adjust the title)
3. Add a link to the new region on `web/index.html`
