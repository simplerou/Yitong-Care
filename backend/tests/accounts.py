"""Provision already-approved staff for legacy business tests, not registration tests."""
from sqlalchemy import select
from app.models.auth import Account

def activate(api,phone):
    with api.app.state.test_factory() as db:
        account=db.scalar(select(Account).where(Account.phone==phone))
        account.status='active'
        db.commit()
