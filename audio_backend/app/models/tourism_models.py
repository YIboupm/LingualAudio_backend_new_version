from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, ForeignKey, Boolean, 
    UniqueConstraint, DateTime, Index
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy_utils import URLType

try:
    from pgvector.sqlalchemy import Vector
except Exception:
    Vector = None

from audio_backend.app.core.database import Base


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True)
    slug = Column(String(80), nullable=False, unique=True, index=True)

    name_es = Column(String(255), nullable=False)
    name_zh = Column(String(255), nullable=False)
    intro_es = Column(Text, nullable=True)
    intro_zh = Column(Text, nullable=True)

    cover_image = Column(String(512), nullable=True)
    gallery = Column(JSONB, nullable=False, server_default='[]')

    # 词汇关联（你原有的系统）
    annotations = Column(JSONB, nullable=False, server_default='[]')
    semantic_vector = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    is_published = Column(Boolean, nullable=False, server_default='true')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    cities = relationship("City", back_populates="country", cascade="all, delete-orphan")


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("country_id", "slug", name="uq_city_country_slug"),)

    id = Column(Integer, primary_key=True)
    country_id = Column(Integer, ForeignKey("countries.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(80), nullable=False, index=True)

    name_es = Column(String(255), nullable=False)
    name_zh = Column(String(255), nullable=False)
    intro_es = Column(Text, nullable=True)
    intro_zh = Column(Text, nullable=True)

    images = Column(JSONB, nullable=False, server_default='[]')
    tags = Column(ARRAY(String), nullable=False, server_default='{}')

    annotations = Column(JSONB, nullable=False, server_default='[]')
    semantic_vector = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    is_published = Column(Boolean, nullable=False, server_default='true')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    country = relationship("Country", back_populates="cities")
    places = relationship("Place", back_populates="city", cascade="all, delete-orphan")


class Place(Base):
    """景点/文化场所主表"""
    __tablename__ = "places"
    __table_args__ = (
        UniqueConstraint("city_id", "slug", name="uq_place_city_slug"),
        Index("idx_place_rating", "rating"),
    )

    id = Column(Integer, primary_key=True)
    city_id = Column(Integer, ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(80), nullable=False, index=True)

    # 基本信息
    name_es = Column(String(255), nullable=False)
    name_zh = Column(String(255), nullable=False)

    # 封面图
    cover_image = Column(String(512), nullable=True)
    
    # 简短介绍（用于列表展示）
    summary_es = Column(Text, nullable=True)
    summary_zh = Column(Text, nullable=True)

    # 视频链接（可选）
    video_url = Column(URLType, nullable=True)
    
    # 标签
    tags = Column(ARRAY(String), nullable=False, server_default='{}')

    # 全局词汇关联（你原有的 annotations 系统）
    # 这里可以存储全文的词汇 ID 映射关系
    annotations = Column(JSONB, nullable=False, server_default='[]')
    
    semantic_vector = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    # 统计
    rating = Column(Float, nullable=True)
    is_published = Column(Boolean, nullable=False, server_default='true')

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    city = relationship("City", back_populates="places")
    place_paragraphs = relationship(
    "Place_Paragraph",
    back_populates="place",
    cascade="all, delete-orphan",
    order_by="Place_Paragraph.order"
)


class Place_Paragraph(Base):
    """段落表：支持多段落 + 独立翻译 + 语法解析"""
    __tablename__ = "place_paragraphs"
    __table_args__ = (
        Index("idx_paragraph_place_order", "place_id", "order"),
    )

    id = Column(Integer, primary_key=True)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="CASCADE"), nullable=False)
    
    # 段落顺序
    order = Column(Integer, nullable=False)
    
    # 段落内容
    text_es = Column(Text, nullable=False)
    text_zh = Column(Text, nullable=False)  # 该段落的中文翻译
    
    # 该段落配图（可选）
    images = Column(JSONB, nullable=False, server_default='[]')
    # 结构示例：
    # [
    #   {"url": "image1.jpg", "caption_es": "...", "caption_zh": "..."},
    #   {"url": "image2.jpg", "caption_es": "...", "caption_zh": "..."}
    # ]
    
    # 该段落的音频朗读（可选）
    audio_url = Column(URLType, nullable=True)
    
    # ===== 词汇关联（继承你原有的系统）=====
    # 记录该段落中哪些词需要关联到词库
    annotations = Column(JSONB, nullable=False, server_default='[]')
    # 结构示例：
    # [
    #   {
    #     "word_id": 1234,           // 词库中的单词 ID
    #     "text": "construyó",       // 原文中的词形
    #     "start": 15,               // 在 text_es 中的起始位置
    #     "end": 24                  // 结束位置
    #   }
    # ]
    
    # ===== 语法解析（新增功能）=====
    # 标注该段落的语法点、句式结构等
    grammar_notes = Column(JSONB, nullable=False, server_default='[]')
    # 结构示例：
    # [
    #   {
    #     "type": "tense",                    // 语法类型：时态/从句/虚拟式等
    #     "category": "pretérito_indefinido", // 具体分类
    #     "text": "construyó",                // 标注的文本
    #     "start": 15,                        // 位置
    #     "end": 24,
    #     "explanation_es": "Pretérito indefinido del verbo construir",
    #     "explanation_zh": "动词 construir 的简单过去时",
    #     "example": "Gaudí construyó muchas obras."  // 例句（可选）
    #   },
    #   {
    #     "type": "structure",
    #     "category": "passive_voice",
    #     "text": "fue construida",
    #     "start": 50,
    #     "end": 64,
    #     "explanation_es": "Voz pasiva con ser + participio",
    #     "explanation_zh": "ser + 过去分词的被动语态"
    #   }
    # ]
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    place = relationship("Place", back_populates="place_paragraphs")