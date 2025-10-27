import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "siele_app")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploaded_audios/")
    MODEL_NAME = os.getenv("MODEL_NAME", "large")

config = Config()
