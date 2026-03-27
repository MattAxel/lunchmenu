"""Extract structured menu data using the Claude Code CLI."""

import json
import os
import subprocess
import tempfile

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


def extract_menu_from_text(text: str, restaurant_name: str) -> dict:
    """Extract menu from text content using Claude Code CLI."""
    prompt = (
        f"Extract the lunch menu for '{restaurant_name}' from this text:\n\n"
        f"{text[:8000]}"
    )
    return _call_claude(prompt)


def extract_menu_from_image(image_bytes: bytes, restaurant_name: str) -> dict:
    """Extract menu from an image using Claude Code CLI's vision capability."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif image_bytes[:4] == b"RIFF":
        ext = ".webp"
    else:
        ext = ".png"

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(image_bytes)
        tmp.close()
        prompt = (
            f"Read the image file at {tmp.name} and extract the lunch menu "
            f"for '{restaurant_name}' from it."
        )
        return _call_claude(prompt, allowed_tools="Read")
    finally:
        os.unlink(tmp.name)


def extract_menu(content: str | bytes, restaurant: dict) -> dict:
    """Extract menu based on content type."""
    if restaurant["type"] == "text":
        return extract_menu_from_text(content, restaurant["name"])
    elif restaurant["type"] == "image":
        return extract_menu_from_image(content, restaurant["name"])
    else:
        raise ValueError(f"Unknown type: {restaurant['type']}")


def _call_claude(prompt: str, allowed_tools: str | None = None) -> dict:
    """Call the Claude Code CLI and return parsed menu JSON."""
    cmd = [
        "claude",
        "-p",
        "--output-format", "json",
        "--no-session-persistence",
        "--bare",
        "--model", "sonnet",
        "--system-prompt", SYSTEM_PROMPT,
    ]
    if allowed_tools:
        cmd.extend(["--allowedTools", allowed_tools])

    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): {result.stderr}"
        )

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"claude CLI returned invalid JSON.\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )
    text = envelope.get("result", "").strip()

    # Try to extract JSON from the response — it may be wrapped in
    # markdown fences or preceded by explanatory text
    import re
    # First try: extract from code fences
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        # Second try: find the first { ... } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Failed to parse menu JSON from Claude response.\n"
            f"Raw result text: {envelope.get('result', '')[:500]}"
        )
