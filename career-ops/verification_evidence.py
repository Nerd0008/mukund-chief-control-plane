"""Private replay inputs for a vacancy decision. Never includes credentials or CVs."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import uuid

ROOT = Path(__file__).resolve().parent.parent / 'runtime/career-ops/verification-evidence'


def save_evidence(record, jd):
    url = str(record.get('url') or '')
    text = str(jd.get('text') or record.get('jd_text') or '')
    payload = {'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
               'candidate':{k:record.get(k) for k in ('company','title','location','country','url','resolved_url')},
               'jd':{k:jd.get(k) for k in ('status','error','fetch_state','vacancy_status','deadline_info',
                                           'posting_identity','discovered_posting','resolved_url','validation_source')},
               'text':text,'text_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
    ROOT.mkdir(parents=True,exist_ok=True)
    path = ROOT / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' +
                   hashlib.sha256(url.encode()).hexdigest()[:12] + '-' + uuid.uuid4().hex[:8] + '.json')
    path.write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    return str(path)
