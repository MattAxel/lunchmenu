"""Fetch raw content from restaurant websites."""

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def fetch_text(url: str) -> str:
    """Fetch a text-based menu page and return cleaned text content."""
    resp = requests.get(url, timeout=30)
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
        page.goto(url, wait_until="networkidle", timeout=60000)

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


def fetch_content(restaurant: dict) -> str | bytes:
    """Fetch content based on restaurant type."""
    if restaurant["type"] == "text":
        return fetch_text(restaurant["url"])
    elif restaurant["type"] == "text_js":
        return fetch_text_playwright(restaurant["url"])
    elif restaurant["type"] == "image":
        return fetch_image(restaurant["url"])
    else:
        raise ValueError(f"Unknown restaurant type: {restaurant['type']}")
