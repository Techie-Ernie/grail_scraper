import os
from sqlalchemy import create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://exam_user:password@localhost/exam_questions"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True
)
