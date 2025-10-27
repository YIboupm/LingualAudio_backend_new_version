# fastapi_backend/routes/story_routes.py

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
from audio_backend.app.models.story_models import Story, Chapter, Paragraph

# 缓存
from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

# 如需鉴权，可把下两行依赖挂到对应路由参数中
from fastapi_backend.routes.auth_utils import get_current_admin_user, get_current_user

router = APIRouter(prefix="/stories", tags=["stories"])

# ==== 缓存命名空间（方便精准失效） ====
NS_STORIES = "stories:list"            # 列表/聚合
NS_STORY_DETAIL = "stories:detail"     # 单个故事详情
NS_CHAPTERS = "stories:chapters"       # 章节列表/详情
NS_PARAGRAPHS = "stories:paragraphs"   # 段落列表/详情

# 与 main.py 保持一致（/files 挂载到 uploads/）
BASE_DIR = Path(__file__).resolve().parents[1]
UPLOADS_DIR = Path(os.getenv("UPLOAD_DIR") or BASE_DIR / "uploads").resolve()
print("SAVE uploads =>", UPLOADS_DIR)

# -----------------------------
# Pydantic Schemas
# -----------------------------
class ParagraphIn(BaseModel):
    paragraph_number: int
    original_text: str
    translation_text: Optional[str] = None


class ParagraphOut(ParagraphIn):
    id: int
    annotations: Optional[List[Dict[str, Any]]] = None
    has_vector: bool = False

    class Config:
        from_attributes = True


class ChapterOut(BaseModel):
    id: int
    chapter_number: int
    title: Optional[str] = None
    image_url: Optional[str] = None
    grammar_explanation: Optional[str] = None

    class Config:
        from_attributes = True


