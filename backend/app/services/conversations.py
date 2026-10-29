"""Single-host conversation writer locks; snapshots never depend on live source rows."""
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from uuid import UUID, uuid4
import fcntl
from sqlalchemy import func, select
from app.core.config import BACKEND_DIR
from app.core.exceptions import BusinessError
from app.models.conversation import PolicyConversation, PolicyTurn
from app.schemas.conversation import ConversationRecord, StoredTurn
from app.schemas.chat import PolicyQuestion, ChatTurn


def get_conversation_lock_dir():
    return BACKEND_DIR/'var'/'conversation_locks'


@contextmanager
def conversation_lock(root: Path, conversation_id: str):
    key=str(UUID(conversation_id))
    root.mkdir(parents=True,exist_ok=True)
    # Do not unlink lock files: unlinking a held inode would break cross-process exclusion.
    with (root/(key+'.lock')).open('a+b') as handle:
        try: fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise BusinessError('该会话正在生成回答，请等待完成后再操作。',409) from None
        try: yield
        finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def require_conversation(db,key):
    row=db.get(PolicyConversation,key)
    if row is None: raise BusinessError('会话不存在或已删除。',404)
    return row


def create(db):
    row=PolicyConversation(id=str(uuid4()),title='新政策咨询')
    db.add(row);db.commit();db.refresh(row)
    return ConversationRecord.model_validate(row)


def listing(db,page,page_size):
    total=db.scalar(select(func.count()).select_from(PolicyConversation)) or 0
    rows=db.scalars(select(PolicyConversation).order_by(PolicyConversation.updated_at.desc(),PolicyConversation.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[ConversationRecord.model_validate(r) for r in rows],'total':total,'page':page,'page_size':page_size}


def recover_interrupted(db,key):
    pending=db.scalars(select(PolicyTurn).where(PolicyTurn.conversation_id==key,PolicyTurn.status=='running')).all()
    for row in pending:
        row.status='failed';row.error='上次回答任务已中断，未保存最终答案。可重试最后一条问题。'
    if pending: db.commit()


def detail(db,key,root,before_seq=None,page_size=20):
    try:
        with conversation_lock(root,key):
            # Read only AFTER taking the lock: a prior MySQL repeatable-read snapshot
            # could otherwise turn a just-completed task back into a failed one.
            db.rollback()
            conversation=require_conversation(db,key)
            recover_interrupted(db,key)
    except BusinessError as error:
        if error.status_code!=409: raise
        db.rollback()
        conversation=require_conversation(db,key)
    statement=select(PolicyTurn).where(PolicyTurn.conversation_id==key)
    if before_seq is not None: statement=statement.where(PolicyTurn.seq<before_seq)
    rows=db.scalars(statement.order_by(PolicyTurn.seq.desc()).limit(page_size+1)).all()
    more=len(rows)>page_size;rows=list(reversed(rows[:page_size]))
    return {'conversation':ConversationRecord.model_validate(conversation),'turns':[StoredTurn.model_validate(row) for row in rows],
            'has_more':more,'next_before_seq':rows[0].seq if more and rows else None}


def delete(db,key,root):
    with conversation_lock(root,key):
        row=require_conversation(db,key);db.delete(row);db.commit()


def ask(db,key,request,root,generate):
    with conversation_lock(root,key):
        conversation=require_conversation(db,key)
        recover_interrupted(db,key)
        request_id=str(request.request_id)
        turn=db.get(PolicyTurn,request_id)
        last_seq=db.scalar(select(func.max(PolicyTurn.seq)).where(PolicyTurn.conversation_id==key)) or 0
        if turn:
            if turn.conversation_id!=key or turn.question!=request.question:
                raise BusinessError('请求标识已被其他问题使用，请刷新后重试。',409)
            if turn.status=='succeeded' or not request.retry: return StoredTurn.model_validate(turn)
            if turn.seq!=last_seq: raise BusinessError('只能重试会话中最后一条失败的问题，请重新提问。',409)
            turn.attempts+=1;turn.status='running';turn.error=None
        else:
            if request.retry: raise BusinessError('待重试的问题不存在，请刷新后重新提问。',404)
            turn=PolicyTurn(id=request_id,conversation_id=key,seq=last_seq+1,question=request.question,status='running',attempts=1)
            db.add(turn)
        conversation.updated_at=datetime.now(UTC).replace(tzinfo=None)
        if turn.seq==1: conversation.title=request.question[:60]
        db.commit()
        # History comes exclusively from successful stored turns preceding this request.
        previous=db.scalars(select(PolicyTurn).where(PolicyTurn.conversation_id==key,PolicyTurn.seq<turn.seq,PolicyTurn.status=='succeeded').order_by(PolicyTurn.seq.desc()).limit(3)).all()
        history=[]
        for row in reversed(previous):
            history.extend([ChatTurn(role='user',content=row.question),ChatTurn(role='assistant',content=row.response['answer'][:6000])])
        try:
            answer=generate(PolicyQuestion(question=request.question,history=history))
            turn.response=answer.model_dump(mode='json');turn.status='succeeded';turn.error=None
            conversation.updated_at=datetime.now(UTC).replace(tzinfo=None)
            db.commit();db.refresh(turn)
            return StoredTurn.model_validate(turn)
        except Exception as error:
            db.rollback()
            # Do not expose provider payloads, credentials or exception details.
            failed=db.get(PolicyTurn,request_id)
            if failed:
                failed.status='failed';failed.error=error.message[:500] if isinstance(error,BusinessError) else '回答服务异常，未保存最终答案。请重试。'
                db.commit()
            raise
