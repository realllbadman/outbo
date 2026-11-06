from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import ENQUIRY_STATUSES, MOTOR_STATUSES, Enquiry, Motor
from app.templating import motor_photos, templates

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("")
def enquiries(request: Request, status: str = "", db: Session = Depends(get_db)):
    query = select(Enquiry).order_by(Enquiry.created_at.desc(), Enquiry.id.desc())
    if status in ENQUIRY_STATUSES:
        query = query.where(Enquiry.status == status)
    else:
        status = ""
    counts = dict(db.execute(select(Enquiry.status, func.count()).group_by(Enquiry.status)).all())
    return templates.TemplateResponse(
        request,
        "admin/enquiries.html",
        {
            "enquiries": db.scalars(query).all(),
            "counts": counts,
            "total": sum(counts.values()),
            "statuses": ENQUIRY_STATUSES,
            "current": status,
        },
    )


def get_enquiry(enquiry_id: int, db: Session) -> Enquiry:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404)
    return enquiry


@router.get("/enquiry/{enquiry_id}")
def enquiry_detail(request: Request, enquiry_id: int, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "admin/enquiry.html",
        {"enquiry": get_enquiry(enquiry_id, db), "statuses": ENQUIRY_STATUSES},
    )


@router.post("/enquiry/{enquiry_id}")
def update_enquiry(
    enquiry_id: int,
    status: str = Form(...),
    internal_notes: str = Form(""),
    db: Session = Depends(get_db),
):
    if status not in ENQUIRY_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status")
    enquiry = get_enquiry(enquiry_id, db)
    enquiry.status = status
    enquiry.internal_notes = internal_notes.strip() or None
    db.commit()
    return RedirectResponse(f"/admin/enquiry/{enquiry_id}", status_code=303)


@router.get("/motors")
def motors(request: Request, status: str = "", saved: Optional[int] = None, db: Session = Depends(get_db)):
    every = db.scalars(select(Motor).order_by(Motor.id)).all()
    if status not in MOTOR_STATUSES:
        status = ""
    rows = [m for m in every if not status or m.status == status]
    counts = {s: sum(1 for m in every if m.status == s) for s in MOTOR_STATUSES}
    photos = {m.id: motor_photos(m) for m in rows}
    return templates.TemplateResponse(
        request,
        "admin/motors.html",
        {
            "motors": rows,
            "photos": photos,
            "counts": counts,
            "total": len(every),
            "current": status,
            "saved_motor": next((m for m in every if m.id == saved), None),
        },
    )


def parse_motor_form(form) -> tuple:
    """Return (values, errors). Blank optional fields become None, so the site shows "—"."""
    values = {}
    errors = {}

    for field in ("name", "make"):
        values[field] = form.get(field, "").strip()
        if not values[field]:
            errors[field] = "Required."
    for field in ("model", "shaft", "notes", "description", "condition", "badge", "image_url"):
        values[field] = form.get(field, "").strip() or None
    if values["image_url"] and not valid_image_url(values["image_url"]):
        errors["image_url"] = "Enter a web address starting with https://"

    for field in ("year", "hours", "price_usd", "hp", "cylinders"):
        raw = form.get(field, "").strip().replace(",", "").lstrip("$")
        if not raw:
            values[field] = None
        elif raw.isdigit():
            values[field] = int(raw)
        else:
            values[field] = raw
            errors[field] = "Enter a whole number."
    if not values["hp"] and "hp" not in errors:
        errors["hp"] = "Required."

    stroke = form.get("stroke", "")
    values["stroke"] = int(stroke) if stroke in ("2", "4") else None
    if values["stroke"] is None:
        errors["stroke"] = "Choose 2 or 4."

    values["status"] = form.get("status", "in_stock")
    if values["status"] not in MOTOR_STATUSES:
        errors["status"] = "Unknown status."
    return values, errors


def render_motor_form(request: Request, motor: Optional[dict], motor_id: Optional[int], errors: dict, status_code=200):
    return templates.TemplateResponse(
        request,
        "admin/motor_form.html",
        {"motor": motor or {}, "motor_id": motor_id, "errors": errors, "statuses": MOTOR_STATUSES},
        status_code=status_code,
    )


