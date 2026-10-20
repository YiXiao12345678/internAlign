from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)


class Resume(Base):
    """
    One row per upload. The newest row for a user is their active resume.
    The original file is kept on disk (stored_path) and never modified, as the
    proposal requires; `text` is the extracted text used for analysis.
    """

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_now)
