# fastapi_backend/main.py
import os
from fastapi import FastAPI
from pathlib import Path
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

# 缓存需要的
import redis.asyncio as redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

# MongoDB
from audio_backend.app.core.mongodb import init_mongodb, close_mongodb

# 路由
from fastapi_backend.routes.auth_routes import router as auth_router
from fastapi_backend.routes.siele_routes import router as siele_router
from fastapi_backend.routes.siele_admin_routes import router as siele_admin_router
from fastapi_backend.routes.story_routes import router as story_router
from fastapi_backend.routes.tourism_admin_routes import router as tourism_admin_routes 
from fastapi_backend.routes.place_routes import router as place_router


def get_app():
    load_dotenv()

    DATABASE_URL = os.getenv("DATABASE_URL")
    SECRET_KEY = os.getenv("SECRET_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # MongoDB 配置
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "siele_app")

    if not DATABASE_URL or not SECRET_KEY:
        raise ValueError("Missing essential environment variables. Check your .env file.")

    app = FastAPI(title="LingualAudio API")

    # --- 中间件 ---
    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        session_cookie="session",
        max_age=86400,
    )

    # --- 注册路由 ---
    app.include_router(auth_router, prefix="/auth")
    app.include_router(siele_router, prefix="/siele-reading", tags=["siele"])
    app.include_router(siele_admin_router,  tags=["siele-admin"])
    app.include_router(story_router, tags=["stories"])
    app.include_router(tourism_admin_routes, tags=["tourism-admin"])
    app.include_router(place_router, tags=["places"])

    # --- 静态文件 ---
    BASE_DIR = Path(__file__).resolve().parent
    env_upload = os.getenv("UPLOAD_DIR")
    if env_upload:
        up = Path(env_upload)
        uploads_dir = (up if up.is_absolute() else (BASE_DIR / up)).resolve()
    else:
        uploads_dir = (BASE_DIR / "uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    print("📁 STATIC /files =>", uploads_dir)
    app.mount("/files", StaticFiles(directory=str(uploads_dir)), name="uploaded_files")

    # --- 健康检查 ---
    @app.get("/")
    def read_root():
        return {
            "message": "LingualAudio API is running!",
            "endpoints": {
                "docs": "/docs",
                "siele_admin": "/siele-reading-admin",
                "siele_reading": "/siele-reading"
            }
        }

    # --- 启动事件：初始化 Redis 和 MongoDB ---
    @app.on_event("startup")
    async def startup_event():
        # 初始化 Redis 缓存
        try:
            r = redis.from_url(REDIS_URL, encoding="utf8", decode_responses=True)
            FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
            print("✅ Redis cache initialized:", REDIS_URL)
        except Exception as e:
            print(f"⚠️  Redis init failed: {e}, using in-memory cache")
        
        # 初始化 MongoDB
        try:
            init_mongodb(MONGODB_URL, MONGODB_DB_NAME)
            print(f"✅ MongoDB initialized: {MONGODB_DB_NAME}")
        except Exception as e:
            print(f"⚠️  MongoDB init failed: {e}")
    
    # --- 关闭事件 ---
    @app.on_event("shutdown")
    async def shutdown_event():
        close_mongodb()
        print("👋 MongoDB connection closed")

    return app