# app/models/user.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP
from sqlalchemy.orm import relationship
from audio_backend.app.core.database import Base  # 你的 Base 位置可能不同，请根据实际调整

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    full_name = Column(String)
    google_id = Column(String, unique=True)

    is_admin = Column(Boolean, default=False, nullable=False)

    is_vip = Column(Boolean, default=False)
    subscription_start = Column(TIMESTAMP)
    subscription_end = Column(TIMESTAMP)
    total_subscription_days = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    # 与 Audio 的一对多关系（注意此处用字符串 "Audio"）
    
    user_words = relationship(
        'UserWord',
        back_populates='user',
        cascade='all, delete-orphan'
    )

    audios = relationship(
        "Audio",
        order_by="Audio.id",
        back_populates="user"
    )

    word_queries = relationship(
    'UserWordQuery',
    back_populates='user',
    cascade='all, delete-orphan',
   )


