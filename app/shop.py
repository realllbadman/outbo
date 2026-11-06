import re
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import emails
from app.db import get_db
from app.forms import EMAIL_RE, ZIP_RE, one_line
from app.models import Motor
from app.templating import CART_COOKIE, CART_LIMIT, cart_ids, templates

# Checkout is a request-to-buy flow. Customers choose a preferred payment method,
# then the business receives the order request by email and follows up to process it.
PAYMENTS_CONNECTED = True

# (value, label, detail)
# (value, label, detail). The customer picks one; we send the payment details when we confirm the order.
PAYMENT_METHODS = (
    ("cash_app", "Cash App", "Pay from your Cash App. We send our $Cashtag when we confirm your order."),
    ("zelle", "Zelle", "Pay from your bank's app. We send our Zelle details when we confirm your order."),
    ("apple_pay", "Apple Pay", "On iPhone, iPad or Mac."),
    ("chime", "Chime", "Pay from your Chime account with Pay Anyone, or use your Chime debit card."),
    ("bank_transfer", "Bank-to-bank transfer (US)", "ACH or wire from your US bank account. We send our bank details when we confirm your order."),
    ("venmo", "Venmo", "Pay from your Venmo app. We send our Venmo username when we confirm your order."),
    ("paypal", "PayPal", "Paid as Goods & Services, so the purchase is covered by PayPal Purchase Protection."),
    ("eu_bank_transfer", "European bank transfer (SEPA)", "For buyers paying from a bank account in Europe. We send our IBAN when we confirm your order."),
    ("card", "Credit or debit card", "Visa, Mastercard, American Express and Discover."),
    ("google_pay", "Google Pay", "On Android or in Chrome."),
)

CONTACT_PREFERENCES = ("Phone", "Email", "Text")

# (value, label, hint). Where the freight truck is going changes the price, so the buyer must choose one.
DELIVERY_TYPES = (
    ("residential", "Home", "The truck lowers the crate with a liftgate."),
    ("business", "Business", "Has a loading dock or forklift."),
    ("marina", "Marina or boat yard", "Staff can unload the crate."),
    ("terminal", "Freight terminal pickup", "Collect from the carrier's depot. Often cheapest."),
    ("local_pickup", "Local pickup", "Collect from us in person."),
)

US_STATES = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
).split()

router = APIRouter()


def payment_label(value: str) -> str:
    lookup = {item[0]: item[1] for item in PAYMENT_METHODS}
    return lookup.get(value, value.replace("_", " ").title())


def buyable():
    return select(Motor).where(Motor.status == "in_stock", Motor.price_usd.is_not(None))


def cart_motors(db: Session, ids: List[int]) -> List[Motor]:
    """The cart's motors that can still be bought, in the order they were added."""
    found = {m.id: m for m in db.scalars(buyable().where(Motor.id.in_(ids)))}
    return [found[i] for i in ids if i in found]


