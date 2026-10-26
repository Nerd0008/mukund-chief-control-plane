"""Sanitized provider failure metadata and native-controller circuit evidence.

No prompts, headers, response bodies, keys or exception strings enter the store.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import email.utils
import math
import os
import sqlite3
import time
from router_brain import RouterDecisionError

DB_PATH = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'hermes/runtime/router-brain/native-health.sqlite3'


def unwrap(error):
    seen = set()
    for _ in range(32):
        if id(error) in seen:
            break
        seen.add(id(error))
        original = getattr(error, 'original', None)
        if not isinstance(original, BaseException):
            break
        error = original
    return error


def retry_after(error, now=None):
    error = unwrap(error)
    headers = getattr(getattr(error, 'response', None), 'headers', None)
    value = None
    if headers is not None:
        value = headers.get('retry-after') or headers.get('Retry-After')
    if value is None:
        body = getattr(error, 'body', None)
        if isinstance(body, dict):
            nested = body.get('error')
            body = nested if isinstance(nested, dict) else body
            value = body.get('retry_after')
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = email.utils.parsedate_to_datetime(value).timestamp() - (time.time() if now is None else now)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return None
    return min(600.0, seconds) if math.isfinite(seconds) and seconds > 0 else None


def metadata(error):
    error = unwrap(error)
    status = getattr(error, 'status_code', None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    body = getattr(error, 'body', None)
    body = body if isinstance(body, dict) else {}
    body = body['error'] if isinstance(body.get('error'), dict) else body
    code = body.get('code') or body.get('reason')
    if isinstance(error, RouterDecisionError):
        import re
        text = str(error)
        category = text if re.fullmatch(r'[a-z_]{1,80}', text) else 'workflow_execution_failed'
    elif status in (400, 413) and code in ('context_length_exceeded', 'context_window_exceeded', 'request_too_large'):
        category = 'provider_context_limit'
    elif status == 429 and code in ('insufficient_quota', 'quota_exhausted', 'billing_limit_exceeded'):
        category = 'provider_quota_exhausted'
    elif status == 404 and str(body.get('message') or '').startswith('This model is no longer free.'):
        category = 'provider_model_withdrawn'
    elif status == 404 and code == 'insufficient_credits_for_paid_model':
        category = 'provider_model_billing_blocked'
    elif status is not None:
        category = {400:'provider_bad_request',401:'provider_auth_failed',402:'provider_billing_blocked',
            403:'provider_permission_denied',404:'provider_model_not_found',408:'provider_timeout',
            409:'provider_conflict',413:'provider_context_limit',422:'provider_bad_request',
            429:'provider_rate_limit'}.get(status, 'provider_unavailable' if status >= 500 else 'workflow_execution_failed')
    elif isinstance(error, TimeoutError) or type(error).__name__ in ('APITimeoutError', 'ReadTimeout', 'ConnectTimeout'):
        category = 'provider_timeout'
    elif type(error).__name__ in ('APIConnectionError','ConnectError','ReadError','RemoteProtocolError'):
        category = 'provider_connection_error'
    elif isinstance(error, __import__('asyncio').CancelledError):
        category = 'workflow_cancelled'
    else:
        category = 'workflow_execution_failed'
    scope = ('provider' if category in ('provider_unavailable','provider_connection_error',
              'provider_billing_blocked','provider_quota_exhausted') else
             'model' if category in ('provider_rate_limit','provider_model_not_found','provider_model_withdrawn','provider_model_billing_blocked','provider_timeout') else 'request')
    return {'error':category, 'http_status':status, 'retry_after_seconds':retry_after(error), 'failure_scope':scope}


@contextmanager
def database():
    con = None
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB_PATH, timeout=2)
        con.row_factory = sqlite3.Row
        con.execute('''CREATE TABLE IF NOT EXISTS health (
            provider TEXT NOT NULL, model TEXT NOT NULL, cooldown REAL NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
            last_failure REAL NOT NULL DEFAULT 0, last_code TEXT,
            latency REAL, PRIMARY KEY(provider,model))''')
        con.execute('''CREATE TABLE IF NOT EXISTS qualification (
            provider TEXT NOT NULL, model TEXT NOT NULL, policy_sha TEXT NOT NULL,
            observed_at REAL NOT NULL, metadata TEXT NOT NULL, PRIMARY KEY(provider,model))''')
        yield con
        con.commit()
    except (sqlite3.Error, OSError):
        raise RouterDecisionError('router_health_unavailable') from None
    finally:
        if con is not None:
            con.close()


def snapshot(provider, model, now=None):
    now = time.time() if now is None else now
    with database() as con:
        rows = con.execute('SELECT * FROM health WHERE provider=? AND model IN (?,?)',
                           (provider, model, '*')).fetchall()
    exact = next((dict(r) for r in rows if r['model'] == model), {})
    cooldown = max((r['cooldown'] for r in rows), default=0)
    last = max(rows, key=lambda r:r['last_failure'], default=None)
    return {'available':cooldown <= now, 'cooldown_until':cooldown,
            'recent_failures':exact.get('failures',0), 'observed_successes':exact.get('successes',0),
            'latency_seconds':exact.get('latency'),
            'last_failure_at':last['last_failure'] if last else 0,
            'last_failure_code':last['last_code'] if last else None}


def record_failure(route, error):
    detail = metadata(error)
    if not detail['error'].startswith('provider_'):
        return detail
    provider, model = route.get('selected_provider'), route.get('selected_model')
    if not provider or not model:
        return detail
    # Auth/permission/request errors retain the host's existing auth/compression
    # recovery. Do not rotate models to bypass a permission restriction.
    category = detail['error']
    duration = max(30, detail['retry_after_seconds'] or 0) if detail['failure_scope'] != 'request' else 0
    if category in ('provider_model_not_found','provider_model_withdrawn','provider_model_billing_blocked','provider_billing_blocked','provider_quota_exhausted'):
        duration = max(duration, 600)
    now = time.time()
    keys = [model] + (['*'] if detail['failure_scope'] == 'provider' else [])
    with database() as con:
        for key in keys:
            con.execute('''INSERT INTO health(provider,model,cooldown,failures,last_failure,last_code)
                VALUES(?,?,?,1,?,?) ON CONFLICT(provider,model) DO UPDATE SET
                cooldown=MAX(health.cooldown,excluded.cooldown),failures=health.failures+1,
                last_failure=excluded.last_failure,last_code=excluded.last_code''',
                (provider,key,now+duration if duration else 0,now,category))
    if category=='provider_model_withdrawn':
        # This is an explicit public endpoint withdrawal, not a guessed outage.
        # Requalification is the only way to clear it if the route returns.
        import json
        with database() as con:
            row=con.execute('SELECT metadata FROM qualification WHERE provider=? AND model=?',(provider,model)).fetchone()
            if row:
                try:proof=json.loads(row['metadata'])
                except (TypeError,ValueError):proof={}
                proof['withdrawn']=True
                con.execute('UPDATE qualification SET metadata=? WHERE provider=? AND model=?',(json.dumps(proof),provider,model))
            else:
                con.execute('INSERT INTO qualification VALUES(?,?,?,?,?)',(provider,model,'',now,json.dumps({'withdrawn':True})))
    return detail


def record_success(route, elapsed, started_at):
    provider, model = route.get('selected_provider'), route.get('selected_model')
    if not provider or not model:
        return
    with database() as con:
        con.execute('''INSERT INTO health(provider,model,successes,latency) VALUES(?,?,1,?)
            ON CONFLICT(provider,model) DO UPDATE SET successes=health.successes+1,
            latency=CASE WHEN health.latency IS NULL THEN excluded.latency
                         ELSE health.latency*0.8+excluded.latency*0.2 END,
            failures=CASE WHEN health.last_failure<? THEN 0 ELSE health.failures END,
            cooldown=CASE WHEN health.last_failure<? THEN 0 ELSE health.cooldown END''',
            (provider,model,max(0,elapsed),started_at,started_at))
