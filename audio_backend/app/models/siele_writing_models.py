from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from audio_backend.app.core.database import Base


class SieleWritingTask(Base):
    __tablename__ = "siele_writing_tasks"

    id = Column(Integer, primary_key=True)
    task_number = Column(Integer, nullable=False)
    option_number = Column(Integer, nullable=True)
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    instructions = Column(Text, nullable=True)
    sample_text = Column(Text, nullable=True)
    rich_content = Column(Text, nullable=True)  # 富文本HTML字段
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("SieleWritingSubmission", back_populates="task")
    references = relationship("SieleWritingReference", back_populates="task")


class SieleWritingReference(Base):
    __tablename__ = "siele_writing_references"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("siele_writing_tasks.id"), nullable=False)

    reference_html = Column(Text, nullable=False)
    high_score_phrases = Column(JSONB, nullable=True)
    translation_html = Column(Text, nullable=True)
    source = Column(String(100), default="official")
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("SieleWritingTask", back_populates="references")


class SieleWritingSubmission(Base):
    __tablename__ = "siele_writing_submissions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    task_id = Column(Integer, ForeignKey("siele_writing_tasks.id"))
    content_html = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending")

    task = relationship("SieleWritingTask", back_populates="submissions")
    scores = relationship("SieleWritingScore", back_populates="submission")
    feedback_versions = relationship("SieleWritingFeedbackVersion", back_populates="submission")


class SieleWritingScore(Base):
    __tablename__ = "siele_writing_scores"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("siele_writing_submissions.id"))
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

    submission = relationship("SieleWritingSubmission", back_populates="scores")


class SieleWritingFeedbackVersion(Base):
    __tablename__ = "siele_writing_feedback_versions"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("siele_writing_submissions.id"))
    ai_rewrite_html = Column(Text, nullable=True)
    tips_html = Column(Text, nullable=True)
    model_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    submission = relationship("SieleWritingSubmission", back_populates="feedback_versions")