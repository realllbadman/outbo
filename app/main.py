import logging
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import emails
from app.admin import router as admin_router
from app.auth import router as login_router
from app.config import settings
from app.db import get_db
from app.forms import EMAIL_RE, ZIP_RE, one_line, parse_int
from app.models import Enquiry, Motor
from app.seed import init_db
from app.shop import PAYMENT_METHODS, router as shop_router
from app.templating import STATIC_DIR, templates

logging.basicConfig(level=logging.INFO)

# (label, title, photo, hp_min, hp_max). Also drives the home page sections and the HP filter.
SERIES = (
    ("High Power", "Serious Power", "wake-rear-dark.jpg", 150, None),
    ("Mid Range", "All-Round Range", "harbor-boats.jpg", 60, 149),
    ("Small Motors", "Small and Simple", "golden-hour-boat.jpg", None, 59),
)


HOME_FEATURED = 9  # motor cards on the home page (three rows on a laptop)
SERIES_PREVIEW = 5  # motors listed beside each photo section on the home page


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.business_name, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(login_router)
app.include_router(admin_router)
app.include_router(shop_router)


@app.exception_handler(404)
def not_found(request: Request, exc: Exception):
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)


def in_stock():
    return select(Motor).where(Motor.status == "in_stock").order_by(Motor.id)


def filter_url(filters: dict, **changes) -> str:
    query = {key: value for key, value in {**filters, **changes}.items() if value}
    return f"/motors?{urlencode(query)}" if query else "/motors"


def build_series(motors) -> list:
    """Home page sections, using the real stock. Empty series are left out."""
    series = []
    for label, title, image, hp_min, hp_max in SERIES:
        members = [
            m for m in motors
            if (hp_min is None or m.hp >= hp_min) and (hp_max is None or m.hp <= hp_max)
        ]
        if members:
            series.append(
                {
                    "label": label,
                    "title": title,
                    "image": image,
                    "motors": sorted(members, key=lambda m: -m.hp),
                    "hp_low": min(m.hp for m in members),
                    "hp_high": max(m.hp for m in members),
                    "url": filter_url({}, hp_min=str(hp_min or ""), hp_max=str(hp_max or "")),
                }
            )
    return series


def build_filter_rows(filters: dict, brands, cylinder_counts) -> list:
    def option(label, **changes):
        active = all(filters[key] == value for key, value in changes.items())
        return {"label": label, "url": filter_url(filters, **changes), "active": active}

    hp_options = [option("All", hp_min="", hp_max="")]
    for label, _, _, hp_min, hp_max in SERIES:
        low, high = str(hp_min or ""), str(hp_max or "")
        span = f"{hp_min}+ HP" if hp_max is None else f"under {hp_max + 1} HP" if hp_min is None else f"{hp_min}–{hp_max} HP"
        hp_options.append(option(f"{label} ({span})", hp_min=low, hp_max=high))
    rows = [
        {"label": "Horse power", "options": hp_options},
        {
            "label": "Technology",
            "options": [option("All", stroke=""), option("Four Stroke", stroke="4"), option("Two Stroke", stroke="2")],
        },
    ]
    if cylinder_counts:
        rows.append(
            {
                "label": "Cylinders",
                "options": [option("All", cylinders="")]
                + [option(f"{count}-Cylinder", cylinders=str(count)) for count in cylinder_counts],
            }
        )
    rows.append({"label": "Brand", "options": [option("All", brand="")] + [option(b, brand=b) for b in brands]})
    return rows


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    motors = db.scalars(in_stock()).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "motors": motors,
            # A short selection on the home page; the full list is one click away on /motors.
            "featured": sorted(motors, key=lambda m: (-(m.year or 0), -m.hp))[:HOME_FEATURED],
            "strip": sorted(motors, key=lambda m: -m.hp)[:3],
            "series": build_series(motors),
            "series_preview": SERIES_PREVIEW,
            "hp_low": min((m.hp for m in motors), default=None),
            "hp_high": max((m.hp for m in motors), default=None),
        },
    )


@app.get("/motors")
def motors(
    request: Request,
    brand: str = "",
    stroke: str = "",
    cylinders: str = "",
    hp_min: str = "",
    hp_max: str = "",
    db: Session = Depends(get_db),
):
    # Query params stay strings because the filter form submits empty values for unset fields.
    query = in_stock()
    if brand:
        query = query.where(Motor.make == brand)
    if parse_int(stroke) in (2, 4):
        query = query.where(Motor.stroke == int(stroke))
    if parse_int(cylinders) is not None:
        query = query.where(Motor.cylinders == int(cylinders))
    if parse_int(hp_min) is not None:
        query = query.where(Motor.hp >= int(hp_min))
    if parse_int(hp_max) is not None:
        query = query.where(Motor.hp <= int(hp_max))

    brands = db.scalars(select(Motor.make).where(Motor.status == "in_stock").distinct().order_by(Motor.make)).all()
    cylinder_counts = db.scalars(
        select(Motor.cylinders)
        .where(Motor.status == "in_stock", Motor.cylinders.is_not(None))
        .distinct()
        .order_by(Motor.cylinders)
    ).all()
    filters = {"brand": brand, "stroke": stroke, "cylinders": cylinders, "hp_min": hp_min, "hp_max": hp_max}
    return templates.TemplateResponse(
        request,
        "motors.html",
        {"motors": db.scalars(query).all(), "filter_rows": build_filter_rows(filters, brands, cylinder_counts)},
    )


