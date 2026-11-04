from datetime import date
from sqlalchemy import String, Text, Date, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, MYSQL_TABLE_OPTIONS

class Resident(TimestampMixin, Base):
    __tablename__ = 'resident'
    __table_args__ = MYSQL_TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_no: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(50), index=True)
    gender: Mapped[str] = mapped_column(String(16))
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    location: Mapped[str] = mapped_column(String(100))
    care_level: Mapped[str] = mapped_column(String(30))
    contact_name: Mapped[str] = mapped_column(String(50))
    contact_relation: Mapped[str] = mapped_column(String(30))
    contact_phone: Mapped[str] = mapped_column(String(32))
    allergies: Mapped[str] = mapped_column(Text)
    chronic_conditions: Mapped[str] = mapped_column(Text)
    dietary_notes: Mapped[str] = mapped_column(Text)
    mobility_notes: Mapped[str] = mapped_column(Text)
    communication_notes: Mapped[str] = mapped_column(Text)
    care_notes: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)

class ResidentAssignment(Base):
    __tablename__ = 'resident_assignment'
    __table_args__ = MYSQL_TABLE_OPTIONS
    resident_id: Mapped[str] = mapped_column(ForeignKey('resident.id', ondelete='CASCADE'), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), primary_key=True)

class ResidentChange(TimestampMixin, Base):
    __tablename__ = 'resident_change'
    __table_args__ = MYSQL_TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resident_id: Mapped[str] = mapped_column(ForeignKey('resident.id'), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('account.id'))
    actor_name: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(300))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict] = mapped_column(JSON)


class ResidentAccountBinding(TimestampMixin, Base):
    __tablename__ = 'resident_account_binding'
    __table_args__ = MYSQL_TABLE_OPTIONS
    resident_id: Mapped[str] = mapped_column(ForeignKey('resident.id'), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('account.id'), unique=True, nullable=False)
