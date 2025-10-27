# audio_backend/app/models/siele_reading_models.py
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from audio_backend.app.core.database import Base


class SieleReadingPassage(Base):
    """
    SIELE 阅读文章 - 支持标记语法
    """
    __tablename__ = 'siele_reading_passages'
    
    # ========== 基础信息 ==========
    id = Column(Integer, primary_key=True)
    tarea_number = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=True)
    
    # ========== 管理员输入的原始标记文本 ⭐ ==========
    raw_markup_text = Column(Text, nullable=False, doc="""
        管理员输入的原始标记文本
        包含所有标记：::zh::, ::grammar::, ::question::, etc.
        方便管理员后续编辑
    """)
    
    # ========== 解析后的结构化数据 ==========
    
    # 纯西班牙语文本（去除所有标记）
    plain_text_es = Column(Text, nullable=False, doc="""
        纯西班牙语文本（用于 spaCy 分析和向量生成）
        示例: "Hola Sara, ¿qué tal todo? Perdona, ayer no te llamé..."
    """)
    
    # spaCy 分析数据
    lemmas = Column(JSONB, nullable=True, doc="""
        每个单词的 lemma
        [
            {"index": 0, "word": "Hola", "lemma": "hola", "pos": "INTJ", "start_char": 0, "end_char": 4},
            {"index": 1, "word": "Sara", "lemma": "Sara", "pos": "PROPN", "start_char": 5, "end_char": 9},
            ...
        ]
    """)
    
    pos_distribution = Column(JSONB, nullable=True, doc='词性分布统计')
    
    # 段落数据（解析标记后生成）
    paragraphs = Column(JSONB, nullable=False, doc="""
        段落结构（自动解析 --- 分隔符和翻译/语法标记）
        [
            {
                "paragraph_id": "p1",
                "text_es": "Hola Sara, ¿qué tal todo? Perdona...",
                "text_zh": "你好，萨拉，一切都好吗？抱歉...",
                "start_char": 0,
                "end_char": 389,
                "grammar_notes": [
                    {
                        "word": "dolía",
                        "note": "过去未完成时 描述过去的状态"
                    },
                    {
                        "word": "me sentí",
                        "note": "简单过去时+反身动词 表达感觉的变化"
                    }
                ]
            },
            {
                "paragraph_id": "p2",
                "text_es": "En el centro siempre me encuentro...",
                "text_zh": "在市中心我总是遇到熟人...",
                "start_char": 390,
                "end_char": 520,
                "grammar_notes": [...]
            }
        ]
    """)
    
    # 词汇标注
    annotations = Column(JSONB, nullable=False, server_default='[]', doc='词汇标注（关联 words 表）')
    
    # 语义向量
    embedding = Column(Vector(768), nullable=True)
    
    # 元数据
    difficulty_level = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)
    sentence_count = Column(Integer, nullable=True)
    cefr_level = Column(String(5), nullable=True)
    
    # MongoDB 题目关联
    mongo_questions_id = Column(String(24), nullable=True, index=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        CheckConstraint('tarea_number BETWEEN 1 AND 5', name='check_tarea_number'),
        Index('idx_passage_tarea', 'tarea_number'),
        Index('idx_passage_embedding', embedding, postgresql_using='ivfflat'),
    )