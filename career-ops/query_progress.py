"""Private, expiring query progress. Never authorizes a write or a worker."""
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

MAX_AGE = 6 * 3600


def signature(prompt, model):
    return hashlib.sha256(json.dumps([prompt, model], ensure_ascii=True).encode()).hexdigest()


def load(path, key, queries):
    if path is None:
        return {}
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
        age = time.time() - doc['created_at']
        if doc['signature'] != key or not 0 <= age <= MAX_AGE:
            return {}
        records = doc['records']
        if not isinstance(records, dict):
            return {}
        return {q: r for q, r in records.items() if q in queries and isinstance(r, dict)
                and r.get('web_search_observed') is True and not r.get('error')
                and isinstance(r.get('results'), list)
                and isinstance(r.get('observed_at'), (int, float))
                and 0 <= time.time() - r['observed_at'] <= MAX_AGE}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save(path, key, records):
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The oldest observation controls expiry; retries never refresh stale evidence.
    created = min((r['observed_at'] for r in records.values()), default=time.time())
    tmp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps({'signature': key, 'created_at': created,
                                  'records': records}, ensure_ascii=True), encoding='utf-8')
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
