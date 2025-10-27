from sqlalchemy import Column, String, Float, Text, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
import time


from audio_backend.app.core.database import Base


class ListeningMaterial(Base):
    __tablename__ = "listening_materials"
    id = Column(String, primary_key=True)
    path = Column(String, nullable=False)
    transcript = Column(Text, nullable=True)
    meta_json = Column(JSONB, nullable=True)
    level = Column(String, nullable=True)
    accent = Column(String, nullable=True)
    mtime = Column(Float, nullable=True)
    annotations = Column(JSONB, nullable=False, server_default='[]')
    created_at = Column(Float, default=lambda: time.time())
    updated_at = Column(Float, default=lambda: time.time(), onupdate=lambda: time.time())

    embedding = relationship("ListeningEmbedding", back_populates="material", uselist=False)

    __table_args__ = (
        Index("ix_material_level", "level"),
        Index("ix_material_accent", "accent"),
    )


class ListeningEmbedding(Base):
    __tablename__ = "listening_embeddings"

    material_id = Column(
        String,
        ForeignKey("listening_materials.id", ondelete="CASCADE"),
        primary_key=True
    )
    text_emb = Column(Vector(768), nullable=True)
    updated_at = Column(Float, default=lambda: time.time())

    material = relationship("ListeningMaterial", back_populates="embedding")