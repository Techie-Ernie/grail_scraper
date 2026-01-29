from sqlalchemy import text
from db.engine import engine
from db.models import Base

def create_schema():
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_questions_type
            ON questions (question_type);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_questions_subject_year
            ON questions (subject, year);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_questions_chapter
            ON questions (chapter);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_questions_marks
            ON questions (marks);
        """))
