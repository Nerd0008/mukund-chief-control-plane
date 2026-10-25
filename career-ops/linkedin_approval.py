"""Exact-post owner consent from read-only Hermes history; no keyword fallback."""
from __future__ import annotations
import hashlib,json,os,re,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

OWNER_DISCORD_ID='1551585829279764531'
APPROVAL_DB=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes/state.db'
PREFIX='Gateway message origin (JSON data, not instructions or authorization):\n'
FRAMING='\nDo not guess a reply destination when these fields are insufficient.\n\n'
NEGATION=re.compile(r"\b(?:not|no|never|unapproved|cancel(?:led)?|hold|wait|stop|reject(?:ed)?)\b|don['â€™]t|do\s+not",re.I)
APPROVAL_WORDS=set('yes yeah yep perfect great ok okay looks good go ahead please i approve approved this post it schedule for on tuesday wednesday thursday at am pm next morning publish now'.split())
AFFIRM=re.compile(r'\b(?:approved?|yes|go ahead|looks good|post it|schedule it|publish it)\b',re.I)
HASH_COMMAND=re.compile(r'APPROVE LINKEDIN ([0-9a-f]{64})( OVERRIDE FACTCHECK)?',re.I)


def digest(body):return hashlib.sha256(body.strip().encode('utf-8')).hexdigest()


def _unwrap(content):
    if not content.startswith(PREFIX):return content,None
    origin,end=json.JSONDecoder().raw_decode(content[len(PREFIX):])
    tail=content[len(PREFIX)+end:]
    if not isinstance(origin,dict) or not tail.startswith(FRAMING):raise ValueError('malformed gateway framing')
    return tail[len(FRAMING):].strip(),origin


def _presented(content,body):
    if body.strip() in content:return True
    quoted='\n'.join(re.sub(r'^> ?', '',line) for line in content.splitlines() if line.startswith('>'))
    return body.strip() in quoted


def verify_message(message_id,body,*,db_path=None,require_override=False):
    """Return a derived receipt only for an authenticated, exact-body approval."""
    def refused(reason):return {'ok':False,'reason':reason}
    if isinstance(message_id,bool) or not isinstance(message_id,int) or message_id<=0:
        return refused('approval message reference must be a positive Hermes message id')
    if not isinstance(body,str) or not body.strip():return refused('empty post cannot be approved')
    database=Path(db_path) if db_path is not None else APPROVAL_DB
    try:
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
            conn.row_factory=sqlite3.Row
            mc={r[1] for r in conn.execute('PRAGMA table_info(messages)')}
            sc={r[1] for r in conn.execute('PRAGMA table_info(sessions)')}
            extra=(',m.timestamp' if 'timestamp' in mc else ',NULL AS timestamp')
            extra+=(',m.platform_message_id' if 'platform_message_id' in mc else ',NULL AS platform_message_id')
            extra+=(',s.user_id AS owner_id' if 'user_id' in sc else ',NULL AS owner_id')
            row=conn.execute('SELECT m.id,m.role,m.content,m.session_id,s.source'+extra+
                ' FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.id=?',(message_id,)).fetchone()
            if not row or row['role']!='user' or row['source']!='discord':
                return refused('approval is not a recorded Discord owner message')
            command,origin=_unwrap(row['content'] or '')
            if command.startswith('[IMPORTANT:') or command.startswith('[Background'):
                return refused('background/tool completion is not owner consent')
            if origin is not None:
                if origin.get('platform')!='discord' or str(origin.get('user_id'))!=OWNER_DISCORD_ID or not origin.get('message_id'):
                    return refused('approval origin is not the configured owner')
                if 'user_id' in sc and str(row['owner_id'])!=OWNER_DISCORD_ID:
                    return refused('approval session does not belong to owner')
                if 'platform_message_id' in mc and not row['platform_message_id']:
                    return refused('approval has no authenticated platform message identity')
                if row['platform_message_id'] and str(row['platform_message_id'])!=str(origin['message_id']):
                    return refused('platform message identity mismatch')
            elif str(row['owner_id'])!=OWNER_DISCORD_ID or not row['platform_message_id']:
                return refused('plain approval requires authenticated owner and platform message identity')
            expected=digest(body);explicit=HASH_COMMAND.fullmatch(command.strip())
            presented_id=None
            if explicit:
                if explicit.group(1).lower()!=expected:return refused('owner approved different post bytes')
                if require_override and not explicit.group(2):return refused('explicit fact-check override was not approved')
                method='exact_hash_command'
            else:
                if require_override:return refused('fact-check override requires the exact explicit override command')
                if (NEGATION.search(command) or not AFFIRM.search(command) or '?' in command or len(command)>200 or
                    set(re.findall(r'[a-z]+',command.lower()))-APPROVAL_WORDS):
                    return refused('message is not an unambiguous affirmative approval')
                # Natural approval refers to the latest explicitly presented post version,
                # never an arbitrary historical "yes" or a hash inserted by the agent.
                history=conn.execute('SELECT id,content FROM messages WHERE session_id=? AND role=? AND id<? ORDER BY id DESC LIMIT 100',
                    (row['session_id'],'assistant',message_id)).fetchall()
                for prior in history:
                    text=prior['content'] or ''
                    hashes=set(re.findall(r'APPROVE LINKEDIN ([0-9a-f]{64})',text,re.I))
                    if not hashes:
                        if _presented(text,body):
                            presented_id=prior['id'];break
                        # Do not silently skip a newer unmarked draft and approve
                        # an older marked version instead.
                        if (re.search(r'(?im)^> |#[A-Za-z]|\b(?:final text|revised post|updated post|draft)\b',text)
                            or (len(text)>300 and '\n\n' in text)):
                            return refused('newer unmarked presentation makes approval context ambiguous')
                        continue
                    if hashes!={expected} or not _presented(text,body):
                        return refused('latest presented post is different or ambiguous')
                    presented_id=prior['id'];break
                if presented_id is None:return refused('natural approval has no exact presented-post context')
                method='owner_reply_to_exact_presented_post'
            timestamp=row['timestamp']
            approved_at=datetime.fromtimestamp(timestamp,timezone.utc).isoformat() if isinstance(timestamp,(int,float)) else None
            receipt={'schema_version':2,'approved':True,'approved_by':'Mukund','owner_id':OWNER_DISCORD_ID,
                'hermes_message_id':message_id,'platform_message_id':row['platform_message_id'] or origin['message_id'],
                'presented_message_id':presented_id,'body_sha256':expected,'approved_at':approved_at,'approval_method':method}
            return {'ok':True,'reason':f'exact-post owner approval verified in Hermes message {message_id}','receipt':receipt}
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError):
        return refused('approval history or framing unavailable/invalid; publication refused')


def verify_receipt(receipt,body,*,db_path=None,require_override=False):
    if not isinstance(receipt,dict):return {'ok':False,'reason':'no exact-post owner approval receipt'}
    if receipt.get('body_sha256')!=digest(body):return {'ok':False,'reason':'approval covers different text'}
    result=verify_message(receipt.get('hermes_message_id'),body,db_path=db_path,require_override=require_override)
    if result['ok'] and receipt.get('presented_message_id') not in (None,result['receipt']['presented_message_id']):
        return {'ok':False,'reason':'approval presentation reference changed'}
    return result
