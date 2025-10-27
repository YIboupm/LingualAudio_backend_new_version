from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from audio_backend.app.core.database import Base


# ==================== 主表：写作任务 ====================
class WritingTask(Base):
    """
    通用写作任务表（DELE）
    支持图片、听力素材等多模态题型
    """
    __tablename__ = "dele_writing_tasks"

    # 基本信息
    id = Column(Integer, primary_key=True)
    exam_type = Column(String(20), nullable=False, default="DELE")   # 固定为 DELE
    level = Column(String(20), nullable=True)        # A2 / B1 / B2 / C1
    title = Column(String(255), nullable=False)
    task_number = Column(Integer, nullable=True)
    section = Column(String(50), nullable=True)      # Tarea 1 / Parte 2

    # 题干与说明
    description_html = Column(Text, nullable=True)   # 题干（HTML）
    instructions_html = Column(Text, nullable=True)  # 写作要求（HTML）

    # 素材
    listening_material_id = Column(
        String,
        ForeignKey("listening_materials.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    images = relationship("WritingImage", back_populates="task", cascade="all, delete-orphan")

    # 附加参数
    min_words = Column(Integer, default=120)
    max_words = Column(Integer, default=180)
    tips_html = Column(Text, nullable=True)
    meta_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    listening_material = relationship("ListeningMaterial", backref="related_writing_tasks")
    submissions = relationship("WritingSubmission", back_populates="task")
    references = relationship("WritingReference", back_populates="task")  # ✅ 范文
    


# ==================== 用户提交 ====================
class WritingSubmission(Base):
    __tablename__ = "dele_writing_submissions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("dele_writing_tasks.id"), nullable=False)

    content_html = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending")   # pending / graded / reviewed

    task = relationship("WritingTask", back_populates="submissions")
    scores = relationship("WritingScore", back_populates="submission")  # ✅ AI评分
    feedback_versions = relationship("WritingFeedbackVersion", back_populates="submission")  # ✅ 反馈版本


# ==================== 范文参考 ====================
class WritingReference(Base):
    __tablename__ = "dele_writing_references"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("dele_writing_tasks.id"), nullable=False)
    reference_html = Column(Text, nullable=False)
    translation_html = Column(Text, nullable=True)
    high_score_phrases = Column(JSONB, nullable=True)
    source = Column(String(100), default="official")
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("WritingTask", back_populates="references")


# ==================== 评分结果 ====================
class WritingScore(Base):
    __tablename__ = "dele_writing_scores"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("dele_writing_submissions.id"))
    model_name = Column(String(100))
    adecuacion = Column(Float)
    coherencia = Column(Float)
    correccion = Column(Float)
    riqueza = Column(Float)
    total_score = Column(Float)

    comentario_es_html = Column(Text, nullable=True)
    comentario_zh_html = Column(Text, nullable=True)
    graded_at = Column(DateTime, default=datetime.utcnow)
    reviewed_by_teacher = Column(Boolean, default=False)

    submission = relationship("WritingSubmission", back_populates="scores")


# ==================== AI反馈版本 ====================
class WritingFeedbackVersion(Base):
    __tablename__ = "dele_writing_feedback_versions"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("dele_writing_submissions.id"))
    ai_rewrite_html = Column(Text, nullable=True)
    tips_html = Column(Text, nullable=True)
    model_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    submission = relationship("WritingSubmission", back_populates="feedback_versions")


class WritingImage(Base):
    """
    多图素材表（对应 DELE 写作任务）
    """
    __tablename__ = "dele_writing_images"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("dele_writing_tasks.id", ondelete="CASCADE"))
    image_url = Column(String, nullable=False)         # 图片路径（URL 或 CDN）
    caption = Column(String, nullable=True)            # 图片说明文字
    order = Column(Integer, default=1)                 # 图片顺序（1,2,3...）

    task = relationship("WritingTask", back_populates="images")