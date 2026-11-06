import aiosmtplib
from sqlalchemy import select

from app.config import clean_password
from app.db import SessionLocal
from app.models import Enquiry, Motor
from app.seed import SEED_MOTORS

ALL_NAMES = {motor["name"] for motor in SEED_MOTORS}
ADMIN = ("test-admin", "test-password")
QUOTE = {
    "name": "Test Buyer",
    "email": "buyer@example.com",
    "phone": "+1 555 000 0000",
    "motor_of_interest": "2015 Suzuki DF150A Four-Stroke",
    "message": "Is this still available?",
    "shipping_zip": "32424",
}


def enquiries():
    with SessionLocal() as db:
        return db.scalars(select(Enquiry)).all()


def listed_names(html):
    return {name for name in ALL_NAMES if name in html}


def test_seeds_all_eight_motors_without_prices(client):
    with SessionLocal() as db:
        motors = db.scalars(select(Motor)).all()
    assert len(motors) == 8
    assert all(m.price_usd is None and m.condition == "Used" and m.status == "in_stock" for m in motors)


def test_quote_saves_row_and_sends_both_emails(client, smtp_calls):
    response = client.post("/quote", data=QUOTE)
    assert response.status_code == 200
    assert "we've got it" in response.text.replace("&#39;", "'")

    rows = enquiries()
    assert len(rows) == 1
    assert rows[0].status == "new"
    assert rows[0].motor_of_interest == QUOTE["motor_of_interest"]

    admin_mail, customer_mail = (call["message"] for call in smtp_calls)
    assert admin_mail["To"] == "terryengine80@gmail.com"
    assert admin_mail["Reply-To"] == QUOTE["email"]
    assert f"/admin/enquiry/{rows[0].id}" in admin_mail.get_content()
    assert QUOTE["message"] in admin_mail.get_content()
    assert customer_mail["To"] == QUOTE["email"]
    assert QUOTE["motor_of_interest"] in customer_mail.get_content()


def test_customer_email_does_not_repeat_unknown_motor_text(client, smtp_calls):
    client.post("/quote", data={**QUOTE, "motor_of_interest": "visit spam.example now"})
    admin_mail, customer_mail = (call["message"] for call in smtp_calls)
    assert "spam.example" in admin_mail.get_content()
    assert "spam.example" not in customer_mail.get_content()
    assert "spam.example" not in customer_mail["Subject"]


