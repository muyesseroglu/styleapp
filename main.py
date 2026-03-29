from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from PIL import Image, ExifTags
import os
import io
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, Photo, WardrobeItem, User
from auth import (
    get_db, get_current_user, authenticate_user,
    get_password_hash, create_access_token, get_user_by_username, get_user_by_email,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

Base.metadata.create_all(bind=engine)

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

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

def find_or_create_wardrobe_item(db, color, clothing_type, style, worn_at, location_name, user_id):
    existing_item = (
        db.query(WardrobeItem)
        .filter(
            WardrobeItem.color == color,
            WardrobeItem.clothing_type == clothing_type,
            WardrobeItem.user_id == user_id
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
        last_location=location_name,
        user_id=user_id
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

def process_single_file(file_bytes, filename, db, user_id):
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
        longitude=longitude,
        user_id=user_id
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
        location_name=location_name,
        user_id=user_id
    )
    return {
        "filename": filename,
        "main_color": main_color,
        "clothing_type": clothing_type,
        "detected_style": detected_style,
        "taken_at": taken_at.isoformat() if taken_at else None,
        "wardrobe_item_id": wardrobe_item.id,
        "wear_count": wardrobe_item.wear_count
    }

@app.get("/")
def home():
    return {"message": "StyleApp API çalışıyor"}

@app.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if get_user_by_username(db, request.username):
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten alınmış")
    if get_user_by_email(db, request.email):
        raise HTTPException(status_code=400, detail="Bu email zaten kayıtlı")
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=get_password_hash(request.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Kayıt başarılı", "username": user.username}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")
    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer", "username": user.username}

@app.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contents = await file.read()
    return process_single_file(contents, file.filename, db, current_user.id)

@app.post("/upload-batch")
async def upload_batch(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    results = []
    for file in files:
        contents = await file.read()
        result = process_single_file(contents, file.filename, db, current_user.id)
        results.append(result)
    return {"total_uploaded": len(results), "results": results}

@app.get("/wardrobe-items")
def get_wardrobe_items(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(WardrobeItem).filter(WardrobeItem.user_id == current_user.id).all()
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
def get_unused_items(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    threshold_date = datetime.utcnow() - timedelta(days=90)
    items = db.query(WardrobeItem).filter(
        WardrobeItem.user_id == current_user.id,
        WardrobeItem.last_worn_at < threshold_date
    ).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "color": item.color,
            "clothing_type": item.clothing_type,
            "style": item.style,
            "wear_count": item.wear_count,
            "last_worn_at": item.last_worn_at.isoformat() if item.last_worn_at else None,
            "message": f"{item.name} uzun süredir giyilmemiş görünüyor."
        }
        for item in items
    ]

@app.get("/style-profile")
def get_style_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(WardrobeItem).filter(WardrobeItem.user_id == current_user.id).all()
    if not items:
        return {"message": "Henüz dolap verisi yok."}
    color_counts = {}
    type_counts = {}
    style_counts = {}
    for item in items:
        color_counts[item.color] = color_counts.get(item.color, 0) + item.wear_count
        type_counts[item.clothing_type] = type_counts.get(item.clothing_type, 0) + item.wear_count
        style_counts[item.style] = style_counts.get(item.style, 0) + item.wear_count
    return {
        "dominant_color": max(color_counts, key=color_counts.get),
        "dominant_clothing_type": max(type_counts, key=type_counts.get),
        "dominant_style": max(style_counts, key=style_counts.get),
        "total_items_detected": len(items)
    }

@app.get("/smart-recommendations")
def smart_recommendations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(WardrobeItem).filter(WardrobeItem.user_id == current_user.id).all()
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
    old_items = db.query(WardrobeItem).filter(
        WardrobeItem.user_id == current_user.id,
        WardrobeItem.last_worn_at < threshold_date
    ).all()
    unused_alerts = [f"{item.name} uzun süredir kullanılmamış." for item in old_items]
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
    