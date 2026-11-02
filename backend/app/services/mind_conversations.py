"""Mind conversation writer. Snapshots keep signals, screening and crisis state."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.core.exceptions import BusinessError
from app.services.ownership import visible_to_account, owner_filter
from app.models.mind_conversation import MindConversation, MindTurn
from app.schemas.chat import ChatTurn
from app.schemas.mind import MindDialogueState, MindProfile, MindQuestion
from app.schemas.mind_conversation import MindConversationQuestion, MindConversationRecord, MindStoredTurn
from app.services.conversations import conversation_lock
from app.services.mind.dialogue_state import build_dialogue


def require_conversation(db, key):
    row = db.get(MindConversation, key)
    if row is None or not visible_to_account(db, row): raise BusinessError('会话不存在或已删除。', 404)
    return row


def _profile(row) -> MindProfile:
    return MindProfile.model_validate(row.profile) if row.profile else MindProfile()


def create(db, profile: MindProfile | None = None):
    row = MindConversation(owner_id=db.info.get('account_id'), id=str(uuid4()), title='新心灵陪伴',
                             profile=profile.model_dump(mode='json') if profile else None)
    db.add(row); db.commit(); db.refresh(row)
    return MindConversationRecord.model_validate(row)


def listing(db, page, page_size):
    total = db.scalar(select(func.count()).select_from(MindConversation).where(owner_filter(db, MindConversation))) or 0
    rows = db.scalars(select(MindConversation).where(owner_filter(db, MindConversation))
                      .order_by(MindConversation.updated_at.desc(), MindConversation.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': [MindConversationRecord.model_validate(row) for row in rows],
            'total': total, 'page': page, 'page_size': page_size}


def recover_interrupted(db, key):
    pending = db.scalars(select(MindTurn).where(MindTurn.conversation_id == key,
                                                  MindTurn.status == 'running')).all()
    for row in pending:
        row.status = 'failed'; row.stage = 'failed'
        row.error = '上次回答任务已中断，未保存最终答案。可重试最后一条问题。'
    if pending: db.commit()


def detail(db, key, root, before_seq=None, page_size=20):
    try:
        with conversation_lock(root, key):
            db.rollback()
            conversation = require_conversation(db, key)
            recover_interrupted(db, key)
    except BusinessError as error:
        if error.status_code != 409: raise
        db.rollback()
        conversation = require_conversation(db, key)
    statement = select(MindTurn).where(MindTurn.conversation_id == key)
    if before_seq is not None: statement = statement.where(MindTurn.seq < before_seq)
    rows = db.scalars(statement.order_by(MindTurn.seq.desc()).limit(page_size + 1)).all()
    more = len(rows) > page_size; rows = list(reversed(rows[:page_size]))
    return {'conversation': MindConversationRecord.model_validate(conversation),
            'turns': [MindStoredTurn.model_validate(row) for row in rows],
            'has_more': more, 'next_before_seq': rows[0].seq if more and rows else None}


def delete(db, key, root):
    with conversation_lock(root, key):
        row = require_conversation(db, key); db.delete(row); db.commit()


def ask(db, key, request: MindConversationQuestion, root, generate):
    with conversation_lock(root, key):
        conversation = require_conversation(db, key)
        recover_interrupted(db, key)
        request_id = str(request.request_id)
        turn = db.get(MindTurn, request_id)
        last_seq = db.scalar(select(func.max(MindTurn.seq)).where(MindTurn.conversation_id == key)) or 0
        if turn:
            if turn.conversation_id != key or turn.question != request.question:
                raise BusinessError('请求标识已被其他问题使用，请刷新后重试。', 409)
            if turn.status == 'succeeded' or not request.retry:
                return MindStoredTurn.model_validate(turn)
            if turn.seq != last_seq:
                raise BusinessError('只能重试会话中最后一条失败的问题，请重新提问。', 409)
            turn.attempts += 1; turn.status = 'running'; turn.error = None; turn.stage = 'understand'
        else:
            if request.retry:
                raise BusinessError('待重试的问题不存在，请刷新后重新提问。', 404)
            turn = MindTurn(id=request_id, conversation_id=key, seq=last_seq + 1,
                              question=request.question, status='running', attempts=1, stage='understand')
            db.add(turn)
        conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
        if turn.seq == 1: conversation.title = request.question[:60]
        db.commit()
        previous = db.scalars(select(MindTurn)
                              .where(MindTurn.conversation_id == key, MindTurn.seq < turn.seq,
                                     MindTurn.status == 'succeeded')
                              .order_by(MindTurn.seq.desc()).limit(3)).all()
        history = []
        for row in reversed(previous):
            history.extend([ChatTurn(role='user', content=row.question),
                            ChatTurn(role='assistant', content=row.response['answer'][:6000])])
        profile = _profile(conversation)
        saved = (previous[0].response or {}).get('dialogue_state') if previous else None
        if saved is not None:
            state = build_dialogue([request.question], MindDialogueState.model_validate(saved), profile)
        else:
            older = db.scalars(select(MindTurn.question)
                               .where(MindTurn.conversation_id == key, MindTurn.seq < turn.seq,
                                      MindTurn.status == 'succeeded')
                               .order_by(MindTurn.seq.desc()).limit(100)).all()
            state = build_dialogue([*reversed(older), request.question], profile=profile)
        try:
            answer = generate(MindQuestion(question=request.question, history=history,
                                             dialogue_state=state, profile=profile))
            answer = answer.model_copy(update={'dialogue_state': state})
            turn.response = answer.model_dump(mode='json'); turn.status = 'succeeded'
            turn.error = None; turn.stage = 'completed'
            conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit(); db.refresh(turn)
            return MindStoredTurn.model_validate(turn)
        except Exception as error:
            db.rollback()
            failed = db.get(MindTurn, request_id)
            if failed:
                failed.status = 'failed'; failed.stage = 'failed'
                failed.error = error.message[:500] if isinstance(error, BusinessError) else '回答服务异常，未保存最终答案。请重试。'
                db.commit()
            raise


def update_profile(db, key, root, profile: MindProfile, dialogue_state: MindDialogueState | None = None):
    with conversation_lock(root, key):
        row = require_conversation(db, key)
        row.profile = profile.model_dump(mode='json')
        row.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        return MindConversationRecord.model_validate(row)


def progress(db, key, request_id):
    require_conversation(db, key)
    row = db.get(MindTurn, request_id)
    if row is None or row.conversation_id != key:
        raise BusinessError('问题尚未保存或不存在。', 404)
    return {'request_id': row.id, 'status': row.status, 'stage': row.stage}


def record_stage(db, key, request_id, stage):
    row = db.get(MindTurn, request_id)
    if row is not None and row.conversation_id == key and row.status == 'running':
        row.stage = stage
        db.commit()
