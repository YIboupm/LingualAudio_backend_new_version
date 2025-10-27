# add_html_article/annotator.py
import spacy
from functools import lru_cache
from audio_backend.app.core.database import get_db
from audio_backend.app.models.word import Word

@lru_cache()
def get_nlp():
    return spacy.load("es_core_news_sm")

@lru_cache()
def get_mapping():
    db = next(get_db())
    words = db.query(Word).filter(Word.lang_code=="es").all()
    mp, fallback = {}, {}
    for w in words:
        mp[(w.lemma, w.pos)] = w.id
        fallback.setdefault(w.lemma, []).append(w.id)
    return mp, fallback

def annotate_html(text: str) -> str:
    nlp = get_nlp()
    mp, fallback = get_mapping()
    paras = []
    for para in text.split("\n\n"):
        doc = nlp(para)
        parts = []
        for tok in doc:
            if tok.is_punct:
                parts.append(tok.text_with_ws)
            else:
                word_text = tok.text.lower()
                lemma = tok.lemma_.lower()
                pos = tok.pos_.lower()

                # 优先按 (lemma, pos) 精确匹配
                wid = mp.get((lemma, pos))

                # 其次按 lemma 回退
                if not wid:
                    wid = (fallback.get(lemma) or [None])[0]

                # 最后按 word_text（原词）再回退
                if not wid:
                    wid = (fallback.get(word_text) or [None])[0]

                if not wid:
                    wid = ""

                parts.append(
                    f'<span data-word-id="{wid}" data-lemma="{lemma}" data-pos="{pos}">'
                    f'{tok.text}</span>{tok.whitespace_}'
                )

        paras.append("<p>" + "".join(parts) + "</p>")

    return "\n".join(paras)




