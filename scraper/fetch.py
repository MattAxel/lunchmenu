"""Fetch raw content from restaurant websites."""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


# Markers of bot-protection / error interstitials. If we get one of these we
# must fail loudly instead of handing the error page to Grok (which then
# "successfully" extracts 0 days and hides the problem).
BLOCK_MARKERS = (
    "access denied",           # Akamai (ica.se)
    "one moment, please",      # hosting JS challenge (poppels.se, delissimo.se over http)
    "just a moment",           # Cloudflare challenge
    "attention required",      # Cloudflare block
)


class BlockedError(RuntimeError):
    """The site served a bot-protection / error page instead of content."""


def _check_blocked(url: str, status: int | None, title: str = "", body: str = "") -> None:
    """Raise BlockedError if the response is an error or challenge page."""
    title_l = (title or "").strip().lower()
    head_l = (body or "")[:3000].lower()
    marker = next(
        (m for m in BLOCK_MARKERS if m in title_l or f"<title>{m}" in head_l),
        None,
    )
    if status is not None and status >= 400:
        raise BlockedError(
            f"HTTP {status} from {url}" + (f" ({title.strip()})" if title else "")
        )
    if marker:
        raise BlockedError(f"Bot-protection page ('{title.strip() or marker}') from {url}")


def _https(url: str) -> str:
    """Upgrade http:// links to https:// (some hosts only challenge plain http)."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def fetch_text(url: str) -> str:
    """Fetch a text-based menu page and return cleaned text content."""
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    _check_blocked(url, resp.status_code, body=resp.text)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script/style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)


def _dismiss_overlays(page):
    """Dismiss cookie/age banners via JS click."""
    page.evaluate("""
        const texts = [
            'Jag är över 20 år och godkänner',
            'Acceptera alla', 'Acceptera',
            'Godkänn alla', 'Godkänn',
            'Accept all', 'Accept'
        ];
        for (const text of texts) {
            const btn = [...document.querySelectorAll('button')]
                .find(b => b.textContent.includes(text));
            if (btn) { btn.click(); break; }
        }
    """)


def fetch_image(url: str) -> bytes:
    """Use Playwright to load a page with a menu image and capture it."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Pre-set cookie consent for sites that block content without it
        context.add_cookies([{
            "name": "CookieInformationConsent",
            "value": '{"consents_approved":["cookie_cat_necessary","cookie_cat_functional","cookie_cat_statistic","cookie_cat_marketing"],"consents_denied":[]}',
            "domain": f".{domain.replace('www.', '')}",
            "path": "/",
        }])

        page = context.new_page()
        resp = page.goto(url, wait_until="networkidle", timeout=60000)
        try:
            _check_blocked(url, resp.status if resp else None, page.title())
        except BlockedError:
            browser.close()
            raise

        _dismiss_overlays(page)
        page.wait_for_timeout(5000)

        # Scroll down to find menu content
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(2000)

        # Look for a menu image — prioritize weekly menu indicators
        image_selectors = [
            "img[alt*='Meny v']",
            "img[alt*='meny v']",
            "img[alt*='vecka']",
            "img[alt*='lunch']",
            "img[src*='lunch']",
            "img[src*='meny']",
            "img[alt*='meny']",
            "img[src*='menu']",
            "img[alt*='menu']",
        ]

        for selector in image_selectors:
            try:
                img = page.locator(selector).first
                if img.is_visible(timeout=2000):
                    # Download the image directly
                    src = img.get_attribute("src")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(url)
                            src = f"{parsed.scheme}://{parsed.netloc}{src}"

                        img_resp = requests.get(src, timeout=30)
                        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                            browser.close()
                            return img_resp.content
            except Exception:
                continue

        # Fallback: take a screenshot of the main content area
        content_selectors = [
            "main",
            "[class*='content']",
            "[class*='menu']",
            "[class*='cafe']",
            "article",
        ]

        for selector in content_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    screenshot = el.screenshot(type="png")
                    browser.close()
                    return screenshot
            except Exception:
                continue

        # Last resort: full page screenshot
        screenshot = page.screenshot(type="png", full_page=True)
        browser.close()
        return screenshot


