from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, MYSQL_TABLE_OPTIONS

class Account(Base):
    __tablename__ = 'account'
    __table_args__ = MYSQL_TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str] = mapped_column(String(11), unique=True)
    name: Mapped[str] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user", server_default="user")
    password_hash: Mapped[str] = mapped_column(String(256))

class LoginSession(Base):
    __tablename__ = 'login_session'
    __table_args__ = MYSQL_TABLE_OPTIONS
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id', ondelete='CASCADE'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
