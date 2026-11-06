from app.db import SessionLocal
from app.models import Motor

ADMIN = ("test-admin", "test-password")
CHECKOUT = {
    "name": "Test Buyer",
    "email": "buyer@example.com",
    "phone": "+1 555 000 0000",
    "address": "1 Dock Rd",
    "city": "Blountstown",
    "state": "FL",
    "shipping_zip": "32424",
    "delivery_type": "residential",
    "payment_method": "card",
}


def set_price(motor_id, price):
    with SessionLocal() as db:
        db.get(Motor, motor_id).price_usd = price
        db.commit()


def test_add_to_cart_lists_motor_and_counts_it(client):
    set_price(8, 4400)
    response = client.post("/cart/add", data={"motor_id": 8})
    assert response.url.path == "/cart"
    assert "2015 Suzuki DF150A Four-Stroke" in response.text
    assert "$4,400" in response.text
    assert '<span class="cart-count">1</span>' in response.text
    assert "In your cart" in client.get("/motors/8").text


def test_adding_twice_keeps_one(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    html = client.post("/cart/add", data={"motor_id": 8}).text
    assert '<span class="cart-count">1</span>' in html


def test_unpriced_motor_cannot_be_added_and_keeps_request_button(client):
    response = client.post("/cart/add", data={"motor_id": 6})
    assert response.url.path == "/motors/6"
    assert "Request this motor" in response.text
    assert "Your cart is empty" in client.get("/cart").text


def test_remove_from_cart(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    assert "Your cart is empty" in client.post("/cart/remove", data={"motor_id": 8}).text


def test_sold_motor_drops_out_of_cart(client):
    set_price(8, 4400)
    set_price(5, 4500)
    client.post("/cart/add", data={"motor_id": 8})
    client.post("/cart/add", data={"motor_id": 5})
    client.post("/admin/motors/8/sold", auth=ADMIN)
    html = client.get("/cart").text
    assert "no longer available" in html
    assert "2015 Suzuki DF150A Four-Stroke" not in html
    assert "2012 Yamaha F150" in html
    assert client.cookies.get("cart") == "5"


def test_checkout_with_empty_cart_goes_to_cart(client):
    assert client.get("/checkout").url.path == "/cart"


def test_checkout_offers_payment_options(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    html = client.get("/checkout").text
    for label in (
        "Cash App", "Zelle", "Apple Pay", "Chime", "Bank-to-bank transfer (US)", "Venmo",
        "PayPal", "European bank transfer (SEPA)", "Credit or debit card", "Google Pay",
    ):
        assert label in html
    assert "Submit order request" in html
    assert "coming soon" not in html


def test_valid_checkout_requests_order_and_sends_emails(client, smtp_calls):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    response = client.post("/checkout", data=CHECKOUT, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/checkout/thanks"
    assert len(smtp_calls) == 2
    admin_mail, customer_mail = (call["message"] for call in smtp_calls)
    assert admin_mail["To"] == "terryengine80@gmail.com"
    assert "New order request" in admin_mail["Subject"]
    assert "Credit or debit card" in admin_mail.get_content()
    assert customer_mail["To"] == CHECKOUT["email"]
    assert "order request" in customer_mail.get_content().lower()


def test_invalid_checkout_shows_errors(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    response = client.post("/checkout", data={**CHECKOUT, "shipping_zip": "abc", "payment_method": "bitcoin"})
    assert response.status_code == 400
    assert "5-digit US ZIP" in response.text
    assert "choose how you" in response.text.replace("&#39;", "'")


def test_valid_checkout_submits_order_request_without_charging(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    response = client.post("/checkout", data=CHECKOUT, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/checkout/thanks"
    with SessionLocal() as db:
        assert db.get(Motor, 8).status == "in_stock"


def test_checkout_summary_does_not_promise_free_freight(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    html = client.get("/checkout").text
    assert "Quoted for your address" in html
    assert "FREE" not in html
    assert "$14.99" not in html


def test_checkout_sends_contact_preference_and_best_time(client, smtp_calls):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    client.post("/checkout", data={**CHECKOUT, "contact_preference": "Text", "best_time": "weekday evenings"})
    admin_mail = smtp_calls[0]["message"].get_content()
    assert "Contact preference: Text" in admin_mail
    assert "Best time to reach: weekday evenings" in admin_mail


def test_invalid_checkout_keeps_contact_answers_and_flags_fields(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    html = client.post("/checkout", data={**CHECKOUT, "shipping_zip": "abc", "contact_preference": "Email", "best_time": "mornings"}).text
    assert 'value="Email" checked' in html
    assert 'value="mornings"' in html
    assert 'aria-invalid="true" aria-describedby="shipping_zip-error"' in html


def test_checkout_refuses_order_without_shipping_details(client, smtp_calls):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    for field in ("address", "city", "state", "shipping_zip", "delivery_type", "name", "phone", "email", "payment_method"):
        response = client.post("/checkout", data={**CHECKOUT, field: ""})
        assert response.status_code == 400, field
        assert "Your order hasn't been sent yet" in response.text
    assert smtp_calls == []  # no order email went out
    assert "2015 Suzuki DF150A" in client.get("/cart").text  # the cart is kept


def test_checkout_rejects_junk_phone_and_address(client):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    html = client.post("/checkout", data={**CHECKOUT, "phone": "123", "address": "abc"}).text
    assert "including the area code" in html
    assert "street number and street name" in html


def test_order_email_includes_delivery_location(client, smtp_calls):
    set_price(8, 4400)
    client.post("/cart/add", data={"motor_id": 8})
    client.post("/checkout", data={**CHECKOUT, "delivery_type": "terminal"})
    assert "Delivery location: Freight terminal pickup" in smtp_calls[0]["message"].get_content()
