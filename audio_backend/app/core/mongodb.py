"""
MongoDB 连接管理
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB 连接管理器"""
    
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    def connect(cls, mongodb_url: str, db_name: str):
        """连接 MongoDB"""
        try:
            cls.client = AsyncIOMotorClient(mongodb_url)
            cls.db = cls.client[db_name]
            logger.info(f"✅ Connected to MongoDB: {db_name}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    @classmethod
    def close(cls):
        """关闭 MongoDB 连接"""
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed")
    
    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """获取数据库实例"""
        if cls.db is None:
            raise RuntimeError("MongoDB not initialized. Call MongoDB.connect() first.")
        return cls.db


# 依赖注入函数
def get_mongo_db() -> AsyncIOMotorDatabase:
    """
    FastAPI 依赖注入函数
    用于路由中获取 MongoDB 数据库实例
    """
    return MongoDB.get_database()


# 初始化函数（在应用启动时调用）
def init_mongodb(mongodb_url: str, db_name: str):
    """初始化 MongoDB 连接"""
    MongoDB.connect(mongodb_url, db_name)


# 关闭函数（在应用关闭时调用）
def close_mongodb():
    """关闭 MongoDB 连接"""
    MongoDB.close()