class StoryOut(BaseModel):
    id: int
    title: str
    cover_image_url: Optional[str] = None
    summary: Optional[str] = None
    translated_summary: Optional[str] = None
    created_at: Optional[datetime] = None
    chapters: List[ChapterOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class StoryIn(BaseModel):
    title: str
    cover_image_url: Optional[str] = None
    summary: Optional[str] = None
    translated_summary: Optional[str] = None


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    cover_image_url: Optional[str] = None
    summary: Optional[str] = None
    translated_summary: Optional[str] = None


class ChapterIn(BaseModel):
    chapter_number: int
    title: Optional[str] = None
    image_url: Optional[str] = None
    grammar_explanation: Optional[str] = None


class ChapterUpdate(BaseModel):
    chapter_number: Optional[int] = None
    title: Optional[str] = None
    image_url: Optional[str] = None
    grammar_explanation: Optional[str] = None


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
    print(f"[UPLOAD] saving -> {abs_path} (name={file.filename}, ct={getattr(file, 'content_type', '')})")
    async with aiofiles.open(abs_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            await f.write(chunk)
    url = f"/files/{rel_path.as_posix()}"
    print(f"[UPLOAD] saved url: {url}")
    return url

def _paragraph_to_dict(p: Paragraph) -> Dict[str, Any]:
    return {
        "id": p.id,
        "paragraph_number": p.paragraph_number,
        "original_text": p.original_text,
        "translation_text": p.translation_text,
        "annotations": getattr(p, "annotations", None),
        "has_vector": getattr(p, "semantic_vector", None) is not None,
    }

def _chapter_to_dict(ch: Chapter) -> Dict[str, Any]:
    return {
        "id": ch.id,
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "image_url": ch.image_url,
        "grammar_explanation": ch.grammar_explanation,
    }

def _chapters_for_story(db: Session, story_id: int) -> List[Chapter]:
    return (
        db.query(Chapter)
        .filter(Chapter.story_id == story_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )

def _story_to_dict(db: Session, s: Story, include_chapters: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": s.id,
        "title": s.title,
        "cover_image_url": s.cover_image_url,
        "summary": s.summary,
        "translated_summary": s.translated_summary,
        "created_at": getattr(s, "created_at", None),
        "chapters": [],
    }
    if include_chapters:
        chapters = getattr(s, "chapters", None) or _chapters_for_story(db, s.id)
        data["chapters"] = [_chapter_to_dict(ch) for ch in chapters]
    return data

def _chapter_number_conflict(db: Session, story_id: int, number: int, exclude_id: Optional[int] = None) -> bool:
    q = db.query(Chapter.id).filter(Chapter.story_id == story_id, Chapter.chapter_number == int(number))
    if exclude_id:
        q = q.filter(Chapter.id != exclude_id)
    return db.query(q.exists()).scalar()

# ==========================
# 缓存失效工具（写操作后调用）
# ==========================
async def _invalidate_all_story_cache():
    # 简单粗暴：写后全清相关空间。吞掉异常避免影响主流程。
    try:
        await FastAPICache.clear(namespace=NS_STORIES)
        await FastAPICache.clear(namespace=NS_STORY_DETAIL)
        await FastAPICache.clear(namespace=NS_CHAPTERS)
        await FastAPICache.clear(namespace=NS_PARAGRAPHS)
    except Exception as e:
        print("[CACHE] clear failed:", e)

# ==========================
#      Story JSON CRUD
# ==========================
@router.get("/", response_model=List[StoryOut])
@cache(expire=60, namespace=NS_STORIES)
def list_stories(db: Session = Depends(get_db)):
    stories = db.query(Story).order_by(Story.id.desc()).all()
    return [_story_to_dict(db, s, include_chapters=True) for s in stories]

@router.post("/", response_model=StoryOut)
async def create_story(payload: StoryIn, db: Session = Depends(get_db)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "title is required")
    cover_url = _normalize_files_url(payload.cover_image_url)
    s = Story(
        title=title,
        cover_image_url=cover_url,
        summary=payload.summary,
        translated_summary=payload.translated_summary,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    await _invalidate_all_story_cache()
    return _story_to_dict(db, s, include_chapters=True)

@router.get("/{story_id}", response_model=StoryOut)
@cache(expire=60, namespace=NS_STORY_DETAIL)
def get_story(story_id: int, db: Session = Depends(get_db)):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")
    return _story_to_dict(db, s, include_chapters=True)

@router.put("/{story_id}", response_model=StoryOut)
async def update_story(story_id: int, payload: StoryUpdate, db: Session = Depends(get_db)):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")

    if payload.title is not None:
        s.title = payload.title.strip() or s.title
    if payload.cover_image_url is not None:
        s.cover_image_url = _normalize_files_url(payload.cover_image_url) if payload.cover_image_url else None
    if payload.summary is not None:
        s.summary = payload.summary
    if payload.translated_summary is not None:
        s.translated_summary = payload.translated_summary

    db.commit()
    db.refresh(s)
    await _invalidate_all_story_cache()
    return _story_to_dict(db, s, include_chapters=True)

@router.delete("/{story_id}", status_code=204)
async def delete_story(story_id: int, db: Session = Depends(get_db)):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")

    urls: List[Optional[str]] = []
    if getattr(s, "cover_image_url", None):
        urls.append(s.cover_image_url)
    chapters = _chapters_for_story(db, story_id)
    for ch in chapters:
        if getattr(ch, "image_url", None):
            urls.append(ch.image_url)

    db.query(Chapter).filter(Chapter.story_id == story_id).delete()
    db.delete(s)
    db.commit()

    removed = _delete_files_by_urls(urls)
    if removed:
        print("Deleted files:", removed)

    await _invalidate_all_story_cache()
    return Response(status_code=204)

# ==========================
#      Chapter JSON CRUD
# ==========================
@router.get("/{story_id}/chapters", response_model=List[ChapterOut])
@cache(expire=60, namespace=NS_CHAPTERS)
def list_chapters(story_id: int, db: Session = Depends(get_db)):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")
    chapters = _chapters_for_story(db, story_id)
    return [_chapter_to_dict(ch) for ch in chapters]

@router.post("/{story_id}/chapters", response_model=ChapterOut)
async def create_chapter(story_id: int, payload: ChapterIn, db: Session = Depends(get_db)):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")

    num = int(payload.chapter_number) if payload.chapter_number is not None else None
    if num is None or num <= 0:
        raise HTTPException(400, "chapter_number must be >= 1")

    if _chapter_number_conflict(db, story_id, num):
        raise HTTPException(status_code=409, detail=f"章节编号 {num} 已存在")

    img_url = _normalize_files_url(payload.image_url)

    ch = Chapter(
        story_id=story_id,
        chapter_number=num,
        title=payload.title or None,
        image_url=img_url,
        grammar_explanation=payload.grammar_explanation or None,
    )
    db.add(ch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"章节编号 {num} 已存在")

    db.refresh(ch)
    await _invalidate_all_story_cache()
    return _chapter_to_dict(ch)

@router.get("/{story_id}/chapters/{chapter_id}", response_model=ChapterOut)
@cache(expire=60, namespace=NS_CHAPTERS)
def get_chapter(story_id: int, chapter_id: int, db: Session = Depends(get_db)):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    return _chapter_to_dict(ch)

@router.put("/{story_id}/chapters/{chapter_id}", response_model=ChapterOut)
async def update_chapter(
    story_id: int, chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db)
):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")

    if payload.chapter_number is not None:
        new_num = int(payload.chapter_number)
        if new_num <= 0:
            raise HTTPException(400, "chapter_number must be >= 1")
        if new_num != ch.chapter_number and _chapter_number_conflict(db, story_id, new_num, exclude_id=ch.id):
            raise HTTPException(status_code=409, detail=f"章节编号 {new_num} 已存在")
        ch.chapter_number = new_num

    if payload.title is not None:
        ch.title = payload.title
    if payload.image_url is not None:
        ch.image_url = _normalize_files_url(payload.image_url) if payload.image_url else None
    if payload.grammar_explanation is not None:
        ch.grammar_explanation = payload.grammar_explanation

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="章节编号冲突")

    db.refresh(ch)
    await _invalidate_all_story_cache()
    return _chapter_to_dict(ch)

@router.delete("/{story_id}/chapters/{chapter_id}", status_code=204)
async def delete_chapter(story_id: int, chapter_id: int, db: Session = Depends(get_db)):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")

    url = ch.image_url
    db.delete(ch)
    db.commit()
    _delete_files_by_urls([url])

    await _invalidate_all_story_cache()
    return Response(status_code=204)

# ==========================
#   Story / Chapter with-image
# ==========================
@router.post("/with-image", response_model=StoryOut)
async def create_story_with_image(
    title: str = Form(...),
    summary: Optional[str] = Form(None),
    translated_summary: Optional[str] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    print(f"[STORY] create with-image, file?: {bool(cover_image)}")
    cover_url = await _save_upload_async(cover_image) if cover_image else None
    s = Story(
        title=title.strip(),
        cover_image_url=cover_url,
        summary=summary,
        translated_summary=translated_summary,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    await _invalidate_all_story_cache()
    return _story_to_dict(db, s, include_chapters=True)

@router.put("/{story_id}/with-image", response_model=StoryOut)
async def update_story_with_image(
    story_id: int,
    title: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    translated_summary: Optional[str] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    keep_existing_image: Optional[str] = Form("true"),
    db: Session = Depends(get_db),
):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")

    if title is not None:
        s.title = title.strip() or s.title
    if summary is not None:
        s.summary = summary
    if translated_summary is not None:
        s.translated_summary = translated_summary

    print(f"[STORY] update with-image story={story_id}, file?: {bool(cover_image)}")
    if cover_image is not None:
        s.cover_image_url = await _save_upload_async(cover_image)
    else:
        keep = _as_bool(keep_existing_image, True)
        if not keep:
            s.cover_image_url = None

    db.commit()
    db.refresh(s)
    await _invalidate_all_story_cache()
    return _story_to_dict(db, s, include_chapters=True)

@router.post("/{story_id}/chapters/with-image", response_model=ChapterOut)
async def create_chapter_with_image(
    story_id: int,
    chapter_number: int = Form(...),
    title: Optional[str] = Form(None),
    grammar_explanation: Optional[str] = Form(None),
    chapter_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    s = db.query(Story).filter(Story.id == story_id).first()
    if not s:
        raise HTTPException(404, "Story not found")

    if int(chapter_number) <= 0:
        raise HTTPException(400, "chapter_number must be >= 1")

    if _chapter_number_conflict(db, story_id, int(chapter_number)):
        raise HTTPException(status_code=409, detail=f"章节编号 {chapter_number} 已存在")

    print(f"[CHAPTER] create with-image story={story_id}, num={chapter_number}, file?: {bool(chapter_image)}")
    img_url = await _save_upload_async(chapter_image) if chapter_image else None

    ch = Chapter(
        story_id=story_id,
        chapter_number=int(chapter_number),
        title=title or None,
        image_url=img_url,
        grammar_explanation=grammar_explanation or None,
    )
    db.add(ch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"章节编号 {chapter_number} 已存在")

    db.refresh(ch)
    await _invalidate_all_story_cache()
    return _chapter_to_dict(ch)

@router.put("/{story_id}/chapters/{chapter_id}/with-image", response_model=ChapterOut)
async def update_chapter_with_image(
    story_id: int,
    chapter_id: int,
    chapter_number: Optional[int] = Form(None),
    title: Optional[str] = Form(None),
    grammar_explanation: Optional[str] = Form(None),
    chapter_image: Optional[UploadFile] = File(None),
    keep_existing_image: Optional[str] = Form("true"),
    db: Session = Depends(get_db),
):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")

    if chapter_number is not None:
        if int(chapter_number) <= 0:
            raise HTTPException(400, "chapter_number must be >= 1")
        if int(chapter_number) != ch.chapter_number and _chapter_number_conflict(
            db, story_id, int(chapter_number), exclude_id=ch.id
        ):
            raise HTTPException(status_code=409, detail=f"章节编号 {chapter_number} 已存在")
        ch.chapter_number = int(chapter_number)

    if title is not None:
        ch.title = title

    print(f"[CHAPTER] update with-image story={story_id}, chapter={chapter_id}, file?: {bool(chapter_image)}")
    if chapter_image is not None:
        ch.image_url = await _save_upload_async(chapter_image)
    else:
        keep = _as_bool(keep_existing_image, True)
        if not keep:
            ch.image_url = None

    if grammar_explanation is not None:
        ch.grammar_explanation = grammar_explanation

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="章节编号冲突")

    db.refresh(ch)
    await _invalidate_all_story_cache()
    return _chapter_to_dict(ch)

# ==========================
#         Paragraphs
# ==========================
@router.get("/{story_id}/chapters/{chapter_id}/paragraphs", response_model=List[ParagraphOut])
@cache(expire=60, namespace=NS_PARAGRAPHS)
def list_paragraphs(story_id: int, chapter_id: int, db: Session = Depends(get_db)):
    ch = db.query(Chapter).filter_by(id=chapter_id, story_id=story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    rows = (
        db.query(Paragraph)
        .filter_by(chapter_id=chapter_id)
        .order_by(Paragraph.paragraph_number.asc())
        .all()
    )
    return [_paragraph_to_dict(p) for p in rows]

@router.post("/{story_id}/chapters/{chapter_id}/paragraphs", response_model=ParagraphOut)
async def create_paragraph(
    story_id: int,
    chapter_id: int,
    body: ParagraphIn,
    db: Session = Depends(get_db),
):
    ch = db.query(Chapter).filter_by(id=chapter_id, story_id=story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")

    # 生成语义向量 + 注释
    try:
        ann_val = annotate_html(body.original_text) if body.original_text else None
    except Exception as e:
        print(f"[ANNOTATE] failed: {e}")
        ann_val = None

    p = Paragraph(
        chapter_id=chapter_id,
        paragraph_number=int(body.paragraph_number),
        original_text=body.original_text,
        translation_text=body.translation_text or "",
        semantic_vector=await _async_get_embedding(body.original_text),
        annotations=_to_annotations_json(ann_val),
    )
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_paragraph_number",
                "message": f"段落编号 {body.paragraph_number} 已存在",
                "chapter_id": chapter_id,
                "paragraph_number": int(body.paragraph_number),
            },
        )
    db.refresh(p)
    await _invalidate_all_story_cache()
    return _paragraph_to_dict(p)

@router.put("/{story_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}", response_model=ParagraphOut)
async def update_paragraph(
    story_id: int,
    chapter_id: int,
    paragraph_id: int,
    body: ParagraphIn,
    db: Session = Depends(get_db),
):
    p = (
        db.query(Paragraph)
        .join(Chapter, Paragraph.chapter_id == Chapter.id)
        .filter(
            Paragraph.id == paragraph_id,
            Paragraph.chapter_id == chapter_id,
            Chapter.story_id == story_id,
        )
        .first()
    )
    if not p:
        raise HTTPException(404, "Paragraph not found")

    original_changed = (body.original_text != p.original_text)

    p.paragraph_number = int(body.paragraph_number)
    p.original_text = body.original_text
    p.translation_text = body.translation_text or ""  # NOT NULL 兜底

    if original_changed:
        p.semantic_vector = await _async_get_embedding(body.original_text)
        try:
            ann_val = annotate_html(body.original_text) if body.original_text else None
        except Exception as e:
            print(f"[ANNOTATE] failed: {e}")
            ann_val = None
        p.annotations = _to_annotations_json(ann_val)

    db.commit()
    db.refresh(p)
    await _invalidate_all_story_cache()
    return _paragraph_to_dict(p)

@router.delete("/{story_id}/chapters/{chapter_id}/paragraphs/{paragraph_id}", status_code=204)
async def delete_paragraph(
    story_id: int,
    chapter_id: int,
    paragraph_id: int,
    db: Session = Depends(get_db),
):
    p = (
        db.query(Paragraph)
        .join(Chapter, Paragraph.chapter_id == Chapter.id)
        .filter(
            Paragraph.id == paragraph_id,
            Paragraph.chapter_id == chapter_id,
            Chapter.story_id == story_id,
        )
        .first()
    )
    if not p:
        raise HTTPException(404, "Paragraph not found")

    db.delete(p)
    db.commit()
    await _invalidate_all_story_cache()
    return Response(status_code=204)

@router.get("/{story_id}/chapters/{chapter_id}/paragraphs/used-numbers", response_model=List[int])
@cache(expire=60, namespace=NS_PARAGRAPHS)
def list_used_paragraph_numbers(
    story_id: int,
    chapter_id: int,
    db: Session = Depends(get_db)
):
    ch = db.query(Chapter).filter_by(id=chapter_id, story_id=story_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    rows = (
        db.query(Paragraph.paragraph_number)
        .filter(Paragraph.chapter_id == chapter_id)
        .order_by(Paragraph.paragraph_number.asc())
        .all()
    )
    return [n for (n,) in rows]
