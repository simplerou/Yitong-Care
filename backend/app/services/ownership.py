from sqlalchemy import true

def visible_to_account(db, row):
    # CLI diagnostics and offline evaluations have no request principal.
    return 'account_id' not in db.info or row.owner_id == db.info['account_id']

def owner_filter(db, model):
    return model.owner_id == db.info['account_id'] if 'account_id' in db.info else true()