def fetch_text_playwright(url: str) -> str:
    """Use Playwright to load a JS-rendered page and return text content."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass  # Some sites never reach networkidle; content is likely loaded

        # Dismiss cookie/age banners by clicking, with JS fallback
        dismissed = False
        for selector in [
            "button:has-text('Jag är över 20 år och godkänner')",
            "button:has-text('Godkänn alla')",
            "button:has-text('Godkänn')",
            "button:has-text('Acceptera alla')",
            "button:has-text('Acceptera')",
            "button:has-text('Accept all')",
            "button:has-text('Accept')",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(force=True)
                    dismissed = True
                    page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        if not dismissed:
            # JS fallback: remove overlay elements
            page.evaluate("""
                document.querySelectorAll(
                    '[id*="cookie"], [class*="cookie"], [id*="consent"], '
                    + '[class*="consent"], [class*="overlay"], [class*="modal"]'
                ).forEach(el => el.remove());
            """)

        page.wait_for_timeout(2000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _canva_design_id(canva_url: str | None) -> str | None:
    import re as _re
    m = _re.search(r"canva\.com/design/([A-Za-z0-9_-]+)", canva_url or "")
    return m.group(1) if m else None


def _discover_canva_url(url: str) -> str:
    """Load the restaurant page and return the embedded Canva view URL."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context()
            ctx.add_cookies([{
                "name": "CookieInformationConsent",
                "value": '{"consents_approved":["cookie_cat_necessary","cookie_cat_functional","cookie_cat_statistic","cookie_cat_marketing"],"consents_denied":[]}',
                "domain": f".{url.split('/')[2].replace('www.', '')}",
                "path": "/",
            }])
            page = ctx.new_page()
            nav_error = None
            resp = None
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                nav_error = exc
            if nav_error is not None and resp is None:
                raise RuntimeError(
                    f"Could not load {url}: {str(nav_error).splitlines()[0]}"
                )
            page.wait_for_timeout(3000)
            _check_blocked(url, resp.status if resp else None, page.title())

            canva_url = page.evaluate("""
            (() => {
                const el = document.querySelector('iframe[data-src*="canva"]')
                        || document.querySelector('iframe[src*="canva"]');
                if (!el) return null;
                const raw = el.getAttribute('data-src') || el.getAttribute('src');
                return raw ? raw.replace('/view?embed', '/view') : null;
            })()
            """)
        finally:
            browser.close()

    if not canva_url:
        raise RuntimeError("No Canva embed found on the page")
    return canva_url


def fetch_canva(url: str, fallback_canva_url: str | None = None) -> str:
    """Fetch text from a menu published as a Canva design.

    1. Try to discover the Canva design URL from the restaurant page
       (*url*). If that fails (site down / blocks our network) and
       *fallback_canva_url* is configured (restaurants.json "canva_url"),
       use that instead. If discovery finds a *different* design than the
       configured one, log it so restaurants.json can be updated.
    2. Open the design's public view URL in a plain, visible (headed)
       Chromium window and read the rendered text in reading order. Canva
       answers headless browsers with a Cloudflare challenge; no stealth
       tweaks are used. Requires a display (DISPLAY, or xvfb-run in CI).
    """
    canva_url = None
    try:
        canva_url = _discover_canva_url(url)
    except Exception as exc:
        if not fallback_canva_url:
            raise
        print(
            f"  Canva lookup on {url} failed ({str(exc)[:160]}); "
            f"using configured canva_url {fallback_canva_url}"
        )
        canva_url = fallback_canva_url
    else:
        found_id = _canva_design_id(canva_url)
        cfg_id = _canva_design_id(fallback_canva_url)
        if cfg_id and found_id and found_id != cfg_id:
            print(
                f"  NOTE: page now embeds Canva design {found_id} "
                f"(restaurants.json canva_url has {cfg_id}) - using the "
                f"page's design; update restaurants.json."
            )

    import os
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "fetch_canva needs a display for a headed browser "
            "(set DISPLAY or run under xvfb-run)"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            resp = None
            try:
                resp = page.goto(canva_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load {canva_url}: {str(exc).splitlines()[0]}"
                ) from exc
            page.wait_for_timeout(10000)
            _check_blocked(canva_url, resp.status if resp else None, page.title())
            text = page.evaluate("document.body ? document.body.innerText : ''")
        finally:
            browser.close()

    if len(text.strip()) < 50:
        raise RuntimeError(f"Canva design {canva_url} rendered no menu text")
    return text


