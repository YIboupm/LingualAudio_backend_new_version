# audio_backend/app/models/__init__.py
# ============================================================
# 导入通用模型
# ============================================================
from .audio import Audio
from .user import User
from .word import Word

# ============================================================
# 导入阅读模块
# ============================================================
from .siele_reading_models import (
    # 常量
    QUESTION_TYPE_SINGLE_CHOICE,
    QUESTION_TYPE_MATCHING,
    QUESTION_TYPE_CLOZE_FRAGMENTS,
    QUESTION_TYPE_CLOZE_MC,
    VALID_QUESTION_TYPES,

    # 模型
    SieleReadingPassage,
    SieleReadingQuestion,
    SieleReadingOption,
    SieleReadingPracticeSession,
    SieleReadingUserAnswer,
    SieleReadingUserStats,
)

# ============================================================
# 导入写作模块（SIELE + DELE）
# ============================================================
from .siele_writing_models import (
    SieleWritingTask,
    SieleWritingReference,
    SieleWritingSubmission,
    SieleWritingScore,
    SieleWritingFeedbackVersion,
)

from .dele_writing_task_models import (
    WritingTask,
    WritingSubmission,
    WritingReference,
    WritingScore,
    WritingFeedbackVersion,
    WritingImage,
)

# ============================================================
# 导入听力素材模块
# ============================================================
from .listening_materials_models import ListeningMaterial
from .tourism_models import Country, City, Place, Place_Paragraph

# ============================================================
# 暴露的公共接口
# ============================================================
__all__ = [
    # ---- 通用模型 ----
    "Audio",
    "User",
    "Word",

    # ---- 阅读常量 ----
    "QUESTION_TYPE_SINGLE_CHOICE",
    "QUESTION_TYPE_MATCHING",
    "QUESTION_TYPE_CLOZE_FRAGMENTS",
    "QUESTION_TYPE_CLOZE_MC",
    "VALID_QUESTION_TYPES",

    # ---- 阅读模型 ----
    "SieleReadingPassage",
    "SieleReadingQuestion",
    "SieleReadingOption",
    "SieleReadingPracticeSession",
    "SieleReadingUserAnswer",
    "SieleReadingUserStats",

    # ---- SIELE 写作模块 ----
    "SieleWritingTask",
    "SieleWritingReference",
    "SieleWritingSubmission",
    "SieleWritingScore",
    "SieleWritingFeedbackVersion",

    # ---- DELE 写作模块 ----
    "WritingTask",
    "WritingSubmission",
    "WritingReference",
    "WritingScore",
    "WritingFeedbackVersion",
    "WritingImage",

    # ---- 听力素材模块 ----
    "ListeningMaterial",

        # ---- 旅游模块 ----
    "Country",
    "City",
    "Place",
    "Place_Paragraph",
]
