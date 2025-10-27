import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from audio_backend.app.models.audio import Audio
from pydantic import BaseModel
from typing import List, Optional

# 上传文件存储目录
UPLOAD_DIR = Path("uploaded_audios")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def save_uploaded_file(file, filename: str) -> str:
    """ 存储上传的音频文件并返回文件路径 """
    file_path = UPLOAD_DIR / filename  # 生成存储路径
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)  # 复制文件内容
    return str(file_path)  # 返回文件路径

def store_audio_in_db(
    db: Session,
    user_id: int,
    filename: str,
    file_url: str,
    file_size: int,
    duration: str,
    selected_model: str,
    detected_language: str,
    transcript: str,
    translated_text: str,
    uploaded_at_dt,
    word_timestamps=None
) -> Audio:
    """ 存储音频信息到数据库 """
    audio_entry = Audio(
        user_id=user_id,
        filename=filename,
        file_url=file_url,
        file_size=file_size,
        audio_format=filename.split(".")[-1],
        audio_type="UPLOADED",
        source_language=detected_language if detected_language else "Unknown",
        original_transcript=transcript if transcript else "",
        translated_transcript=translated_text if translated_text else "",
        translation_model=selected_model,
        translation_quality="BASIC",
        duration=duration, 
        uploaded_at=uploaded_at_dt,
        word_timestamps=word_timestamps
    )

    db.add(audio_entry)
    db.commit()
    db.refresh(audio_entry)

    return audio_entry


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float

class AudioDetailResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    file_url: str
    file_size: int
    audio_format: str
    audio_type: str
    source_language: str
    original_transcript: str
    translated_transcript: str
    summary: str
    uploaded_at: str  # 格式化时间
    duration: str
    location: dict | None
    word_timestamps: Optional[List[WordTimestamp]] = None 

def get_audio_by_id(audio_id: int, db: Session):
    """ 根据 audio_id 获取语音详情 """
    return db.query(Audio).filter(Audio.id == audio_id).first()

def get_audio_detail_response(audio_id: int, db: Session) -> AudioDetailResponse:
    """ 获取 audio 详情并转换为 API 可返回的格式 """
    audio = get_audio_by_id(audio_id, db)

    if not audio:
        return None  # 让 API 层处理 404 逻辑

    return AudioDetailResponse(
        id=audio.id,
        user_id=audio.user_id,
        filename=audio.filename,
        file_url=f"http://127.0.0.1:8001/audio/play/{audio.id}",  # 让前端请求这个 URL 播放音频
        file_size=audio.file_size,
        audio_format=audio.audio_format,
        audio_type=audio.audio_type,
        source_language=audio.source_language,
        original_transcript=audio.original_transcript or "暂无转录内容",
        translated_transcript=audio.translated_transcript or "暂无翻译内容",
        summary=audio.summary or "暂无摘要",
        uploaded_at=audio.uploaded_at.isoformat(),
        duration=audio.duration or "未知时长",
        location=audio.location if audio.location else None,
        word_timestamps=audio.word_timestamps  # ✅ 直接返回数据库中存储的 JSONB 数据
    )