# fastapi_backend/routes/siele_routes.py

# fastapi_backend/routes/siele_routes.py

from typing import List, Optional,Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi_cache.decorator import cache

from audio_backend.app.core.database import SessionLocal
from audio_backend.app.models.siele_reading_models import SieleReadingPassage

router = APIRouter(tags=["siele"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PassageSummary(BaseModel):
    id: int
    titulo: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


@router.get(
    "/passages/{tarea}",
    response_model=List[PassageSummary],
    summary="列出指定 Tarea 的文章简略列表"
)
@cache(expire=60)
async def list_passage_summaries(tarea: int, db: Session = Depends(get_db)):
    """
    返回每篇文章的 id、titulo 和创建时间，用于列表展示。
    """
    passages = (
        db.query(
            SieleReadingPassage.id,
            SieleReadingPassage.title,
            SieleReadingPassage.created_at
        )
        .filter_by(tarea_number=tarea)
        .order_by(SieleReadingPassage.id)
        .all()
    )
    if not passages:
        raise HTTPException(404, "No passages found")

    # raw 查询返回的是 tuple(id, title, created_at)
    return [
        PassageSummary(
            id=p[0],
            titulo=p[1],
            created_at=p[2],
        )
        for p in passages
    ]


class PassageDetailOut(BaseModel):
    id: int
    tarea_number: int
    title: Optional[str]
    content_doc: Any

    class Config:
        orm_mode = True


@router.get("/passages/{tarea}/{passage_id}", response_model=PassageDetailOut)
@cache(expire=60)
async def get_passage_detail(
    tarea: int,
    passage_id: int,
    db: Session = Depends(get_db)
):
    """
    获取某个 Tarea 下、指定 ID 的文章详情。
    """
    passage = (
        db.query(SieleReadingPassage)
          .filter_by(tarea_number=tarea, id=passage_id)
          .first()
    )
    if not passage:
        raise HTTPException(404, "Passage not found")
    return passage

