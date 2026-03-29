from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.responses import HTMLResponse
from PIL import Image, ExifTags
import os
import io
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, Photo, WardrobeItem

app = FastAPI()

UPLOAD_FOLDER = "uploads"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rgb_to_color_name(r, g, b):
    if r < 60 and g < 60 and b < 60:
        return "siyah"
    if r > 200 and g > 200 and b > 200:
        return "beyaz"
    if r > 150 and g < 100 and b < 100:
        return "kırmızı"
    if r < 120 and g < 120 and b > 150:
        return "mavi"
    if r < 140 and g > 120 and b < 140:
        return "yeşil"
    if 80 <= r <= 180 and 80 <= g <= 180 and 80 <= b <= 180:
        return "gri"
    if r > 100 and g > 70 and b < 80:
        return "kahverengi"
    return "karışık"


def fake_predict_clothing(main_color: str):
    mapping = {
        "siyah": "ceket",
        "gri": "hoodie",
        "beyaz": "t-shirt",
        "mavi": "kot pantolon",
        "kahverengi": "gömlek",
        "kırmızı": "sweatshirt"
    }
    return mapping.get(main_color, "t-shirt")


def get_detected_style(main_color: str, clothing_type: str):
    if clothing_type in ["hoodie", "sweatshirt", "eşofman"]:
        return "streetwear"
    if clothing_type in ["gömlek", "ceket"]:
        return "classic"
    if main_color in ["siyah", "beyaz", "gri"]:
        return "minimal"
    return "casual"


def get_category_from_type(clothing_type: str):
    upper = {
        "hoodie", "sweatshirt", "gömlek", "ceket",
        "t-shirt", "oversize t-shirt", "blazer", "basic hoodie"
    }
    lower = {"kot pantolon", "eşofman", "pantolon", "siyah pantolon"}
    shoes = {"sneaker", "deri ayakkabı", "beyaz sneaker"}

    if clothing_type in upper:
        return "üst"
    if clothing_type in lower:
        return "alt"
    if clothing_type in shoes:
        return "ayakkabı"
    return "diğer"


def extract_metadata(image: Image.Image):
    taken_at = None
    latitude = None
    longitude = None
    location_name = None

    try:
        exif = image.getexif()
        if exif:
            exif_data = {}
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                exif_data[tag] = value

            date_str = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
            if date_str:
                try:
                    taken_at = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except:
                    taken_at = None
    except:
        pass

    return taken_at, latitude, longitude, location_name


