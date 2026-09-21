"""Extract structured menu data using the xAI Grok API."""

import base64
import json
import os
import re

import requests

SYSTEM_PROMPT = """You are a lunch menu extractor for Swedish restaurants.
Extract the weekly lunch menu and return ONLY valid JSON with this structure:

{
  "days": [
    {
      "day": "Måndag",
      "dishes": [
        {"name": "Dish name in Swedish", "price": "125 kr"}
      ]
    }
  ]
}

Rules:
- Use Swedish day names: Måndag, Tisdag, Onsdag, Torsdag, Fredag
- Include prices when visible (format: "125 kr" or "115kr" normalized to "115 kr")
- If no price is found for a dish, set price to null
- If a day has no dishes, omit that day
- Only include this week's menu, not previous weeks
- Keep dish names faithful to the source: include the dish title AND the key sides/description as written. Do not invent shorter marketing titles, and do not drop the descriptive part when the source has one.
- Extract only that day's lunch specials. Do NOT copy "always available" / standing alternatives (e.g. a permanent Caesar salad, house burger, or "stående alternativ") onto each weekday unless that day explicitly lists them among the daily specials.
- "Veckans" items in a shared weekly box (pizza/salad sold every day) may be listed under every weekday.
- If dishes are clearly one shared weekly set with NO day labels (e.g. numbered 1-6 with only "Mån-Fre"), list ALL of those under EVERY weekday
- Never invent dishes that are not visible in the source
- Return ONLY the JSON, no other text"""

XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4.6"
MIN_PDF_TEXT_CHARS = 50


def extract_menu_from_text(text: str, restaurant_name: str) -> dict:
    """Extract menu from text content using the xAI Grok API."""
    prompt = (
        f"Extract the lunch menu for '{restaurant_name}' from this text:\n\n"
        f"{text[:8000]}"
    )
    return _call_grok([{"type": "text", "text": prompt}])


def extract_menu_from_image(image_bytes: bytes, restaurant_name: str) -> dict:
    """Extract menu from an image using Grok vision (multimodal)."""
    mime = _detect_image_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    prompt = (
        f"Extract the lunch menu for '{restaurant_name}' from this image."
    )
    return _call_grok(
        [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    )


def extract_menu_from_pdf(pdf_bytes: bytes, restaurant_name: str) -> dict:
    """Extract menu from a PDF via text when clean, else Grok vision on pages.

    Designed menus (e.g. Delissimo) often yield jumbled pypdf text; rendering
    pages to images and using vision is more reliable then.
    """
    text = _extract_pdf_text(pdf_bytes)
    if _pdf_text_looks_usable(text):
        return extract_menu_from_text(text, restaurant_name)

    images = _render_pdf_pages(pdf_bytes)
    if not images:
        if len(text.strip()) >= MIN_PDF_TEXT_CHARS:
            return extract_menu_from_text(text, restaurant_name)
        raise RuntimeError(
            "PDF text was unusable and page rendering failed. "
            "Re-scrape as type 'image' or add data/overrides/."
        )

    # One vision call with up to first 2 pages (weekly lunch fits on 1)
    content = [
        {
            "type": "text",
            "text": (
                f"Extract the lunch menu for '{restaurant_name}' from these "
                f"PDF page image(s). Ignore decorative repeated logos."
            ),
        }
    ]
    for image_bytes in images[:2]:
        mime = _detect_image_mime(image_bytes)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return _call_grok(content)


def _pdf_text_looks_usable(text: str) -> bool:
    """Reject decorative/jumbled PDF text that confuses day assignment."""
    cleaned = text.strip()
    if len(cleaned) < MIN_PDF_TEXT_CHARS:
        return False
    # Delissimo-style PDFs repeat the brand hundreds of times as vector text
    brand_hits = cleaned.lower().count("delissimo")
    if brand_hits >= 20:
        return False
    letters = sum(ch.isalpha() for ch in cleaned)
    if letters and brand_hits / max(letters / 10, 1) > 5:
        return False
    return True


def _render_pdf_pages(pdf_bytes: bytes, scale: float = 2.0) -> list[bytes]:
    """Render PDF pages to PNG bytes using pypdfium2."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "pypdfium2 is required to render PDF pages for vision extraction"
        ) from exc

    from io import BytesIO

    pdf = pdfium.PdfDocument(pdf_bytes)
    images: list[bytes] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            buf = BytesIO()
            pil_image.save(buf, format="PNG")
            images.append(buf.getvalue())
            page.close()
    finally:
        pdf.close()
    return images


def extract_menu(content: str | bytes, restaurant: dict) -> dict:
    """Extract menu based on content type."""
    if restaurant["type"] in ("text", "text_days", "text_js", "canva"):
        return extract_menu_from_text(content, restaurant["name"])
    elif restaurant["type"] == "image":
        return extract_menu_from_image(content, restaurant["name"])
    elif restaurant["type"] == "pdf":
        return extract_menu_from_pdf(content, restaurant["name"])
    else:
        raise ValueError(f"Unknown type: {restaurant['type']}")


def _detect_image_mime(image_bytes: bytes) -> str:
    """Return a MIME type for common image formats."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    # Fallback: treat unknown as PNG (Playwright screenshots are usually PNG)
    return "image/png"


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text)
    return "\n\n".join(parts)


def _parse_menu_json(text: str) -> dict:
    """Parse menu JSON from model output, stripping fences/extra prose."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)
    return json.loads(text)


def _call_grok(user_content, max_retries: int = 3) -> dict:
    """Call the xAI Grok chat completions API and return parsed menu JSON.

    Retries up to *max_retries* times on parse failures (the most
    common transient error) without re-fetching the page content.
    """
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "XAI_API_KEY is not set. Export it in your environment "
            "(see .env.example) before running the scraper."
        )

    model = os.environ.get("XAI_MODEL", DEFAULT_MODEL)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                XAI_API_URL, headers=headers, json=payload, timeout=120
            )
        except requests.RequestException as exc:
            last_error = RuntimeError(f"Grok API request failed: {exc}")
            continue

        if resp.status_code != 200:
            last_error = RuntimeError(
                f"Grok API failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )
            continue

        try:
            data = resp.json()
        except json.JSONDecodeError:
            last_error = RuntimeError(
                f"Grok API returned invalid JSON.\nbody: {resp.text[:500]}"
            )
            continue

        try:
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                # Some multimodal responses may return content parts
                if isinstance(text, list):
                    text = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in text
                    )
                else:
                    text = str(text)
        except (KeyError, IndexError, TypeError) as exc:
            last_error = RuntimeError(
                f"Unexpected Grok API response shape: {exc}\n"
                f"body: {json.dumps(data)[:500]}"
            )
            continue

        try:
            return _parse_menu_json(text)
        except json.JSONDecodeError:
            last_error = RuntimeError(
                f"Failed to parse menu JSON from Grok response "
                f"(attempt {attempt}/{max_retries}).\n"
                f"Raw content: {text[:500]}"
            )

    raise last_error
