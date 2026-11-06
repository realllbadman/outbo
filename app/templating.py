from datetime import datetime
from typing import List, Optional

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import BASE_DIR, settings

STATIC_DIR = BASE_DIR / "static"
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
CART_COOKIE = "cart"
CART_LIMIT = 50


def money(price: Optional[int]) -> str:
    return "Call for Price" if price is None else f"${price:,}"


def number(value: Optional[int]) -> str:
    return "—" if value is None else f"{value:,}"


def dash(value) -> str:
    return "—" if value in (None, "") else str(value)


def asset(path: str) -> str:
    """URL of a file in static/, stamped with its last-change time so browsers fetch the new version after an edit."""
    try:
        version = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={version}"


def motor_photos(motor) -> List[str]:
    """Photo URLs for a motor (or a motor id); the first is the main one.

    The motor's image_url comes first, then any files in static/motors/<id>/, sorted by filename.
    """
    motor_id = getattr(motor, "id", motor)
    image_url = getattr(motor, "image_url", None)
    photos = [image_url] if image_url else []
    folder = STATIC_DIR / "motors" / str(motor_id)
    if folder.is_dir():
        files = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in PHOTO_EXTENSIONS)
        photos += [f"/static/motors/{motor_id}/{name}" for name in files]
    return photos


def cart_ids(request) -> List[int]:
    """Motor IDs in the visitor's cart cookie. Only IDs are kept there; prices always come from the database."""
    ids = []
    for part in request.cookies.get(CART_COOKIE, "").split(","):
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids[:CART_LIMIT]


def motor_summary(motor) -> str:
    """A plain description built only from the motor's known specs, for when none was written."""
    kind = [
        motor.condition,
        f"{motor.cylinders}-cylinder" if motor.cylinders else None,
        f"{motor.hp} HP",
        f"{motor.stroke}-stroke",
        motor.make,
        motor.model,
    ]
    text = " ".join(part for part in kind if part)
    text = text[0].upper() + text[1:]
    if motor.year:
        text += f" from {motor.year}"
    text += "."
    if motor.shaft:
        text += f" Shaft: {motor.shaft}."
    if motor.hours is not None:
        text += f" Hours: {motor.hours:,}."
    return text


env = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(["html"]),
    cache_size=0,
)
env.filters.update(money=money, number=number, dash=dash)
env.globals.update(asset=asset, biz=settings,motor_photos=motor_photos, motor_summary=motor_summary, cart_ids=cart_ids, current_year=lambda: datetime.now().year)

templates = Jinja2Templates(env=env)