def test_quote_is_saved_when_smtp_fails(client, monkeypatch):
    async def broken_send(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr(aiosmtplib, "send", broken_send)
    response = client.post("/quote", data=QUOTE)
    assert response.status_code == 200
    assert len(enquiries()) == 1


def test_invalid_quote_shows_errors_and_saves_nothing(client, smtp_calls):
    response = client.post("/quote", data={**QUOTE, "email": "not-an-email", "message": ""})
    assert response.status_code == 400
    assert "valid email" in response.text
    assert enquiries() == []
    assert smtp_calls == []


def test_honeypot_is_ignored(client, smtp_calls):
    response = client.post("/quote", data={**QUOTE, "website": "http://spam.example"})
    assert response.status_code == 200
    assert enquiries() == []
    assert smtp_calls == []


def test_quote_page_prefills_motor(client):
    assert "2017 Mercury 225 Pro XS" in client.get("/quote?motor=6").text


def test_filter_by_brand(client):
    html = client.get("/motors?brand=Mercury").text
    assert listed_names(html) == {"2006 Mercury 60 HP 4-Cylinder EFI 4-Stroke", "2017 Mercury 225 Pro XS"}


def test_filter_by_stroke(client):
    html = client.get("/motors?stroke=2").text
    assert listed_names(html) == {
        "Yamaha 90 HP 2-Stroke",
        "1997 Yamaha 40 HP 2-Cyl Carbureted 2-Stroke",
        "Evinrude E-TEC 135 HP",
    }


def test_filter_by_hp_range(client):
    html = client.get("/motors?hp_min=135&hp_max=150").text
    assert listed_names(html) == {
        "2012 Yamaha F150 150HP Four-Stroke",
        "Evinrude E-TEC 135 HP",
        "2015 Suzuki DF150A Four-Stroke",
    }


def test_blank_and_invalid_filters_are_ignored(client):
    html = client.get("/motors?brand=&stroke=&hp_min=abc&hp_max=").text
    assert listed_names(html) == ALL_NAMES


def test_filter_bar_marks_active_option_and_keeps_other_filters(client):
    html = client.get("/motors?stroke=4&brand=Mercury").text
    assert '<a href="/motors?brand=Mercury&amp;stroke=4" aria-current="true">Four Stroke</a>' in html
    assert 'href="/motors?brand=Mercury&amp;stroke=2"' in html
    assert 'href="/motors?brand=Mercury&amp;stroke=4&amp;hp_min=150"' in html


def test_home_series_use_real_stock(client):
    html = client.get("/").text
    assert "150–225 HP" in html
    assert "60–135 HP" in html
    assert "25–40 HP" in html
    assert 'href="/motors?hp_min=60&amp;hp_max=149"' in html


def test_sold_motor_changes_home_series(client):
    client.post("/admin/motors/6/sold", auth=ADMIN)
    html = client.get("/").text
    assert "150 HP" in html
    assert "150–225 HP" not in html


def test_call_for_price_and_formatted_price(client):
    with SessionLocal() as db:
        db.get(Motor, 5).price_usd = 7200
        db.commit()
    assert "$7,200" in client.get("/motors/5").text
    priced_off = client.get("/motors/6").text
    assert "Call for Price" in priced_off
    assert "+ shipping" in priced_off


def test_unknown_specs_show_dash_not_invented_values(client):
    html = client.get("/motors/1").text
    assert "<th scope=\"row\">Year</th><td>—</td>" in html
    assert "<th scope=\"row\">Hours</th><td>—</td>" in html


def test_sold_motor_leaves_listing_and_hides_request_button(client):
    client.post("/admin/motors/6/sold", auth=ADMIN)
    assert "2017 Mercury 225 Pro XS" not in client.get("/motors").text
    detail = client.get("/motors/6").text
    assert "has been sold" in detail
    assert "Request this motor" not in detail


def test_unknown_motor_is_404(client):
    assert client.get("/motors/999").status_code == 404


def test_admin_requires_credentials(client):
    for response in (
        client.get("/admin", follow_redirects=False),
        client.get("/admin", auth=("test-admin", "wrong"), follow_redirects=False),
        client.post("/admin/motors/1/sold", follow_redirects=False),
    ):
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")
    assert "has been sold" not in client.get("/motors/1").text


def test_admin_rejects_cross_site_post(client):
    response = client.post("/admin/motors/1/sold", auth=ADMIN, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_admin_lists_and_updates_enquiry(client):
    client.post("/quote", data=QUOTE)
    enquiry_id = enquiries()[0].id
    assert QUOTE["name"] in client.get("/admin", auth=ADMIN).text

    client.post(f"/admin/enquiry/{enquiry_id}", auth=ADMIN, data={"status": "contacted", "internal_notes": "Called"})
    updated = client.get(f"/admin/enquiry/{enquiry_id}", auth=ADMIN).text
    assert '<option value="contacted" selected>' in updated
    assert "Called" in updated


def test_admin_adds_and_edits_motor(client):
    form = {"name": "Test Motor", "make": "Honda", "hp": "50", "stroke": "4", "status": "in_stock", "price_usd": "$6,500"}
    assert client.post("/admin/motors/new", auth=ADMIN, data=form).status_code == 200
    assert "$6,500" in client.get("/motors/9").text

    client.post("/admin/motors/9/edit", auth=ADMIN, data={**form, "price_usd": ""})
    assert "Call for Price" in client.get("/motors/9").text


def test_admin_edit_form_shows_saved_values(client):
    html = client.get("/admin/motors/8/edit", auth=ADMIN).text
    assert 'value="DF150A"' in html
    assert '<option value="4" selected>' in html


def test_app_password_spaces_are_stripped():
    assert clean_password(" abcd efgh ijkl mnop ") == "abcdefghijklmnop"


def test_motor_page_suggests_other_in_stock_motors(client):
    html = client.get("/motors/1").text
    assert "You might also like" in html
    suggestions = html.split("You might also like", 1)[1]
    assert suggestions.count('<article class="card">') == 3
    assert 'href="/motors/1"' not in suggestions


def test_sold_motors_are_not_suggested(client):
    client.post("/admin/motors/6/sold", auth=ADMIN)
    for motor_id in (5, 8):
        suggestions = client.get(f"/motors/{motor_id}").text.split("You might also like", 1)[1]
        assert 'href="/motors/6"' not in suggestions


def test_image_url_is_shown_on_card_and_detail_page(client):
    url = "https://example.com/motor.jpg"
    form = {"name": "Photo Motor", "make": "Honda", "hp": "50", "stroke": "4", "status": "in_stock", "image_url": url}
    client.post("/admin/motors/new", auth=ADMIN, data=form)
    assert f'src="{url}"' in client.get("/motors/9").text
    assert f'src="{url}"' in client.get("/motors").text


def test_image_url_must_be_a_web_address(client):
    form = {"name": "Bad Photo", "make": "Honda", "hp": "50", "stroke": "4", "status": "in_stock", "image_url": "javascript:alert(1)"}
    html = client.post("/admin/motors/new", auth=ADMIN, data=form).text
    assert "Enter a web address" in html
    assert "Bad Photo" not in client.get("/motors").text


def test_photo_manager_lists_motors_and_saves_a_new_link(client):
    html = client.get("/admin/photos", auth=ADMIN).text
    assert 'id="motor-1"' in html and 'action="/admin/photos/1"' in html

    url = "https://example.com/new.jpg"
    response = client.post("/admin/photos/1", auth=ADMIN, data={"image_url": url, "action": "save"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("#motor-1")
    assert f'src="{url}"' in client.get("/motors/1").text


def test_photo_manager_flags_shared_photos_and_can_remove(client):
    url = "https://example.com/same.jpg"
    for motor_id in (1, 2):
        client.post(f"/admin/photos/{motor_id}", auth=ADMIN, data={"image_url": url})
    assert "Same photo as #2" in client.get("/admin/photos", auth=ADMIN).text

    client.post("/admin/photos/2", auth=ADMIN, data={"image_url": url, "action": "remove"})
    assert "Same photo as" not in client.get("/admin/photos", auth=ADMIN).text


def test_photo_manager_rejects_bad_links_and_needs_login(client):
    response = client.post("/admin/photos/1", auth=ADMIN, data={"image_url": "not a link"})
    assert response.status_code == 400 and "Enter a full web address" in response.text
    assert client.get("/admin/photos", follow_redirects=False).headers["location"] == "/admin/login?next=/admin/photos"


def test_photo_manager_says_which_motor_was_changed(client):
    client.post("/admin/photos/2", auth=ADMIN, data={"image_url": "https://example.com/x.jpg"})
    html = client.get("/admin/photos?saved=2&did=saved", auth=ADMIN).text
    assert "New photo saved for" in html and "<strong>#2</strong>" in html
    assert "Save #2" in html

    client.post("/admin/photos/2", auth=ADMIN, data={"action": "remove"})
    assert "Photo removed from" in client.get("/admin/photos?saved=2&did=removed", auth=ADMIN).text
