# Terry Marine Outboards

Outboard motor sales site. Customers add motors to a cart, choose a preferred payment method, and submit an order request. The business receives the request by email and follows up to confirm the final details, freight and payment method before processing the order.

## Checkout and order requests

Priced motors have an **Add to cart** button. Motors without a price keep the **Request** button. The checkout form collects the buyer's contact details, delivery address and preferred payment method, then submits the order request to the business by email.

This is not a live payment processor flow. The customer chooses how they want to pay, the order request is emailed to the business, and the business replies to confirm and process the order. Nothing is charged automatically at checkout. Freight is not charged at the moment of order request; the business confirms the final cost for the delivery address before completing the sale.

## Run it

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # then fill in SMTP_PASS, ADMIN_USER and ADMIN_PASS
.venv/bin/python run.py
```

Open http://localhost:8030. The admin panel is at http://localhost:8030/admin (on a live site, `yourdomain.com/admin`). It shows a sign-in page; use `ADMIN_USER` and `ADMIN_PASS` from `.env`. Admin stays locked until both are set. You stay signed in for 12 hours, and **Log out** is at the top right. After 5 wrong passwords in a row, sign-in is blocked for 10 minutes.

`run.py` prevents "port already in use" errors. It stops any older copy of this site, then starts on port 8030. If another program is using 8030, it leaves that program alone, uses the next free port and prints the address. To prefer a different port, run `PORT=9000 .venv/bin/python run.py`. Press Ctrl+C to stop the site.

The database (`outboard.db`) is created on first run and seeded with the 8 motors. Delete it only if you want to start over, because that also deletes your enquiries.

If `SMTP_PASS` is blank, enquiries are still saved, but no email is sent and a warning is logged.

## Set prices

Every motor starts as "Call for Price". To set a price, go to **Admin → Motors → Edit**. Leave the price blank to go back to "Call for Price".

## Add many motors at once

Copy `motors_template.csv`, add one row per real motor and save it as CSV. Excel, LibreOffice and Google Sheets can all do this. Only `make`, `hp` and `stroke` are required, and `stroke` must be 2 or 4. Leave anything you don't know blank and the site shows "—".

```bash
.venv/bin/python import_motors.py motors.csv           # checks the file, changes nothing
.venv/bin/python import_motors.py motors.csv --apply   # adds the motors
```

If any row has a problem, nothing is added. Motors already listed are reported as problems, so running the file twice can't add them twice. If you really have several identical motors, add `--allow-duplicates`. `name` is built automatically, for example "2016 Honda BF90 90 HP 4-Stroke". Motors without a price show "Call for Price". Motors without a `description` show a short summary built from their specs.

## Add motor photos

The quickest way is **Admin → Photos**: paste an image link for any motor and press Save. The preview updates as you paste, and the page flags motors with no photo, a broken link or a photo another motor already uses. To fill every motor with free photos from Wikimedia Commons in one go, run `.venv/bin/python fill_photos.py` (preview) and then `.venv/bin/python fill_photos.py --apply`.

You can also put image files in `static/motors/<motor-id>/`. You can see each motor's ID in **Admin → Motors**. They show after the image link, if a motor has one.

```
static/motors/5/1-main.jpg
static/motors/5/2-side.jpg
static/motors/5/3-powerhead.jpg
```

The first filename alphabetically is the main photo on the card and detail page. The rest appear as thumbnails. Accepted types are `.jpg`, `.jpeg`, `.png`, `.webp` and `.avif`. A motor with no photos shows a "Photo coming soon" panel.

## Background photos

Background photos are in `static/img/`. To change one, replace the file and keep its name. They're from Pexels, so check its current licence before relying on them commercially:

| File | Used on | Source |
|---|---|---|
| `boat-wake-aerial.jpg` | Home hero | https://www.pexels.com/photo/photo-of-speed-boat-on-sea-3274984/ |
| `wake-rear-dark.jpg` | High Power section | https://www.pexels.com/photo/motorboat-in-a-lake-20037850/ |
| `harbor-boats.jpg` | Mid Range section, About | https://www.pexels.com/photo/boats-docked-in-the-harbor-8292102/ |
| `golden-hour-boat.jpg` | Small Motors section, Contact | https://www.pexels.com/photo/white-boat-on-body-of-water-during-golden-hour-358588/ |
| `calm-sea-sky.jpg` | Shipping band, Financing | https://www.pexels.com/photo/a-calm-sea-under-a-blue-sky-with-white-clouds-8333086/ |
| `aerial-boats-teal.jpg` | Quote band, Shipping | https://www.pexels.com/photo/boat-making-wake-while-floating-in-sea-5474885/ |

## Run the tests

```bash
.venv/bin/python -m pytest
```

Tests use an in-memory database and a fake mail sender. They don't use your `.env` values for the database, SMTP password or admin login.

## Preview file

`outboard-preview.html` is a snapshot of the home page for checking the design. Open it from the project folder so it can find `static/`. Its links and form need the running site, and it doesn't update when the inventory changes.
