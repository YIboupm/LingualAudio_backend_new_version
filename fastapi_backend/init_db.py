import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine, Base
import models  # 确保正确导入你的模型
import models
print("Models imported successfully:", models)

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully.")

