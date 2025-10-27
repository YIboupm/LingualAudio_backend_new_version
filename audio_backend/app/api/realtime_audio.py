from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from audio_backend.app.core.database import get_db
from audio_backend.app.models.audio import Audio
from audio_backend.app.utils.file_handler import save_uploaded_file
from dateutil import parser
import json
import os

router = APIRouter()

@router.post("/realtime/upload/")
async def upload_realtime_audio(
    file: UploadFile = File(...),
    user_id: int = Form(...),
    original_transcript: str = Form(...),
    translated_transcript: str = Form(...),
    translation_model: str = Form(...),
    translation_quality: str = Form(...),
    audio_type: str = Form(...),
    source_language: str = Form(...),
    filename: str = Form(...),
    duration: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    uploaded_at: str = Form(...),
    location: str = Form(None),
    word_timestamps: str = Form(None),
    db: Session = Depends(get_db)
):
    print("收到上传请求:")
    print("user_id:", user_id)
    print("original_transcript:", original_transcript)
    print("translated_transcript:", translated_transcript)
    print("translation_model:", translation_model)
    print("translation_quality:", translation_quality)
    print("audio_type:", audio_type)
    print("filename:", filename)
    print("duration:", duration)
    print("start_time:", start_time)
    print("end_time:", end_time)
    print("uploaded_at:", uploaded_at)
    print("location:", location)
    print("word_timestamps:", word_timestamps)
    try:
        start_dt = parser.isoparse(start_time)
        end_dt = parser.isoparse(end_time)
        uploaded_dt = parser.isoparse(uploaded_at)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")

    # 保存音频文件
    file_path = save_uploaded_file(file, filename)
    file_size = os.path.getsize(file_path)

    # 解析 JSON 字段
    location_data = json.loads(location) if location else None
    word_ts_data = json.loads(word_timestamps) if word_timestamps else None

    # 存入数据库
    audio = Audio(
        user_id=user_id,
        filename=filename,
        file_url=file_path,
        file_size=file_size,
        audio_format="m4a",
        audio_type=audio_type,
        source_language=source_language,  # 或根据前端后续指定
        original_transcript=original_transcript,
        translated_transcript=translated_transcript,
        word_timestamps=word_ts_data,
        translation_model=translation_model,
        translation_quality=translation_quality,
        start_time=start_dt,
        end_time=end_dt,
        duration=duration,
        location=location_data,
        uploaded_at=uploaded_dt,
    )

    db.add(audio)
    db.commit()
    db.refresh(audio)

    return {
        "message": "Real-time audio uploaded successfully",
        "audio_id": audio.id
    }
