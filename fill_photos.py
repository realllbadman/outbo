"""Give every motor its own photo from Wikimedia Commons (free-to-use images).

    .venv/bin/python fill_photos.py           # show which photo each motor would get, changes nothing
    .venv/bin/python fill_photos.py --apply   # save the photo links (backs up outboard.db first)

Photos come from each brand's "outboard motors" category on Commons, and no photo is used twice.
Logos, diagrams, cutaways and close-ups of parts are skipped. When a brand runs out of photos,
the rest of its motors get general outboard motor photos instead (the script says which ones).
Needs an internet connection.
"""
import argparse
import json
import re
import shutil
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "outboard-listing-demo/1.0 (local student project)"
THUMB_WIDTH = 900

BRAND_CATEGORIES = {
    "yamaha": "Category:Yamaha outboard motors",
    "mercury": "Category:Mercury outboard motors",
    "suzuki": "Category:Suzuki outboard motors",
    "honda": "Category:Honda outboard motors",
    "evinrude": "Category:Evinrude outboard motors",
    "johnson": "Category:Johnson outboard motors",
    "tohatsu": "Category:Tohatsu outboard motors",
    "selva": "Category:Selva outboard motors",
}
FALLBACK_CATEGORY = "Category:Outboard motors"

# Files and subcategories whose names contain these are not photos of a motor.
SKIP_WORDS = (
    "logo", "diagram", "drawing", "schematic", "cutaway", "cut model", "cut-model", "plate", "label",
    "interior", "sump", "manual", "advert", "brochure", "poster", "catalog", "map", "sticker",
    "carburet", "propeller", "fuel cooler", "vst", "gearbox", "lower unit", "piston", "badge", "emblem",
    "johnson electric", "schraube",
)
# Old photos and museum pieces look wrong next to a used-motor listing from the 1990s onwards.
VINTAGE_WORDS = ("fortepan", "national archives", "museum", "curioseum", "pc-3", " p7", "hurricane", "antique", "vintage")
# Photos of whole boats or harbours, where the motor is small.
SCENE_WORDS = ("boats", "harbour", "harbor", "port of", "marina", "sailing school", "river", "lake", "beach", "dog")
# Subcategories of boats, ships and people: the motor is usually a small part of those photos.
SKIP_SUBCATEGORY_WORDS = (
    "boat", "ship", "vessel", "craft", "rhib", "dinghies", "dinghy", "inflatable", "yacht", "kayak",
    "canoe", "people", "racing", "in use", "military", "navy", "coast guard", "rescue",
)
# Words in a file title that say the photo is of a motor (several languages appear on Commons).
MOTOR_WORDS = ("outboard", "motor", "engine", "außenbord", "aussenbord", "hors-bord", "moteur", "fuoribordo", "perämoottori")
TWO_STROKE_HINTS =("2-stroke", "two-stroke", "2 stroke", "e-tec", "etec", "optimax", "enduro")
FOUR_STROKE_HINTS = ("4-stroke", "four-stroke", "4 stroke", "fourstroke", "verado", "df", " bf", "f1", "f2", "f3", "mfs")

Fetch = Callable[[dict], dict]


def use_ipv4_only() -> None:
    """Many home networks have no working IPv6 route ("Network is unreachable"); browsers fall back
    to IPv4 on their own, but Python may not, so only hand it IPv4 addresses."""
    original = socket.getaddrinfo

    def ipv4_getaddrinfo(host, port, family=0, *args, **kwargs):
        return original(host, port, socket.AF_INET, *args, **kwargs)

    socket.getaddrinfo = ipv4_getaddrinfo


