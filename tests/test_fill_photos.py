from fill_photos import assign, collect, score, skip_name


def photo(title, category="Category:Yamaha outboard motors"):
    return {"title": title, "url": f"https://upload.example/{title}", "category": category}


def fake_commons(files_by_category, subcats_by_category):
    """A stand-in for the Commons API that answers the two queries fill_photos makes."""
    def fetch(params):
        if params.get("list") == "categorymembers":
            members = [{"title": t} for t in subcats_by_category.get(params["cmtitle"], [])]
            return {"query": {"categorymembers": members}}
        pages = [
            {"title": title, "imageinfo": [{"mime": mime, "width": 1200, "height": 900, "thumburl": f"https://upload.example/{title}"}]}
            for title, mime in files_by_category.get(params["gcmtitle"], [])
        ]
        return {"query": {"pages": pages}}
    return fetch


def test_collect_follows_subcategories_and_skips_logos_and_non_photos():
    fetch = fake_commons(
        {
            "Category:Yamaha outboard motors": [("File:Yamaha F150 on boat.jpg", "image/jpeg"), ("File:Yamaha logo.svg", "image/svg+xml")],
            "Category:Yamaha F115": [("File:Yamaha F115.jpg", "image/jpeg"), ("File:Yamaha F115 serial plate.jpg", "image/jpeg")],
            "Category:Yamaha logos": [("File:Yamaha old logo.png", "image/png")],
        },
        {"Category:Yamaha outboard motors": ["Category:Yamaha F115", "Category:Yamaha logos"]},
    )
    titles = [p["title"] for p in collect(fetch, "Category:Yamaha outboard motors")]
    assert titles == ["File:Yamaha F150 on boat.jpg", "File:Yamaha F115.jpg"]


def test_every_motor_gets_a_different_photo_and_overflow_uses_general_photos():
    motors = [{"id": i, "make": "Yamaha", "model": None, "hp": 50, "stroke": 4} for i in (1, 2, 3)]
    pools = {"yamaha": [photo("File:Yamaha A.jpg"), photo("File:Yamaha B.jpg")]}
    fallback = [photo("File:Outboard C.jpg", "Category:Outboard motors")]
    chosen = assign(motors, pools, fallback)
    urls = [chosen[i]["url"] for i in (1, 2, 3)]
    assert len(set(urls)) == 3
    assert chosen[3]["title"] == "File:Outboard C.jpg"


def test_motor_gets_photo_matching_its_model_and_stroke():
    motors = [{"id": 1, "make": "Yamaha", "model": "F115", "hp": 115, "stroke": 4}]
    pools = {"yamaha": [photo("File:Yamaha 2-stroke 40.jpg"), photo("File:Yamaha F115 bet.JPG")]}
    assert assign(motors, pools, [])[1]["title"] == "File:Yamaha F115 bet.JPG"


def test_selva_yamaha_motor_can_use_either_brand():
    motors = [{"id": 1, "make": "Selva / Yamaha", "model": None, "hp": 25, "stroke": 4}]
    pools = {"yamaha": [photo("File:Yamaha A.jpg")], "selva": []}
    assert assign(motors, pools, [])[1]["title"] == "File:Yamaha A.jpg"


def test_museum_pieces_rank_below_modern_photos():
    motor = {"id": 1, "make": "Johnson", "model": None, "hp": 50, "stroke": 2}
    assert score(photo("File:1927 Johnson Seahorse.jpg"), motor) < score(photo("File:Johnson outboard.jpg"), motor)


def test_skip_name():
    assert skip_name("File:Mercury Verado Mid & Lower Unit Cutaway .jpg")
    assert not skip_name("File:Merc 50 hp.jpg")
