"""Local, private failure evidence; never includes keys, account identity or raw patient records."""
import json
import logging
import os
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from app.core.config import BACKEND_DIR

def get_menu_diagnostic_dir():return BACKEND_DIR/'var'/'diagnostics'/'menu_planner'

def write_failure(root:Path,packet:dict):
    try:
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        key='menu-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:10]+'.json'
        with open(root/key,'x',encoding='utf-8',opener=lambda name,flags:os.open(name,flags,0o600)) as handle:
            json.dump({'schema_version':1,**packet},handle,ensure_ascii=False,indent=2)
        return key
    except OSError as error:
        logging.getLogger(__name__).warning('Menu diagnostic could not be saved: %s',type(error).__name__)
        return None
