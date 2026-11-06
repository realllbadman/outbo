import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def clean_password(value: str) -> str:
    """Gmail displays app passwords in groups of four; SMTP needs them unspaced."""
    return value.replace(" ", "").strip()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'outboard.db'}")

    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "terryengine80@gmail.com")
    smtp_pass: str = clean_password(os.getenv("SMTP_PASS", ""))

    admin_user: str = os.getenv("ADMIN_USER", "")
    admin_pass: str = os.getenv("ADMIN_PASS", "")

    business_name: str = os.getenv("BUSINESS_NAME", "Terry Marine Outboards")
    business_location: str = os.getenv("BUSINESS_LOCATION", "Blountstown, Florida")
    business_email: str = "terryengine80@gmail.com"
    whatsapp_display: str = "+1 949 816 8565"
    whatsapp_url: str = "https://wa.me/19498168565"
    phone_display: str = "+1 850 343 7282"
    phone_url: str = "tel:+18503437282"

    # Used for the admin link in alert emails, so it can't be spoofed via the Host header.
    site_url: str = os.getenv("SITE_URL", f"http://localhost:{os.getenv('PORT', '8030')}").rstrip("/")


settings = Settings()
