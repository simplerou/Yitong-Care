from datetime import datetime,date
from sqlalchemy import String,Integer,JSON,DateTime,Date,ForeignKey,UniqueConstraint,Boolean
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base,TimestampMixin,MYSQL_TABLE_OPTIONS

class Credential(TimestampMixin,Base):
    __tablename__='ops_credential'
    __table_args__=MYSQL_TABLE_OPTIONS
    account_id:Mapped[str]=mapped_column(ForeignKey('account.id'),primary_key=True)
    qualification:Mapped[str]=mapped_column(String(80))
    valid_until:Mapped[date]=mapped_column(Date)

class ClinicalProfile(TimestampMixin,Base):
    __tablename__='ops_clinical_profile'
    __table_args__=MYSQL_TABLE_OPTIONS
    resident_id:Mapped[str]=mapped_column(ForeignKey('resident.id'),primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    resident_version:Mapped[int]=mapped_column(Integer)
    data:Mapped[dict]=mapped_column(JSON)

class ConstraintToken(TimestampMixin,Base):
    __tablename__='ops_constraint'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    private_context:Mapped[dict]=mapped_column(JSON)
    public_data:Mapped[dict]=mapped_column(JSON)
    fingerprint:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime)

class Draft(TimestampMixin,Base):
    __tablename__='ops_draft'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    owner_id:Mapped[str]=mapped_column(ForeignKey('account.id'),index=True)
    kind:Mapped[str]=mapped_column(String(24),index=True)
    status:Mapped[str]=mapped_column(String(24),index=True,default='pending')
    risk:Mapped[int]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(Integer,default=1)
    proposed:Mapped[dict]=mapped_column(JSON)
    current:Mapped[dict]=mapped_column(JSON)
    private_context:Mapped[dict]=mapped_column(JSON)
    source_hash:Mapped[str]=mapped_column(String(64))
    validation:Mapped[dict]=mapped_column(JSON)
    trace:Mapped[list]=mapped_column(JSON)
    expires_at:Mapped[datetime]=mapped_column(DateTime)
    decision_by:Mapped[str|None]=mapped_column(ForeignKey('account.id'),nullable=True)
    decision_note:Mapped[str]=mapped_column(String(1000),default='')

class Execution(TimestampMixin,Base):
    __tablename__='ops_execution'
    __table_args__=(UniqueConstraint('draft_id','sequence',name='uq_ops_execution_draft_seq'),MYSQL_TABLE_OPTIONS)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    draft_id:Mapped[str]=mapped_column(ForeignKey('ops_draft.id'),index=True)
    resident_id:Mapped[str|None]=mapped_column(ForeignKey('resident.id'),nullable=True)
    assignee_id:Mapped[str|None]=mapped_column(ForeignKey('account.id'),nullable=True)
    sequence:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(24),default='pending')
    data:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict]=mapped_column(JSON,default=dict)

class Correction(TimestampMixin,Base):
    __tablename__='ops_correction'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    draft_id:Mapped[str]=mapped_column(ForeignKey('ops_draft.id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('account.id'))
    route:Mapped[str]=mapped_column(String(16))
    tag:Mapped[str]=mapped_column(String(40))
    reason:Mapped[str]=mapped_column(String(1000))
    before:Mapped[dict]=mapped_column(JSON)
    after:Mapped[dict]=mapped_column(JSON)
    closed:Mapped[bool]=mapped_column(Boolean,default=False)

class Event(TimestampMixin,Base):
    __tablename__='ops_event'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('account.id'),index=True)
    action:Mapped[str]=mapped_column(String(60),index=True)
    object_id:Mapped[str]=mapped_column(String(64),default='')
    data:Mapped[dict]=mapped_column(JSON)

class Shift(TimestampMixin,Base):
    __tablename__='ops_shift'
    __table_args__=(UniqueConstraint('account_id','start_at',name='uq_ops_shift_account_start'),MYSQL_TABLE_OPTIONS)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    draft_id:Mapped[str]=mapped_column(ForeignKey('ops_draft.id'))
    account_id:Mapped[str]=mapped_column(ForeignKey('account.id'),index=True)
    start_at:Mapped[datetime]=mapped_column(DateTime)
    end_at:Mapped[datetime]=mapped_column(DateTime)
    hourly_rate:Mapped[str]=mapped_column(String(24))
    checked_in:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    checked_out:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class DrugReference(TimestampMixin,Base):
    __tablename__='ops_drug_reference'
    __table_args__=MYSQL_TABLE_OPTIONS
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    drug_id:Mapped[str]=mapped_column(String(80),index=True)
    category:Mapped[str]=mapped_column(String(24))
    chunk_id:Mapped[int]=mapped_column(ForeignKey('document_chunk.id',ondelete='CASCADE'))
    section:Mapped[str]=mapped_column(String(100))
    valid_from:Mapped[date]=mapped_column(Date)
    valid_until:Mapped[date|None]=mapped_column(Date,nullable=True)
    source_hash:Mapped[str]=mapped_column(String(64))
