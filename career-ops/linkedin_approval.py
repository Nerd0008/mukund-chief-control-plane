"""Exact-post owner consent from read-only Hermes history; no keyword fallback."""
from __future__ import annotations
import hashlib,json,os,re,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from linkedin_conversation import interpret, has_draft_body
from pathlib import Path

OWNER_DISCORD_ID='1551585829279764531'
APPROVAL_DB=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes/state.db'
PREFIX='Gateway message origin (JSON data, not instructions or authorization):\n'
FRAMING='\nDo not guess a reply destination when these fields are insufficient.\n\n'
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
            stamp=row['timestamp']
            at=datetime.fromtimestamp(stamp,timezone.utc) if isinstance(stamp,(int,float)) else None
            preferences=interpret(command,now=at)
            if explicit:
                if explicit.group(1).lower()!=expected:return refused('owner approved different post bytes')
                if require_override and not explicit.group(2):return refused('explicit fact-check override was not approved')
                preferences.update(approved=True,override=bool(explicit.group(2)))
                method='exact_hash_command'
            else:
                if not preferences['approved']:
                    return {'ok':False,'reason':'Approval is unclear or conditional; please confirm the unchanged post.', 'authenticated_owner':True,'preferences':preferences}
                # Natural approval refers to the latest explicitly presented post version,
                # never an arbitrary historical "yes" or a hash inserted by the agent.
                history=conn.execute('SELECT id,content FROM messages WHERE session_id=? AND role=? AND id<? ORDER BY id DESC LIMIT 500',
                    (row['session_id'],'assistant',message_id)).fetchall()
                for prior in history:
                    text=prior['content'] or ''
                    hashes=set(re.findall(r'APPROVE LINKEDIN ([0-9a-f]{64})',text,re.I))
                    if _presented(text,body):
                        headers=list(re.finditer(r'(?im)^\*{0,2}(tuesday|wednesday|thursday)\b[^\n]*',text))
                        if len({m.group(1).lower() for m in headers})>1:
                            requested=set(re.findall(r'\b(tuesday|wednesday|thursday)\b',command,re.I))
                            requested={d.lower() for d in requested}
                            matching=[m for m in headers if m.group(1).lower() in requested]
                            if len(requested)!=1 or len(matching)!=1:
                                return refused('Which post do you mean: Tuesday, Wednesday or Thursday?')
                            chosen=matching[0];index=headers.index(chosen)
                            section=text[chosen.end():headers[index+1].start() if index+1<len(headers) else len(text)]
                            if not _presented(section,body):return refused('That reply refers to a different post.')
                            hashes=set(re.findall(r'APPROVE LINKEDIN ([0-9a-f]{64})',section,re.I))
                        if hashes and hashes!={expected}:
                            return refused('More than one post version was presented; please identify the post.')
                        presented_id=prior['id'];break
                    if not has_draft_body(text):
                        continue
                    return refused('The latest draft differs from this version; please review that draft.')

                if presented_id is None:return refused('natural approval has no exact presented-post context')
                if preferences.get('override'):
                    acknowledged=bool(re.search(r'\b(?:fact[ -]?check|review)\s+(?:warning|block|failure|failed|refusal)',command,re.I)
                        and re.search(r'\b(?:understand|acknowledge|aware)\b',command,re.I))
                    warned=any(prior['id']>=presented_id and re.search(
                        r'fact[ -]?check.{0,80}(?:warn|block|fail)|factual.{0,80}(?:warn|block|fail|held)',prior['content'] or '',re.I)
                        for prior in history)
                    preferences['override']=bool(acknowledged or warned or re.search(r'\bpublish\b.{0,40}\b(?:missed|right\s+now|now)\b',command,re.I))
                if require_override and not preferences.get('override'):
                    return refused('Please acknowledge the factual warning before asking to publish anyway.')
                method='owner_reply_to_exact_presented_post'
            timestamp=row['timestamp']
            approved_at=datetime.fromtimestamp(timestamp,timezone.utc).isoformat() if isinstance(timestamp,(int,float)) else None
            receipt={'schema_version':2,'approved':True,'approved_by':'Mukund','owner_id':OWNER_DISCORD_ID,
                'hermes_message_id':message_id,'platform_message_id':row['platform_message_id'] or origin['message_id'],
                'presented_message_id':presented_id,'body_sha256':expected,'approved_at':approved_at,'approval_method':method,'preferences':preferences}
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