def with_cart(response, ids: List[int]):
    if ids:
        response.set_cookie(CART_COOKIE, ",".join(map(str, ids[:CART_LIMIT])), max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax")
    else:
        response.delete_cookie(CART_COOKIE)
    return response


@router.get("/cart")
def cart(request: Request, db: Session = Depends(get_db)):
    ids = cart_ids(request)
    motors = cart_motors(db, ids)
    response = templates.TemplateResponse(
        request,
        "cart.html",
        {"motors": motors, "subtotal": sum(m.price_usd for m in motors), "dropped": len(ids) - len(motors)},
    )
    # Sold or unpriced motors drop out of the cart.
    return with_cart(response, [m.id for m in motors]) if len(motors) != len(ids) else response


@router.post("/cart/add")
def add_to_cart(request: Request, motor_id: int = Form(...), db: Session = Depends(get_db)):
    if db.scalar(buyable().where(Motor.id == motor_id)) is None:
        return RedirectResponse(f"/motors/{motor_id}", status_code=303)
    ids = cart_ids(request)
    if motor_id not in ids:
        ids.append(motor_id)
    return with_cart(RedirectResponse("/cart", status_code=303), ids)


@router.post("/cart/remove")
def remove_from_cart(request: Request, motor_id: int = Form(...)):
    ids = [i for i in cart_ids(request) if i != motor_id]
    return with_cart(RedirectResponse("/cart", status_code=303), ids)


def render_checkout(request: Request, motors: List[Motor], values: dict, errors: dict, status_code=200, attempted=False):
    return templates.TemplateResponse(
        request,
        "checkout.html",
        {
            "motors": motors,
            "subtotal": sum(m.price_usd for m in motors),
            "values": values,
            "errors": errors,
            "payment_methods": PAYMENT_METHODS,
            "delivery_types": DELIVERY_TYPES,
            "contact_preferences": CONTACT_PREFERENCES,
            "states": US_STATES,
            "payments_connected": PAYMENTS_CONNECTED,
            "attempted": attempted,
        },
        status_code=status_code,
    )


@router.get("/checkout")
def checkout(request: Request, db: Session = Depends(get_db)):
    motors = cart_motors(db, cart_ids(request))
    if not motors:
        return RedirectResponse("/cart", status_code=303)
    return render_checkout(request, motors, {"payment_method": PAYMENT_METHODS[0][0]}, {})


@router.post("/checkout")
def submit_checkout(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    address2: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    shipping_zip: str = Form(""),
    delivery_type: str = Form(""),
    payment_method: str = Form(""),
    contact_preference: str = Form(""),
    best_time: str = Form(""),
    db: Session = Depends(get_db),
):
    motors = cart_motors(db, cart_ids(request))
    if not motors:
        return RedirectResponse("/cart", status_code=303)

    values = {
        "name": one_line(name, 120),
        "email": one_line(email, 200),
        "phone": one_line(phone, 40),
        "address": one_line(address, 200),
        "address2": one_line(address2, 200),
        "city": one_line(city, 100),
        "state": one_line(state, 2).upper(),
        "shipping_zip": one_line(shipping_zip, 10),
        "delivery_type": delivery_type,
        "payment_method": payment_method,
        "contact_preference": contact_preference if contact_preference in CONTACT_PREFERENCES else CONTACT_PREFERENCES[0],
        "best_time": one_line(best_time, 100),
    }
    errors = {}
    for field, message in (
        ("name", "Please enter your name."),
        ("phone", "Please enter a phone number."),
        ("address", "Please enter the delivery address."),
        ("city", "Please enter the city."),
    ):
        if not values[field]:
            errors[field] = message
    if values["phone"] and len(re.sub(r"\D", "", values["phone"])) < 10:
        errors["phone"] = "Please enter a full phone number, including the area code."
    if values["address"] and (len(values["address"]) < 5 or not re.search(r"\d", values["address"]) or not re.search(r"[A-Za-z]", values["address"])):
        errors["address"] = "Please enter the street number and street name, e.g. 12 Dock Road."
    if values["city"] and not re.search(r"[A-Za-z]{2}", values["city"]):
        errors["city"] = "Please enter the city."
    if delivery_type not in {value for value, _, _ in DELIVERY_TYPES}:
        errors["delivery_type"] = "Please choose where the motor is being delivered."
    if not EMAIL_RE.fullmatch(values["email"]):
        errors["email"] = "Please enter a valid email address."
    if values["state"] not in US_STATES:
        errors["state"] = "Please choose a state."
    if not ZIP_RE.fullmatch(values["shipping_zip"]):
        errors["shipping_zip"] = "Please enter a 5-digit US ZIP."
    if payment_method not in {value for value, _, _ in PAYMENT_METHODS}:
        errors["payment_method"] = "Please choose how you'd like to pay."
    if errors:
        return render_checkout(request, motors, values, errors, status_code=400)

    order = {
        **values,
        "payment_method": payment_method,
        "payment_method_label": payment_label(payment_method),
        "delivery_type_label": dict((v, label) for v, label, _ in DELIVERY_TYPES).get(delivery_type, delivery_type),
        "items": [
            {"name": motor.name, "price": float(motor.price_usd), "quantity": 1}
            for motor in motors
        ],
        "subtotal": sum(motor.price_usd for motor in motors),
    }
    background_tasks.add_task(emails.notify_order_request, order)
    response = RedirectResponse("/checkout/thanks", status_code=303)
    return with_cart(response, [])


@router.get("/checkout/thanks")
def checkout_thanks(request: Request):
    return templates.TemplateResponse(request, "checkout_thanks.html", {})
