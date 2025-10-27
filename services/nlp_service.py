# nlp_service.py
"""
NLP 分析服务
提供西班牙语文本的词性分析和难度评估
"""
import spacy
from functools import lru_cache
from typing import Dict, Any


class NLPService:
    """NLP 分析服务"""
    
    def __init__(self):
        try:
            self.nlp = spacy.load("es_core_news_sm")
        except OSError:
            print("⚠️  spaCy 模型未安装，正在下载...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "es_core_news_sm"])
            self.nlp = spacy.load("es_core_news_sm")
    
    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        分析西班牙语文本
        
        Returns:
            {
                "lemmas": [...],
                "pos_distribution": {...},
                "word_count": int,
                "sentence_count": int
            }
        """
        doc = self.nlp(text)
        
        # 生成 lemmas
        lemmas = []
        for i, token in enumerate(doc):
            if not token.is_punct and not token.is_space:
                lemmas.append({
                    "index": i,
                    "word": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "is_stop": token.is_stop,
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text)
                })
        
        # 统计词性分布
        pos_distribution = {}
        word_count = 0
        for token in doc:
            if not token.is_punct and not token.is_space:
                pos_distribution[token.pos_] = pos_distribution.get(token.pos_, 0) + 1
                word_count += 1
        
        # 统计句子数
        sentence_count = len(list(doc.sents))
        
        return {
            "lemmas": lemmas,
            "pos_distribution": pos_distribution,
            "word_count": word_count,
            "sentence_count": sentence_count
        }
    
    def estimate_difficulty(self, pos_distribution: Dict[str, int], word_count: int) -> float:
        """
        评估文本难度（0-10）
        
        基于：
        - 词汇量
        - 复杂词性占比（动词、形容词、副词）
        """
        if word_count == 0:
            return 0.0
        
        # 基础难度 = 词汇量影响
        base_difficulty = min(word_count / 100.0, 5.0)  # 最多 5 分
        
        # 复杂词性权重
        complex_pos_weight = {
            "VERB": 0.3,
            "ADJ": 0.2,
            "ADV": 0.2,
            "NOUN": 0.1
        }
        
        # 计算复杂度得分
        complexity_score = 0.0
        for pos, count in pos_distribution.items():
            if pos in complex_pos_weight:
                complexity_score += (count / word_count) * complex_pos_weight[pos] * 10
        
        # 总难度 = 基础难度 + 复杂度得分
        total_difficulty = base_difficulty + complexity_score
        
        # 限制在 0-10 之间
        return min(max(total_difficulty, 0.0), 10.0)


# 单例模式
@lru_cache(maxsize=1)
def get_nlp_service() -> NLPService:
    """获取 NLP 服务单例"""
    return NLPService()