@app.get("/motors/{motor_id}")
def motor_detail(request: Request, motor_id: int, db: Session = Depends(get_db)):
    motor = db.get(Motor, motor_id)
    if motor is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "motor_detail.html", {"motor": motor, "similar": similar_motors(db, motor)}
    )


def similar_motors(db: Session, motor: Motor, limit: int = 3) -> list:
    """In-stock motors closest in power, preferring the same stroke and brand."""
    others = db.scalars(in_stock().where(Motor.id != motor.id)).all()

    def distance(other: Motor) -> float:
        score = abs(other.hp - motor.hp) / max(motor.hp, 1)
        if other.stroke != motor.stroke:
            score += 0.5
        if other.make != motor.make:
            score += 0.15
        return score

    return sorted(others, key=lambda other: (distance(other), other.id))[:limit]


@app.get("/quote")
def quote_form(request: Request, motor: str = "", db: Session = Depends(get_db)):
    motor_id = parse_int(motor)
    selected = db.get(Motor, motor_id) if motor_id is not None else None
    values = {"motor_of_interest": selected.name if selected else ""}
    return templates.TemplateResponse(request, "quote.html", {"values": values, "errors": {}})


@app.post("/quote")
def submit_quote(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    motor_of_interest: str = Form(""),
    message: str = Form(""),
    shipping_zip: str = Form(""),
    website: str = Form(""),
    db: Session = Depends(get_db),
):
    # "website" is a hidden honeypot field: only bots fill it in.
    if website:
        return RedirectResponse("/quote/thanks", status_code=303)

    values = {
        "name": one_line(name, 120),
        "email": one_line(email, 200),
        "phone": one_line(phone, 40),
        "motor_of_interest": one_line(motor_of_interest, 200),
        "message": message.strip()[:5000],
        "shipping_zip": one_line(shipping_zip, 10),
    }

    errors = {}
    if not values["name"]:
        errors["name"] = "Please enter your name."
    if not EMAIL_RE.fullmatch(values["email"]):
        errors["email"] = "Please enter a valid email address."
    if not values["phone"]:
        errors["phone"] = "Please enter a phone or WhatsApp number."
    if not values["message"]:
        errors["message"] = "Please tell us what you need."
    if values["shipping_zip"] and not ZIP_RE.fullmatch(values["shipping_zip"]):
        errors["shipping_zip"] = "Please enter a 5-digit US ZIP, or leave this blank."
    if errors:
        return templates.TemplateResponse(
            request, "quote.html", {"values": values, "errors": errors}, status_code=400
        )

    enquiry = Enquiry(**{**values, "motor_of_interest": values["motor_of_interest"] or None, "shipping_zip": values["shipping_zip"] or None})
    db.add(enquiry)
    db.commit()

    known_motor = db.scalar(select(Motor.name).where(Motor.name == values["motor_of_interest"]))
    background_tasks.add_task(emails.notify_enquiry, {**values, "id": enquiry.id}, known_motor)
    return RedirectResponse("/quote/thanks", status_code=303)


@app.get("/quote/thanks")
def quote_thanks(request: Request):
    return templates.TemplateResponse(request, "quote_done.html", {})


@app.get("/shipping")
def shipping(request: Request):
    return templates.TemplateResponse(request, "shipping.html", {})


@app.get("/financing")
def financing(request: Request):
    return templates.TemplateResponse(request, "financing.html", {"payment_methods": PAYMENT_METHODS})


@app.get("/about")
def about(request: Request, db: Session = Depends(get_db)):
    motors = db.scalars(in_stock()).all()
    brands = {}
    for m in motors:
        brands[m.make] = brands.get(m.make, 0) + 1
    return templates.TemplateResponse(
        request,
        "about.html",
        {
            "motor_count": len(motors),
            "brands": sorted(brands.items(), key=lambda item: -item[1]),
            "hp_low": min((m.hp for m in motors), default=None),
            "hp_high": max((m.hp for m in motors), default=None),
        },
    )


@app.get("/contact")
def contact(request: Request):
    return templates.TemplateResponse(request, "contact.html", {})
