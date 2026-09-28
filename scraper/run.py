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


IMAGE_OVERRIDE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
OVERRIDE_EXTS = (".txt",) + IMAGE_OVERRIDE_EXTS


def _find_override(name: str) -> Path | None:
    """Return data/overrides/<slug>.{txt,png,jpg,jpeg,webp} if present."""
    slug = _slug(name)
    for ext in OVERRIDE_EXTS:
        for candidate in (OVERRIDES_DIR / f"{slug}{ext}",
                          OVERRIDES_DIR / f"{slug}{ext.upper()}"):
            if candidate.exists():
                return candidate
    return None


def _check_week(menu_data: dict, expected_week: str, require: bool) -> None:
    """Reject menus whose printed week number isn't the current ISO week."""
    expected_no = int(expected_week.split("-W")[1])
    found = menu_data.get("week")
    try:
        found_no = int(found) if found is not None else None
    except (TypeError, ValueError):
        found_no = None
    if found_no is None:
        if require:
            raise RuntimeError(
                f"No week number found in source (expected week {expected_no})"
            )
        print(f"  WARNING: no week number in source; assuming week {expected_no}")
        return
    if found_no != expected_no:
        raise RuntimeError(
            f"Source menu is for week {found_no}, expected week {expected_no}"
        )
    print(f"  Week check OK (week {found_no}).")


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

    existing_ok = {
        r["name"] for r in existing["restaurants"] if "error" not in r
    }

    for restaurant in restaurants:
        print(f"--- {restaurant['name']} ({restaurant['area']}) ---")

        # Skip if already fetched successfully this week (unless filtering)
        if restaurant["name"] in existing_ok and not restaurant_filter:
            print("  Already fetched this week, skipping.")
            continue

        # Remove old entry if re-fetching (kept aside: if the re-fetch
        # fails, a good entry from earlier this week is restored instead of
        # being replaced by an error).
        previous_ok = next(
            (r for r in existing["restaurants"]
             if r["name"] == restaurant["name"]
             and "error" not in r and r.get("days")),
            None,
        )
        existing["restaurants"] = [
            r for r in existing["restaurants"]
            if r["name"] != restaurant["name"]
        ]

        # Check for manual override file (.txt menu text or a menu image)
        override_file = _find_override(restaurant["name"])
        use_override = override_file is not None
        if use_override:
            print(f"  Using override file: {override_file.name}")
        override_is_image = (
            use_override and override_file.suffix.lower() in IMAGE_OVERRIDE_EXTS
        )

        # Week check: always for image overrides (a stale photo from last
        # week must not be republished); opt-in per restaurant via
        # "week_check": true in restaurants.json.
        week_check = override_is_image or (
            restaurant.get("week_check", False) and not use_override
        )
        expected_week = week_label if week_check else None

        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                if override_is_image:
                    content = override_file.read_bytes()
                elif use_override:
                    content = override_file.read_text(encoding="utf-8")
                else:
                    print(f"  Fetching from {restaurant['url']}...")
                    content = fetch_content(restaurant)
                content_desc = (
                    f"{len(content)} chars" if isinstance(content, str)
                    else f"{len(content)} bytes"
                )
                print(f"  Got {content_desc}. Extracting menu...")

                if override_is_image:
                    from scraper.extract import extract_menu_from_image
                    menu_data = extract_menu_from_image(
                        content, restaurant["name"], expected_week
                    )
                elif use_override:
                    from scraper.extract import extract_menu_from_text
                    menu_data = extract_menu_from_text(content, restaurant["name"])
                else:
                    menu_data = extract_menu(content, restaurant, expected_week)

                if expected_week:
                    _check_week(
                        menu_data, expected_week,
                        # Configured restaurants always print a week number;
                        # a user-supplied photo might not, so only reject a
                        # mismatch there.
                        require=not override_is_image,
                    )

                days = menu_data.get("days", []) or []
                if not days:
                    # Don't record an empty menu as success: it hides blocked
                    # pages / wrong images and prevents a retry next run.
                    raise RuntimeError("No menu days extracted from source")
                entry = {
                    "name": restaurant["name"],
                    "area": restaurant["area"],
                    "region": restaurant.get("region", "torslanda"),
                    "url": restaurant["url"],
                    "days": days,
                }
                existing["restaurants"].append(entry)
                print(f"  Extracted {len(entry['days'])} days.")
                break

            except Exception as e:
                if attempt < max_retries:
                    print(f"  Attempt {attempt} failed: {e}. Retrying...")
                    continue
                print(f"  ERROR: {e}")
                if previous_ok is not None:
                    print("  Keeping this week's previously fetched menu.")
                    existing["restaurants"].append(previous_ok)
                    break
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
