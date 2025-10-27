#audio-backend/app/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from audio_backend.app.api import audio, realtime_audio

def get_app():
    app = FastAPI(title="Audio Processing API")

    #
    app.include_router(audio.router, prefix="/audio", tags=["Audio"])
    app.include_router(realtime_audio.router, prefix="/realtime", tags=["RealTime"])

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        print("请求验证错误！")
        print("请求路径：", request.url.path)
        print("错误详情：", exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.get("/")
    def health_check():
        return {"status": "running"}

    return app
