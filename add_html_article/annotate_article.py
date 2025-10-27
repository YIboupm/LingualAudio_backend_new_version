import os
import sys
import argparse
#
# 这个脚本的作用是给一篇西班牙语文章打上 data-word-id 标注
# —— 第一步：把项目根目录加入 sys.path，好让下面的 import 能找到你的 models ——
proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import spacy

from audio_backend.app.models.word import Word

def build_mapping(db_url: str, lang_code: str):
    engine = create_engine(db_url, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    all_words = session.query(Word).filter_by(lang_code=lang_code).all()
    session.close()
    # (lemma, pos) -> id
    mp = {(w.lemma, w.pos): w.id for w in all_words}
    # 额外准备一个只按 lemma → [ids] 的备选表
    by_lemma = {}
    for w in all_words:
        by_lemma.setdefault(w.lemma, []).append(w.id)
    return mp, by_lemma

def annotate(text: str, nlp, mapping, fallback):
    out = []
    for para in text.split('\n\n'):
        doc = nlp(para)
        line = []
        for tok in doc:
            # 1) 标点直接放原文
            if tok.is_punct:
                line.append(tok.text_with_ws)
                continue

            lemma = tok.lemma_
            pos   = tok.pos_.lower()    # spaCy 给的是大写 UPOS
            word_id = mapping.get((lemma, pos), "")

            # 2) 如果连 (lemma,pos) 都没找到，就退回到「只按 lemma」粗匹配
            if not word_id and lemma in fallback:
                word_id = fallback[lemma][0]  # 多条取第一个

            span = (
                f'<span '
                f'data-word-id="{word_id}" '
                f'data-lemma="{lemma}" '
                f'data-pos="{pos}">'
                f'{tok.text}</span>'
                f'{tok.whitespace_}'
            )
            line.append(span)

        out.append('<p>' + ''.join(line) + '</p>')

    return '\n\n'.join(out)

def main():
    parser = argparse.ArgumentParser(
        description="给一篇西班牙语文章打上 data-word-id 标注"
    )
    parser.add_argument('-i','--input',  required=True,
                        help="原文 txt 文件路径，比如 ./my_article.txt")
    parser.add_argument('-o','--output', required=True,
                        help="输出 HTML 文件路径，比如 ./annotated.html")
    parser.add_argument('-d','--db-url',
        default="postgresql://liangyibo:mypassword@localhost:5432/userandaudio",
        help="SQLAlchemy 数据库 URL")
    parser.add_argument('-l','--lang', default="es",
                        help="文章语言代码 (默认 es)")
    args = parser.parse_args()

    print("加载数据库映射…")
    mapping, fallback = build_mapping(args.db_url, args.lang)

    print("加载 spaCy 模型…")
    try:
        nlp = spacy.load("es_core_news_sm")
    except OSError:
        spacy.cli.download("es_core_news_sm")
        nlp = spacy.load("es_core_news_sm")

    print(f"读取原文：{args.input}")
    with open(args.input, 'r', encoding='utf-8') as f:
        text = f.read()

    print("开始标注…")
    html = annotate(text, nlp, mapping, fallback)

    print(f"写入结果：{args.output}")
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    print("完成！")

if __name__ == "__main__":
    main()