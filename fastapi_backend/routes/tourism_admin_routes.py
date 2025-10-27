# fastapi_backend/routes/tourism_admin_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from audio_backend.app.core.database import get_db
from fastapi_backend.routes.auth_utils import get_current_admin_user, get_current_user
from audio_backend.app.models.tourism_models import Country, City, Place

router = APIRouter(
    prefix="/tourism/admin",
    tags=["tourism-admin"]
)

# -------------------- 国家 --------------------
@router.post("/countries", status_code=status.HTTP_201_CREATED)
async def create_country(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    data = await request.json()
    country = Country(
        slug=data["slug"],
        name_es=data["name_es"],
        name_zh=data["name_zh"],
        intro_es=data.get("intro_es"),
        intro_zh=data.get("intro_zh"),
        cover_image=data.get("cover_image"),
        gallery=data.get("gallery", []),
    )
    db.add(country)
    db.commit()
    db.refresh(country)
    return {"id": country.id, "slug": country.slug, "name_es": country.name_es, "name_zh": country.name_zh}

@router.get("/countries")
async def list_countries(db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    countries = db.query(Country).order_by(Country.id.desc()).all()
    return [
        {
            "id": c.id,
            "name_es": c.name_es,
            "name_zh": c.name_zh,
            "cover_image": c.cover_image
        }
        for c in countries
    ]

@router.get("/countries/{country_id}")
async def get_country(country_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    country = db.query(Country).filter(Country.id == country_id).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    return {
        "id": country.id,
        "slug": country.slug,
        "name_es": country.name_es,
        "name_zh": country.name_zh,
        "intro_es": country.intro_es,
        "intro_zh": country.intro_zh,
        "cover_image": country.cover_image,
        "gallery": country.gallery,
        "created_at": country.created_at.isoformat(),
        "updated_at": country.updated_at.isoformat(),
    }

@router.put("/countries/{country_id}")
async def update_country(country_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    country = db.query(Country).filter(Country.id == country_id).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    data = await request.json()
    for field in ["slug", "name_es", "name_zh", "intro_es", "intro_zh", "cover_image", "gallery"]:
        if field in data:
            setattr(country, field, data[field])

    db.commit()
    db.refresh(country)
    return {"id": country.id, "slug": country.slug, "name_es": country.name_es, "name_zh": country.name_zh}

@router.delete("/countries/{country_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_country(country_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    country = db.query(Country).filter(Country.id == country_id).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    db.delete(country)
    db.commit()
    return None


# -------------------- 城市 --------------------
@router.post("/cities", status_code=status.HTTP_201_CREATED)
async def create_city(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    data = await request.json()
    city = City(
        country_id=data["country_id"],
        slug=data["slug"],
        name_es=data["name_es"],
        name_zh=data["name_zh"],
        intro_es=data.get("intro_es"),
        intro_zh=data.get("intro_zh"),
        images=data.get("images", []),
        tags=data.get("tags", []),
    )
    db.add(city)
    db.commit()
    db.refresh(city)
    return {"id": city.id, "slug": city.slug, "name_es": city.name_es, "name_zh": city.name_zh}

@router.get("/cities")
async def list_cities(country_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cities = db.query(City).filter(City.country_id == country_id).all()
    return [
        {
            "id": c.id,
            "name_es": c.name_es,
            "name_zh": c.name_zh,
            "cover_image": c.images[0] if c.images else None  # 只取第一张作为封面
        }
        for c in cities
    ]

@router.get("/cities/{city_id}")
async def get_city(city_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    return {
        "id": city.id,
        "slug": city.slug,
        "name_es": city.name_es,
        "name_zh": city.name_zh,
        "intro_es": city.intro_es,
        "intro_zh": city.intro_zh,
        "images": city.images,
        "tags": city.tags,
        "created_at": city.created_at.isoformat(),
        "updated_at": city.updated_at.isoformat(),
    }

@router.put("/cities/{city_id}")
async def update_city(city_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    data = await request.json()
    for field in ["slug", "name_es", "name_zh", "intro_es", "intro_zh", "images", "tags"]:
        if field in data:
            setattr(city, field, data[field])

    db.commit()
    db.refresh(city)
    return {"id": city.id, "slug": city.slug, "name_es": city.name_es, "name_zh": city.name_zh}

@router.delete("/cities/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city(city_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_admin_user)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    db.delete(city)
    db.commit()
    return None


