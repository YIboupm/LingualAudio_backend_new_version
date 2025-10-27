# audio-backend/app/models/word.py
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from audio_backend.app.core.database import Base


class Word(Base):
    __tablename__ = 'words'
    id = Column(Integer, primary_key=True)
    lemma = Column(Text, nullable=False, index=True)
    lang_code = Column(String(10), nullable=False, default='es')
    pos = Column(String(50), nullable=False)
    pos_title = Column(String(100), nullable=False)
    #hyphenation = Column(Text)
    #etymology = Column(Text)
    categories = Column(ARRAY(Text))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    


    # 关联
    senses = relationship(
        'Sense',
        back_populates='word',
        cascade='all, delete-orphan'
    )
    pronunciation = relationship(
        'Pronunciation',
        back_populates='word',
        uselist=False,
        cascade='all, delete-orphan'
    )
    forms = relationship(
        'Form',
        back_populates='word',
        cascade='all, delete-orphan'
    )
    user_marks = relationship(
        'UserWord',
        back_populates='word',
        cascade='all, delete-orphan'
    )
    queries    = relationship(
        'UserWordQuery', 
        back_populates='word', 
        cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('lemma', 'lang_code', 'pos', name='uq_word_lang_pos'),
    )

class Sense(Base):
    __tablename__ = 'senses'
    id = Column(Integer, primary_key=True)
    word_id = Column(
        Integer,
        ForeignKey('words.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    sense_index = Column(Integer, nullable=False)
    definition = Column(Text, nullable=False)
    examples = Column(ARRAY(Text))

    # 关联
    word = relationship('Word', back_populates='senses')
    translations = relationship(
        'Translation',
        back_populates='sense',
        cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('ix_sense_word_senseidx', 'word_id', 'sense_index'),
    )

class Translation(Base):
    __tablename__ = 'translations'
    id = Column(Integer, primary_key=True)
    sense_id = Column(
        Integer,
        ForeignKey('senses.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    target_lang = Column(String(10), nullable=False)
    text = Column(Text, nullable=False)
    tags = Column(ARRAY(Text))

    # 关联
    sense = relationship('Sense', back_populates='translations')

class Pronunciation(Base):
    __tablename__ = 'pronunciations'
    word_id = Column(
        Integer,
        ForeignKey('words.id', ondelete='CASCADE'),
        primary_key=True
    )
    ipa = Column(Text)
    audio_url = Column(Text)

    # 关联
    word = relationship('Word', back_populates='pronunciation')

class Form(Base):
    __tablename__ = 'forms'
    id = Column(Integer, primary_key=True)
    word_id = Column(
        Integer,
        ForeignKey('words.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    form = Column(Text, nullable=False)
    tags = Column(ARRAY(Text))

    # 关联
    word = relationship('Word', back_populates='forms')

    __table_args__ = (
        UniqueConstraint('word_id', 'form', name='uq_form_word_form'),
    )

class UserWord(Base):
    __tablename__ = 'user_words'
    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True
    )
    word_id = Column(
        Integer,
        ForeignKey('words.id', ondelete='CASCADE'),
        primary_key=True
    )
    marked_at = Column(DateTime(timezone=True), server_default=func.now())

    # —— 关系 —— 
    user     = relationship('User', back_populates='user_words')
    word     = relationship('Word', back_populates='user_marks')



class UserWordQuery(Base):
    __tablename__ = 'user_word_queries'
    id         = Column(Integer, primary_key=True)
    user_id    = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    word_id    = Column(
        Integer,
        ForeignKey('words.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    queried_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    )

    # 方便 ORM 联查
    user       = relationship('User', back_populates='word_queries')
    word       = relationship('Word', back_populates='queries')

    __table_args__ = (
        # 如果想在同一秒重复记录也分开，可不去 dedupe
        # 下面的唯一索引防止重复：如果想允许多次同秒查询，则去掉它
        # UniqueConstraint('user_id', 'word_id', 'queried_at', name='uq_user_word_time'),
        Index('ix_user_word_queries_user_word', 'user_id', 'word_id'),
    )

# 然后，在 User 和 Word 模型中分别加上反向关系：



# in audio-backend/app/models/word.py (if you want)
Word.queries = relationship(
    'UserWordQuery',
    back_populates='word',
    cascade='all, delete-orphan',
)

