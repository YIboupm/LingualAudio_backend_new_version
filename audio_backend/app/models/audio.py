# audio-backend/app/models/audio.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from audio_backend.app.core.database import Base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func  
from audio_backend.app.models.user import User

class Audio(Base):
    __tablename__ = "audio"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  

    filename = Column(String, nullable=False)  # 文件名（所有录音都必须有）
    file_url = Column(String, nullable=False)  # 语音文件存储路径
    file_size = Column(Integer, nullable=False)  # 以字节为单位存储
    audio_format = Column(String, nullable=False)  # 音频格式（如 mp3、wav）
    
    audio_type = Column(String, nullable=False)  # 直接使用 String 存储
    source_language = Column(String, nullable=False, default="English")  # 改为 String

    original_transcript = Column(Text, nullable=True)

    word_timestamps = Column(JSONB, nullable=True) # 逐词时间戳

    translated_transcript = Column(Text, nullable=True)  
    summary = Column(Text, nullable=True)  

    translation_model = Column(String, nullable=False, default="Whisper")  # 改为 String
    translation_quality = Column(String, default="basic")  # 改为 String

    start_time = Column(TIMESTAMP(timezone=True), server_default=func.now())  
    end_time = Column(TIMESTAMP(timezone=True), nullable=True)  
    duration = Column(String, nullable=True)  

    location = Column(JSONB, nullable=True)  # 存储 JSONB 格式位置信息
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())  

    user = relationship(User, back_populates="audios") 

