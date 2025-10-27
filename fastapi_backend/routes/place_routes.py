# fastapi_backend/routes/place_routes.py

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
import asyncio
from functools import partial

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import aiofiles

from add_html_article.annotator import annotate_html
from fastapi_backend.Recommendation_Algorithm.embedding_service import get_embedding
from audio_backend.app.core.database import get_db
from audio_backend.app.models.tourism_models import Place, Place_Paragraph

# 缓存
from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

# 鉴权
from fastapi_backend.routes.auth_utils import get_current_admin_user, get_current_user

router = APIRouter(prefix="/places", tags=["places"])

# ==== 缓存命名空间 ====
NS_PLACES = "places:list"
NS_PLACE_DETAIL = "places:detail"
NS_PARAGRAPHS = "places:paragraphs"

# 上传目录（与你的项目保持一致）
BASE_DIR = Path(__file__).resolve().parents[1]
UPLOADS_DIR = Path(os.getenv("UPLOAD_DIR") or BASE_DIR / "uploads").resolve()
print("SAVE uploads =>", UPLOADS_DIR)

# -----------------------------
# Pydantic Schemas
# -----------------------------
class ImageSchema(BaseModel):
    url: str
    caption_es: Optional[str] = None
    caption_zh: Optional[str] = None


class AnnotationSchema(BaseModel):
    word_id: int
    text: str
    start: int
    end: int


class GrammarNoteSchema(BaseModel):
    type: str  # tense, structure, clause, etc.
    category: str
    text: str
    start: int
    end: int
    explanation_es: str
    explanation_zh: str
    example: Optional[str] = None


class ParagraphIn(BaseModel):
    order: int = Field(..., ge=1, description="段落顺序（从1开始）")
    text_es: str = Field(..., min_length=1)
    text_zh: str = Field(..., min_length=1)
    images: List[ImageSchema] = []
    audio_url: Optional[str] = None
    annotations: List[AnnotationSchema] = []
    grammar_notes: List[GrammarNoteSchema] = []


class ParagraphOut(BaseModel):
    id: int
    place_id: int
    order: int
    text_es: str
    text_zh: str
    images: List[dict]
    audio_url: Optional[str]
    annotations: List[dict]
    grammar_notes: List[dict]
    has_vector: bool = False

    class Config:
        from_attributes = True


class PlaceIn(BaseModel):
    city_id: int
    slug: str = Field(..., min_length=1, max_length=80)
    name_es: str = Field(..., min_length=1, max_length=255)
    name_zh: str = Field(..., min_length=1, max_length=255)
    summary_es: Optional[str] = None
    summary_zh: Optional[str] = None
    video_url: Optional[str] = None
    tags: List[str] = []
    is_published: bool = True


class PlaceUpdate(BaseModel):
    slug: Optional[str] = Field(None, min_length=1, max_length=80)
    name_es: Optional[str] = None
    name_zh: Optional[str] = None
    summary_es: Optional[str] = None
    summary_zh: Optional[str] = None
    video_url: Optional[str] = None
    tags: Optional[List[str]] = None
    is_published: Optional[bool] = None


class PlaceOut(BaseModel):
    id: int
    city_id: int
    slug: str
    name_es: str
    name_zh: str
    cover_image: Optional[str]
    summary_es: Optional[str]
    summary_zh: Optional[str]
    video_url: Optional[str]
    tags: List[str]
    rating: Optional[float]
    is_published: bool
    created_at: Optional[datetime] = None
    paragraphs: List[ParagraphOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PlaceListOut(BaseModel):
    id: int
    slug: str
    name_es: str
    name_zh: str
    cover_image: Optional[str]
    summary_es: Optional[str]
    tags: List[str]
    rating: Optional[float]
    is_published: bool

    class Config:
        from_attributes = True


# ==========================
#        Helper utils
# ==========================
async def _async_get_embedding(text: Optional[str]):
    """在线程池里跑同步 get_embedding，避免阻塞事件循环。"""
    if not text:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(get_embedding, text))


