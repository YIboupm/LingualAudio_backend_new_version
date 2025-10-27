# audio_backend/app/models/story_models.py

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from audio_backend.app.core.database import Base


class Story(Base):
    __tablename__ = 'stories'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    cover_image_url = Column(String(512), nullable=True)  # 故事封面图
    summary = Column(Text, nullable=True)  # 故事简介
    translated_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 一个故事下包含多个章节
    chapters = relationship(
        'Chapter',
        back_populates='story',
        cascade='all, delete-orphan',
        order_by='Chapter.chapter_number'
    )


class Chapter(Base):
    __tablename__ = 'chapters'
    id = Column(Integer, primary_key=True)
    story_id = Column(
        Integer,
        ForeignKey('stories.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    image_url = Column(String(512), nullable=True)  # 章节封面图
    grammar_explanation = Column(Text, nullable=True)  # 富文本 HTML 格式语法讲解

    story = relationship('Story', back_populates='chapters')
    # 一个章节下包含多个段落
    paragraphs = relationship(
        'Paragraph',
        back_populates='chapter',
        cascade='all, delete-orphan',
        order_by='Paragraph.paragraph_number'
    )

    __table_args__ = (
        UniqueConstraint('story_id', 'chapter_number', name='uq_story_chapter'),
    )


class Paragraph(Base):
    __tablename__ = 'paragraphs'
    id = Column(Integer, primary_key=True)
    chapter_id = Column(
        Integer,
        ForeignKey('chapters.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    paragraph_number = Column(Integer, nullable=False)
    original_text = Column(Text, nullable=False)
    translation_text = Column(Text, nullable=False)
    # 自动化脚本生成的标注列表
    annotations = Column(JSONB, nullable=False, server_default='[]')
    # 语义向量（pgvector）
    semantic_vector = Column(Vector(768), nullable=True)

    chapter = relationship('Chapter', back_populates='paragraphs')
    # 用户对生词的标记
    

    __table_args__ = (
        UniqueConstraint('chapter_id', 'paragraph_number', name='uq_chapter_paragraph'),
    )