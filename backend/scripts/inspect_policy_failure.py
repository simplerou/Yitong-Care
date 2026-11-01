"""Export an existing failed chat snapshot. No model/search/retrieval calls."""
import argparse
import json
import os
import sys
from uuid import uuid4
from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import BACKEND_DIR
from app.db.session import SessionLocal
from app.models.conversation import PolicyTurn, PolicyConversation


def main(argv=None):
    parser=argparse.ArgumentParser(description='只读取已保存的网页失败问答，不调用模型')
    parser.add_argument('--contains',default='9999',help='匹配原问题；默认9999')
    parser.add_argument('--latest-conversation',action='store_true',help='导出最近活动会话的最近100轮问答，不限失败类型')
    parser.add_argument('--latest-turn',action='store_true',help='导出最近一次已保存回答及完整联网诊断，不限失败原因')
    args=parser.parse_args(argv)
    if args.latest_turn and args.latest_conversation: parser.error('请选择一种导出模式')
    try:
        with SessionLocal() as db:
            if args.latest_conversation:
                conversation=db.scalar(select(PolicyConversation).order_by(PolicyConversation.updated_at.desc(),PolicyConversation.id.desc()).limit(1))
                if conversation is None:
                    print('尚无会话；未调用模型。');return 1
                rows=list(reversed(db.scalars(select(PolicyTurn).where(PolicyTurn.conversation_id==conversation.id).order_by(PolicyTurn.seq.desc()).limit(100)).all()))
                if not rows:
                    print('最近会话尚无问答；未调用模型。');return 1
                turn=rows[-1]
                payload={'mode':'latest_conversation_read_only','conversation_id':conversation.id,'title':conversation.title,
                    'starts_at_seq':rows[0].seq,'earlier_turns_omitted':rows[0].seq>1,
                    'turns':[{'seq':row.seq,'created_at':str(row.created_at),'question':row.question,'status':row.status,
                        'answer':(row.response or {}).get('answer'),'reason':(row.response or {}).get('reason'),
                        'dialogue_state':(row.response or {}).get('dialogue_state'),'answer_checks':(row.response or {}).get('answer_checks'),'steps':(row.response or {}).get('steps')}
                        for row in rows]}
            else:
                statement=select(PolicyTurn).where(PolicyTurn.response.is_not(None))
                if not args.latest_turn: statement=statement.where(PolicyTurn.question.contains(args.contains,autoescape=True))
                rows=db.scalars(statement.order_by(PolicyTurn.created_at.desc()).limit(1 if args.latest_turn else 50)).all()
                turn=(rows[0] if rows else None) if args.latest_turn else next((row for row in rows if (row.response or {}).get('reason')=='unsupported_numeric_expansion'),None)
                if turn is None:
                    print('未找到匹配的已保存回答；未调用模型。');return 1
                previous=db.scalars(select(PolicyTurn).where(PolicyTurn.conversation_id==turn.conversation_id,PolicyTurn.seq<turn.seq,PolicyTurn.status=='succeeded').order_by(PolicyTurn.seq.desc()).limit(3)).all()
                payload={'mode':'latest_saved_turn_no_model_calls' if args.latest_turn else 'saved_failed_chat_snapshot_no_model_calls','request_id':turn.id,
                    'created_at':str(turn.created_at),'question':turn.question,'response':turn.response,
                    'preceding_turns':[{'question':row.question,'answer':(row.response or {}).get('answer'),'created_at':str(row.created_at)} for row in reversed(previous)]}
    except SQLAlchemyError as error:
        print('无法读取MySQL：'+type(error).__name__+'；未输出连接详情，未调用模型。');return 1
    directory=BACKEND_DIR/'var'/'diagnostics'
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/(datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+turn.id+'-'+uuid4().hex[:8]+'.json')
    # Diagnostic includes conversation content and public source snapshots, never credentials.
    with open(path,'x',encoding='utf-8',opener=lambda name,flags:os.open(name,flags,0o600)) as handle:
        json.dump(payload,handle,ensure_ascii=False,indent=2)
    print('保存时间：'+str(turn.created_at))
    if args.latest_conversation:
        print('导出问答轮数：'+str(len(payload['turns'])))
    else:
        if args.latest_turn:
            print('原问题：'+turn.question)
            print('联网状态：'+str((turn.response or {}).get('web_status')))
            print('联网诊断：'+json.dumps((turn.response or {}).get('web_diagnostics'),ensure_ascii=False))
        print('具体检查：'+json.dumps((turn.response or {}).get('answer_checks'),ensure_ascii=False))
    print('诊断文件：'+str(path))
    print('只读取历史记录；没有生成新回答或调用模型。')
    return 0


if __name__=='__main__': sys.exit(main())
