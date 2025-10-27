# run_main.py
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# fastapi-cache2
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
import redis.asyncio as aioredis

# 让 Python 能找到两个子项目
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR / "audio_backend"))
sys.path.append(str(BASE_DIR / "fastapi_backend"))

# 分别导入两个子项目的 get_app（仅用于拿到路由/异常处理器/静态挂载信息）
from audio_backend.app.main import get_app as get_audio_app
from fastapi_backend.main import get_app as get_user_app

# 导入 MongoDB 初始化函数
from audio_backend.app.core.mongodb import init_mongodb, close_mongodb

def create_unified_app() -> FastAPI:
    load_dotenv()

    SECRET_KEY = os.getenv("SECRET_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "siele_app")
    
    if not SECRET_KEY:
        raise RuntimeError("Missing SECRET_KEY in .env")

    # 1) 先各自生成子 app（注意：不会触发它们的 startup）
    audio_app = get_audio_app()
    user_app = get_user_app()

    # 2) 创建总 app & 中间件
    app = FastAPI(title="LingualAudio Unified API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        session_cookie="session",
        max_age=86400,
    )

    # 3) 统一初始化 fastapi-cache2 和 MongoDB（总入口负责）
    @app.on_event("startup")
    async def _init_services():
        # 初始化 Redis 缓存
        try:
            r = aioredis.from_url(REDIS_URL, encoding="utf8", decode_responses=True)
            FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
            print(f"[run_main] ✅ fastapi-cache initialized with Redis: {REDIS_URL}")
        except Exception as e:
            FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
            print(f"[run_main] ⚠️  Redis init failed ({e}), fallback to InMemory cache.")
        
        # 初始化 MongoDB
        try:
            init_mongodb(MONGODB_URL, MONGODB_DB_NAME)
            print(f"[run_main] ✅ MongoDB initialized: {MONGODB_DB_NAME}")
        except Exception as e:
            print(f"[run_main] ❌ MongoDB init failed: {e}")
            raise

    # 4) 关闭连接
    @app.on_event("shutdown")
    async def _close_services():
        try:
            close_mongodb()
            print("[run_main] MongoDB connection closed")
        except Exception as e:
            print(f"[run_main] Error closing MongoDB: {e}")

    # 5) 合并路由（把两个子 app 的 routes 挂到总 app 上）
    for route in audio_app.router.routes:
        app.router.routes.append(route)
    for route in user_app.router.routes:
        app.router.routes.append(route)

    # 6) 合并异常处理器（顺序：先 audio，再 user；可按需要调整）
    for key, handler in audio_app.exception_handlers.items():
        app.add_exception_handler(key, handler)
    for key, handler in user_app.exception_handlers.items():
        app.add_exception_handler(key, handler)

    # 7) 静态文件（子 app 的 app.mount 不会自动带过来，所以在总 app 再挂一次）
    #    对齐 fastapi_backend/main.py 的 /files 逻辑
    env_upload = os.getenv("UPLOAD_DIR")
    if env_upload:
        up = Path(env_upload)
        uploads_dir = (up if up.is_absolute() else (BASE_DIR / "fastapi_backend" / up)).resolve()
    else:
        uploads_dir = (BASE_DIR / "fastapi_backend" / "uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    print("[run_main] STATIC /files =>", uploads_dir)
    app.mount("/files", StaticFiles(directory=str(uploads_dir)), name="uploaded_files")

    # 8) 统一的请求体验证错误处理（可选）
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": exc.body},
        )

    # 9) 健康检查
    @app.get("/")
    def health_check():
        return {"status": "Unified backend running!"}

    return app

app = create_unified_app()