# fastapi_backend/routes/siele_admin_routes.py
"""
SIELE 阅读材料管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 正确的导入路径
from audio_backend.app.core.database import get_db
from audio_backend.app.core.mongodb import get_mongo_db
from audio_backend.app.models.siele_reading_models import SieleReadingPassage
from fastapi_backend.Recommendation_Algorithm.embedding_service import get_embedding

# 动态导入（如果文件存在）
try:
    sys.path.insert(0, str(project_root))
    from services.markup_parser import SieleMarkupParser
    from services.nlp_service import get_nlp_service
except ImportError as e:
    print(f"⚠️  Warning: Failed to import modules: {e}")
    class SieleMarkupParser:
        def parse(self, text):
            raise NotImplementedError("markup_parser.py not found")
    def get_nlp_service():
        raise NotImplementedError("nlp_service.py not found")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reading/admin", tags=["Reading Admin"])


# ==================== Pydantic Models ====================
class MarkupTextInput(BaseModel):
    """标记文本输入"""
    markup_text: str


class PassageResponse(BaseModel):
    """文章创建响应"""
    passage_id: int
    mongo_questions_id: Optional[str]
    message: str
    tarea_number: int
    title: Optional[str]
    paragraph_count: int
    question_count: int
    word_count: int


# ==================== API Routes ====================
@router.post("/preview")
async def preview_markup(data: MarkupTextInput):
    """
    预览标记文本的解析结果（不保存到数据库）
    
    Args:
        data: 包含标记文本的输入
        
    Returns:
        解析后的结构化数据（供前端预览）
    """
    try:
        # 解析标记文本
        parser = SieleMarkupParser()
        result = parser.parse(data.markup_text)
        
        # 添加 NLP 分析（如果可用）
        nlp_service = get_nlp_service()
        if result["plain_text_es"]:
            nlp_result = nlp_service.analyze_text(result["plain_text_es"])
            result["word_count"] = nlp_result["word_count"]
            result["sentence_count"] = nlp_result["sentence_count"]
            result["difficulty_estimate"] = nlp_service.estimate_difficulty(
                nlp_result["pos_distribution"],
                nlp_result["word_count"]
            )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Preview failed: {e}", exc_info=True)
        raise HTTPException(500, f"解析失败: {str(e)}")


@router.post("/passages", response_model=PassageResponse)
async def create_passage_from_markup(
    data: MarkupTextInput,
    db_pg: Session = Depends(get_db),
    db_mongo: AsyncIOMotorDatabase = Depends(get_mongo_db)
):
    """
    从标记文本创建阅读材料
    
    工作流程:
    1. 解析标记文本
    2. NLP 分析（lemmas, POS）
    3. 生成语义向量
    4. 保存到 PostgreSQL
    5. 保存题目到 MongoDB
    """
    try:
        # 1. 解析标记
        parser = SieleMarkupParser()
        parsed_data = parser.parse(data.markup_text)
        
        if not parsed_data["plain_text_es"]:
            raise HTTPException(400, "未找到西班牙语文本")
        
        # 2. NLP 分析
        nlp_service = get_nlp_service()
        nlp_result = nlp_service.analyze_text(parsed_data["plain_text_es"])
        
        # 3. 生成语义向量
        embedding = await asyncio.to_thread(
            get_embedding,
            parsed_data["plain_text_es"]
        )
        
        # 4. 创建 PostgreSQL 记录
        passage = SieleReadingPassage(
            tarea_number=parsed_data["tarea_number"],
            title=parsed_data["title"],
            raw_markup_text=data.markup_text,  # 保存原始标记文本
            plain_text_es=parsed_data["plain_text_es"],
            paragraphs=parsed_data["paragraphs"],
            lemmas=parsed_data["lemmas"],
            pos_distribution=parsed_data["pos_distribution"],
            word_count=nlp_result["word_count"],
            sentence_count=nlp_result["sentence_count"],
            difficulty_level=nlp_service.estimate_difficulty(
                nlp_result["pos_distribution"],
                nlp_result["word_count"]
            ),
            embedding=embedding
        )
        
        db_pg.add(passage)
        db_pg.flush()
        
        # 5. 如果有题目，保存到 MongoDB
        mongo_id = None
        if parsed_data["questions"]:
            questions_collection = db_mongo["siele_reading_questions"]
            mongo_doc = {
                "passage_id": passage.id,
                "tarea_number": parsed_data["tarea_number"],
                "tarea_type": "single_choice",
                "questions": parsed_data["questions"],
                "created_at": datetime.utcnow()
            }
            result = await questions_collection.insert_one(mongo_doc)
            mongo_id = str(result.inserted_id)
            
            # 更新 PostgreSQL 中的 mongo_questions_id
            passage.mongo_questions_id = mongo_id
        
        db_pg.commit()
        db_pg.refresh(passage)
        
        logger.info(f"✅ Created passage {passage.id} with {len(parsed_data['questions'])} questions")
        
        return PassageResponse(
            passage_id=passage.id,
            mongo_questions_id=mongo_id,
            message="创建成功！",
            tarea_number=parsed_data["tarea_number"],
            title=parsed_data["title"],
            paragraph_count=len(parsed_data["paragraphs"]),
            question_count=len(parsed_data["questions"]),
            word_count=nlp_result["word_count"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create passage: {e}", exc_info=True)
        db_pg.rollback()
        raise HTTPException(500, f"创建失败: {str(e)}")


@router.put("/passages/{passage_id}")
async def update_passage_from_markup(
    passage_id: int,
    data: MarkupTextInput,
    db_pg: Session = Depends(get_db),
    db_mongo: AsyncIOMotorDatabase = Depends(get_mongo_db)
):
    """更新阅读材料（重新解析标记）"""
    try:
        passage = db_pg.query(SieleReadingPassage).filter_by(id=passage_id).first()
        if not passage:
            raise HTTPException(404, "文章不存在")
        
        parser = SieleMarkupParser()
        parsed_data = parser.parse(data.markup_text)
        
        nlp_service = get_nlp_service()
        nlp_result = nlp_service.analyze_text(parsed_data["plain_text_es"])
        
        embedding = await asyncio.to_thread(
            get_embedding,
            parsed_data["plain_text_es"]
        )
        
        # 更新字段
        passage.title = parsed_data["title"]
        passage.raw_markup_text = data.markup_text
        passage.plain_text_es = parsed_data["plain_text_es"]
        passage.paragraphs = parsed_data["paragraphs"]
        passage.lemmas = parsed_data["lemmas"]
        passage.pos_distribution = parsed_data["pos_distribution"]
        passage.embedding = embedding
        passage.word_count = nlp_result["word_count"]
        passage.sentence_count = nlp_result["sentence_count"]
        passage.difficulty_level = nlp_service.estimate_difficulty(
            nlp_result["pos_distribution"],
            nlp_result["word_count"]
        )
        
        # 更新题目
        if parsed_data["questions"]:
            questions_collection = db_mongo["siele_reading_questions"]
            existing_doc = await questions_collection.find_one({"passage_id": passage_id})
            
            if existing_doc:
                await questions_collection.update_one(
                    {"passage_id": passage_id},
                    {"$set": {
                        "questions": parsed_data["questions"],
                        "updated_at": datetime.utcnow()
                    }}
                )
            else:
                mongo_doc = {
                    "passage_id": passage_id,
                    "tarea_number": parsed_data["tarea_number"],
                    "tarea_type": "single_choice",
                    "questions": parsed_data["questions"],
                    "created_at": datetime.utcnow()
                }
                result = await questions_collection.insert_one(mongo_doc)
                passage.mongo_questions_id = str(result.inserted_id)
        
        db_pg.commit()
        logger.info(f"✅ Updated passage {passage_id}")
        
        return {"message": "更新成功！", "passage_id": passage_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update passage: {e}", exc_info=True)
        db_pg.rollback()
        raise HTTPException(500, f"更新失败: {str(e)}")


@router.get("/passages/{passage_id}/raw")
async def get_passage_raw_markup(
    passage_id: int,
    db_pg: Session = Depends(get_db)
):
    """获取文章的原始标记文本（供管理员编辑）"""
    passage = db_pg.query(SieleReadingPassage).filter_by(id=passage_id).first()
    if not passage:
        raise HTTPException(404, "文章不存在")
    
    return {
        "passage_id": passage_id,
        "raw_markup_text": passage.raw_markup_text or "",
        "title": passage.title,
        "tarea_number": passage.tarea_number
    }


@router.delete("/passages/{passage_id}")
async def delete_passage(
    passage_id: int,
    db_pg: Session = Depends(get_db),
    db_mongo: AsyncIOMotorDatabase = Depends(get_mongo_db)
):
    """删除阅读材料（同时删除 PostgreSQL 和 MongoDB 数据）"""
    try:
        passage = db_pg.query(SieleReadingPassage).filter_by(id=passage_id).first()
        if not passage:
            raise HTTPException(404, "文章不存在")
        
        # 删除 MongoDB 中的题目
        questions_collection = db_mongo["siele_reading_questions"]
        await questions_collection.delete_many({"passage_id": passage_id})
        
        # 删除 PostgreSQL 记录
        db_pg.delete(passage)
        db_pg.commit()
        
        logger.info(f"✅ Deleted passage {passage_id}")
        
        return {"message": "删除成功！", "passage_id": passage_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete passage: {e}", exc_info=True)
        db_pg.rollback()
        raise HTTPException(500, f"删除失败: {str(e)}")