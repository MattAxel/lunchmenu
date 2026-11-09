"""Publish a hand-entered weekly menu (e.g. from an email) for one restaurant.

The restaurant must exist in restaurants.json (normally with "type": "manual",
which the scraper never fetches or overwrites). The entry is merged into
data/menus-<week>.json, replacing any earlier entry for that restaurant, and
web/<region>/latest.json is regenerated when <week> is the week shown there
(or newer).

Items are given as lines "Dish text" or "Dish text | price", either on the
command line (--item, repeatable), in a text file (--items-file, one per
line; '-' = stdin) or as JSON (--items-json: a list of strings or of
{"name": ..., "price": ...}). By default the same weekly items are listed on
every weekday Monday-Friday; --days limits that.

Example:
  python -m scraper.manual_entry "Ahlströms Konditori" --week 2026-W46 \\
      --item "Veckans soppa: Tomatsoppa" \\
      --item "Veckans varma: Tuna melt | 125 kr"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
RESTAURANTS_FILE = ROOT / "restaurants.json"
WEEKDAYS = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag"]


def current_week_label() -> str:
    year, week, _ = datetime.now().isocalendar()
    return f"{year}-W{week:02d}"


def _parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    name, _, price = line.partition("|")
    dish = {"name": name.strip()}
    if price.strip():
        dish["price"] = price.strip()
    return dish


def parse_items(args) -> list[dict]:
    dishes: list[dict] = []
    for line in args.item or []:
        if (d := _parse_line(line)):
            dishes.append(d)
    if args.items_file:
        text = (sys.stdin.read() if args.items_file == "-"
                else Path(args.items_file).read_text(encoding="utf-8"))
        dishes += [d for d in map(_parse_line, text.splitlines()) if d]
    if args.items_json:
        raw = args.items_json
        if Path(raw).is_file():
            raw = Path(raw).read_text(encoding="utf-8")
        for it in json.loads(raw):
            if isinstance(it, str):
                if (d := _parse_line(it)):
                    dishes.append(d)
            else:
                d = {"name": str(it["name"]).strip()}
                if it.get("price"):
                    d["price"] = str(it["price"]).strip()
                dishes.append(d)
    return dishes


def find_restaurant(query: str) -> dict:
    restaurants = json.loads(RESTAURANTS_FILE.read_text(encoding="utf-8"))
    exact = [r for r in restaurants if r["name"].lower() == query.lower()]
    matches = exact or [r for r in restaurants
                        if query.lower() in r["name"].lower()]
    if len(matches) != 1:
        sys.exit(f"Expected exactly one restaurant matching '{query}', "
                 f"found: {[r['name'] for r in matches]}")
    return matches[0]


def publish(restaurant: dict, week: str, dishes: list[dict],
            days: list[str]) -> None:
    week_file = DATA_DIR / f"menus-{week}.json"
    data = {"week": week, "generated": "", "restaurants": []}
    if week_file.exists():
        data = json.loads(week_file.read_text(encoding="utf-8"))

    entry = {
        "name": restaurant["name"],
        "area": restaurant["area"],
        "region": restaurant.get("region", "torslanda"),
        "url": restaurant["url"],
        "days": [{"day": d, "dishes": [dict(x) for x in dishes]} for d in days],
    }
    if restaurant.get("type") == "manual":
        entry["manual"] = True

    # Replace any earlier entry (placeholder or older version); keep order.
    others = [r for r in data["restaurants"] if r["name"] != restaurant["name"]]
    idx = next((i for i, r in enumerate(data["restaurants"])
                if r["name"] == restaurant["name"]), len(others))
    others.insert(min(idx, len(others)), entry)
    data["restaurants"] = others
    data["week"] = week
    data["generated"] = datetime.now().isoformat(timespec="seconds")

    week_file.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"Saved {restaurant['name']} ({len(days)} days x {len(dishes)} "
          f"items) to {week_file.relative_to(ROOT)}")

    region = entry["region"]
    region_file = WEB_DIR / region / "latest.json"
    shown_week = None
    if region_file.exists():
        shown_week = json.loads(region_file.read_text(encoding="utf-8")).get("week")
    if shown_week and shown_week > week:
        print(f"{region_file.relative_to(ROOT)} shows {shown_week}; "
              "not touching it.")
        return
    # Regenerate every region's latest.json from the week file (same as the
    # scraper does).
    regions: dict[str, list] = {}
    for r in data["restaurants"]:
        regions.setdefault(r.get("region", "torslanda"), []).append(r)
    for reg, rs in regions.items():
        f = WEB_DIR / reg / "latest.json"
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps({"week": data["week"],
                                 "generated": data["generated"],
                                 "restaurants": rs},
                                ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"Updated {f.relative_to(ROOT)}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Publish a hand-entered weekly menu for one restaurant.")
    p.add_argument("restaurant", help="restaurant name (or unique part of it)")
    p.add_argument("--week", default=current_week_label(),
                   help="ISO week, e.g. 2026-W46 (default: current week)")
    p.add_argument("--item", action="append",
                   help='"Dish text" or "Dish text | price" (repeatable)')
    p.add_argument("--items-file", help="text file, one item per line ('-' = stdin)")
    p.add_argument("--items-json", help="JSON list (inline or a file path)")
    p.add_argument("--days", default=",".join(WEEKDAYS),
                   help="comma list of weekdays to list the items on "
                        "(default: Måndag-Fredag)")
    args = p.parse_args()

    if not (len(args.week) == 8 and args.week[4:6] == "-W"
            and args.week[:4].isdigit() and args.week[6:].isdigit()):
        sys.exit(f"--week must look like 2026-W46, got '{args.week}'")
    days = [d.strip().capitalize() for d in args.days.split(",") if d.strip()]
    bad = [d for d in days if d not in WEEKDAYS]
    if bad:
        sys.exit(f"Unknown weekday(s): {bad}; use {WEEKDAYS}")
    dishes = parse_items(args)
    if not dishes:
        sys.exit("No items given (use --item, --items-file or --items-json)")
    publish(find_restaurant(args.restaurant), args.week, dishes, days)


if __name__ == "__main__":
    main()
