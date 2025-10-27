# services/markup_parser_enhanced.py
"""
增强版 SIELE 标记解析器
支持题型：
1. Tarea 1-3: 独立选择题（已有）
2. Tarea 4: 完形填空 - 选择片段 (cloze-fragments)
3. Tarea 5: 完形填空 - 选择单词 (cloze-multiple-choice)
"""
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
    - ::question::...::question:: - 独立题目（Tarea 1-3）
    - [[gap1|A|B|C|D]]answer:B[[/gap]] - 嵌入式完形填空
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
                "question_type": "single_choice" | "cloze_fragments" | "cloze_mc",
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
            "question_type": "single_choice",  # 默认类型
            "lemmas": [],
            "pos_distribution": {}
        }
        
        # 1. 提取元数据
        result["tarea_number"] = self._extract_tarea_number(raw_markup_text)
        result["title"] = self._extract_title(raw_markup_text)
        
        # 2. 判断题型并提取题目
        if result["tarea_number"] in [4, 5]:
            # Tarea 4-5: 完形填空（嵌入式）
            raw_markup_text, questions, question_type = self._extract_cloze_questions(
                raw_markup_text, 
                result["tarea_number"]
            )
            result["questions"] = questions
            result["question_type"] = question_type
        else:
            # Tarea 1-3: 独立选择题
            raw_markup_text, questions = self._extract_questions(raw_markup_text)
            result["questions"] = questions
            result["question_type"] = "single_choice"
        
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
                current_char_pos += len(para_data["text_es"]) + 1
        
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
    
    def _extract_cloze_questions(
        self, 
        text: str, 
        tarea_number: int
    ) -> Tuple[str, List[Dict], str]:
        """
        提取完形填空题目（Tarea 4-5）
        
        标记格式:
        [[gap1|A|B|C|D]]answer:B[[/gap]]
        或
        [[gap1|opción1|opción2|opción3]]answer:2[[/gap]]
        
        Returns:
            (清理后的文本, 题目列表, 题型)
        """
        questions = []
        question_type = "cloze_fragments" if tarea_number == 4 else "cloze_mc"
        
        # 匹配 [[gapN|...]]answer:X[[/gap]]
        pattern = r'\[\[gap(\d+)\|([^\]]+)\]\]answer:([^\[]+)\[\[/gap\]\]'
        matches = re.finditer(pattern, text)
        
        for match in matches:
            gap_number = int(match.group(1))
            options_str = match.group(2)
            correct_answer = match.group(3).strip()
            
            # 分割选项
            options_list = [opt.strip() for opt in options_str.split('|')]
            
            # 构建选项列表
            options = []
            for i, option_content in enumerate(options_list):
                # 对于 Tarea 4，选项可能是 A、B、C、D
                # 对于 Tarea 5，选项可能是具体的词
                label = chr(65 + i) if len(options_list) <= 5 else str(i + 1)
                
                # 判断是否是正确答案
                is_correct = False
                if correct_answer.upper() == label:
                    is_correct = True
                elif correct_answer == str(i + 1):
                    is_correct = True
                elif correct_answer == option_content:
                    is_correct = True
                
                options.append({
                    "label": label,
                    "content": option_content,
                    "is_correct": is_correct
                })
            
            questions.append({
                "question_id": gap_number,
                "gap_id": f"gap{gap_number}",
                "question_type": question_type,
                "options": options
            })
        
        # 清理文本：将 [[gap...]] 替换为占位符
        cleaned_text = re.sub(pattern, r'___GAP\1___', text)
        
        return cleaned_text, questions, question_type
    
    def _extract_questions(self, text: str) -> Tuple[str, List[Dict]]:
        """
        提取独立题目（Tarea 1-3）
        
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
        解析独立题目块（Tarea 1-3）- 修复版本
        """
        questions = []
        
        # 使用 finditer 直接找到所有题目
        pattern = r'(\d+)\.\s+(.+?)(?=\d+\.\s+|$)'
        matches = re.finditer(pattern, block, re.DOTALL)
        
        for match in matches:
            question_num = int(match.group(1))
            question_content = match.group(2).strip()
            
            # 提取题干和选项
            lines = question_content.split('\n')
            stem = lines[0].strip()
            
            options = []
            correct_answer = None
            
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                
                # 匹配选项 [A] text
                option_match = re.match(r'\[([A-Z])\]\s+(.+)', line)
                if option_match:
                    label = option_match.group(1)
                    content = option_match.group(2).strip()
                    content = re.sub(r'::answer:[A-Z]::', '', content).strip()
                    options.append({
                        "label": label,
                        "content": content,
                        "is_correct": False
                    })
                
                # 匹配答案 ::answer:B::
                answer_match = re.search(r'::answer:([A-Z])::', line)
                if answer_match:
                    correct_answer = answer_match.group(1)
            
            # 标记正确答案
            if correct_answer:
                for opt in options:
                    if opt["label"] == correct_answer:
                        opt["is_correct"] = True
            
            # 只添加有选项的题目
            if options:
                questions.append({
                    "question_id": question_num,
                    "stem": stem,
                    "options": options,
                    "question_type": "single_choice"
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
        """
        # 1. 提取西班牙语文本（第一部分，直到遇到标记）
        spanish_match = re.match(r'^(.*?)(?=::zh::|::grammar::|$)', raw_para, re.DOTALL)
        text_es = spanish_match.group(1).strip() if spanish_match else raw_para.strip()
        
        # 移除完形填空的占位符（如果有）
        text_es = re.sub(r'___GAP\d+___', '[___]', text_es)
        
        # 2. 提取中文翻译
        zh_match = re.search(r'::zh::(.*?)::zh::', raw_para, re.DOTALL)
        text_zh = zh_match.group(1).strip() if zh_match else ""
        
        # 3. 提取语法讲解
        grammar_notes = []
        grammar_match = re.search(r'::grammar::(.*?)::grammar::', raw_para, re.DOTALL)
        
        if grammar_match:
            grammar_text = grammar_match.group(1).strip()
            for line in grammar_text.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    line = line[1:].strip()
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