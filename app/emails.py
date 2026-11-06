import logging
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

import aiosmtplib

from app.config import settings

log = logging.getLogger("outboard.email")


async def send_mail(to: str, subject: str, body: str, reply_to: Optional[str] = None) -> bool:
    """Send one email. Failures are logged, never raised: the enquiry is already saved."""
    if not settings.smtp_pass:
        log.warning("SMTP_PASS is not set; skipped email to %s: %s", to, subject)
        return False
    try:
        msg = EmailMessage()
        msg["From"] = formataddr((settings.business_name, settings.smtp_user))
        msg["To"] = to
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=True,
            username=settings.smtp_user,
            password=settings.smtp_pass,
            timeout=20,
        )
        return True
    except Exception:
        log.exception("Failed to send email to %s: %s", to, subject)
        return False


async def notify_enquiry(enquiry: dict, known_motor: Optional[str]) -> None:
    """Email the admin and the customer about a saved enquiry.

    known_motor is only set when the motor matched the database. Customer emails
    never repeat free text from the form, so the form can't be used to send
    someone else arbitrary content from the business address.
    """
    motor = enquiry["motor_of_interest"] or "General enquiry"
    await send_mail(
        settings.business_email,
        f"New enquiry #{enquiry['id']}: {motor}",
        (
            f"Name: {enquiry['name']}\n"
            f"Email: {enquiry['email']}\n"
            f"Phone/WhatsApp: {enquiry['phone']}\n"
            f"Motor: {motor}\n"
            f"Shipping ZIP: {enquiry['shipping_zip'] or '—'}\n\n"
            f"Message:\n{enquiry['message']}\n\n"
            f"Open in admin: {settings.site_url}/admin/enquiry/{enquiry['id']}\n"
        ),
        reply_to=enquiry["email"],
    )

    about = f"your enquiry about {known_motor}" if known_motor else "your enquiry"
    await send_mail(
        enquiry["email"],
        f"We got {about} — {settings.business_name}",
        (
            f"Thanks — we got {about}, and we'll reply shortly.\n\n"
            "If you'd rather talk now:\n"
            f"WhatsApp: {settings.whatsapp_display}\n"
            f"Call / SMS: {settings.phone_display}\n\n"
            f"{settings.business_name}\n"
            f"{settings.business_location}\n"
        ),
    )


async def notify_order_request(order: dict) -> None:
    """Email the business and the customer about a submitted order request."""
    payment_label = order.get("payment_method_label") or order.get("payment_method", "").replace("_", " ").title()
    item_lines = "\n".join(
        f"- {item['name']} — ${item['price']:,.2f}" for item in order.get("items", [])
    ) or "- No items listed"
    body = (
        f"Name: {order['name']}\n"
        f"Email: {order['email']}\n"
        f"Phone: {order['phone']}\n"
        f"Address: {order['address']}\n"
        f"Address 2: {order['address2'] or '—'}\n"
        f"City: {order['city']}\n"
        f"State: {order['state']}\n"
        f"ZIP: {order['shipping_zip']}\n"
        f"Delivery location: {order.get('delivery_type_label') or '—'}\n"
        f"Contact preference: {order.get('contact_preference') or '—'}\n"
        f"Best time to reach: {order.get('best_time') or '—'}\n"
        f"Preferred payment method: {payment_label}\n\n"
        f"Items:\n{item_lines}\n\n"
        f"Subtotal: ${order['subtotal']:,.2f}"
    )
    await send_mail(
        settings.business_email,
        "New order request",
        body,
        reply_to=order["email"],
    )

    await send_mail(
        order["email"],
        f"We got your order request — {settings.business_name}",
        (
            f"Thanks, {order['name']}. We received your order request and will follow up by email to confirm the final details, freight and payment.\n\n"
            f"Preferred payment method: {payment_label}\n"
            f"Delivery: {order.get('delivery_type_label') or '—'}, {order['address']}, {order['city']}, {order['state']} {order['shipping_zip']}\n\n"
            f"Items:\n{item_lines}\n\n"
            f"Subtotal: ${order['subtotal']:,.2f}\n\n"
            f"If you need to talk sooner, call {settings.phone_display} or message on WhatsApp: {settings.whatsapp_url}."
        ),
    )
