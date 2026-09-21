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
- Include prices when visible (format: "125 kr")
- If no price is found for a dish, set price to null
- If a day has no dishes, omit that day
- Only include this week's menu, not previous weeks
- If dishes are NOT assigned to specific days (e.g. numbered 1-6 with "Mån-Fre"), list ALL dishes under EVERY weekday
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
    """Extract menu from a PDF by pulling text with pypdf, then calling Grok."""
    text = _extract_pdf_text(pdf_bytes)
    if len(text.strip()) < MIN_PDF_TEXT_CHARS:
        raise RuntimeError(
            "PDF text extraction returned little or no text (likely a scanned "
            "image PDF). Re-scrape this restaurant as type 'image' instead, "
            "or provide a text override under data/overrides/."
        )
    return extract_menu_from_text(text, restaurant_name)


def extract_menu(content: str | bytes, restaurant: dict) -> dict:
    """Extract menu based on content type."""
    if restaurant["type"] in ("text", "text_js", "canva"):
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
