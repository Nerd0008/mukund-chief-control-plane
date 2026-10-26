"""Compatible, locally qualified model offers over the existing native client.

Never swaps credentials/transports, drops parameters or trusts 429 alternates.
Qualification is explicit; no network request is made while assembling offers.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json,time
from router_brain import RouterDecisionError
from workflow_health import database,snapshot
POLICY_PATH=Path(__file__).with_name('native_controller_policy.json')


def policy():
    try:
        raw=POLICY_PATH.read_bytes(); value=json.loads(raw)
        assert value['version']==1 and value['provider']=='nous' and value['api_mode']=='chat_completions'
        assert 0<value['qualification_ttl_seconds']<=604800
        rows=value['models'];assert rows and len({r['model'] for r in rows})==len(rows)
        for row in rows:
            assert isinstance(row['model'],str) and type(row['context_length']) is int and row['context_length']>0
            assert isinstance(row['parameters'],list) and isinstance(row['input_modalities'],list)
        return value,hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError,KeyError,AssertionError,TypeError):
        raise RouterDecisionError('controller_policy_invalid') from None


def qualify(model,metadata):
    config,sha=policy()
    assert model in {r['model'] for r in config['models']}
    # Store allowlisted booleans, never synthetic response content or errors.
    safe={k:metadata.get(k) is True for k in ('chat','tools','tool_continuation','stream','english','vision','withdrawn')}
    with database() as con:
        previous=con.execute('SELECT metadata FROM qualification WHERE provider=? AND model=?',(config['provider'],model)).fetchone()
        try:was_withdrawn=previous is not None and json.loads(previous['metadata']).get('withdrawn') is True
        except (ValueError,TypeError,AttributeError):was_withdrawn=True
        core_pass=all(safe[k] for k in ('chat','tools','tool_continuation','stream','english'))
        safe['withdrawn']=safe['withdrawn'] or (was_withdrawn and not core_pass)
        con.execute('INSERT OR REPLACE INTO qualification VALUES(?,?,?,?,?)',
                    (config['provider'],model,sha,time.time(),json.dumps(safe)))
    return not safe["withdrawn"] and all(safe[k] for k in ("chat","tools","tool_continuation","stream","english"))


def compatible(request,row):
    # Text encodings can require almost one token per byte. A byte budget is
    # deliberately conservative; uncertain fits do not get a smaller model.
    size=len(json.dumps({k:v for k,v in request.items() if k in ('messages','tools','functions')},
                       ensure_ascii=False,default=str).encode('utf-8'))
    output=request.get('max_completion_tokens') or request.get('max_tokens') or 8192
    if not isinstance(output,(int,float)) or output<1 or size+output+2048>row['context_length']:return False
    for message in request.get('messages') or []:
        content=message.get('content')
        if isinstance(content,list):
            for part in content:
                if not isinstance(part,dict):return False
                kind=part.get('type')
                if kind not in ('text','input_text'):
                    if kind not in ('image_url','input_image') or 'image' not in row['input_modalities']:return False
    basic={'model','messages','timeout','stream','stream_options','extra_headers','extra_query'}
    aliases={'max_completion_tokens':'max_tokens','reasoning_effort':'reasoning'}
    for key,value in request.items():
        if value is None or key in basic:continue
        if key=='extra_body':
            if not isinstance(value,dict):return False
            # These are endpoint-level Hermes attribution/affinity fields, not
            # optional model capabilities. Preserve them exactly on every model.
            if 'tags' in value and (not isinstance(value['tags'],list) or any(not isinstance(t,str) for t in value['tags'])):return False
            if 'session_id' in value and not isinstance(value['session_id'],str):return False
            if any(k not in ('tags','session_id') and aliases.get(k,k) not in row['parameters'] for k in value):return False
        elif aliases.get(key,key) not in row['parameters']:return False
    return True


def offers(provider,model,api_mode,request):
    primary={'id':'native','provider':provider,'model':model,
             'capabilities':['preserve-native-tool-and-stream-protocol']}
    # Unknown/custom providers retain their existing single native transport.
    if provider!='nous' or api_mode not in ('','chat','chat_completions'):return [primary]
    config,sha=policy()
    if model not in {r['model'] for r in config['models']}:return [primary]
    result=[]
    now=time.time()
    with database() as con:
        qualified={r['model']:dict(r) for r in con.execute('SELECT * FROM qualification WHERE provider=?',(provider,))}
    try:withdrawn=json.loads((qualified.get(model) or {}).get('metadata') or '{}').get('withdrawn') is True
    except (ValueError,TypeError,AttributeError):withdrawn=True
    if not withdrawn:result.append(primary)
    for row in config['models']:
        name=row['model']
        if name==model or not compatible(request,row):continue
        proof=qualified.get(name)
        if not proof or proof['policy_sha']!=sha or not 0<=now-proof['observed_at']<=config['qualification_ttl_seconds']:continue
        try:checks=json.loads(proof['metadata'])
        except (ValueError,TypeError):continue
        if checks.get('withdrawn') is True:continue
        if not all(checks.get(k) is True for k in ('chat','tools','tool_continuation','stream','english')):continue
        has_image=any(isinstance(m.get('content'),list) and any(isinstance(p,dict) and p.get('type') in ('image_url','input_image') for p in m['content']) for m in request.get('messages') or [])
        if has_image and checks.get('vision') is not True:continue
        result.append({'id':'native-'+hashlib.sha256(name.encode()).hexdigest()[:12],
                       'provider':provider,'model':name,'capabilities':['preserve-native-tool-and-stream-protocol'],
                       'evidence':{'qualification':'live chat, tool call, tool result continuation, streaming and English verified',
                                   'context_capacity':row['context_length']}})
    return result