def http_fetch(params: dict, retries: int = 6) -> dict:
    """One API call, spaced out and retried, because Commons limits how fast clients may ask."""
    query = urlencode({**params, "format": "json", "formatversion": "2", "maxlag": "5"})
    request = Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        time.sleep(1.0)
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 503) or attempt == retries - 1:
                raise
            wait = error.headers.get("Retry-After", "")
            time.sleep(int(wait) if wait.isdigit() else 5 * (attempt + 1))
        except (URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise OSError("Wikimedia Commons kept refusing requests")


def paged(fetch: Fetch, params: dict) -> Iterable[dict]:
    """Yield every response page, following the API's 'continue' markers."""
    extra = {}
    while True:
        data = fetch({**params, **extra})
        yield data
        if "continue" not in data:
            return
        extra = data["continue"]


def skip_name(name: str) -> bool:
    lowered = name.lower().replace("_", " ")
    return any(word in lowered for word in SKIP_WORDS)


def subcategories(fetch: Fetch, category: str) -> List[str]:
    found = []
    params = {"action": "query", "list": "categorymembers", "cmtitle": category, "cmtype": "subcat", "cmlimit": "500"}
    for data in paged(fetch, params):
        for member in data.get("query", {}).get("categorymembers", []):
            title = member["title"]
            if not skip_name(title) and not any(word in title.lower() for word in SKIP_SUBCATEGORY_WORDS):
                found.append(title)
    return found


def category_photos(fetch: Fetch, category: str) -> List[dict]:
    """Photos directly in a category: [{title, url, category}]."""
    photos = []
    params = {
        "action": "query", "generator": "categorymembers", "gcmtitle": category, "gcmtype": "file",
        "gcmlimit": "200", "prop": "imageinfo", "iiprop": "url|mime|size", "iiurlwidth": str(THUMB_WIDTH),
    }
    for data in paged(fetch, params):
        for page in data.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            title = page.get("title", "")
            if info.get("mime") not in ("image/jpeg", "image/png") or skip_name(title):
                continue
            if info.get("width", 0) < 500 or info.get("height", 0) < 400:
                continue
            url = info.get("thumburl") or info.get("url")
            if url:
                photos.append({"title": title, "url": url, "category": category})
    return photos


def collect(fetch: Fetch, category: str, depth: int = 2, limit: int = 400) -> List[dict]:
    """Photos in a category and its subcategories (breadth first), without duplicates."""
    seen_categories, seen_urls, photos = set(), set(), []
    level = [category]
    for current_depth in range(depth + 1):
        next_level = []
        for cat in level:
            if cat in seen_categories:
                continue
            seen_categories.add(cat)
            for photo in category_photos(fetch, cat):
                if photo["url"] not in seen_urls:
                    seen_urls.add(photo["url"])
                    photos.append(photo)
            if len(photos) >= limit:
                return photos
            if current_depth < depth:
                next_level += subcategories(fetch, cat)
        level = next_level
    return photos


def brands_for(make: str) -> List[str]:
    lowered = make.lower()
    return [brand for brand in BRAND_CATEGORIES if brand in lowered]


def score(photo: dict, motor: dict) -> int:
    text = f"{photo['title']} {photo['category']}".lower().replace("_", " ")
    title = photo["title"].lower().replace("_", " ")
    points = 0
    # Most important: the photo is of a motor, ideally naming the motor's brand.
    if any(brand in title for brand in brands_for(motor["make"])):
        points += 5
    if any(word in title for word in MOTOR_WORDS):
        points += 4
    if re.search(rf"(?<!\d){motor['hp']}(?!\d)", text):
        points += 3
    if motor.get("model") and motor["model"].lower() in text:
        points += 3
    hints = TWO_STROKE_HINTS if motor["stroke"] == 2 else FOUR_STROKE_HINTS
    other = FOUR_STROKE_HINTS if motor["stroke"] == 2 else TWO_STROKE_HINTS
    if any(hint in text for hint in hints):
        points += 2
    if any(hint in text for hint in other):
        points -= 2
    if re.search(r"\b19[0-7]\d\b", title) or any(word in title for word in VINTAGE_WORDS):
        points -= 8
    if any(word in title for word in SCENE_WORDS):
        points -= 4
    return points


def assign(motors: List[dict], pools: Dict[str, List[dict]], fallback: List[dict]) -> Dict[int, Optional[dict]]:
    """Pick a different photo for every motor: best-scoring unused photo of its brand, else a general one."""
    used = set()
    chosen: Dict[int, Optional[dict]] = {}
    for motor in sorted(motors, key=lambda m: m["id"]):
        candidates = [p for brand in brands_for(motor["make"]) for p in pools.get(brand, []) if p["url"] not in used]
        if not candidates:
            candidates = [p for p in fallback if p["url"] not in used]
        if not candidates:
            chosen[motor["id"]] = None
            continue
        best = max(candidates, key=lambda p: score(p, motor))  # max keeps the first of equal scores
        used.add(best["url"])
        chosen[motor["id"]] = best
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Give every motor its own Wikimedia Commons photo.")
    parser.add_argument("--apply", action="store_true", help="save the photo links (without this, only shows them)")
    parser.add_argument("--cache", help="JSON file to keep the Commons photo lists in, so a second run needs no lookups")
    args = parser.parse_args()
    use_ipv4_only()

    from app.db import SessionLocal
    from app.models import Motor
    from app.seed import init_db

    init_db()
    with SessionLocal() as db:
        rows = db.query(Motor).order_by(Motor.id).all()
        motors = [{"id": m.id, "make": m.make, "model": m.model, "hp": m.hp, "stroke": m.stroke} for m in rows]
        needed = {brand for m in motors for brand in brands_for(m["make"])}

        cache = Path(args.cache) if args.cache else None
        if cache and cache.exists():
            saved = json.loads(cache.read_text())
            pools, fallback = saved["pools"], saved["fallback"]
            print(f"Using the photo lists saved in {cache}")
        else:
            try:
                pools = {}
                for brand in sorted(needed):
                    print(f"Looking up {brand} photos...", flush=True)
                    pools[brand] = collect(http_fetch, BRAND_CATEGORIES[brand])
                    print(f"  found {len(pools[brand])}")
                print("Looking up general outboard photos (used when a brand runs out)...", flush=True)
                fallback = collect(http_fetch, FALLBACK_CATEGORY, depth=1)
                print(f"  found {len(fallback)}")
            except OSError as error:
                print(f"Couldn't reach Wikimedia Commons ({error}). Check the internet connection and try again.")
                return 1
            if cache:
                cache.write_text(json.dumps({"pools": pools, "fallback": fallback}))

        chosen = assign(motors, pools, fallback)
        general, missing = [], []
        print()
        for m in rows:
            photo = chosen[m.id]
            if photo is None:
                missing.append(m.id)
                print(f"  #{m.id:<3} {m.name}: no photo left")
                continue
            if not any(photo in pools.get(b, []) for b in brands_for(m.make)):
                general.append(m.id)
            print(f"  #{m.id:<3} {m.name}\n        {photo['title']}")

        print(f"\n{len(rows) - len(missing)} of {len(rows)} motors get their own photo.")
        if general:
            ids = ", ".join(f"#{i}" for i in general)
            print(f"{len(general)} of those got a general outboard photo because their brand ran out: {ids}")
        if not args.apply:
            print("Nothing was changed. Run again with --apply to save these photos.")
            return 0

        db_file = Path(__file__).with_name("outboard.db")
        if db_file.exists():
            backup = db_file.with_name(f"outboard-before-photos-{datetime.now():%Y%m%d-%H%M%S}.db")
            shutil.copy2(db_file, backup)
            print(f"Backed up the database to {backup.name}")
        for m in rows:
            if chosen[m.id] is not None:
                m.image_url = chosen[m.id]["url"]
        db.commit()
        print("Saved. Restart the site to be safe, then refresh the page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