def _to_annotations_json(val: Optional[Any]) -> List[Dict[str, Any]]:
    if val is None:
        return []
    if isinstance(val, str):
        return [{"type": "html", "html": val}]
    if isinstance(val, dict):
        return [val]
    if isinstance(val, list):
        return val
    return []


def _url_to_abs_path(u: Optional[str]) -> Optional[Path]:
    """仅处理本地静态文件：/files/... 其它（http/https 或 None）直接忽略。"""
    if not u or u.startswith(("http://", "https://")):
        return None
    raw = u.lstrip("/")
    if not raw.startswith("files/"):
        return None
    rel = raw[len("files/") :]
    p = (UPLOADS_DIR / rel).resolve()
    if str(p).startswith(str(UPLOADS_DIR)):
        return p
    return None


def _delete_files_by_urls(urls: List[Optional[str]]) -> List[str]:
    removed: List[str] = []
    for u in set(filter(None, urls)):
        p = _url_to_abs_path(u)
        if p and p.exists():
            try:
                p.unlink()
                removed.append(str(p))
            except Exception as e:
                print("WARN: unlink failed:", p, e)
    return removed


def _as_bool(v: Optional[str], default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


def _normalize_files_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return u
    if u.startswith(("http://", "https://")):
        return u
    raw = u.lstrip("/")
    if raw.startswith("files/"):
        return "/" + raw
    if raw.startswith("uploads/"):
        return "/files/" + raw[len("uploads/") :]
    return f"/files/{raw}"


async def _save_upload_async(file: Optional[UploadFile], subdir: str = "images") -> Optional[str]:
    if not file:
        print("[UPLOAD] no file received")
        return None
    try:
        file.file.seek(0)
    except Exception:
        pass
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    today = datetime.now().strftime("%Y/%m/%d")
    rel_path = Path(subdir) / today / f"{uuid4().hex}{ext}"
    abs_path = (UPLOADS_DIR / rel_path).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[UPLOAD] saving -> {abs_path} (name={file.filename})")
    async with aiofiles.open(abs_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            await f.write(chunk)
    url = f"/files/{rel_path.as_posix()}"
    print(f"[UPLOAD] saved url: {url}")
    return url


def _paragraph_to_dict(p: Place_Paragraph) -> Dict[str, Any]:
    return {
        "id": p.id,
        "place_id": p.place_id,
        "order": p.order,
        "text_es": p.text_es,
        "text_zh": p.text_zh,
        "images": getattr(p, "images", []),
        "audio_url": getattr(p, "audio_url", None),
        "annotations": getattr(p, "annotations", []),
        "grammar_notes": getattr(p, "grammar_notes", []),
        "has_vector": getattr(p, "semantic_vector", None) is not None,
    }


def _paragraphs_for_place(db: Session, place_id: int) -> List[Place_Paragraph]:
    return (
        db.query(Place_Paragraph)
        .filter(Place_Paragraph.place_id == place_id)
        .order_by(Place_Paragraph.order.asc())
        .all()
    )


def _place_to_dict(db: Session, p: Place, include_paragraphs: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": p.id,
        "city_id": p.city_id,
        "slug": p.slug,
        "name_es": p.name_es,
        "name_zh": p.name_zh,
        "cover_image": p.cover_image,
        "summary_es": p.summary_es,
        "summary_zh": p.summary_zh,
        "video_url": p.video_url,
        "tags": p.tags or [],
        "rating": p.rating,
        "is_published": p.is_published,
        "created_at": getattr(p, "created_at", None),
        "paragraphs": [],
    }
    if include_paragraphs:
        paragraphs = getattr(p, "paragraphs", None) or _paragraphs_for_place(db, p.id)
        data["paragraphs"] = [_paragraph_to_dict(para) for para in paragraphs]
    return data


def _order_conflict(db: Session, place_id: int, order: int, exclude_id: Optional[int] = None) -> bool:
    q = db.query(Place_Paragraph.id).filter(Place_Paragraph.place_id == place_id, Place_Paragraph.order == int(order))
    if exclude_id:
        q = q.filter(Place_Paragraph.id != exclude_id)
    return db.query(q.exists()).scalar()


# ==========================
# 缓存失效工具
# ==========================
async def _invalidate_all_place_cache():
    try:
        await FastAPICache.clear(namespace=NS_PLACES)
        await FastAPICache.clear(namespace=NS_PLACE_DETAIL)
        await FastAPICache.clear(namespace=NS_PARAGRAPHS)
    except Exception as e:
        print("[CACHE] clear failed:", e)


# ==========================
#      Place JSON CRUD
# ==========================
@router.get("", response_model=List[PlaceListOut])
@cache(expire=60, namespace=NS_PLACES)
def list_places(
    city_id: Optional[int] = None,
    tag: Optional[str] = None,
    published_only: bool = True,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # 可选登录
):
    """获取 Place 列表（不含段落内容）"""
    query = db.query(Place)
    
    if city_id:
        query = query.filter(Place.city_id == city_id)
    
    if tag:
        query = query.filter(Place.tags.contains([tag]))
    
    # 非管理员只能看已发布的
    is_admin = current_user and getattr(current_user, "is_admin", False)
    if not is_admin:
        query = query.filter(Place.is_published == True)
    elif published_only:
        query = query.filter(Place.is_published == True)
    
    places = query.order_by(Place.created_at.desc()).offset(skip).limit(limit).all()
    return [_place_to_dict(db, p, include_paragraphs=False) for p in places]


@router.get("/{place_id}", response_model=PlaceOut)
@cache(expire=60, namespace=NS_PLACE_DETAIL)
def get_place_detail(
    place_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # 可选登录
):
    """获取 Place 详情（包含所有段落）"""
    place = db.query(Place).filter(Place.id == place_id).first()
    
    if not place:
        raise HTTPException(404, "Place not found")
    
    # 非管理员无法查看未发布的内容
    is_admin = current_user and getattr(current_user, "is_admin", False)
    if not place.is_published and not is_admin:
        raise HTTPException(403, "This place is not published")
    
    return _place_to_dict(db, place, include_paragraphs=True)


@router.post("", response_model=PlaceOut)
async def create_place(
    payload: PlaceIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """创建新 Place（仅管理员）"""
    # 检查 slug 是否重复
    existing = db.query(Place).filter(
        Place.city_id == payload.city_id,
        Place.slug == payload.slug
    ).first()
    
    if existing:
        raise HTTPException(400, f"Place with slug '{payload.slug}' already exists in this city")
    
    place = Place(**payload.model_dump())
    db.add(place)
    db.commit()
    db.refresh(place)
    await _invalidate_all_place_cache()
    return _place_to_dict(db, place, include_paragraphs=True)


@router.put("/{place_id}", response_model=PlaceOut)
async def update_place(
    place_id: int,
    payload: PlaceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """更新 Place 基本信息（仅管理员）"""
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    # 更新字段
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(place, key, value)
    
    db.commit()
    db.refresh(place)
    await _invalidate_all_place_cache()
    return _place_to_dict(db, place, include_paragraphs=True)


@router.delete("/{place_id}", status_code=204)
async def delete_place(
    place_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """删除 Place（级联删除所有段落）（仅管理员）"""
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    # 收集需要删除的文件
    urls: List[Optional[str]] = []
    if place.cover_image:
        urls.append(place.cover_image)
    
    # 段落中的图片
    paragraphs = _paragraphs_for_place(db, place_id)
    for para in paragraphs:
        images = getattr(para, "images", [])
        for img in images:
            if isinstance(img, dict) and img.get("url"):
                urls.append(img["url"])
    
    db.delete(place)
    db.commit()
    
    removed = _delete_files_by_urls(urls)
    if removed:
        print("Deleted files:", removed)
    
    await _invalidate_all_place_cache()
    return Response(status_code=204)


# ==========================
#   Place with-image
# ==========================
@router.post("/with-image", response_model=PlaceOut)
async def create_place_with_image(
    city_id: int = Form(...),
    slug: str = Form(...),
    name_es: str = Form(...),
    name_zh: str = Form(...),
    summary_es: Optional[str] = Form(None),
    summary_zh: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string: '["tag1", "tag2"]'
    is_published: Optional[str] = Form("true"),
    cover_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)
):
    """创建 Place（带封面图上传）"""
    import json
    
    # 检查 slug 重复
    existing = db.query(Place).filter(
        Place.city_id == city_id,
        Place.slug == slug
    ).first()
    if existing:
        raise HTTPException(400, f"Place with slug '{slug}' already exists")
    
    print(f"[PLACE] create with-image, file?: {bool(cover_image)}")
    cover_url = await _save_upload_async(cover_image) if cover_image else None
    
    tags_list = json.loads(tags) if tags else []
    
    place = Place(
        city_id=city_id,
        slug=slug,
        name_es=name_es,
        name_zh=name_zh,
        cover_image=cover_url,
        summary_es=summary_es,
        summary_zh=summary_zh,
        video_url=video_url,
        tags=tags_list,
        is_published=_as_bool(is_published, True)
    )
    db.add(place)
    db.commit()
    db.refresh(place)
    await _invalidate_all_place_cache()
    return _place_to_dict(db, place, include_paragraphs=True)


@router.put("/{place_id}/with-image", response_model=PlaceOut)
async def update_place_with_image(
    place_id: int,
    slug: Optional[str] = Form(None),
    name_es: Optional[str] = Form(None),
    name_zh: Optional[str] = Form(None),
    summary_es: Optional[str] = Form(None),
    summary_zh: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    is_published: Optional[str] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    keep_existing_image: Optional[str] = Form("true"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)
):
    """更新 Place（支持更换封面图）"""
    import json
    
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    if slug is not None:
        place.slug = slug
    if name_es is not None:
        place.name_es = name_es
    if name_zh is not None:
        place.name_zh = name_zh
    if summary_es is not None:
        place.summary_es = summary_es
    if summary_zh is not None:
        place.summary_zh = summary_zh
    if video_url is not None:
        place.video_url = video_url
    if tags is not None:
        place.tags = json.loads(tags) if tags else []
    if is_published is not None:
        place.is_published = _as_bool(is_published, True)
    
    print(f"[PLACE] update with-image place={place_id}, file?: {bool(cover_image)}")
    if cover_image is not None:
        place.cover_image = await _save_upload_async(cover_image)
    else:
        keep = _as_bool(keep_existing_image, True)
        if not keep:
            place.cover_image = None
    
    db.commit()
    db.refresh(place)
    await _invalidate_all_place_cache()
    return _place_to_dict(db, place, include_paragraphs=True)


# ==========================
#         Paragraphs
# ==========================
@router.get("/{place_id}/paragraphs", response_model=List[ParagraphOut])
@cache(expire=60, namespace=NS_PARAGRAPHS)
def list_paragraphs(
    place_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # 可选登录
):
    """获取段落列表"""
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    is_admin = current_user and getattr(current_user, "is_admin", False)
    if not place.is_published and not is_admin:
        raise HTTPException(403, "This place is not published")
    
    paragraphs = _paragraphs_for_place(db, place_id)
    return [_paragraph_to_dict(p) for p in paragraphs]


@router.post("/{place_id}/paragraphs", response_model=ParagraphOut)
async def create_paragraph(
    place_id: int,
    body: ParagraphIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """添加段落（仅管理员）"""
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    # 检查 order 是否重复
    if _order_conflict(db, place_id, body.order):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_order",
                "message": f"段落顺序 {body.order} 已存在",
                "place_id": place_id,
                "order": body.order,
            }
        )
    
    # 生成语义向量 + 注释（仅对 text_es）
    try:
        ann_val = annotate_html(body.text_es) if body.text_es else None
    except Exception as e:
        print(f"[ANNOTATE] failed: {e}")
        ann_val = None
    
    p = Place_Paragraph(
        place_id=place_id,
        order=body.order,
        text_es=body.text_es,
        text_zh=body.text_zh,
        images=body.images or [],
        audio_url=body.audio_url,
        annotations=body.annotations or [],  # 用户传入的词汇关联
        grammar_notes=body.grammar_notes or [],
        semantic_vector=await _async_get_embedding(body.text_es),
    )
    
    # 如果 annotate_html 有返回结果，可以合并到 annotations
    # 这里假设你的 annotations 是词汇关联，annotate_html 是另一种标注
    # 如果需要合并，可以这样：
    # if ann_val:
    #     p.annotations.append({"type": "auto", "data": ann_val})
    
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_order",
                "message": f"段落顺序 {body.order} 已存在",
                "place_id": place_id,
                "order": body.order,
            }
        )
    
    db.refresh(p)
    await _invalidate_all_place_cache()
    return _paragraph_to_dict(p)


@router.put("/{place_id}/paragraphs/{paragraph_id}", response_model=ParagraphOut)
async def update_paragraph(
    place_id: int,
    paragraph_id: int,
    body: ParagraphIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """更新段落（仅管理员）"""
    p = db.query(Place_Paragraph).filter(
        Place_Paragraph.id == paragraph_id,
        Place_Paragraph.place_id == place_id
    ).first()
    
    if not p:
        raise HTTPException(404, "Paragraph not found")
    
    # 检查 order 冲突
    if body.order != p.order and _order_conflict(db, place_id, body.order, exclude_id=p.id):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_order",
                "message": f"段落顺序 {body.order} 已存在",
                "place_id": place_id,
                "order": body.order,
            }
        )
    
    text_changed = (body.text_es != p.text_es)
    
    p.order = body.order
    p.text_es = body.text_es
    p.text_zh = body.text_zh
    p.images = body.images or []
    p.audio_url = body.audio_url
    p.annotations = body.annotations or []
    p.grammar_notes = body.grammar_notes or []
    
    # 如果西语文本变了，重新生成向量
    if text_changed:
        p.semantic_vector = await _async_get_embedding(body.text_es)
    
    db.commit()
    db.refresh(p)
    await _invalidate_all_place_cache()
    return _paragraph_to_dict(p)


