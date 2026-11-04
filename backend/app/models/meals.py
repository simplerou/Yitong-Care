from datetime import date
from sqlalchemy import String, Integer, Date, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, MYSQL_TABLE_OPTIONS
class WeeklyMenu(TimestampMixin,Base):
    __tablename__='weekly_menu'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    week_start:Mapped[date]=mapped_column(Date,unique=True)
    status:Mapped[str]=mapped_column(String(16),default='draft')
    version:Mapped[int]=mapped_column(Integer,default=1)
    data:Mapped[dict]=mapped_column(JSON)
class MealProfile(TimestampMixin,Base):
    __tablename__='meal_profile'
    __table_args__=MYSQL_TABLE_OPTIONS
    resident_id:Mapped[str]=mapped_column(ForeignKey('resident.id'),primary_key=True)
    resident_version:Mapped[int]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(Integer,default=1)
    data:Mapped[dict]=mapped_column(JSON)
class MealSelection(TimestampMixin,Base):
    __tablename__='meal_selection'
    __table_args__=(UniqueConstraint('resident_id','meal_date','meal',name='uq_meal_selection_resident_slot'),MYSQL_TABLE_OPTIONS)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    resident_id:Mapped[str]=mapped_column(ForeignKey('resident.id'))
    menu_id:Mapped[str]=mapped_column(ForeignKey('weekly_menu.id'))
    meal_date:Mapped[date]=mapped_column(Date)
    meal:Mapped[str]=mapped_column(String(16))
    option_id:Mapped[str]=mapped_column(String(36))
    version:Mapped[int]=mapped_column(Integer,default=1)
    profile_version:Mapped[int]=mapped_column(Integer)
    resident_version:Mapped[int]=mapped_column(Integer)
class MealChange(TimestampMixin,Base):
    __tablename__='meal_change'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('account.id'))
    kind:Mapped[str]=mapped_column(String(30))
    entity_id:Mapped[str]=mapped_column(String(36))
    data:Mapped[dict]=mapped_column(JSON)
