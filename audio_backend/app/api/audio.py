from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from audio_backend.app.services.audio_service import process_audio
from audio_backend.app.utils.file_handler import save_uploaded_file, store_audio_in_db  # ✅ 引入文件存储 & 数据库存储
from audio_backend.app.core.database import get_db  
from audio_backend.app.models.audio import Audio  
from dateutil import parser
from pydantic import BaseModel
from typing import List
from audio_backend.app.utils.file_handler import get_audio_detail_response, AudioDetailResponse 
import os
from fastapi.responses import FileResponse
from fastapi import status

from audio_backend.app.core.database import get_db
from audio_backend.app.utils.file_handler import (
    save_uploaded_file,
    store_audio_in_db,
    get_audio_detail_response,
    get_audio_by_id
)



router = APIRouter()

# ✅ 定义 Pydantic 模型（确保和前端 `AudioModel` 对应）
class AudioResponse(BaseModel):
    id: int
    filename: str
    duration: str
    uploadedAt: str
    sourceLanguage: str
    audioType: str
    originalTranscript: str

# ✅ 获取用户语音列表（支持分页）
@router.get("/user_audios/{user_id}", response_model=List[AudioResponse])
def get_user_audios(user_id: int, page: int = 1, page_size: int = 6, db: Session = Depends(get_db)):
    """ 获取用户上传的语音列表（支持分页） """
    
    # 计算偏移量
    offset = (page - 1) * page_size

    # 查询数据库，按时间降序排序
    audios = (
        db.query(Audio)
        .filter(Audio.user_id == user_id)
        .order_by(Audio.uploaded_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    
    print(f"📡 查询分页数据: user_id={user_id}, page={page}, page_size={page_size}, offset={offset}, 返回 {len(audios)} 条数据")

    if not audios:
        print(f"❌ 没有找到 user_id={user_id} 的语音数据")
        return []  # ✅ 返回空数组，而不是 404

    # 组装返回数据
    return [
        AudioResponse(
            id=audio.id,
            filename=audio.filename,
            duration=audio.duration,
            uploadedAt=audio.uploaded_at.isoformat(),
            sourceLanguage=audio.source_language,
            audioType=audio.audio_type,
            originalTranscript=audio.original_transcript,
        )
        for audio in audios
    ]


@router.delete("/audio/{audio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audio(audio_id: int, db: Session = Depends(get_db)):
    """ 删除指定 audio_id 的语音记录和音频文件 """

    audio = get_audio_by_id(audio_id, db)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    file_path = audio.file_url
    filename = audio.filename

    # 尝试删除文件（忽略文件不存在错误）
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"✅ 删除音频文件: {file_path}")
        else:
            print(f"⚠️ 音频文件不存在: {file_path}")
    except Exception as e:
        print(f"❌ 删除音频文件失败: {e}")

    # 删除数据库记录
    db.delete(audio)
    db.commit()
    print(f"🗑️ 数据库记录已删除: {filename}")
    return


@router.post("/upload/")
async def test_audio(
    file: UploadFile = File(...),
    user_id: int = Form(...),
    selected_model: str = Form(...),
    duration: str = Form(...),
    uploaded_at: str = Form(...),
    file_size: int = Form(...),
    db: Session = Depends(get_db)
):
    """ 处理音频上传 API """    
    try:
        uploaded_at_dt = parser.isoparse(uploaded_at)  # 解析时间
    except ValueError:
        return {"error": "Invalid datetime format. Expected YYYY-MM-DDTHH:MM:SS±HH:MM"}

    # ✅ 存储文件
    file_path = save_uploaded_file(file, file.filename)

    # ✅ 处理音频
    transcript, translated_text, detected_language, word_timestamps, model_message = "", "", "", None, ""
    #process_audio(file_path, selected_model)
    # ✅ 存入数据库
    audio_entry = store_audio_in_db(
        db=db,
        user_id=user_id,
        filename=file.filename,
        file_url=file_path,
        file_size=file_size,
        duration=duration,
        selected_model=selected_model,
        detected_language=detected_language,
        transcript=transcript,
        translated_text=translated_text,
        uploaded_at_dt=uploaded_at_dt,
        word_timestamps=word_timestamps 
    )

    return {
        "id": audio_entry.id,
        "filename": audio_entry.filename,
        "source_language": detected_language if detected_language else "Unknown",
        "original_transcript": transcript if transcript else "Not processed",
        "translated_transcript": translated_text if translated_text else "Not processed",
        "message": model_message
    }



@router.get("/audio/{audio_id}", response_model=AudioDetailResponse)
def get_audio_detail(audio_id: int, db: Session = Depends(get_db)):
    """ 获取特定 audio_id 的语音详情 """

    audio_detail = get_audio_detail_response(audio_id, db)  # ✅ 调用 file_handler.py 里的方法

    if not audio_detail:
        raise HTTPException(status_code=404, detail="Audio not found")

    return audio_detail

@router.get("/audio/play/{audio_id}")
def stream_audio(audio_id: int, db: Session = Depends(get_db)):
    """ 提供音频文件流，让前端可以播放 """
    audio = get_audio_by_id(audio_id, db)

    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    file_path = audio.file_url  # 直接从数据库获取存储的路径
    
    print("Attempting to stream audio from file path:", file_path)
    print("Current working directory:", os.getcwd())


    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(file_path, media_type="audio/mpeg", filename=audio.filename)


@router.put("/audio/{audio_id}/summary")
def update_audio_summary(audio_id: int, summary: str, db: Session = Depends(get_db)):
    """ 更新特定 audio_id 的 summary（摘要） """
    audio = get_audio_by_id(audio_id, db)

    if not audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    audio.summary = summary
    db.commit()

    return {"message": "Summary updated successfully"}