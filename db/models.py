from sqlalchemy import (
    Column, Integer, Text, String, CheckConstraint,
    TIMESTAMP
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)

    question_type = Column(
        String,
        nullable=False
    )  # 'exam' or 'understanding'

    category = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    subject = Column(String, nullable=False)
    chapter = Column(String, nullable=False)

    question_text = Column(Text, nullable=False)
    marks = Column(Integer)

    source_link = Column(Text)
    answer_link = Column(Text)

    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "question_type IN ('exam', 'understanding')",
            name="question_type_check"
        ),
        CheckConstraint(
            """
            (question_type = 'exam' AND marks IS NOT NULL)
            OR
            (question_type = 'understanding' AND marks IS NULL)
            """,
            name="marks_consistency_check"
        ),
    )
