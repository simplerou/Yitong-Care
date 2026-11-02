"""Health conversation writer. Snapshots include the vitals assessment of that turn."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.core.exceptions import BusinessError
from app.services.ownership import visible_to_account, owner_filter
from app.models.health_conversation import HealthConversation, HealthTurn
from app.schemas.chat import ChatTurn
from app.schemas.health import HealthDialogueState, HealthProfile, HealthQuestion
from app.schemas.health_conversation import (
    HealthConversationDetail, HealthConversationQuestion, HealthConversationRecord, HealthStoredTurn,
)
from app.services.health.dialogue_state import build_dialogue


def require_conversation(db, key):
    row = db.get(HealthConversation, key)
    if row is None or not visible_to_account(db, row): raise BusinessError('会话不存在或已删除。', 404)
    return row


def create(db, profile: HealthProfile | None = None):
    row = HealthConversation(owner_id=db.info.get('account_id'), id=str(uuid4()), title='新健康咨询',
                            profile=profile.model_dump(mode='json') if profile else None)
    db.add(row); db.commit(); db.refresh(row)
    return HealthConversationRecord.model_validate(row)


def listing(db, page, page_size):
    total = db.scalar(select(func.count()).select_from(HealthConversation).where(owner_filter(db, HealthConversation))) or 0
    rows = db.scalars(select(HealthConversation).where(owner_filter(db, HealthConversation))
                      .order_by(HealthConversation.updated_at.desc(), HealthConversation.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': [HealthConversationRecord.model_validate(row) for row in rows],
            'total': total, 'page': page, 'page_size': page_size}


def recover_interrupted(db, key):
    pending = db.scalars(select(HealthTurn).where(HealthTurn.conversation_id == key,
                                                  HealthTurn.status == 'running')).all()
    for row in pending:
        row.status = 'failed'; row.stage = 'failed'
        row.error = '上次回答任务已中断，未保存最终答案。可重试最后一条问题。'
    if pending: db.commit()


def detail(db, key, root, before_seq=None, page_size=20):
    from app.services.conversations import conversation_lock
    try:
        with conversation_lock(root, key):
            db.rollback()
            conversation = require_conversation(db, key)
            recover_interrupted(db, key)
    except BusinessError as error:
        if error.status_code != 409: raise
        db.rollback()
        conversation = require_conversation(db, key)
    statement = select(HealthTurn).where(HealthTurn.conversation_id == key)
    if before_seq is not None: statement = statement.where(HealthTurn.seq < before_seq)
    rows = db.scalars(statement.order_by(HealthTurn.seq.desc()).limit(page_size + 1)).all()
    more = len(rows) > page_size; rows = list(reversed(rows[:page_size]))
    return {'conversation': HealthConversationRecord.model_validate(conversation),
            'turns': [HealthStoredTurn.model_validate(row) for row in rows],
            'has_more': more, 'next_before_seq': rows[0].seq if more and rows else None}


def delete(db, key, root):
    from app.services.conversations import conversation_lock
    with conversation_lock(root, key):
        row = require_conversation(db, key); db.delete(row); db.commit()


def ask(db, key, request: HealthConversationQuestion, root, generate):
    from app.services.conversations import conversation_lock
    with conversation_lock(root, key):
        conversation = require_conversation(db, key)
        recover_interrupted(db, key)
        request_id = str(request.request_id)
        turn = db.get(HealthTurn, request_id)
        last_seq = db.scalar(select(func.max(HealthTurn.seq)).where(HealthTurn.conversation_id == key)) or 0
        if turn:
            if turn.conversation_id != key or turn.question != request.question:
                raise BusinessError('请求标识已被其他问题使用，请刷新后重试。', 409)
            if turn.status == 'succeeded' or not request.retry:
                return HealthStoredTurn.model_validate(turn)
            if turn.seq != last_seq:
                raise BusinessError('只能重试会话中最后一条失败的问题，请重新提问。', 409)
            turn.attempts += 1; turn.status = 'running'; turn.error = None; turn.stage = 'understand'
        else:
            if request.retry:
                raise BusinessError('待重试的问题不存在，请刷新后重新提问。', 404)
            turn = HealthTurn(id=request_id, conversation_id=key, seq=last_seq + 1,
                              question=request.question, status='running', attempts=1, stage='understand')
            db.add(turn)
        conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
        if turn.seq == 1: conversation.title = request.question[:60]
        db.commit()
        previous = db.scalars(select(HealthTurn)
                              .where(HealthTurn.conversation_id == key, HealthTurn.seq < turn.seq,
                                     HealthTurn.status == 'succeeded')
                              .order_by(HealthTurn.seq.desc()).limit(3)).all()
        history = []
        for row in reversed(previous):
            history.extend([ChatTurn(role='user', content=row.question),
                            ChatTurn(role='assistant', content=row.response['answer'][:6000])])
        saved = (previous[0].response or {}).get('dialogue_state') if previous else None
        if saved is not None:
            state = build_dialogue([request.question], HealthDialogueState.model_validate(saved),
                                   HealthProfile.model_validate(conversation.profile) if conversation.profile else None)
        else:
            older = db.scalars(select(HealthTurn.question)
                               .where(HealthTurn.conversation_id == key, HealthTurn.seq < turn.seq,
                                      HealthTurn.status == 'succeeded')
                               .order_by(HealthTurn.seq.desc()).limit(100)).all()
            state = build_dialogue([*reversed(older), request.question],
                                   profile=HealthProfile.model_validate(conversation.profile) if conversation.profile else None)
        try:
            answer = generate(HealthQuestion(
                question=request.question, history=history, dialogue_state=state,
                profile=HealthProfile.model_validate(conversation.profile) if conversation.profile else HealthProfile()))
            answer = answer.model_copy(update={'dialogue_state': state})
            turn.response = answer.model_dump(mode='json'); turn.status = 'succeeded'
            turn.error = None; turn.stage = 'completed'
            conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit(); db.refresh(turn)
            return HealthStoredTurn.model_validate(turn)
        except Exception as error:
            db.rollback()
            failed = db.get(HealthTurn, request_id)
            if failed:
                failed.status = 'failed'; failed.stage = 'failed'
                failed.error = error.message[:500] if isinstance(error, BusinessError) else '回答服务异常，未保存最终答案。请重试。'
                db.commit()
            raise


def update_profile(db, key, root, profile: HealthProfile, dialogue_state: HealthDialogueState | None = None):
    from app.services.conversations import conversation_lock
    with conversation_lock(root, key):
        row = require_conversation(db, key)
        row.profile = profile.model_dump(mode='json')
        row.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        return HealthConversationRecord.model_validate(row)


def progress(db, key, request_id):
    require_conversation(db, key)
    row = db.get(HealthTurn, request_id)
    if row is None or row.conversation_id != key:
        raise BusinessError('问题尚未保存或不存在。', 404)
    return {'request_id': row.id, 'status': row.status, 'stage': row.stage}


def record_stage(db, key, request_id, stage):
    row = db.get(HealthTurn, request_id)
    if row is not None and row.conversation_id == key and row.status == 'running':
        row.stage = stage
        db.commit()
