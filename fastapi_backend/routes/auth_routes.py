from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from fastapi_backend.schemas import UserCreate, UserLogin, Token
from fastapi_backend.database import SessionLocal
from fastapi_backend.crud import get_user_by_email, create_user
from fastapi_backend.routes.auth_utils import hash_password, verify_password, create_access_token
from datetime import timedelta
import os
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from pydantic import BaseModel


class UserInfo(BaseModel):
    id: int
    email: str
    full_name: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserInfo

# 加载环境变量
load_dotenv()

router = APIRouter()

# 配置 Google OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    authorize_params=None,
    access_token_url="https://oauth2.googleapis.com/token",
    access_token_params=None,
    client_kwargs={"scope": "openid email profile"},
)

# 获取数据库连接
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 用户注册接口
@router.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail={"error": "Email already registered"}
        )
    
    hashed_password = hash_password(user.password)
    new_user = create_user(db, user.email, hashed_password, user.full_name)
    
    access_token = create_access_token({"sub": new_user.email}, timedelta(minutes=30))
    return {"access_token": access_token, "token_type": "bearer"}

# 用户登录接口
@router.post("/login", response_model=LoginResponse)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid email or password"}
        )
    
    access_token = create_access_token({"sub": db_user.email}, timedelta(minutes=30))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "email": db_user.email,
            "full_name": db_user.full_name
        }
    }

# Google 登录接口
@router.get("/auth/google/login")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    return await oauth.google.authorize_redirect(request, redirect_uri)

# Google 回调处理
@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        raise HTTPException(
            status_code=400,
            detail={"error": "Failed to fetch user info"}
        )

    email = user_info["email"]
    full_name = user_info.get("name", "Google User")

    # 检查用户是否已存在
    db_user = get_user_by_email(db, email)
    if not db_user:
        db_user = create_user(db, email, "google_oauth", full_name)

    # 生成 JWT 访问令牌
    access_token = create_access_token({"sub": db_user.email}, timedelta(minutes=30))
    return {"access_token": access_token, "token_type": "bearer"}
