# main.py
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
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")  # 默认本地

    if not DATABASE_URL or not SECRET_KEY:
        raise ValueError("Missing essential environment variables. Check your .env file.")

    app = FastAPI()

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
    app.include_router(siele_admin_router, prefix="/siele-reading-admin", tags=["siele-admin"])
    app.include_router(story_router, tags=["stories"])
    app.include_router(tourism_admin_routes, tags=["tourism-admin"])
    app.include_router(place_router, tags=["places"])
    # 在 def get_app() 中添加:
    try:
     from fastapi_backend.routes.siele_reading_routes import router
     app.include_router(router)
     print("✅ SIELE reading routes loaded")
    except Exception as e:
      print(f"⚠️  Reading routes error: {e}")

    # --- 静态文件 ---
    BASE_DIR = Path(__file__).resolve().parent
    env_upload = os.getenv("UPLOAD_DIR")
    if env_upload:
        up = Path(env_upload)
        uploads_dir = (up if up.is_absolute() else (BASE_DIR / up)).resolve()
    else:
        uploads_dir = (BASE_DIR / "uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    print("STATIC /files =>", uploads_dir)
    app.mount("/files", StaticFiles(directory=str(uploads_dir)), name="uploaded_files")

    # --- 健康检查 ---
    @app.get("/")
    def read_root():
        return {"message": "Hello, FastAPI!"}

    # --- 初始化 Redis 缓存 ---
    @app.on_event("startup")
    async def startup_event():
        r = redis.from_url(REDIS_URL, encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")

    return app
