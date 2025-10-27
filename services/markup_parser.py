# services/markup_parser.py
import re
from typing import List, Dict, Any, Tuple
import spacy


class SieleMarkupParser:
    """
    SIELE 阅读材料标记解析器
    支持的标记：
    - ::tarea:N:: - Tarea 编号
    - ::title:xxx:: - 标题
    - ::zh::...::zh:: - 中文翻译
    - ::grammar::...::grammar:: - 语法讲解
    - ::question::...::question:: - 题目
    - --- - 段落分隔符
    """
    
    def __init__(self):
        self.nlp = spacy.load("es_core_news_sm")
    
    def parse(self, raw_markup_text: str) -> Dict[str, Any]:
        """
        解析标记文本
        
        Returns:
            {
                "tarea_number": 1,
                "title": "...",
                "plain_text_es": "...",
                "paragraphs": [...],
                "questions": [...],
                "lemmas": [...],
                "pos_distribution": {...}
            }
        """
        result = {
            "tarea_number": None,
            "title": None,
            "plain_text_es": "",
            "paragraphs": [],
            "questions": [],
            "lemmas": [],
            "pos_distribution": {}
        }
        
        # 1. 提取元数据
        result["tarea_number"] = self._extract_tarea_number(raw_markup_text)
        result["title"] = self._extract_title(raw_markup_text)
        
        # 2. 提取题目（先提取，因为题目不参与段落分析）
        raw_markup_text, questions = self._extract_questions(raw_markup_text)
        result["questions"] = questions
        
        # 3. 移除元数据标记
        content_text = self._remove_metadata_tags(raw_markup_text)
        
        # 4. 按 --- 分段
        raw_paragraphs = re.split(r'\n---+\n', content_text)
        
        # 5. 解析每个段落
        current_char_pos = 0
        spanish_text_parts = []
        
        for idx, raw_para in enumerate(raw_paragraphs):
            raw_para = raw_para.strip()
            if not raw_para:
                continue
            
            # 解析段落（提取西班牙语、翻译、语法）
            para_data = self._parse_paragraph(raw_para, idx + 1, current_char_pos)
            
            if para_data:
                result["paragraphs"].append(para_data)
                spanish_text_parts.append(para_data["text_es"])
                current_char_pos += len(para_data["text_es"]) + 1  # +1 for space
        
        # 6. 生成纯西班牙语文本
        result["plain_text_es"] = "\n\n".join(spanish_text_parts)
        
        # 7. spaCy 分析
        doc = self.nlp(result["plain_text_es"])
        
        # 生成 lemmas
        result["lemmas"] = []
        for i, token in enumerate(doc):
            if not token.is_punct and not token.is_space:
                result["lemmas"].append({
                    "index": i,
                    "word": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "is_stop": token.is_stop,
                    "start_char": token.idx,
                    "end_char": token.idx + len(token.text)
                })
        
        # 统计词性分布
        result["pos_distribution"] = {}
        for token in doc:
            if not token.is_punct and not token.is_space:
                result["pos_distribution"][token.pos_] = \
                    result["pos_distribution"].get(token.pos_, 0) + 1
        
        return result
    
    def _extract_tarea_number(self, text: str) -> int:
        """提取 Tarea 编号"""
        match = re.search(r'::tarea:(\d+)::', text)
        return int(match.group(1)) if match else 1
    
    def _extract_title(self, text: str) -> str:
        """提取标题"""
        match = re.search(r'::title:(.+?)::', text)
        return match.group(1).strip() if match else None
    
    def _extract_questions(self, text: str) -> Tuple[str, List[Dict]]:
        """
        提取题目块
        
        Returns:
            (清理后的文本, 题目列表)
        """
        questions = []
        
        # 匹配 ::question::...::question::
        question_pattern = r'::question::(.*?)::question::'
        matches = re.finditer(question_pattern, text, re.DOTALL)
        
        for match in matches:
            question_block = match.group(1).strip()
            parsed_questions = self._parse_question_block(question_block)
            questions.extend(parsed_questions)
        
        # 移除题目块
        cleaned_text = re.sub(question_pattern, '', text, flags=re.DOTALL)
        
        return cleaned_text, questions
    
    def _parse_question_block(self, block: str) -> List[Dict]:
        """
        解析题目块
        
        示例输入:
        1. Isabel escribe este correo a Sara para...
           [A] comer con ella.
           [B] invitarla a un viaje.
           [C] hablarle de su nuevo trabajo.
        ::answer:B::
        
        2. En el texto se dice...
        """
        questions = []
        
        # 按题号分割
        question_texts = re.split(r'\n(\d+)\.\s+', block)
        
        for i in range(1, len(question_texts), 2):
            if i + 1 > len(question_texts):
                break
            
            question_num = int(question_texts[i])
            question_content = question_texts[i + 1].strip()
            
            # 提取题干和选项
            lines = question_content.split('\n')
            stem = lines[0].strip()
            
            options = []
            correct_answer = None
            
            for line in lines[1:]:
                line = line.strip()
                
                # 匹配选项 [A] text
                option_match = re.match(r'\[([A-Z])\]\s+(.+)', line)
                if option_match:
                    label = option_match.group(1)
                    content = option_match.group(2).strip()
                    options.append({
                        "label": label,
                        "content": content,
                        "is_correct": False  # 暂时设为 False
                    })
                
                # 匹配答案 ::answer:B::
                answer_match = re.search(r'::answer:([A-Z])::',line)
                if answer_match:
                    correct_answer = answer_match.group(1)
            
            # 标记正确答案
            if correct_answer:
                for opt in options:
                    if opt["label"] == correct_answer:
                        opt["is_correct"] = True
            
            questions.append({
                "question_id": question_num,
                "stem": stem,
                "options": options
            })
        
        return questions
    
    def _remove_metadata_tags(self, text: str) -> str:
        """移除元数据标记"""
        text = re.sub(r'::tarea:\d+::', '', text)
        text = re.sub(r'::title:.+?::', '', text)
        return text.strip()
    
    def _parse_paragraph(
        self, 
        raw_para: str, 
        paragraph_id: int,
        start_char: int
    ) -> Dict[str, Any]:
        """
        解析单个段落
        
        输入示例:
        Hola Sara, ¿qué tal todo?...
        
        ::zh::你好，萨拉...::zh::
        
        ::grammar::
        - dolía [过去未完成时] 描述过去的状态
        - me sentí [简单过去时+反身动词] 表达感觉的变化
        ::grammar::
        """
        
        # 1. 提取西班牙语文本（第一部分，直到遇到标记）
        spanish_match = re.match(r'^(.*?)(?=::zh::|::grammar::|$)', raw_para, re.DOTALL)
        text_es = spanish_match.group(1).strip() if spanish_match else raw_para.strip()
        
        # 2. 提取中文翻译
        zh_match = re.search(r'::zh::(.*?)::zh::', raw_para, re.DOTALL)
        text_zh = zh_match.group(1).strip() if zh_match else ""
        
        # 3. 提取语法讲解
        grammar_notes = []
        grammar_match = re.search(r'::grammar::(.*?)::grammar::', raw_para, re.DOTALL)
        
        if grammar_match:
            grammar_text = grammar_match.group(1).strip()
            # 解析每一行语法讲解
            for line in grammar_text.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    line = line[1:].strip()
                    # 格式: word [类型] 说明
                    note_match = re.match(r'(.+?)\s*\[(.+?)\]\s*(.+)', line)
                    if note_match:
                        grammar_notes.append({
                            "word": note_match.group(1).strip(),
                            "type": note_match.group(2).strip(),
                            "note": note_match.group(3).strip()
                        })
        
        return {
            "paragraph_id": f"p{paragraph_id}",
            "text_es": text_es,
            "text_zh": text_zh,
            "start_char": start_char,
            "end_char": start_char + len(text_es),
            "grammar_notes": grammar_notes
        }