@router.get("/motors/new")
def new_motor(request: Request):
    return render_motor_form(request, {"status": "in_stock", "condition": "Used"}, None, {})


@router.post("/motors/new")
async def create_motor(request: Request, db: Session = Depends(get_db)):
    values, errors = parse_motor_form(await request.form())
    if errors:
        return render_motor_form(request, values, None, errors, status_code=400)
    motor = Motor(**values)
    db.add(motor)
    db.commit()
    return RedirectResponse(f"/admin/motors?saved={motor.id}#motor-{motor.id}", status_code=303)


def get_motor(motor_id: int, db: Session) -> Motor:
    motor = db.get(Motor, motor_id)
    if motor is None:
        raise HTTPException(status_code=404)
    return motor


@router.get("/motors/{motor_id}/edit")
def edit_motor(request: Request, motor_id: int, db: Session = Depends(get_db)):
    return render_motor_form(request, get_motor(motor_id, db), motor_id, {})


@router.post("/motors/{motor_id}/edit")
async def save_motor(request: Request, motor_id: int, db: Session = Depends(get_db)):
    motor = get_motor(motor_id, db)
    values, errors = parse_motor_form(await request.form())
    if errors:
        return render_motor_form(request, values, motor_id, errors, status_code=400)
    for field, value in values.items():
        setattr(motor, field, value)
    db.commit()
    return RedirectResponse(f"/admin/motors?saved={motor_id}#motor-{motor_id}", status_code=303)


def valid_image_url(url: str) -> bool:
    return url.lower().startswith(("https://", "http://")) and len(url) <= 500 and " " not in url


@router.get("/photos")
def photos(request: Request, saved: Optional[int] = None, did: str = "saved", db: Session = Depends(get_db)):
    rows = db.scalars(select(Motor).order_by(Motor.id)).all()
    return render_photos(request, rows, saved=saved, did="removed" if did == "removed" else "saved")


def render_photos(request: Request, rows, saved=None, did="saved", error_id=None, error_value="", status_code=200):
    uses = {}
    for m in rows:
        if m.image_url:
            uses.setdefault(m.image_url, []).append(m.id)
    shared = {m.id: [i for i in uses[m.image_url] if i != m.id] for m in rows if m.image_url and len(uses[m.image_url]) > 1}
    groups = {}  # brand -> motors, in order of first appearance
    for m in rows:
        groups.setdefault(m.make, []).append(m)
    by_id = {m.id: m for m in rows}
    return templates.TemplateResponse(
        request,
        "admin/photos.html",
        {
            "motors": rows,
            "groups": list(groups.items()),
            "shared": shared,
            "missing": sum(1 for m in rows if not m.image_url),
            "saved_motor": by_id.get(saved),
            "did": did,
            "error_id": error_id,
            "error_value": error_value,
        },
        status_code=status_code,
    )


@router.post("/photos/{motor_id}")
def save_photo(request: Request, motor_id: int, image_url: str = Form(""), action: str = Form("save"), db: Session = Depends(get_db)):
    motor = get_motor(motor_id, db)
    url = image_url.strip()
    if action == "remove":
        motor.image_url = None
    elif not valid_image_url(url):
        rows = db.scalars(select(Motor).order_by(Motor.id)).all()
        return render_photos(request, rows, error_id=motor_id, error_value=url, status_code=400)
    else:
        motor.image_url = url
    db.commit()
    did = "removed" if action == "remove" else "saved"
    return RedirectResponse(f"/admin/photos?saved={motor_id}&did={did}#motor-{motor_id}", status_code=303)


@router.post("/motors/{motor_id}/sold")
def mark_sold(motor_id: int, db: Session = Depends(get_db)):
    motor = get_motor(motor_id, db)
    motor.status = "sold"
    db.commit()
    return RedirectResponse(f"/admin/motors?saved={motor_id}#motor-{motor_id}", status_code=303)
