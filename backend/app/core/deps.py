from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_session_factory():
    return SessionLocal
