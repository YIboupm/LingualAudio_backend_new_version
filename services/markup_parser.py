# services/markup_parser_enhanced.py
import re
from typing import List, Dict, Any, Tuple
import spacy
from functools import lru_cache


class SieleMarkupParser:
    """
    SIELE 阅读材料标记解析器 + 词汇标注
    """
    
    def __init__(self, db_session=None):
        self.nlp = spacy.load("es_core_news_sm")
        self.db_session = db_session
        self._word_mapping = None
        self._word_fallback = None
    
    def _init_word_mapping(self):
        """初始化单词映射表"""
        if self._word_mapping is not None:
            return
        
        if self.db_session is None:
            # 如果没有数据库连接，跳过词汇标注
            self._word_mapping = {}
            self._word_fallback = {}
            return
        
        try:
            from audio_backend.app.models.word import Word
            
            words = self.db_session.query(Word).filter(
                Word.lang_code == "es"
            ).all()
            
            self._word_mapping = {}
            self._word_fallback = {}
            
            for w in words:
                # 精确匹配: (lemma, pos) -> word_id
                key = (w.lemma.lower(), w.pos.lower())
                self._word_mapping[key] = w.id
                
                # 回退匹配: lemma -> [word_ids]
                self._word_fallback.setdefault(w.lemma.lower(), []).append(w.id)
        
        except Exception as e:
            print(f"⚠️  词汇映射初始化失败: {e}")
            self._word_mapping = {}
            self._word_fallback = {}
    
    def parse(self, raw_markup_text: str) -> Dict[str, Any]:
        """
        解析标记文本 + 生成词汇标注
        
        Returns:
            {
                "tarea_number": 1,
                "title": "...",
                "raw_markup_text": "...",  # ⭐ 原始标记文本
                "plain_text_es": "...",
                "paragraphs": [...],
                "questions": [...],
                "question_type": "single_choice" | "cloze_fragments" | "cloze_mc",
                "lemmas": [...],
                "pos_distribution": {...},
                "annotations": [...]  # ⭐ 词汇标注
            }
        """
        result = {
            "tarea_number": None,
            "title": None,
            "raw_markup_text": raw_markup_text,  # ⭐ 保存原始文本
            "plain_text_es": "",
            "paragraphs": [],
            "questions": [],
            "question_type": "single_choice",
            "lemmas": [],
            "pos_distribution": {},
            "annotations": []  # ⭐ 词汇标注
        }
        
        # 1. 提取元数据
        result["tarea_number"] = self._extract_tarea_number(raw_markup_text)
        result["title"] = self._extract_title(raw_markup_text)
        
        # 2. 判断题型并提取题目
        if result["tarea_number"] in [4, 5]:
            raw_markup_text, questions, question_type = self._extract_cloze_questions(
                raw_markup_text, 
                result["tarea_number"]
            )
            result["questions"] = questions
            result["question_type"] = question_type
        else:
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
        
        # 8. ⭐ 生成词汇标注
        result["annotations"] = self._generate_annotations(doc)
        
        return result
    
    def _generate_annotations(self, doc) -> List[Dict[str, Any]]:
        """
        生成词汇标注（映射到 words 表）
        
        Returns:
            [
                {
                    "index": 0,
                    "word": "Hola",
                    "lemma": "hola",
                    "pos": "intj",
                    "start_char": 0,
                    "end_char": 4,
                    "word_id": 12345  # 关联到 words 表
                },
                ...
            ]
        """
        # 初始化词汇映射
        self._init_word_mapping()
        
        annotations = []
        
        for i, token in enumerate(doc):
            # 跳过标点和空格
            if token.is_punct or token.is_space:
                continue
            
            word_text = token.text.lower()
            lemma = token.lemma_.lower()
            pos = token.pos_.lower()
            
            # 查找 word_id
            word_id = None
            
            # 策略1: 精确匹配 (lemma, pos)
            if (lemma, pos) in self._word_mapping:
                word_id = self._word_mapping[(lemma, pos)]
            
            # 策略2: 回退到 lemma
            elif lemma in self._word_fallback:
                word_id = self._word_fallback[lemma][0]  # 取第一个
            
            # 策略3: 回退到原词
            elif word_text in self._word_fallback:
                word_id = self._word_fallback[word_text][0]
            
            annotations.append({
                "index": i,
                "word": token.text,
                "lemma": lemma,
                "pos": pos,
                "start_char": token.idx,
                "end_char": token.idx + len(token.text),
                "word_id": word_id  # 可能为 None
            })
        
        return annotations
    
    def generate_annotated_html(self, plain_text_es: str, annotations: List[Dict]) -> str:
        """
        生成带词汇标注的 HTML
        
        Args:
            plain_text_es: 纯西班牙语文本
            annotations: 词汇标注列表
        
        Returns:
            HTML 字符串，每个单词都有 data-word-id 属性
        """
        if not annotations:
            return plain_text_es
        
        # 按字符位置排序
        annotations = sorted(annotations, key=lambda x: x["start_char"])
        
        html_parts = []
        last_pos = 0
        
        for ann in annotations:
            start = ann["start_char"]
            end = ann["end_char"]
            word = ann["word"]
            word_id = ann.get("word_id") or ""
            lemma = ann["lemma"]
            pos = ann["pos"]
            
            # 添加单词之前的文本
            if start > last_pos:
                html_parts.append(plain_text_es[last_pos:start])
            
            # 添加标注的单词
            html_parts.append(
                f'<span data-word-id="{word_id}" '
                f'data-lemma="{lemma}" '
                f'data-pos="{pos}" '
                f'class="word-link">'
                f'{word}</span>'
            )
            
            last_pos = end
        
        # 添加剩余文本
        if last_pos < len(plain_text_es):
            html_parts.append(plain_text_es[last_pos:])
        
        return ''.join(html_parts)
    
    def generate_paragraph_html(self, paragraphs: List[Dict], annotations: List[Dict]) -> List[Dict]:
        """
        为每个段落生成带标注的 HTML
        
        Args:
            paragraphs: 段落列表
            annotations: 词汇标注列表
        
        Returns:
            更新后的段落列表（增加 html_es 字段）
        """
        result = []
        
        for para in paragraphs:
            start_char = para["start_char"]
            end_char = para["end_char"]
            
            # 筛选这个段落的标注
            para_annotations = [
                ann for ann in annotations
                if start_char <= ann["start_char"] < end_char
            ]
            
            # 调整标注的字符位置（相对于段落开头）
            adjusted_annotations = []
            for ann in para_annotations:
                adjusted = ann.copy()
                adjusted["start_char"] -= start_char
                adjusted["end_char"] -= start_char
                adjusted_annotations.append(adjusted)
            
            # 生成 HTML
            html_es = self.generate_annotated_html(
                para["text_es"],
                adjusted_annotations
            )
            
            # 添加到结果
            para_copy = para.copy()
            para_copy["html_es"] = html_es
            result.append(para_copy)
        
        return result
    
    # ========== 以下是原有的解析方法（不变） ==========
    
    def _extract_tarea_number(self, text: str) -> int:
        match = re.search(r'::tarea:(\d+)::', text)
        return int(match.group(1)) if match else 1
    
    def _extract_title(self, text: str) -> str:
        match = re.search(r'::title:(.+?)::', text)
        return match.group(1).strip() if match else None
    
    def _extract_cloze_questions(
        self, 
        text: str, 
        tarea_number: int
    ) -> Tuple[str, List[Dict], str]:
        questions = []
        question_type = "cloze_fragments" if tarea_number == 4 else "cloze_mc"
        
        pattern = r'\[\[gap(\d+)\|([^\]]+)\]\]answer:([^\[]+)\[\[/gap\]\]'
        matches = re.finditer(pattern, text)
        
        for match in matches:
            gap_number = int(match.group(1))
            options_str = match.group(2)
            correct_answer = match.group(3).strip()
            
            options_list = [opt.strip() for opt in options_str.split('|')]
            
            options = []
            for i, option_content in enumerate(options_list):
                label = chr(65 + i) if len(options_list) <= 5 else str(i + 1)
                
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
        
        cleaned_text = re.sub(pattern, r'___GAP\1___', text)
        
        return cleaned_text, questions, question_type
    
    def _extract_questions(self, text: str) -> Tuple[str, List[Dict]]:
        questions = []
        
        question_pattern = r'::question::(.*?)::question::'
        matches = re.finditer(question_pattern, text, re.DOTALL)
        
        for match in matches:
            question_block = match.group(1).strip()
            parsed_questions = self._parse_question_block(question_block)
            questions.extend(parsed_questions)
        
        cleaned_text = re.sub(question_pattern, '', text, flags=re.DOTALL)
        
        return cleaned_text, questions
    
    def _parse_question_block(self, block: str) -> List[Dict]:
        questions = []
        
        pattern = r'(\d+)\.\s+(.+?)(?=\d+\.\s+|$)'
        matches = re.finditer(pattern, block, re.DOTALL)
        
        for match in matches:
            question_num = int(match.group(1))
            question_content = match.group(2).strip()
            
            lines = question_content.split('\n')
            stem = lines[0].strip()
            
            options = []
            correct_answer = None
            
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                
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
                
                answer_match = re.search(r'::answer:([A-Z])::', line)
                if answer_match:
                    correct_answer = answer_match.group(1)
            
            if correct_answer:
                for opt in options:
                    if opt["label"] == correct_answer:
                        opt["is_correct"] = True
            
            if options:
                questions.append({
                    "question_id": question_num,
                    "stem": stem,
                    "options": options,
                    "question_type": "single_choice"
                })
        
        return questions
    
    def _remove_metadata_tags(self, text: str) -> str:
        text = re.sub(r'::tarea:\d+::', '', text)
        text = re.sub(r'::title:.+?::', '', text)
        return text.strip()
    
    def _parse_paragraph(
        self, 
        raw_para: str, 
        paragraph_id: int,
        start_char: int
    ) -> Dict[str, Any]:
        spanish_match = re.match(r'^(.*?)(?=::zh::|::grammar::|$)', raw_para, re.DOTALL)
        text_es = spanish_match.group(1).strip() if spanish_match else raw_para.strip()
        
        text_es = re.sub(r'___GAP\d+___', '[___]', text_es)
        
        zh_match = re.search(r'::zh::(.*?)::zh::', raw_para, re.DOTALL)
        text_zh = zh_match.group(1).strip() if zh_match else ""
        
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