@router.delete("/{place_id}/paragraphs/{paragraph_id}", status_code=204)
async def delete_paragraph(
    place_id: int,
    paragraph_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """删除段落（仅管理员）"""
    p = db.query(Place_Paragraph).filter(
        Place_Paragraph.id == paragraph_id,
        Place_Paragraph.place_id == place_id
    ).first()
    
    if not p:
        raise HTTPException(404, "Paragraph not found")
    
    # 删除段落中的图片文件
    images = getattr(p, "images", [])
    urls = [img.get("url") for img in images if isinstance(img, dict)]
    
    db.delete(p)
    db.commit()
    
    removed = _delete_files_by_urls(urls)
    if removed:
        print("Deleted files:", removed)
    
    await _invalidate_all_place_cache()
    return Response(status_code=204)


@router.post("/{place_id}/paragraphs/reorder", status_code=204)
async def reorder_paragraphs(
    place_id: int,
    paragraph_ids: List[int],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)  # 仅管理员
):
    """
    批量调整段落顺序（仅管理员）
    传入排序后的 paragraph_id 列表，自动分配 order 为 1, 2, 3...
    """
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    paragraphs = db.query(Place_Paragraph).filter(
        Place_Paragraph.place_id == place_id,
        Place_Paragraph.id.in_(paragraph_ids)
    ).all()
    
    if len(paragraphs) != len(paragraph_ids):
        raise HTTPException(400, "Some paragraph IDs are invalid")
    
    # 按传入的顺序重新分配 order
    paragraph_map = {p.id: p for p in paragraphs}
    for new_order, pid in enumerate(paragraph_ids, start=1):
        paragraph_map[pid].order = new_order
    
    db.commit()
    await _invalidate_all_place_cache()
    return Response(status_code=204)


@router.get("/{place_id}/paragraphs/used-orders", response_model=List[int])
@cache(expire=60, namespace=NS_PARAGRAPHS)
def list_used_paragraph_orders(
    place_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # 可选登录
):
    """获取已使用的段落顺序号"""
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(404, "Place not found")
    
    rows = (
        db.query(Place_Paragraph.order)
        .filter(Place_Paragraph.place_id == place_id)
        .order_by(Place_Paragraph.order.asc())
        .all()
    )
    return [n for (n,) in rows]