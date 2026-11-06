"""Add real motors to the inventory from a CSV file.

    .venv/bin/python import_motors.py motors.csv           # check only, changes nothing
    .venv/bin/python import_motors.py motors.csv --apply   # add the motors

If any row has a problem, nothing is added.
"""
import argparse
import csv
import sys
from datetime import datetime
from typing import Iterable, List, Tuple

from sqlalchemy import select

from app.admin import parse_motor_form
from app.db import SessionLocal
from app.models import Motor
from app.seed import init_db

COLUMNS = ("make", "model", "year", "hp", "stroke", "cylinders", "shaft", "hours", "price_usd", "condition", "description", "notes", "badge")
REQUIRED = {"make", "hp", "stroke"}


def motor_key(motor: dict) -> tuple:
    return (
        motor["make"].lower(),
        (motor["model"] or "").lower(),
        motor["year"],
        motor["hp"],
        motor["stroke"],
        motor["hours"],
    )


def build_name(motor: dict) -> str:
    parts = [motor["year"], motor["make"], motor["model"], f"{motor['hp']} HP", f"{motor['stroke']}-Stroke"]
    return " ".join(str(part) for part in parts if part)


def parse_rows(lines: Iterable[str], existing_keys=(), allow_duplicates: bool = False) -> Tuple[List[dict], List[str]]:
    """Return (motors, errors). Row numbers match the rows shown in a spreadsheet."""
    reader = csv.DictReader(lines)
    headers = [(header or "").strip() for header in reader.fieldnames or []]
    missing = REQUIRED - set(headers)
    unknown = set(headers) - set(COLUMNS)
    if missing or unknown:
        problems = []
        if missing:
            problems.append(f"missing columns: {', '.join(sorted(missing))}")
        if unknown:
            problems.append(f"unknown columns: {', '.join(sorted(unknown))}")
        return [], ["Header row: " + "; ".join(problems)]
    reader.fieldnames = headers

    motors, errors = [], []
    seen = set(existing_keys)
    for number, row in enumerate(reader, start=2):
        cleaned = {key: (value or "").strip() for key, value in row.items() if key}
        if not any(cleaned.values()):
            continue
        # The name is filled in here so that parse_motor_form's required-name check passes.
        cleaned["name"] = "pending"
        motor, row_errors = parse_motor_form(cleaned)
        problems = [f"{field}: {message}" for field, message in row_errors.items()]
        year = motor["year"]
        if isinstance(year, int) and not 1950 <= year <= datetime.now().year + 1:
            problems.append(f"year: {year} doesn't look right.")
        if problems:
            errors.append(f"Row {number}: " + " ".join(problems))
            continue
        motor["name"] = build_name(motor)
        key = motor_key(motor)
        if key in seen and not allow_duplicates:
            errors.append(f"Row {number}: already listed: {motor['name']}.")
            continue
        seen.add(key)
        motors.append(motor)
    return motors, errors


def existing_motor_keys(db) -> set:
    return {
        (m.make.lower(), (m.model or "").lower(), m.year, m.hp, m.stroke, m.hours)
        for m in db.scalars(select(Motor))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Add real motors to the inventory from a CSV file.")
    parser.add_argument("csv_file")
    parser.add_argument("--apply", action="store_true", help="add the motors (without this, only checks the file)")
    parser.add_argument("--allow-duplicates", action="store_true", help="allow several identical motors")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db, open(args.csv_file, newline="", encoding="utf-8-sig") as handle:
        motors, errors = parse_rows(handle, existing_motor_keys(db), args.allow_duplicates)
        if errors:
            print(f"Nothing was added. Fix {len(errors)} problem(s) and run this again:")
            print("\n".join(f"  {error}" for error in errors))
            return 1
        if not motors:
            print("The file has no motors in it.")
            return 1
        for motor in motors:
            print(f"  {motor['name']}")
        if not args.apply:
            print(f"\n{len(motors)} motor(s) look fine. Nothing was added. Run again with --apply to add them.")
            return 0
        db.add_all(Motor(**motor) for motor in motors)
        db.commit()
        print(f"\nAdded {len(motors)} motor(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
