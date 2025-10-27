from pydantic import BaseModel
from datetime import datetime

class AudioCreateResponse(BaseModel):
    id: int
    filename: str
    original_transcript: str
    translated_transcript: str
    translation_model: str
    uploaded_at: datetime
