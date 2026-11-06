from sqlalchemy import create_engine, inspect, text

from app.seed import add_missing_columns
from import_motors import existing_motor_keys, parse_rows
from app.db import SessionLocal
from app.models import Motor

HEADER = "make,model,year,hp,stroke,cylinders,shaft,hours,price_usd,condition,notes,badge\n"


def rows(*lines):
    return [HEADER, *[line + "\n" for line in lines]]


def test_parses_a_full_row_and_builds_the_name():
    motors, errors = parse_rows(rows('Honda,BF90,2016,90,4,4,"25""",310,"$6,500",Used,Clean,'))
    assert errors == []
    motor = motors[0]
    assert motor["name"] == "2016 Honda BF90 90 HP 4-Stroke"
    assert (motor["cylinders"], motor["hours"], motor["price_usd"]) == (4, 310, 6500)
    assert motor["shaft"] == '25"'
    assert motor["status"] == "in_stock"


def test_blank_details_stay_blank_rather_than_being_filled_in():
    motors, errors = parse_rows(rows("Tohatsu,,,30,2,,,,,,,"))
    assert errors == []
    motor = motors[0]
    assert motor["name"] == "Tohatsu 30 HP 2-Stroke"
    for field in ("model", "year", "cylinders", "shaft", "hours", "price_usd", "condition", "notes", "badge"):
        assert motor[field] is None


def test_three_stroke_is_rejected():
    motors, errors = parse_rows(rows("Yamaha,,2010,50,3,3,,,,,,"))
    assert motors == []
    assert "Row 2" in errors[0] and "stroke" in errors[0]


def test_required_fields_and_bad_numbers_are_reported_by_row():
    _, errors = parse_rows(rows(",,,,,,,,,,,", "Honda,,20x0,,4,,,,,,,"))
    assert len(errors) == 1
    assert "Row 3" in errors[0]
    assert "year" in errors[0] and "hp" in errors[0]


def test_unlikely_year_is_rejected():
    _, errors = parse_rows(rows("Honda,,1850,50,4,,,,,,,"))
    assert "year" in errors[0]


def test_wrong_columns_are_reported():
    _, errors = parse_rows(["make,horsepower\n", "Honda,50\n"])
    assert "missing columns: hp, stroke" in errors[0]
    assert "unknown columns: horsepower" in errors[0]


def test_duplicates_in_file_and_database_are_rejected_unless_allowed(client):
    line = "Yamaha,F150,2012,150,4,,XL,200,,,,"
    with SessionLocal() as db:
        existing = existing_motor_keys(db)
    _, errors = parse_rows(rows(line), existing)
    assert "already listed" in errors[0]

    other = "Honda,BF50,2015,50,4,,,100,,,,"
    _, errors = parse_rows(rows(other, other), existing)
    assert "Row 3" in errors[0]

    motors, errors = parse_rows(rows(other, other), existing, allow_duplicates=True)
    assert errors == [] and len(motors) == 2


def test_cylinder_filter_only_offers_real_values(client):
    html = client.get("/motors").text
    assert ">2-Cylinder<" in html and ">4-Cylinder<" in html
    assert ">3-Cylinder<" not in html
    filtered = client.get("/motors?cylinders=4").text
    assert "2006 Mercury 60 HP" in filtered
    assert "2017 Mercury 225 Pro XS" not in filtered


def test_import_keeps_written_description():
    header = "make,hp,stroke,description\n"
    motors, errors = parse_rows([header, 'Honda,50,4,"Serviced in March, new impeller."\n'])
    assert errors == []
    assert motors[0]["description"] == "Serviced in March, new impeller."


def test_summary_uses_only_known_specs(client):
    assert "Used 150 HP 4-stroke Yamaha F150 from 2012. Shaft: XL. Hours: 200." in client.get("/motors/5").text
    sparse = client.get("/motors/1").text
    assert "Used 90 HP 2-stroke Yamaha." in sparse
    assert "Shaft: " not in sparse
    assert "Hours: " not in sparse


def test_written_description_replaces_summary_and_is_escaped(client):
    with SessionLocal() as db:
        db.get(Motor, 5).description = "Fresh service. <script>x</script>"
        db.commit()
    html = client.get("/motors/5").text
    assert "Fresh service. &lt;script&gt;" in html
    assert "<script>x" not in html
    assert "Used 150 HP 4-stroke" not in html


def test_admin_saves_description(client):
    form = {"name": "Test Motor", "make": "Honda", "hp": "50", "stroke": "4", "status": "in_stock", "description": "Written by hand."}
    client.post("/admin/motors/new", auth=("test-admin", "test-password"), data=form)
    assert "Written by hand." in client.get("/motors/9").text
    assert "Written by hand." in client.get("/admin/motors/9/edit", auth=("test-admin", "test-password")).text


def test_existing_database_gets_the_new_column_and_keeps_its_rows():
    old = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)
    with old.begin() as connection:
        connection.execute(text("CREATE TABLE motors (id INTEGER PRIMARY KEY, name VARCHAR(200))"))
        connection.execute(text("INSERT INTO motors (name) VALUES ('Existing motor')"))
    add_missing_columns(old)
    add_missing_columns(old)
    assert {"cylinders", "description"} <= {column["name"] for column in inspect(old).get_columns("motors")}
    with old.connect() as connection:
        assert connection.execute(text("SELECT name FROM motors")).scalars().all() == ["Existing motor"]
