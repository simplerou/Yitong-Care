from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, MYSQL_TABLE_OPTIONS

class Account(Base):
    __tablename__ = 'account'
    __table_args__ = MYSQL_TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str] = mapped_column(String(11), unique=True)
    name: Mapped[str] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user", server_default="user")
    status: Mapped[str] = mapped_column(String(16),nullable=False,default='active',server_default='active')
    requested_role: Mapped[str | None] = mapped_column(String(16),nullable=True)
    application_note: Mapped[str] = mapped_column(String(500),nullable=False,default='',server_default='')
    review_note: Mapped[str] = mapped_column(String(1000),nullable=False,default='',server_default='')
    application_version: Mapped[int] = mapped_column(Integer,nullable=False,default=1,server_default='1')
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256))

class LoginSession(Base):
    __tablename__ = 'login_session'
    __table_args__ = MYSQL_TABLE_OPTIONS
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id', ondelete='CASCADE'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
