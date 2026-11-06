from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import Motor

# price_usd is None for every motor until the owner sets real prices in /admin/motors.
SEED_MOTORS = [
    {"name": "Yamaha 90 HP 2-Stroke", "make": "Yamaha", "hp": 90, "stroke": 2, "badge": "Available"},
    {
        "name": "1997 Yamaha 40 HP 2-Cyl Carbureted 2-Stroke",
        "make": "Yamaha",
        "year": 1997,
        "hp": 40,
        "stroke": 2,
        "cylinders": 2,
        "shaft": '20" (L)',
        "notes": "2-cylinder carbureted",
    },
    {"name": "Selva / Yamaha 25 HP Outboard (2008)", "make": "Selva / Yamaha", "year": 2008, "hp": 25, "stroke": 4},
    {
        "name": "2006 Mercury 60 HP 4-Cylinder EFI 4-Stroke",
        "make": "Mercury",
        "year": 2006,
        "hp": 60,
        "stroke": 4,
        "cylinders": 4,
        "shaft": '20" mid',
        "hours": 414,
        "notes": "152–160 PSI compression on all four cylinders",
    },
    {
        "name": "2012 Yamaha F150 150HP Four-Stroke",
        "make": "Yamaha",
        "model": "F150",
        "year": 2012,
        "hp": 150,
        "stroke": 4,
        "shaft": "XL",
        "hours": 200,
        "notes": "Main-dealer service history reported; condition reported excellent",
        "badge": "Low Hours",
    },
    {
        "name": "2017 Mercury 225 Pro XS",
        "make": "Mercury",
        "model": "225 Pro XS",
        "year": 2017,
        "hp": 225,
        "stroke": 4,
        "hours": 189,
        "badge": "Pro XS",
    },
    {
        "name": "Evinrude E-TEC 135 HP",
        "make": "Evinrude",
        "model": "E-TEC 135",
        "hp": 135,
        "stroke": 2,
        "notes": "E-TEC",
    },
    {
        "name": "2015 Suzuki DF150A Four-Stroke",
        "make": "Suzuki",
        "model": "DF150A",
        "year": 2015,
        "hp": 150,
        "stroke": 4,
        "shaft": '25"',
        "hours": 370,
    },
]


def seed_motors(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Motor)):
        return
    db.add_all(Motor(condition="Used", status="in_stock", **motor) for motor in SEED_MOTORS)
    db.commit()


def add_missing_columns(bind) -> None:
    """create_all doesn't change existing tables, so add columns newer than the database."""
    existing = {column["name"] for column in inspect(bind).get_columns("motors")}
    with bind.begin() as connection:
        for name, column_type in (("cylinders", "INTEGER"), ("description", "TEXT"), ("image_url", "VARCHAR(500)")):
            if name not in existing:
                connection.execute(text(f"ALTER TABLE motors ADD COLUMN {name} {column_type}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    with SessionLocal() as db:
        seed_motors(db)
