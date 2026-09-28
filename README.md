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
| Bryggan (ICA Maxi) | Amhult | Menu image (`img[alt^="meny v."]`) → Grok Vision, week-checked |
| Masala Corner | Amhult | Text scraping |
| Tsuki Hana | Amhult | Text scraping |
| Tilda & Josper | Amhult | Text scraping |
| Kalimera | Amhult | Text scraping |

### Platinan

| Name | Area | Method |
|------|------|--------|
| Björkmans Skafferi | Platinan | Text scraping (JS) |
| Pagoden | Platinan | Text scraping |
| Poppels Citybryggeriet | Platinan | Canva design (headed browser) → Grok, week-checked |

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

Restaurants that already have a good menu for the current week are skipped. Re-fetch some anyway (a failed re-fetch keeps the existing menu):
```bash
python -m scraper.run --force Bryggan,Poppels   # or --force all (also via $SCRAPER_FORCE)
```

Poppels (Canva) needs a display for its headed browser; on a headless machine use `xvfb-run -a python -m scraper.run`.

Start the web server:
```bash
./serve.sh
# Open http://localhost:8000
```

Output goes to `data/menus-YYYY-WNN.json` and `web/{region}/latest.json`.

## GitHub Actions

- **Scrape Lunch Menus** (`.github/workflows/scrape.yml`) runs every Monday at 05:37 UTC (07:37 Stockholm summer / 06:37 winter) with a retry run at 08:07 UTC (10:07 / 09:07). The retry only fetches restaurants that are still missing or failed. It runs `xvfb-run … python -m scraper.run` with `TZ=Europe/Stockholm` and commits `data/` and `web/*/latest.json` as github-actions[bot] if anything besides the timestamp changed. Run it manually from the Actions tab (**Run workflow**). The optional `force` input (`all` or e.g. `Bryggan,Poppels`) re-fetches restaurants that are already done. Screenshots and the log are uploaded as a `scraper-debug-*` artifact when the run fails or a restaurant has an error.
- **Deploy Lunch Menu** (`.github/workflows/weekly.yml`) deploys `web/` from the tip of `main` to GitHub Pages on push to `main`, and also after a successful scrape run. That second trigger is needed because commits pushed with `GITHUB_TOKEN` don't trigger `push` workflows.

Setup: add the `XAI_API_KEY` repository secret (Settings → Secrets and variables → Actions) and set Pages to use GitHub Actions as its source.

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
- `"text"` — plain HTTP fetch of a single menu page
- `"text_days"` — fetches separate weekday pages under one site (e.g. Masala Corner) and extracts the full week
- `"text_js"` — uses Playwright for JS-rendered pages, then extracts text
- `"image"` — loads the page with Playwright, downloads the menu `<img>` (first `img[alt^="meny v." i]`, then generic menu selectors, then a screenshot as a last resort), then Grok vision reads it. With `"week_check": true`, a week number in the alt text or file name (e.g. `meny v.40`) must match the current week.
- `"pdf"` — downloads a PDF, extracts text with pypdf, then Grok; scanned PDFs should use `"image"` instead

- `"canva"` — finds the Canva embed on the restaurant page and reads the design's text in a plain visible Chromium window (Canva challenges headless browsers; needs a display, e.g. `xvfb-run` in CI). Optional `"canva_url"` is used when the page can't be loaded (e.g. Poppels blocks our network); if the page embeds a different design than `canva_url`, a NOTE is logged.

Optional `"week_check": true` passes the current ISO week to the extraction prompt and rejects the result unless the source prints that week number (catches stale menus and "next week" pages).

### Manual overrides

For restaurants that can't be scraped automatically, put a file in `data/overrides/` named after the restaurant slug (lowercase, spaces → `-`, `&` removed, e.g. `bryggan`, `poppels-citybryggeriet`). The scraper uses it instead of fetching:

- `{slug}.txt` — menu text, extracted like a text page.
- `{slug}.png` / `.jpg` / `.jpeg` / `.webp` — a photo/screenshot of the menu, extracted with Grok vision. Image overrides are always week-checked: if the image shows a different week number (e.g. last week's photo left behind) the run fails for that restaurant instead of republishing a stale menu. Replace or delete the file each week.

If a re-run fails for a restaurant that already has a good menu for the current week, the existing menu is kept.

## Adding a new region

1. Add restaurants to `restaurants.json` with the new `region` value
2. Create `web/{region}/index.html` (copy from an existing region page and adjust the title)
3. Add a link to the new region on `web/index.html`
