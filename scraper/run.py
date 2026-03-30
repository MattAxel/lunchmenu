"""Orchestrate menu fetching and extraction, save results."""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from scraper.fetch import fetch_content
from scraper.extract import extract_menu

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OVERRIDES_DIR = DATA_DIR / "overrides"
WEB_DIR = ROOT / "web"
RESTAURANTS_FILE = ROOT / "restaurants.json"


def _slug(name: str) -> str:
    """Convert restaurant name to a filename slug."""
    return name.lower().replace(" ", "-").replace("&", "").replace("--", "-")


def current_week_label() -> str:
    """Return the current ISO week label, e.g. '2026-W13'."""
    now = datetime.now()
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def run(restaurant_filter: str | None = None):
    """Fetch and extract menus for all (or one) restaurant(s)."""
    DATA_DIR.mkdir(exist_ok=True)

    with open(RESTAURANTS_FILE) as f:
        restaurants = json.load(f)

    if restaurant_filter:
        restaurants = [
            r for r in restaurants
            if restaurant_filter.lower() in r["name"].lower()
        ]
        if not restaurants:
            print(f"No restaurant matching '{restaurant_filter}'")
            sys.exit(1)

    week_label = current_week_label()
    output_file = DATA_DIR / f"menus-{week_label}.json"

    # Load existing data if we're adding to it
    existing = {"week": week_label, "generated": "", "restaurants": []}
    if output_file.exists():
        with open(output_file) as f:
            existing = json.load(f)

    existing_names = {r["name"] for r in existing["restaurants"]}

    for restaurant in restaurants:
        print(f"--- {restaurant['name']} ({restaurant['area']}) ---")

        # Skip if already fetched this week (unless filtering)
        if restaurant["name"] in existing_names and not restaurant_filter:
            print("  Already fetched this week, skipping.")
            continue

        # Remove old entry if re-fetching
        existing["restaurants"] = [
            r for r in existing["restaurants"]
            if r["name"] != restaurant["name"]
        ]

        # Check for manual override file
        override_file = OVERRIDES_DIR / f"{_slug(restaurant['name'])}.txt"
        use_override = override_file.exists()
        if use_override:
            print(f"  Using override file: {override_file.name}")

        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                if use_override:
                    content = override_file.read_text(encoding="utf-8")
                else:
                    print(f"  Fetching from {restaurant['url']}...")
                    content = fetch_content(restaurant)
                content_desc = (
                    f"{len(content)} chars" if isinstance(content, str)
                    else f"{len(content)} bytes"
                )
                print(f"  Got {content_desc}. Extracting menu...")

                if use_override:
                    from scraper.extract import extract_menu_from_text
                    menu_data = extract_menu_from_text(content, restaurant["name"])
                else:
                    menu_data = extract_menu(content, restaurant)

                entry = {
                    "name": restaurant["name"],
                    "area": restaurant["area"],
                    "region": restaurant.get("region", "torslanda"),
                    "url": restaurant["url"],
                    "days": menu_data.get("days", []),
                }
                existing["restaurants"].append(entry)
                print(f"  Extracted {len(entry['days'])} days.")
                break

            except Exception as e:
                if attempt < max_retries:
                    print(f"  Attempt {attempt} failed: {e}. Retrying...")
                    continue
                print(f"  ERROR: {e}")
                existing["restaurants"].append({
                    "name": restaurant["name"],
                    "area": restaurant["area"],
                    "region": restaurant.get("region", "torslanda"),
                    "url": restaurant["url"],
                    "days": [],
                    "error": str(e),
                })

    existing["generated"] = datetime.now().isoformat(timespec="seconds")
    existing["week"] = week_label

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_file}")

    # Split by region and write to web/{region}/latest.json
    regions = {}
    for r in existing["restaurants"]:
        region = r.get("region", "torslanda")
        regions.setdefault(region, []).append(r)

    for region, region_restaurants in regions.items():
        region_dir = WEB_DIR / region
        region_dir.mkdir(exist_ok=True)
        region_data = {
            "week": existing["week"],
            "generated": existing["generated"],
            "restaurants": region_restaurants,
        }
        region_file = region_dir / "latest.json"
        with open(region_file, "w", encoding="utf-8") as f:
            json.dump(region_data, f, ensure_ascii=False, indent=2)
        print(f"Copied to {region_file}")


if __name__ == "__main__":
    # Optional: pass a restaurant name to fetch only that one
    filter_name = sys.argv[1] if len(sys.argv) > 1 else None
    run(filter_name)
