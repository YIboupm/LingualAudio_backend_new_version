# audio-backend/app/models/word.py
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base

class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False)  # 'es', 'en' 等

    part_of_speech = Column(String, nullable=True)  # noun, verb, adj...
    meaning_en = Column(Text, nullable=True)
    meaning_zh = Column(Text, nullable=True)

    example_sentence = Column(Text, nullable=True)
    conjugations = Column(JSONB, nullable=True)  # JSON 存词形变化

    pronunciation_audio = Column(String, nullable=True)  # 发音文件名（如 Es-comer.ogg）

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