def fetch_pdf(url: str, area: str) -> bytes:
    """Fetch a PDF menu linked from a page, matched by area name.

    Prefer the link's own label and filename. Parent/nav text often lists
    every location (e.g. "ÖJERSJÖ | PARTILLE | … | PLATINAN"), so matching
    on parent alone picks the wrong PDF.
    """
    from urllib.parse import urljoin, urlparse

    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    _check_blocked(url, resp.status_code, body=resp.text)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    area_l = area.lower()
    candidates: list[tuple[int, str, str]] = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.lower().endswith(".pdf"):
            continue
        pdf_url = urljoin(url, href)
        link_text = link.get_text(" ", strip=True)
        filename = urlparse(pdf_url).path.rsplit("/", 1)[-1].lower()
        score = 0
        if area_l in link_text.lower():
            score += 100
        if area_l in filename:
            score += 50
        if score:
            candidates.append((score, pdf_url, link_text))

    if not candidates:
        raise RuntimeError(f"No PDF link found matching area '{area}' on {url}")

    candidates.sort(key=lambda item: (-item[0], item[1]))
    # Delissimo links PDFs as http://; its host answers plain http with a JS
    # bot-challenge HTML page, while https serves the real file.
    pdf_url = _https(candidates[0][1])
    pdf_resp = requests.get(pdf_url, headers=DEFAULT_HEADERS, timeout=30)
    pdf_resp.raise_for_status()
    if not pdf_resp.content.lstrip()[:5] == b"%PDF-":
        _check_blocked(pdf_url, pdf_resp.status_code, body=pdf_resp.text)
        raise RuntimeError(
            f"Expected a PDF from {pdf_url} but got "
            f"{pdf_resp.headers.get('Content-Type', 'unknown')} "
            f"({len(pdf_resp.content)} bytes)"
        )
    return pdf_resp.content


def fetch_text_days(base_url: str, day_paths: list[str]) -> str:
    """Fetch one page per weekday and concatenate with day labels.

    Used when a restaurant publishes lunch on separate day URLs
    (e.g. Masala Corner on masalacorner.se/mandag/ … /fredag/).
    """
    parts: list[str] = []
    day_names = {
        "mandag": "Måndag",
        "måndag": "Måndag",
        "tisdag": "Tisdag",
        "onsdag": "Onsdag",
        "torsdag": "Torsdag",
        "fredag": "Fredag",
    }
    for path in day_paths:
        slug = path.strip("/")
        url = urljoin(base_url if base_url.endswith("/") else base_url + "/", slug + "/")
        label = day_names.get(slug.lower(), slug.capitalize())
        parts.append(f"=== {label} ===\n{fetch_text(url)}")
    return "\n\n".join(parts)



def fetch_content(restaurant: dict) -> str | bytes:
    """Fetch content based on restaurant type."""
    if restaurant["type"] == "text":
        return fetch_text(restaurant["url"])
    elif restaurant["type"] == "text_days":
        return fetch_text_days(restaurant["url"], restaurant["day_paths"])
    elif restaurant["type"] == "text_js":
        return fetch_text_playwright(restaurant["url"])
    elif restaurant["type"] == "image":
        return fetch_image(restaurant["url"])
    elif restaurant["type"] == "canva":
        return fetch_canva(restaurant["url"], restaurant.get("canva_url"))
    elif restaurant["type"] == "pdf":
        return fetch_pdf(restaurant["url"], restaurant["area"])
    else:
        raise ValueError(f"Unknown restaurant type: {restaurant['type']}")