def find_or_create_wardrobe_item(
    db: Session,
    color: str,
    clothing_type: str,
    style: str,
    worn_at: datetime | None,
    location_name: str | None
):
    existing_item = (
        db.query(WardrobeItem)
        .filter(
            WardrobeItem.color == color,
            WardrobeItem.clothing_type == clothing_type
        )
        .first()
    )

    actual_worn_at = worn_at if worn_at else datetime.utcnow()

    if existing_item:
        existing_item.wear_count += 1
        existing_item.last_worn_at = actual_worn_at
        if location_name:
            existing_item.last_location = location_name
        db.commit()
        db.refresh(existing_item)
        return existing_item

    new_item = WardrobeItem(
        name=f"{color} {clothing_type}",
        color=color,
        clothing_type=clothing_type,
        style=style,
        wear_count=1,
        last_worn_at=actual_worn_at,
        last_location=location_name
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


def process_single_file(file_bytes: bytes, filename: str, db: Session):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    original_image = Image.open(io.BytesIO(file_bytes))

    taken_at, latitude, longitude, location_name = extract_metadata(original_image)

    resized = image.resize((100, 100))
    pixels = list(resized.getdata())

    avg_r = sum(pixel[0] for pixel in pixels) // len(pixels)
    avg_g = sum(pixel[1] for pixel in pixels) // len(pixels)
    avg_b = sum(pixel[2] for pixel in pixels) // len(pixels)

    main_color = rgb_to_color_name(avg_r, avg_g, avg_b)
    clothing_type = fake_predict_clothing(main_color)
    detected_style = get_detected_style(main_color, clothing_type)

    photo = Photo(
        filename=filename,
        saved_path=file_path,
        main_color=main_color,
        clothing_type=clothing_type,
        detected_style=detected_style,
        taken_at=taken_at,
        location_name=location_name,
        latitude=latitude,
        longitude=longitude
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    wardrobe_item = find_or_create_wardrobe_item(
        db=db,
        color=main_color,
        clothing_type=clothing_type,
        style=detected_style,
        worn_at=taken_at,
        location_name=location_name
    )

    return {
        "filename": filename,
        "saved_path": file_path,
        "main_color": main_color,
        "clothing_type": clothing_type,
        "detected_style": detected_style,
        "taken_at": taken_at.isoformat() if taken_at else None,
        "location_name": location_name,
        "wardrobe_item_id": wardrobe_item.id,
        "wear_count": wardrobe_item.wear_count
    }


@app.get("/")
def home():
    return {"message": "API çalışıyor"}


@app.get("/batch-test", response_class=HTMLResponse)
def batch_test_page():
    return """
    <html>
        <head>
            <meta charset="utf-8">
            <title>Çoklu Foto Yükleme</title>
        </head>
        <body style="font-family: Arial; padding: 24px;">
            <h2>Çoklu Foto Yükleme Testi</h2>
            <form action="/upload-batch" enctype="multipart/form-data" method="post">
                <input name="files" type="file" multiple>
                <button type="submit">Yükle</button>
            </form>
        </body>
    </html>
    """


@app.post("/upload")
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    return process_single_file(contents, file.filename, db)


@app.post("/upload-batch")
async def upload_batch(
    files: List[UploadFile] = File(..., description="Birden fazla foto yükle"),
    db: Session = Depends(get_db)
):
    results = []

    for file in files:
        contents = await file.read()
        result = process_single_file(contents, file.filename, db)
        results.append(result)

    return {
        "total_uploaded": len(results),
        "results": results
    }


@app.get("/wardrobe-items")
def get_wardrobe_items(db: Session = Depends(get_db)):
    items = db.query(WardrobeItem).all()

    return [
        {
            "id": item.id,
            "name": item.name,
            "color": item.color,
            "clothing_type": item.clothing_type,
            "style": item.style,
            "category": get_category_from_type(item.clothing_type),
            "wear_count": item.wear_count,
            "last_worn_at": item.last_worn_at.isoformat() if item.last_worn_at else None,
            "last_location": item.last_location
        }
        for item in items
    ]


@app.get("/unused-items")
def get_unused_items(db: Session = Depends(get_db)):
    threshold_date = datetime.utcnow() - timedelta(days=90)

    items = (
        db.query(WardrobeItem)
        .filter(WardrobeItem.last_worn_at < threshold_date)
        .all()
    )

    return [
        {
            "id": item.id,
            "name": item.name,
            "color": item.color,
            "clothing_type": item.clothing_type,
            "style": item.style,
            "wear_count": item.wear_count,
            "last_worn_at": item.last_worn_at.isoformat() if item.last_worn_at else None,
            "last_location": item.last_location,
            "message": f"{item.name} uzun süredir giyilmemiş görünüyor."
        }
        for item in items
    ]


@app.get("/style-profile")
def get_style_profile(db: Session = Depends(get_db)):
    items = db.query(WardrobeItem).all()

    if not items:
        return {"message": "Henüz dolap verisi yok."}

    color_counts = {}
    type_counts = {}
    style_counts = {}

    for item in items:
        color_counts[item.color] = color_counts.get(item.color, 0) + item.wear_count
        type_counts[item.clothing_type] = type_counts.get(item.clothing_type, 0) + item.wear_count
        style_counts[item.style] = style_counts.get(item.style, 0) + item.wear_count

    dominant_color = max(color_counts, key=color_counts.get)
    dominant_type = max(type_counts, key=type_counts.get)
    dominant_style = max(style_counts, key=style_counts.get)

    return {
        "dominant_color": dominant_color,
        "dominant_clothing_type": dominant_type,
        "dominant_style": dominant_style,
        "total_items_detected": len(items)
    }


@app.get("/outfit-history/{item_id}")
def get_outfit_history(item_id: int, db: Session = Depends(get_db)):
    item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()

    if not item:
        return {"message": "Ürün bulunamadı."}

    matching_photos = (
        db.query(Photo)
        .filter(
            Photo.main_color == item.color,
            Photo.clothing_type == item.clothing_type
        )
        .all()
    )

    return {
        "item": {
            "id": item.id,
            "name": item.name,
            "wear_count": item.wear_count
        },
        "history": [
            {
                "photo_id": photo.id,
                "filename": photo.filename,
                "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
                "location_name": photo.location_name
            }
            for photo in matching_photos
        ]
    }


@app.post("/set-item-date/{item_id}")
def set_item_date(item_id: int, days_ago: int, db: Session = Depends(get_db)):
    item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()

    if not item:
        return {"message": "Ürün bulunamadı"}

    new_date = datetime.utcnow() - timedelta(days=days_ago)
    item.last_worn_at = new_date

    db.commit()
    db.refresh(item)

    return {
        "message": f"{item.name} tarihi güncellendi",
        "new_date": new_date.isoformat()
    }


@app.get("/recommend-items")
def recommend_items(db: Session = Depends(get_db)):
    items = db.query(WardrobeItem).all()

    if not items:
        return {"message": "Dolap boş"}

    style_counts = {}
    owned_types = set()

    for item in items:
        style_counts[item.style] = style_counts.get(item.style, 0) + item.wear_count
        owned_types.add(item.clothing_type)

    dominant_style = max(style_counts, key=style_counts.get)

    style_requirements = {
        "streetwear": ["hoodie", "sneaker", "oversize t-shirt", "eşofman"],
        "classic": ["gömlek", "blazer", "pantolon", "deri ayakkabı"],
        "minimal": ["beyaz t-shirt", "siyah pantolon", "basic hoodie"],
        "casual": ["t-shirt", "kot pantolon", "sweatshirt"]
    }

    required_items = style_requirements.get(dominant_style, [])
    missing_items = []

    for req in required_items:
        if req not in owned_types:
            search_query = req.replace(" ", "+")
            missing_items.append({
                "item": req,
                "reason": f"{dominant_style} tarzın için eksik",
                "search_links": [
                    f"https://www.google.com/search?q={search_query}+erkek",
                    f"https://www.trendyol.com/sr?q={search_query}"
                ]
            })

    return {
        "dominant_style": dominant_style,
        "missing_items": missing_items
    }


@app.get("/smart-recommendations")
def smart_recommendations(db: Session = Depends(get_db)):
    items = db.query(WardrobeItem).all()

    if not items:
        return {"message": "Henüz dolap verisi yok."}

    color_counts = {}
    style_counts = {}
    category_counts = {"üst": 0, "alt": 0, "ayakkabı": 0, "diğer": 0}

    for item in items:
        color_counts[item.color] = color_counts.get(item.color, 0) + item.wear_count
        style_counts[item.style] = style_counts.get(item.style, 0) + item.wear_count

        category = get_category_from_type(item.clothing_type)
        category_counts[category] = category_counts.get(category, 0) + 1

    dominant_style = max(style_counts, key=style_counts.get)
    dominant_colors_sorted = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    dominant_colors = [color for color, _ in dominant_colors_sorted[:3]]

    insights = []
    missing_basics = []
    unused_alerts = []

    if category_counts["üst"] > category_counts["alt"]:
        insights.append("Üst parça sayın alt parçalardan fazla.")
        missing_basics.append("nötr alt parça")

    if category_counts["ayakkabı"] == 0:
        insights.append("Dolabında ayakkabı verisi görünmüyor.")
        missing_basics.append("beyaz sneaker")

    if dominant_style == "streetwear":
        insights.append("Streetwear tarzın güçlü görünüyor.")
        missing_basics.extend(["oversize t-shirt", "sneaker"])

    elif dominant_style == "minimal":
        insights.append("Minimal ve sade parçalara ağırlık veriyorsun.")
        missing_basics.extend(["siyah pantolon", "beyaz sneaker"])

    elif dominant_style == "classic":
        insights.append("Klasik ve daha düzenli bir stil çizgin var.")
        missing_basics.extend(["blazer", "deri ayakkabı"])

    elif dominant_style == "casual":
        insights.append("Rahat ve günlük kombinleri tercih ediyorsun.")
        missing_basics.extend(["basic sweatshirt", "kot pantolon"])

    threshold_date = datetime.utcnow() - timedelta(days=90)
    old_items = (
        db.query(WardrobeItem)
        .filter(WardrobeItem.last_worn_at < threshold_date)
        .all()
    )

    for item in old_items:
        unused_alerts.append(f"{item.name} uzun süredir kullanılmamış.")

    cleaned_missing_basics = []
    seen = set()
    owned_types = {item.clothing_type for item in items}

    for basic in missing_basics:
        if basic not in seen and basic not in owned_types:
            cleaned_missing_basics.append(basic)
            seen.add(basic)

    return {
        "dominant_style": dominant_style,
        "dominant_colors": dominant_colors,
        "wardrobe_balance": category_counts,
        "insights": insights,
        "missing_basics": cleaned_missing_basics,
        "unused_alerts": unused_alerts
    }